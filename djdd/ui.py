# encoding: utf8
import djdd
import click
import os
import logging


@click.group()
def cli():
    """ This is a tool to create .deb packages for deploying Django sites on
        production Debian systems.
    """
    logging.basicConfig()


################################################################################
# NEW COMMAND
################################################################################

@cli.command()
@click.option('--dir', envvar='DJDD_BUILD_DIRECTORY', default='_djdd_build', required=True,
                       help='directory for the debbootstrap instance', show_default=True,
                       type=click.Path(resolve_path=True, writable=True, file_okay=False),
                       metavar='PATH')
@click.option('--suite', help="Name of the target Debian environment's suite",
                              default="wheezy", required=True, prompt="Debian suite")
@click.option('--arch', help="Name of the target Debian environment's architecture",
                                default="amd64", required=True, prompt="Debian arch")
@click.option('--mirror', help="Use a preferred (local) Debian mirror")
def create(dir, suite, arch, mirror):
    """ Creates a new build environment, building a clean debian machine and
        setting up schroot for non-root access.
    """
    djdd.install_build_environment(dir, suite, arch, mirror)


@cli.command()
@click.option('--dir', envvar='DJDD_BUILD_DIRECTORY', default='_djdd_build', required=True,
                       help='directory for the debbootstrap instance', show_default=True,
                       type=click.Path(resolve_path=True, file_okay=False),
                       metavar='PATH')
def uninstall(dir):
    """ Removes the installed configuration for the given build environment.
    """
    djdd.uninstall_build_environment(dir)


################################################################################
# ADD COMMAND
################################################################################

@cli.command()
@click.argument('name', required=True)
@click.option('--dir', envvar='DJDD_BUILD_DIRECTORY', default='_djdd_build', required=True,
                       help='directory for the debbootstrap instance', show_default=True,
                       type=click.Path(resolve_path=True, file_okay=False),
                       metavar='PATH')
@click.option('--clone', metavar='REPOSITORY', multiple=True, required=True, prompt="URI for Git respository to clone",
                         help='URI of your source code respository for git to clone')
@click.option('--identity', default=None, show_default=True,
                       help='SSH private key (NB will be copied to build directory)',
                       type=click.Path(resolve_path=True), metavar='ID_FILE')
def add(name, dir, clone, identity):
    """ Add a new build area for the software of the given name,
        cloning the given repository URI(s).
    """
    djdd.add_software(dir, name, clone, identity)


################################################################################
# BUILD COMMAND
################################################################################


@cli.command()
@click.option('--dir', envvar='DJDD_BUILD_DIRECTORY', default='_djdd_build',
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
def build(dir, variant, version, settings, venv_depends, src_depends):
    """ Build the required debian packages using the given build environment.
    """
    #djdd.build_site(dir, variant, version, settings, venv_depends, src_depends)
