# encoding: utf8
import os
import tempfile
import errno
import sys
import grp
import subprocess

from djdd.base import BuildEnvironment, logger, sudo
from djdd import constants


# TODO: If something fails during init, break off


def install_build_environment(dir, debian_suite, debian_arch, debian_mirror=None, tar=None, variant_database=None):
    """ Creates a new build directory
        The following aspects require root privileges:
            * debootstrap
            * schroot config installation
    """
    build_env = BuildEnvironment(dir, variant_database)

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

    # Make sure the djdd group exists
    try:
        grp.getgrnam(build_env.unix_group_name).gr_gid
    except KeyError:
        sudo(['addgroup', '--system', build_env.unix_group_name])
        logger.info('Group "{}" created for accessing this build environment'.format(build_env.unix_group_name))

    # Create the directories with djdd group write permissions
    if not os.path.lexists(build_env.dir):
        sudo(['mkdir', '-m', '04770', '-p', build_env.dir], user="root", group=build_env.unix_group_name)
    if not os.path.lexists(build_env.log_dir):
        os.makedirs(build_env.log_dir)
    if not os.path.lexists(build_env.root_dir):
        os.makedirs(build_env.root_dir)

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
        sudo(['cp', '-R', profile_skel, build_env.schroot_profile_dir], user='root', group=build_env.unix_group_name)

    # Put a symlink in the build directory so that future calls can find it
    if not build_env.has_config_link:
        # Install the configuration
        schroot_config = SCHROOT_CONFIG_TEMPLATE.format(env=build_env).strip()
        with tempfile.NamedTemporaryFile() as f:
            # NB schroot does not like whitespace
            for line in schroot_config.splitlines():
                f.write(line.lstrip()+"\n")
            f.flush()
            os.chmod(f.name, 0o664)
            # Move into place (as root)
            sudo(['cp', f.name, build_env.schroot_config_filename])

        os.symlink(build_env.schroot_config_filename, build_env.schroot_config_link)

    if not os.path.exists(build_env.debootstrap_complete):
        # Create the debootstrap
        cmd_debootstrap = ['/usr/sbin/debootstrap', '--variant=minbase', '--arch', debian_arch]
        if tar is not None:
            tar = os.path.abspath(tar)
            cmd_debootstrap.extend(["--unpack-tarball", tar])
        cmd_debootstrap.extend([debian_suite, build_env.root_dir])
        if debian_mirror is not None:
            cmd_debootstrap.append(debian_mirror)
        sudo(cmd_debootstrap)

        # Install our required packages for building (eg git, virtualenv, debhelper etc)
        with build_env.chroot() as call:
            call('echo "exit 0" > /sbin/start-stop-daemon', shell=True, root=True)
            call('echo "en_US ISO-8859-1\nen_US.UTF-8 UTF-8" > /etc/locale.gen', shell=True, root=True)
            # Install anything we need
            if debian_mirror is not None:
                call('echo "deb {} {} main" > /etc/apt/sources.list'.format(debian_mirror, debian_suite), shell=True)
            call('apt-get update', shell=True, root=True)
            call(['apt-get', 'install', '--assume-yes'] + constants.DJDD_DEPENDENCIES, root=True)

            # Add user for building
            call('addgroup {env.build_group}'.format(env=build_env), shell=True, root=True)
            call('adduser --system --quiet --ingroup "{env.build_group}" '
                 '--gecos "DjDD Build user" "{env.build_user}"'.format(env=build_env), shell=True, root=True)
            call('adduser {env.build_user} {env.build_group}'.format(env=build_env), shell=True, root=True)

        # Touch the marker file to signify that bootstrap was successfully completed
        with open(build_env.debootstrap_complete, "w") as f:
            pass

    # Create variant database if necessary
    build_env.create_variant_database()


def uninstall_build_environment(dir):
    """ Uninstalls the configuration with that name.
    """
    # TODO This currently needs to be run as root, change to sudo
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
