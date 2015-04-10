import grp
import os
import urlparse
import sys
import shutil
from .base import BuildEnvironment, logger, NAMESPACE


def add_software(dir, name, repositories, identity):
    """ Once schroot has been configured, a regular user can initialise the directory."""
    build_env = BuildEnvironment(dir)

    # Check that user is a member of djdd group, if not, ask to add
    # XXX should we allow root?
    gid_djdd = grp.getgrnam(build_env.unix_group_name).gr_gid
    if gid_djdd not in os.getgroups():
        logger.error("Your user is not a member of the {group} group.".format(user=build_env.unix_group_name))
        sys.exit(6)

    identity_dir = '/var/lib/{namespace}/{name}/ssh/'.format(namespace=NAMESPACE, name=name)
    if identity is not None:
        identity_filename = os.path.join(identity_dir, 'id_rsa_custom')
    else:
        identity_filename = os.path.join(identity_dir, 'id_rsa')

    # Create a directory for the builds
    repository_base_dir = '/var/lib/{namespace}/{name}/repository/'.format(namespace=NAMESPACE, name=name)
    with build_env.chroot() as call:
        call(["mkdir", "-p", repository_base_dir], root=True)
        call(["mkdir", "-p", identity_dir], root=True)
        call(["chown", ":{build_group}".format(build_group=build_env.build_group),
                repository_base_dir, identity_dir], root=True)
        call(["chmod", "g+rwX", repository_base_dir, identity_dir], root=True)

        # If no identity, create one
        if identity is None and not os.path.exists(build_env.ext_filename(identity_filename)):
            comment = u"djdd {}".format(name)
            call(["ssh-keygen", "-t", "rsa", "-C", comment, "-N", "", "-q", "-f", identity_filename])#, capture_output=True)
            print("Created SSH key:\n")
            call(["cat", identity_filename + ".pub"])
            print("\n")
            raw_input("Add this key to the repository and press Enter to continue...")
        else:
            shutil.copyfile(identity, build_env.ext_filename(identity_filename))
            os.chmod(build_env.ext_filename(identity_filename), 0o2770) # 770 == ug+rwx,o-rwx

        # Checkout the source code
        for repository in repositories:
            name = urlparse.urlparse(repository).path.rsplit("/", 1)[-1]
            repository_dir = os.path.join(repository_base_dir, name)
            print("Cloning {} in build environment".format(name))
            if os.path.exists(build_env.ext_filename(repository_dir)):
                print("This repository has already been cloned.")
            else:
                with build_env.sshagent(call, identity_filename) as ssh_call:
                    # No point in being quiet, let the user see what's happening
                    ssh_call(["git", "clone", repository, repository_dir, "--mirror"])  #, "--quiet"])


def add_variant(dir, name, branch):
    """ Once schroot has been configured, a regular user can initialise the directory."""
    #build_env = BuildEnvironment(dir)
