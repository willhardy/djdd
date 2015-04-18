
# Using an absolute, centralised path
# This will be created with sudo, so there shouldn't be issues with permissions.
DEFAULT_BUILD_DIR = '/var/lib/djdd/build'

DEFAULT_DATABASE = 'postgres://will:djdd@localhost/djdd'

# These packages will be installed in the build environment
# XXX Eventually, people are going to want to choose their own version of python/pip/virtualenv
DJDD_DEPENDENCIES = [ 'locales', 'python-pip', 'python-virtualenv', 'git-buildpackage', 'debhelper', 'build-essential', 'git', 'git-core']
