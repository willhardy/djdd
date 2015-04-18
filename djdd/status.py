import os
import collections
from djdd.base import BuildEnvironment

def get_build_state(build_env):
    """
    one of:

    (0, "nothing")
    (1, "chroot configured")
    (2, "debootstrap created")
    (3, "variant database")

    """
    if not build_env.has_config:
        return (0, "not initialized")
    if not os.path.exists(build_env.debootstrap_complete):
        return (1, "partially initialized: chroot configured, no debootstrap")
    if not build_env.variant_database_exists():
        return (2, "partially initialized: debootstrap created, no variant database")
    return (3, "initialized")

def get_status(dir, variant_database=None):
    """ Shows the current state of the build directory, listing any defined sources and variants.
    """
    build_env = BuildEnvironment(dir, variant_database)
    status = {}
    status['root_dir'] = build_env.root_dir
    status['log_dir'] = build_env.root_dir
    status['has_config'] = build_env.has_config
    status['database'] = build_env.variant_database

    # 1. Initialisation status
    build_state = get_build_state(build_env)
    status['status'] = build_state

    # 2. Softwares
    # Get a list of respositories
    if build_state[0] >= 2: # debootstrap
        repositories = collections.defaultdict(list)
        repository_base_dir = '/var/lib/{namespace}/*/repository'.format(namespace=build_env.NAMESPACE)
        with build_env.chroot() as call:
            software_dirs = call('ls -d {}'.format(repository_base_dir), shell=True, capture_output=True)
            for software_dir in software_dirs.splitlines():
                software = os.path.basename(os.path.dirname(software_dir))
                repos = call('ls -d {}/*.git'.format(software_dir), shell=True, capture_output=True)
                for repo in repos.splitlines():
                    repository, ext = os.path.splitext(os.path.basename(repo))
                    repositories[software].append(repository)

        # 2a. SRCs
        status['software'] = dict(repositories)

    # 2b. Variants
    if build_state[0] >= 3: # database
        variants = collections.defaultdict(list)
        for variant in build_env.list_variant_infos():
            variants[variant.get('software')].append(variant)
        status['variants'] = dict(variants)

    return status
