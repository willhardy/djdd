# encoding: utf8
import os
import re
import errno
import random
import sys
import grp
import functools
import shutil
import contextlib
import subprocess
import logging


# These packages will be installed in the build environment
# XXX Eventually, people are going to want to choose their own version of python/pip/virtualenv
DJDD_DEPENDENCIES = [ 'locales', 'python-pip', 'python-virtualenv', 'git-buildpackage', 'debhelper', 'build-essential', 'git', 'git-core']

# We're going call our users/groups/directories/etc by this name
NAMESPACE = "djdd"

logger = logging.getLogger(NAMESPACE)


def uninstall_build_environment(dir):
    """ Uninstalls the configuration with that name.
        This probably needs to be run as root.
    """
    build_env = BuildEnvironment(dir)

    # End all open sessions
    all_sessions = subprocess.check_output(['schroot', '--list', '--all-sessions', '--quiet'])
    our_prefix = "session:{}-".format(build_env.name)
    open_sessions = [s for s in all_sessions.splitlines() if s.startswith(our_prefix)]
    if open_sessions:
        logger.error("There are open schroot sessions for this build directory:")
        for session in open_sessions:
            logger.error("   {}".format(session))
        logger.error("Please end them using something like:")
        for session in open_sessions:
            logger.error("   schroot --chroot {} --end-session".format(session))
        sys.exit(1)

    # Delete the configuration
    try:
        os.unlink(build_env.schroot_config_filename)
    except OSError as e:
        if e.errno == errno.ENOENT:
            logger.info("No configuration installed, nothing to uninstall.")
        elif e.errno == errno.EACCES:
            logger.error("Cannot remove configuration, insufficient permission. Maybe try as root?")
            sys.exit(2)
    try:
        os.unlink(build_env.schroot_config_link)
    except OSError as e:
        if e.errno == errno.EACCES:
            logger.error("Cannot remove link configuration, insufficient permission.")
            sys.exit(2)

    # We could remove the group if there are no more registered environments with this group name
    # but because we don't delete the directories, we won't remove the group
    logger.info("Uninstalled this build directory, you may now delete it.")


