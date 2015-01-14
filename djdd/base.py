import os
import re
import random
import logging
import functools
import contextlib
import subprocess

# We're going call our users/groups/directories/etc by this name
NAMESPACE = "djdd"

logger = logging.getLogger(NAMESPACE)


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
            call_fn(['kill', SSH_AGENT_PID])
            # Re-add the group permissions to the identity file
            os.chmod(self.ext_filename(identity_file), 0o2770) # 770 == ug+rwx,o-rwx