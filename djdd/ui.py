# encoding: utf8
import djdd
import click
import logging
from .constants import DEFAULT_BUILD_DIR


@click.group()
def cli():
    """ This is a tool to create .deb packages for deploying Django sites on
        production Debian systems.
    """
    logging.basicConfig()


################################################################################
# INIT COMMAND
################################################################################

@cli.command()
@click.option('--dir', envvar='DJDD_BUILD_DIRECTORY', default=DEFAULT_BUILD_DIR, required=True,
                       help='directory for the debbootstrap instance', show_default=True,
                       type=click.Path(resolve_path=True, writable=True, file_okay=False),
                       metavar='PATH')
@click.option('--suite', help="Name of the target Debian environment's suite",
                              default="wheezy", required=True, prompt="Debian suite")
@click.option('--arch', help="Name of the target Debian environment's architecture",
                                default="amd64", required=True, prompt="Debian arch")
@click.option('--mirror', help="Use a preferred (local) Debian mirror")
@click.option('--tar', help="Use a the given debootstrap package tarball")
@click.option('--db', envvar='postgres://username:password@server:port/name',
                        help="Connect to the given external database for storing variant configuration. "
                              "By default, a private database is created on the build server.")
def init(dir, suite, arch, mirror, tar, db):
    """ Creates a new build environment, building a clean debian machine and
        setting up schroot for non-root access.
    """
    djdd.install_build_environment(dir, suite, arch, mirror, tar, db)


@cli.command()
@click.option('--dir', envvar='DJDD_BUILD_DIRECTORY', default=DEFAULT_BUILD_DIR, required=True,
                       help='directory for the debbootstrap instance', show_default=True,
                       type=click.Path(resolve_path=True, file_okay=False),
                       metavar='PATH')
def uninstall(dir):
    """ Removes the installed configuration for the given build environment.
    """
    djdd.uninstall_build_environment(dir)


@cli.command()
@click.option('--dir', envvar='DJDD_BUILD_DIRECTORY', default=DEFAULT_BUILD_DIR, required=True,
                       help='directory for the debbootstrap instance', show_default=True,
                       type=click.Path(resolve_path=True, writable=True, file_okay=False),
                       metavar='PATH')
@click.option('--db', envvar='postgres://username:password@server:port/name',
                        help="Connect to the given external database for storing variant configuration. "
                              "By default, a private database is created on the build server.")
def status(dir, db):
    """ Shows the current state of the build directory, listing any defined sources and variants.
    """
    status = djdd.get_status(dir, db)
    if status.get('database'):
        database = "postgres://{db.user}:XXXXX@{db.host}/{db.database}".format(db=status['database'])
    else:
        database = "invalid/unconfigured"

    print
    print u"BUILD ENVIRONMENT:"
    print u"-" * 80
    print u" Build directory: {}".format(status['root_dir'])
    print u"          Status: {}".format(status['status'][1])
    print u"        Database: {}".format(database)
    print
    for software, repositories in status['software'].items():
        print u"SOFTWARE: {}".format(software)
        print u"-" * 80
        print u"  repositories: {}".format(", ".join(repositories))
        print u"      variants: {}".format(", ".join(status['variants'].get(software, [])) or "None")
    print


################################################################################
# SRC COMMAND
################################################################################

@cli.command()
@click.argument('name', required=True)
@click.option('--dir', envvar='DJDD_BUILD_DIRECTORY', default=DEFAULT_BUILD_DIR, required=True,
                       help='directory for the debbootstrap instance', show_default=True,
                       type=click.Path(resolve_path=True, file_okay=False),
                       metavar='PATH')
@click.option('--clone', metavar='REPOSITORY', multiple=True, required=True, prompt="URI for Git respository to clone",
                         help='URI of your source code respository for git to clone')
@click.option('--identity', default=None, show_default=True,
                       help='SSH private key (NB will be copied to build directory)',
                       type=click.Path(resolve_path=True), metavar='ID_FILE')
def src(name, dir, clone, identity):
    """ Add a new build area for the software of the given name,
        cloning the given repository URI(s).
    """
    djdd.add_software(dir, name, clone, identity)


################################################################################
# VARIANT COMMAND
################################################################################

@cli.command()
@click.argument('name', required=True)
@click.option('--dir', envvar='DJDD_BUILD_DIRECTORY', default=DEFAULT_BUILD_DIR, required=True,
                       help='directory for the debbootstrap instance', show_default=True,
                       type=click.Path(resolve_path=True, file_okay=False),
                       metavar='PATH')
@click.option('--branch', metavar='REPOSITORY:BRANCH', multiple=True,
                          prompt="Use a special branch if necessary",
                          help='URI of your source code respository for git to clone')
def variant(name, dir, branch):
    """ Add a new build area for the software of the given name,
        cloning the given repository URI(s).
    """
    djdd.add_variant(dir, name, branch)


################################################################################
# BUILD COMMAND
################################################################################


@cli.command()
@click.argument('software', required=True)
@click.option('--dir', envvar='DJDD_BUILD_DIRECTORY', default=DEFAULT_BUILD_DIR,
                       help='directory for the debbootstrap instance',
                       type=click.Path(exists=True, resolve_path=True,
                                            writable=True, file_okay=False),
                       metavar='PATH')
@click.option('--variant', help='optional variant for this build')
@click.option('--version', help='version number to build')
@click.option('--settings', help='django settings module to use')
@click.option('--venv-depends', default="venv-debian-depends.txt",
                               help='debian-requirements.txt file for the virtualenv')
@click.option('--src-depends', default="src-debian-depends.txt",
                               help='debian-requirements.txt file for the source')
def build(dir, software, variant, version, settings, venv_depends, src_depends):
    """ Build the required debian packages using the given build environment.
    """
    #djdd.build_site(dir, software, variant, version, settings, venv_depends, src_depends)