def install_build_environment(dir, debian_suite, debian_arch, debian_mirror=None):
    """ Creates a new build directory (run as root).
        The following aspects require root privileges:
            * debootstrap
            * schroot config installation
    """
    build_env = BuildEnvironment(dir)

    # Check that debootstrap and schroot is installed
    REQUIRED_PACKAGES = {
        'debootstrap': '/usr/sbin/debootstrap',
        'schroot': '/usr/bin/schroot',
            }
    missing = [name for name, key_file in REQUIRED_PACKAGES.items()
                    if not os.path.exists(key_file)]
    if missing:
        logger.error("Please install the following required packages:\n"
                     "apt-get install {}".format(" ".join(missing)))
        sys.exit(4)

    # Check early if there are obvious permissions problems, this should be run by root
    if not os.access(os.path.dirname(build_env.schroot_config_filename), os.W_OK):
        logger.error("Do not have permission to install schroot configuration. Please run as root.")
        sys.exit(3)

    # Make sure the djdd group exists
    try:
        gid_djdd = grp.getgrnam(build_env.unix_group_name).gr_gid
    except KeyError:
        subprocess.call(['addgroup', '--system', build_env.unix_group_name])
        logger.info('Group "{}" created for accessing this build environment'.format(build_env.unix_group_name))
        gid_djdd = grp.getgrnam(build_env.unix_group_name).gr_gid

    # Create the directories with djdd group write permissions
    if not os.path.lexists(build_env.dir):
        os.makedirs(build_env.dir)
        os.chown(build_env.dir, build_env.dir_parent_uid, gid_djdd)
        os.chmod(build_env.dir, 0o2770) # 770 == ug+rwx,o-rwx
    if not os.path.lexists(build_env.log_dir):
        os.makedirs(build_env.log_dir)
        os.chown(build_env.log_dir, build_env.dir_parent_uid, gid_djdd)
        #os.chmod(build_env.log_dir, 0o2770)
    if not os.path.lexists(build_env.root_dir):
        os.makedirs(build_env.root_dir)
        os.chown(build_env.root_dir, build_env.dir_parent_uid, gid_djdd)
        #os.chmod(build_env.root_dir, 0o2770)

    # Install our chroot in global schroot config to allow normal users to chroot
    # Whitespace will eventually be stripped from each line
    SCHROOT_CONFIG_TEMPLATE = """
        [{env.name}]
        description=DjDD build environment
        type=directory
        directory={env.root_dir}
        groups={env.unix_group_name}
        root-groups={env.unix_group_name}
        profile=djdd
    """
    # Install a profile directory if it doesn't exist
    if not os.path.exists(build_env.schroot_profile_dir):
        profile_skel = os.path.join(os.path.dirname(__file__), 'templates', 'schroot-profile')
        shutil.copytree(profile_skel, build_env.schroot_profile_dir)

    # Install the configuration
    schroot_config = SCHROOT_CONFIG_TEMPLATE.format(env=build_env).strip()
    with open(build_env.schroot_config_filename, 'w') as f:
        # schroot does not like whitespace
        for line in schroot_config.splitlines():
            f.write(line.lstrip()+"\n")

    # Put a symlink in the build directory so that future calls can find it
    if not build_env.has_config_link:
        os.symlink(build_env.schroot_config_filename, build_env.schroot_config_link)

    # Create the debootstrap
    cmd_debootstrap = ['/usr/sbin/debootstrap', '--variant=minbase', '--arch', debian_arch, debian_suite, build_env.root_dir]
    if debian_mirror is not None:
        cmd_debootstrap.append(debian_mirror)
    subprocess.call(cmd_debootstrap)

    # Tidy up some aspects of the system (as root)
    if debian_mirror is not None:
        sources_list = os.path.join(build_env.root_dir, "etc/apt/sources.list")
        with open(sources_list, 'w') as f:
            f.write("deb {} {} main\n".format(debian_mirror, debian_suite))
        # This is the chroot version of the above
        #cmd = 'echo "deb {} {} main" > /etc/apt/sources.list'
        #call(cmd.format(debian_mirror, debian_suite), shell=True)

    # From here on out we don't need to be root.
    # XXX we could potentially drop privileges to the user who owns the parent dir?

    # Install our required packages for building (eg git, virtualenv, debhelper etc)
    with build_env.chroot() as call:
        call('echo "exit 0" > /sbin/start-stop-daemon', shell=True, root=True)
        call('echo "en_US ISO-8859-1\nen_US.UTF-8 UTF-8" > /etc/locale.gen', shell=True, root=True)
        # Install anything we need
        call('apt-get update', shell=True, root=True)
        call(['apt-get', 'install', '--assume-yes'] + DJDD_DEPENDENCIES, root=True)

        # Add user for building
        call('addgroup {env.build_group}'.format(env=build_env), shell=True, root=True)
        call('adduser --system --quiet --ingroup "{env.build_group}" '
             '--gecos "DjDD Build user" "{env.build_user}"'.format(env=build_env), shell=True, root=True)
        call('adduser {env.build_user} {env.build_group}'.format(env=build_env), shell=True, root=True)


