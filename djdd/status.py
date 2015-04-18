import os
import collections
from djdd.base import BuildEnvironment
from djdd import exceptions

def get_build_states(build_env):
    """
    Return a set of achieved states, eg set(['chroot', 'debootstrap']).
    """
    states = set()
    if build_env.has_config:
        states.add('chroot')
        if os.path.exists(build_env.debootstrap_complete):
            states.add('debootstrap')

            try:
                db_exists = build_env.variant_database_exists()
            except exceptions.VariantDBConnectionError:
                states.add('variant-db-missing')
            else:
                if db_exists:
                    states.add('variant-db')
                    states.add('complete')
    return states


def get_build_state_message(states):
    if 'chroot' not in states:
        return "not initialized"
    if 'debootstrap' not in states:
        return "partially initialized: chroot configured, no debootstrap"
    if 'variant-db-missing' in states:
        return "partially initialized: unable to connect to variant database"
    if 'variant-db' not in states:
        return "partially initialized: variant database not configured"
    if 'complete' in states:
        return "initialized"


def get_status(dir, variant_database=None):
    """ Shows the current state of the build directory, listing any defined sources and variants.
    """
    build_env = BuildEnvironment(dir, variant_database)
    status = {}
    status['root_dir'] = build_env.dir
    status['log_dir'] = build_env.log_dir
    status['has_config'] = build_env.has_config
    status['database'] = build_env.variant_database

    # 1. Initialisation status
    build_states = get_build_states(build_env)
    build_state_msg = get_build_state_message(build_states)
    status['status'] = (build_states, build_state_msg)

    # 2. Softwares
    # Get a list of respositories
    if 'debootstrap' in build_states:
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
    if 'variant-db' in build_states:
        variants = collections.defaultdict(list)
        for variant in build_env.list_variant_infos():
            variants[variant.get('software')].append(variant)
        status['variants'] = dict(variants)

    return status
