import os
import contextlib
import subprocess

# postinst
#apt-get install debootstrap schroot
#addgroup djdd


@contextlib.contextmanager
def chroot(root_dir):
    chroot_session = subprocess.check_output(['schroot', '--begin-session'])
    cmd_schroot = ['schroot', '--chroot', chroot_session, '--run-session', root_dir]
    def call(cmd, shell=False):
        if shell:
            full_cmd = ' '.join(cmd_schroot) + ' ' + cmd
        else:
            full_cmd = cmd_schroot + cmd
        subprocess.call(full_cmd, shell=shell)
    yield call
    subprocess.call(['schroot', '-chroot', chroot_session, '--end-session'])


def initialize_build_directory(name, dir, debian_suite, suite, debian_arch, clone, debian_mirror=None, sudo=True):
    log_dir = os.path.join(dir, "logs")
    root_dir = os.path.join(dir, "debootstrap_root")
    schroot_config_file = os.path.join(dir, "schroot.conf")
    schroot_config_link = os.path.join("/etc/schroot/chroot.d", name+".conf")
    link_marker = os.path.join(dir, "WAITING_FOR_LINK")
    is_restart = os.path.exists(schroot_config_link) or (os.path.exists(link_marker) and sudo)

    os.makedirs(log_dir)
    os.makedirs(root_dir)

    if not is_restart:
        # Create the debootstrap
        cmd_debootstrap = ['debootstrap', '--arch', debian_arch, debian_suite, root_dir]
        if debian_mirror is not None:
            cmd_debootstrap.append(debian_mirror)
        subprocess.call(cmd_debootstrap)

        # Create schroot config for our build directory
        schroot_config = """
[{name}]
description=djdd build {name}
type=directory
directory={dir}
groups=djdd
root-groups=root
run-exec-scripts=false
run-setup-scripts=false
        """.format(name=name, dir=root_dir).strip()
        with open(schroot_config_file, 'w') as f:
            f.write(schroot_config)

        # Only try with sudo if asked to
        cmd_link = ["ln", "-s", schroot_config_file, schroot_config_link]
        if sudo:
            subprocess.call(["sudo"] + cmd_link)
        else:
            print("Run the following as root and retry: {}\n".format(" ".join(cmd_link)))
            open(link_marker, 'wa').close()
            sys.exit(1)

    # If the marker is set, but the file exists, then remove the marker and continue
    if os.path.exists(link_marker) and os.path.exists(schroot_config_link):
        os.remove(link_marker)

    if schroot_config_link:
        dependencies = [ 'locales', 'python-pip', 'python-virtualenv', 'git-buildpackage', 'python-jinja2']
        dependencies += [ 'debhelper', 'build-essential', 'libbz2-dev', 'libevent-dev', 'libgeos-dev', 'libpq-dev', 'libsqlite3-dev', 'python-dev', 'libpng12-dev', 'libxml2', 'libxml2-dev', 'libxslt-dev', 'libncurses5-dev', 'git', 'git-core', 'mercurial', 'postgresql-server-dev-9.1', 'postgresql-9.1', 'libxml2-dev', 'libproj-dev', 'libjson0-dev', 'libgeos-dev', 'xsltproc', 'docbook-xsl', 'docbook-mathml', 'python2.7' ]

        with chroot(root_dir) as call:
            # Tidy up some aspects of the system (as root)
            if debian_mirror is not None:
                cmd = 'echo "deb {} {} main" > /etc/apt/sources.list'
                call(cmd.format(debian_mirror, debian_suite), shell=True)
            call('echo "exit 0" > /sbin/start-stop-daemon', shell=True)
            call('echo "en_US ISO-8859-1\nen_US.UTF-8 UTF-8" > /etc/locale.gen', shell=True)
            # Install anything we need
            call('apt-get update', shell=True)
            call(['apt-get', 'install'] + dependencies)