def add_software(dir, name, repositories, identity):
    """ Once schroot has been configured, a regular user can initialise the directory."""
    build_env = BuildEnvironment(dir)

    # Check that user is a member of djdd group, if not, ask to add
    # XXX should we allow root?
    gid_djdd = grp.getgrnam(build_env.unix_group_name).gr_gid
    if gid_djdd not in os.getgroups():
        logging.error("Your user is not a member of the {group} group.".format(user=build_env.unix_group_name))
        sys.exit(6)

    internal_identity_dir = '/var/lib/{namespace}/{name}/ssh/'.format(namespace=NAMESPACE, name=name)
    if identity is not None:
        identity_filename = os.path.join(internal_identity_dir, 'id_rsa_custom')
        ext_identity_filename = os.path.join(build_env.root_dir, identity_filename.lstrip("/"))
        shutil.copyfile(identity, ext_identity_filename)
        os.chmod(ext_identity_filename, 0o2700) # 700 == ug+rwx,o-rwx
    else:
        identity_filename = os.path.join(internal_identity_dir, 'id_rsa')

    # Create a directory for the builds
    internal_repository_dir = '/var/lib/{namespace}/{name}/repository/'.format(namespace=NAMESPACE, name=name)
    with build_env.chroot() as call:
        call(["mkdir", "-p", internal_repository_dir], root=True)
        call(["mkdir", "-p", internal_identity_dir], root=True)
        call(["chown", ":{build_group}".format(build_group=build_env.build_group),
                internal_repository_dir, internal_identity_dir], root=True)
        call(["chmod", "g+rwX", internal_repository_dir, internal_identity_dir], root=True)

        # If no identity, create one
        if identity is None and not os.path.exists(os.path.join(build_env.root_dir, identity_filename.lstrip("/"))):
            comment = u"djdd {}".format(name)
            call(["ssh-keygen", "-t", "rsa", "-C", comment, "-N", "", "-q", "-f", identity_filename])#, capture_output=True)
            print("Created SSH key:\n")
            call(["cat", identity_filename])
            print("\n")
            raw_input("Add this key to the repository and press Enter to continue...")

        # Checkout the source code
        for repository in repositories:
            with build_env.sshagent(call, identity_filename) as ssh_call:
                # No point in being quiet, let the user see what's happening
                ssh_call(["git", "clone", repository, internal_repository_dir, "--mirror"])  #, "--quiet"])


################################################################################
# HELPER FUNCTIONS
################################################################################

class BuildEnvironment(object):
    """ Object to provide information on and a little interaction with
        a given build directory.
    """

    SCHROOT_CONFIG_DIR = "/etc/schroot/chroot.d"
    RE_CONFIG_NAME = re.compile(r'^\[(\w+)\]$', re.MULTILINE)
    RE_CONFIG_DIRECTORY = re.compile(r"^directory=(.+)$", re.MULTILINE)

    # This might be configurable one day
    unix_group_name = NAMESPACE
    build_group = NAMESPACE
    build_user = NAMESPACE
    schroot_profile_dir = '/etc/schroot/djdd'

    def __init__(self, dir):
        self.dir = dir
        self.dir_parent_uid = os.stat(os.path.dirname(dir)).st_uid
        self.schroot_config_link = os.path.join(dir, "schroot.conf")
        self.root_dir = os.path.join(dir, "debootstrap_root")
        self.log_dir = os.path.join(dir, "logs")

        self.has_config_link = os.path.lexists(self.schroot_config_link)
        self.has_config = os.path.exists(self.schroot_config_link)

        self.schroot_config_filename = None
        self.name = None


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

    def get_name_from_config(self):
        """ Uses the name in the schroot configuration file. """
        if not self.schroot_config_filename:
            return
        with open(self.schroot_config_filename) as f:
            content = f.read()
        match = self.RE_CONFIG_NAME.search(content)
        match2 = self.RE_CONFIG_DIRECTORY.search(content)
        if match:
            return match.group(1)

    def check_configuration_linked(self):
        """ Checks that the configuration is linked to this directory before
            attempting to access it via schroot.
        """
        with open(self.schroot_config_filename, 'r') as f:
            content = f.read()
        match = self.RE_CONFIG_DIRECTORY.search(content)
        if not match:
            raise ValueError("No directory configured, schroot will probably not work.")
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
                full_cmd = ' '.join(cmd_schroot + extra_args) + ' /bin/sh -c \'{}\''.format(cmd)
            else:
                full_cmd = cmd_schroot + extra_args + cmd
            return subprocess_fn(full_cmd, shell=shell, env=env)

        try:
            yield call
        except:
            raise
        finally:
            subprocess.call(['schroot', '--chroot', chroot_session, '--end-session', '--force'])

    @contextlib.contextmanager
    def sshagent(self, call_fn, identity_file):
        # SSH calls want this to exist, so make sure it does
        call_fn(['mkdir', '-p', os.environ['HOME']], root=True)
        call_fn(['chown', os.environ['USER'], os.environ['HOME']], root=True)

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
            call_fn(['kill', SSH_AGENT_PID])
