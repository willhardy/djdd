import os

# postinst
#PACKAGE_GROUP = "djdd"
#apt-get install debootstrap schroot
#addgroup $PACKAGE_GROUP


def initialize_build_directory(name, dir, clones, debian_suite, debian_arch, debian_mirror=None):
    # SUDO
    #adduser `whoami` djdd

    log_dir = os.path.join(dir, "logs")
    root_dir = os.path.join(dir, "debootstrap_root")
    schroot_config_file = os.path.join(dir, "schroot.conf")

    os.makedirs(log_dir)
    os.makedirs(root_dir)

    # Is there a reason why only this directory is created?
    #internal_cache_dir = os.path.join(root_dir, "var/local/cache/djdd")
    #os.makedirs(internal_cache_dir)

    # Create the debootstrap
    debootstrap_cmd = ['debootstrap', '--arch', debian_arch, debian_suite, root_dir]
    if debian_mirror is not None:
        debootstrap_cmd.append(debian_mirror)
    subprocess.call(debootstrap_cmd)

    # Setup schroot
    schroot_config = """
    [{name}]
    description=djdd build {name}
    type=directory
    directory={dir}
    groups=djdd
    root-groups=root
    run-exec-scripts=false
    run-setup-scripts=false
    """.format(name=name, dir=root_dir)
    with open(schroot_config_file, 'w') as f:
        f.write(schroot_config)
    # XXX AS ROOT
    #ln -s schroot_config_file schroot_config_link

    # Tidy up some aspects of the system (as root)
    # XXX AS ROOT
    if debian_mirror is not None:
        with open(os.path.join(root_dir, 'etc/apt/sources.list'), 'w') as f:
            f.write("deb {} {} main\n".format(debian_mirror, debian_suite))
    # XXX AS ROOT
    with open(os.path.join(root_dir, 'sbin/start-stop-daemon'), 'w') as f:
        f.write("exit 0\n")
    # XXX AS ROOT
    with open(os.path.join(root_dir, 'etc/locale.gen'), 'w') as f:
        f.write("en_US ISO-8859-1\nen_US.UTF-8 UTF-8\n")

    # Install everything we need
    dependencies = [ 'locales', 'python-pip', 'python-virtualenv', 'git-buildpackage', 'python-jinja2']
    dependencies += [ 'debhelper', 'build-essential', 'libbz2-dev', 'libevent-dev', 'libgeos-dev', 'libpq-dev', 'libsqlite3-dev', 'python-dev', 'libpng12-dev', 'libxml2', 'libxml2-dev', 'libxslt-dev', 'libncurses5-dev', 'git', 'git-core', 'mercurial', 'postgresql-server-dev-9.1', 'postgresql-9.1', 'libxml2-dev', 'libproj-dev', 'libjson0-dev', 'libgeos-dev', 'xsltproc', 'docbook-xsl', 'docbook-mathml', 'python2.7' ]
    # XXX subprocess? single line in shell mode?
    #schroot /var/local/lokaler-build "apt-get update && apt-get install $dependencies"
    #SESSION=`schroot --begin-session`
    #schroot --chroot "$SESSION" --run-session /var/local/lokaler-build apt-get update
    #schroot --chroot "$SESSION" --run-session /var/local/lokaler-build apt-get install $dependencies
    #schroot --chroot "$SESSION" --end-session
