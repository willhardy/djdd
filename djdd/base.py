import os
import re
import random
import logging
import urlparse
import functools
import contextlib
import subprocess
import psycopg2
import collections

from djdd import constants
from djdd import exceptions

# We're going call our users/groups/directories/etc by this name
NAMESPACE = "djdd"

logger = logging.getLogger(NAMESPACE)
logging.basicConfig(level="DEBUG")

urlparse.uses_netloc.append('postgres')

DatabaseConnection = collections.namedtuple("DatabaseConnection", "user,host,port,password,database")


################################################################################
# HELPER FUNCTIONS
################################################################################


def sudo(cmd, user=None, group=None):
    """ call the given arguments with sudo. """
    args = ['sudo']
    if user:
        args.extend(['-u', user])
    if group:
        args.extend(['-g', group])
    args += cmd
    print "SUDO call: {}".format(" ".join(args))
    subprocess.call(args)


class BuildEnvironment(object):
    """ Object to provide information on and a little interaction with
        a given build directory.
    """
    SCHROOT_CONFIG_DIR = "/etc/schroot/chroot.d"
    RE_CONFIG_NAME = re.compile(r'^\[(\w+)\]$', re.MULTILINE)
    RE_CONFIG_DIRECTORY = re.compile(r"^directory=(.+)$", re.MULTILINE)

    # Use the global variable for now
    NAMESPACE = NAMESPACE

    # This might be configurable one day
    unix_group_name = NAMESPACE
    build_group = NAMESPACE
    build_user = NAMESPACE
    schroot_profile_dir = '/etc/schroot/djdd'

    def __init__(self, dir=None, variant_database=None):
        self.dir = dir or constants.DEFAULT_BUILD_DIR
        self.schroot_config_link = os.path.join(self.dir, "schroot.conf")
        self.root_dir = os.path.join(self.dir, "debootstrap_root")
        self.debootstrap_complete = os.path.join(self.dir, "debootstrap_complete")
        self.log_dir = os.path.join(self.dir, "logs")

        self.has_config_link = os.path.lexists(self.schroot_config_link)
        self.has_config = os.path.exists(self.schroot_config_link)

        self.schroot_config_filename = None
        self.name = None

        # Variant database
        self.variant_database = self.parse_database_uri(variant_database or constants.DEFAULT_DATABASE)

        # If we have a symlink, we can use it to get the filename for the config
        if self.has_config_link:
            self.schroot_config_filename = os.path.realpath(self.schroot_config_link)
            # If we have config we can use it to get the name
            # (we must have a filename if we already have config).
            if self.has_config:
                self.name = self.get_name_from_config()

        # If link or config is missing, we need to generate a new name/filename
        # If just the name is missing, regenerate and we'll need to recreate the link
        if self.schroot_config_filename is None or self.name is None:
            # Look for a filename that doesn't exist.
            # This really won't be threadsafe, but it shouldn't be necessary
            # for the number of processes that are likely to be running.
            while True:
                name = NAMESPACE + "_" + "".join(random.choice("abcdefghijklmnopqrstuvwxyz") for x in range(5))
                filename = os.path.join(self.SCHROOT_CONFIG_DIR, "{}.conf".format(name))
                if not os.path.exists(filename):
                    break
            self.name = name
            self.schroot_config_filename = filename

    def parse_database_uri(self, database):
        """ Parse and validate the database string.
        """
        connection_string = database or constants.DEFAULT_DATABASE
        try:
            uri = urlparse.urlparse(connection_string)
            db_name = uri.path.strip("/")
            connection = DatabaseConnection(user=uri.username,
                    host=uri.hostname, port=uri.port, password=uri.password, database=db_name)
        except ValueError, e:
            msg = "Could not parse database connection string \"{}\":\n{}".format(connection_string, e)
            raise exceptions.BuildEnvironmentError(msg, self)
        if uri.scheme != "postgres":
            msg = "Only postgres:// database connection strings are accepted, not \"{}\"".format(connection_string)
            raise exceptions.BuildEnvironmentError(msg, self)
        if not db_name:
            msg = "No database name provided (as path) \"{}\"".format(connection_string)
            raise exceptions.BuildEnvironmentError(msg, self)
        return connection

    @property
    def conn(self):
        """ Returns the current database connection.
            If none exists, one will be created on the first call.
        """
        try:
            return self._conn
        except AttributeError:
            pass

        db = self.variant_database
        try:
            self._conn = psycopg2.connect(database=db.database, host=db.host, port=db.port, user=db.user, password=db.password)
        except psycopg2.OperationalError:
            raise exceptions.VariantDBConnectionError(format_database_connection(db), build_env=self)
        else:
            return self._conn

    def create_variant_database(self):
        """ Create a local database for storing decided variant information.
        """
        logger.debug("Creating varient database")
        # If it is a local database, create it
        if self.variant_database.host in ("localhost", None):
            # create the postgres database if not exists
            db_name = self.variant_database.database
            output = subprocess.check_output(['psql', '-l']).splitlines()
            if not any(line.startswith(" {} ".format(db_name)) for line in output):
                # TODO User privileges?! Different owner?
                sudo(['createdb', db_name, '-E', 'utf8', '-O', 'will'], user='postgres')
                # TODO If that doesn't work, tell the user what to run and exit

        # Create the tables we need, if needed
        # 'id' is globally unique, so that eg port numbers are unique across
        #      varants AND software titles.
        # 'software' is only a name so far, avoid extra table with denormalised form
        query = """
        CREATE TABLE IF NOT EXISTS variant (
             id integer PRIMARY KEY,
             software character varying(50),
             key character varying(50) NOT NULL,
             name character varying(100) NOT NULL,
             subdomain character varying(50) UNIQUE NOT NULL,
             postgres_name character varying(50) UNIQUE NOT NULL,
             elasticsearch_name character varying(50) UNIQUE NOT NULL,
             redis_number integer UNIQUE NOT NULL,
             gunicorn_port integer UNIQUE NOT NULL,
             UNIQUE (software, key)
        );
        COMMIT;
        """
        logger.debug("Creating database tables")
        curs = self.conn.cursor()
        curs.execute(query)

        if not self.variant_database_exists():
            # TODO If that didn't work, tell the user what to run and exit
            logger.error("Create table failed!")

    def list_variant_infos(self):
        """ Get the variant information from the variant database for all variants.
            Returns an iterable of dicts eg.
            [{
                'software': 'mysoftware',
                'id': 1,
                'key': 'berlin',
                'name': 'Berlin',
                'subdomain': 'berlin',
                'postgres_name': 'berlin',
                'elasticsearch_name': 'berlin',
                'redis_number': 1,
                'gunicorn_port': 4001,
            }]
        """
        query = """
                SELECT
                    software, id, key, name, subdomain, postgres_name,
                    elasticsearch_name, redis_number, gunicorn_port
                FROM variant
                ORDER BY key
                """
        curs = self.conn.cursor()
        curs.execute(query)
        results = curs.fetchall()
        headers = ('software', 'id', 'key', 'name', 'subdomain', 'postgres_name', 'elasticsearch_name', 'redis_number', 'gunicorn_port')
        for result in results:
            yield dict(zip(headers, result))

    def variant_database_exists(self):
        """ Checks if we can connect to the db, the table exists, and we
            have access to it.
        """

        query = """
            SELECT EXISTS (
               SELECT 1
               FROM   information_schema.tables
               WHERE  table_schema = 'public'
               AND    table_name = 'variant'
            );
        """
        curs = self.conn.cursor()
        curs.execute(query)
        result = curs.fetchone()[0]
        return result

    def get_variant_info(self, software, variant):
        """ Get the variant information from the variant database.
            Returns a dict eg.
            {
                'software': 'mysoftware',
                'id': 1,
                'key': 'berlin',
                'name': 'Berlin',
                'subdomain': 'berlin',
                'postgres_name': 'berlin',
                'elasticsearch_name': 'berlin',
                'redis_number': 1,
                'gunicorn_port': 4001,
            }
        """
        query = """
                SELECT
                    software, id, key, name, subdomain, postgres_name,
                    elasticsearch_name, redis_number, gunicorn_port
                FROM variant
                WHERE software = %s AND key = %s
                """
        curs = self.conn.cursor()
        curs.execute(query, (software, variant,))
        results = curs.fetchone()
        headers = ('software', 'id', 'key', 'name', 'subdomain', 'postgres_name', 'elasticsearch_name', 'redis_number', 'gunicorn_port')
        if results:
            return dict(zip(headers, results))

    def set_variant_info(self, software, variant, info):
        """ Sets variant information in the variant datbase.
            info is a dict as provided by self.get_variant_info().
        """
        query = """INSERT INTO variant
                    (software, id, key, name, subdomain, postgres_name,
                     elasticsearch_name, redis_number, gunicorn_port)
                VALUES
                    (%s, %s, %s, %s, %s, %s,
                     %s, %s, %s);
                COMMIT;
                """
        vars =  (software, info["id"], variant, info["name"], info["subdomain"], info["postgres_name"],
                 info["elasticsearch_name"], info["redis_number"], info["gunicorn_port"])
        curs = self.conn.cursor()
        curs.execute(query, vars)
        # XXX Check that it worked
        return True

    def get_next_variant_id(self):
        """ Returns an integer: the possible variant ID for the next variant.
            You can use this to generate new information (eg port number) for
            your variant. This is only a possible variant ID; the eventual
            call to self.set_variant_info() might fail, so you would need to
            get a new variant ID and try again.

            We could have a unique variant ID per software,
            but we won't.
        """
        query = "SELECT MAX(id) from variant;"
        curs = self.conn.cursor()
        curs.execute(query)
        vid = curs.fetchone()
        return (vid[0] or 0) + 1

    def get_name_from_config(self):
        """ Uses the name in the schroot configuration file. """
        if not self.schroot_config_filename:
            return
        with open(self.schroot_config_filename) as f:
            content = f.read()
        match = self.RE_CONFIG_NAME.search(content)
        #match2 = self.RE_CONFIG_DIRECTORY.search(content)
        if match:
            return match.group(1)

    def check_configuration_linked(self):
        """ Checks that the configuration is linked to this directory before
            attempting to access it via schroot.
        """
        with open(self.schroot_config_filename, 'r') as f:
            content = f.read()
        match = self.RE_CONFIG_DIRECTORY.search(content)
        assert match, "No directory configured, schroot will probably not work."
        configured_root_dir = match.group(1)

        if self.root_dir != configured_root_dir.strip():
            raise ValueError("Configuration does not match build directory.\n"
                    "Has the directory been moved? Rerun the install command as root.")

    @contextlib.contextmanager
    def chroot(self):
        """ Context manager for running (multiple) commands in a chroot.
            This takes care of subprocess calls and chroot session management.
        """
        self.check_configuration_linked()
        chroot_session = 'session:{}'.format(subprocess.check_output(['schroot', '--chroot', self.name, '--begin-session']).decode("ascii").strip())
        cmd_schroot = ['schroot', '--chroot', chroot_session, '--run-session', '--directory', '/']
        def call(cmd, shell=False, root=False, capture_output=False, env=None):
            if capture_output:
                subprocess_fn = functools.partial(subprocess.check_output, stderr=subprocess.STDOUT)
            else:
                subprocess_fn = subprocess.call
            extra_args = []
            if root:
                extra_args.extend(["--user", "root"])
            if env:
                extra_args.append("-p")
            extra_args.append("--")
            if shell:
                escaped_cmd = cmd.replace("'", "'\''")
                full_cmd = ' '.join(cmd_schroot + extra_args) + ' /bin/sh -c \'{}\''.format(escaped_cmd)
            else:
                full_cmd = cmd_schroot + extra_args + cmd
            return subprocess_fn(full_cmd, shell=shell, env=env)

        try:
            yield call
        except:
            raise
        finally:
            subprocess.call(['schroot', '--chroot', chroot_session, '--end-session', '--force'])

    def ext_filename(self, filename):
        return os.path.join(self.root_dir, filename.lstrip("/"))

    @contextlib.contextmanager
    def sshagent(self, call_fn, identity_file):
        # SSH calls want this to exist, so make sure it does
        call_fn(['mkdir', '-p', os.environ['HOME']], root=True)
        call_fn(['chown', os.environ['USER'], os.environ['HOME']], root=True)

        # temporarily remove group permissions for ssh key
        os.chmod(self.ext_filename(identity_file), 0o2700) # 700 == u+rwx,og-rwx

        output = call_fn(['ssh-agent'], capture_output=True)
        SSH_AUTH_SOCK = output.splitlines()[0].split(";", 1)[0].split("=", 1)[1]
        SSH_AGENT_PID = output.splitlines()[1].split(";", 1)[0].split("=", 1)[1]
        preserve_envs = ['HOME', 'LOGNAME', 'USER']
        new_env = {k: os.environ[k] for k in preserve_envs}
        new_env['SSH_AUTH_SOCK'] = SSH_AUTH_SOCK
        new_env['SSH_AGENT_PID'] = SSH_AGENT_PID
        def ssh_call(cmd, shell=False, root=False, capture_output=False, env=None):
            if env is not None:
                _env = env.copy()
                _env['SSH_AUTH_SOCK'] = SSH_AUTH_SOCK
                _env['SSH_AGENT_PID'] = SSH_AGENT_PID
            else:
                _env = new_env

            return call_fn(cmd, shell=shell, root=root, capture_output=capture_output, env=_env)

        ssh_call(['ssh-add', identity_file], capture_output=True, env=new_env)
        try:
            yield ssh_call
        except:
            raise
        finally:
            subprocess.call(['/bin/kill', SSH_AGENT_PID])
            # Re-add the group permissions to the identity file
            os.chmod(self.ext_filename(identity_file), 0o2770) # 770 == ug+rwx,o-rwx


def format_database_connection(db):
    if db:
        if db.user:
            user = db.user + (":XXXXX" if db.password else "") + "@"
        else:
            user = ""
        if db.port:
            port = ":{}".format(db.port)
        else:
            port = ""
        return "postgres://{user}{db.host}{port}/{db.database}".format(user=user, db=db, port=port)
    else:
        return "invalid/unconfigured"
