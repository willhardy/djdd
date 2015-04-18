from .base import BuildEnvironment, logger

def add_variant(dir, software_name, variant_name):
    """ Once schroot has been configured, a regular user can initialise the directory."""
    build_env = BuildEnvironment(dir)

    variant_info = build_env.get_variant_info(software_name, variant_name)
    if variant_info is None:
        vid = build_env.get_next_variant_id()
    else:
        vid = variant_info['id']

    # Create the required variant info dict, using a hardcoded algorithm for now,
    # but use the software_name later.
    variant_info = {
            'id': vid,
            'software': software_name,
            'key': variant_name,
            'name': variant_name,  # TODO: use a hook
            'subdomain': variant_name,  # TODO: use a hook
            'postgres_name': '{}_{}'.format(software_name, variant_name),  # TODO: use a hook
            'elasticsearch_name': variant_name,  # TODO: use a hook
            'redis_number': vid,  # TODO: use a hook
            'gunicorn_port': 4000 + vid,  # TODO: use a hook
        }

    build_env.set_variant_info(software_name, variant_name, variant_info)
    logger.debug(u"Added variant {} for software {}".format(variant_name, software_name))
