# encoding: utf8
import os
import errno
import sys
import grp
import shutil
import subprocess

from .base import BuildEnvironment, logger


# These packages will be installed in the build environment
# XXX Eventually, people are going to want to choose their own version of python/pip/virtualenv
DJDD_DEPENDENCIES = [ 'locales', 'python-pip', 'python-virtualenv', 'git-buildpackage', 'debhelper', 'build-essential', 'git', 'git-core']



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
