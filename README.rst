*****************
django-deb-deploy
*****************

**this is a work in progress, it is not yet completed. A working version
should be released in the next week or two.**

This is a tool to create .deb packages for deploying Django sites on
production Debian systems.

For now, the following is assumed/configured:

* A debian package for the virtualenv, created from the requirements.txt file
* A debian package for the version of your source code
* A debian package for your site, which depends on the above packages and contains:

  - nginx configuration
  - systemd configuration for the site's process (gunicorn) and any celery
    workers
  - postinst script to ensure database, users etc. exist, to switch
    running gunicorn process to new software version atomically, and to
    optionally run migrate (default off!)

A new package name is created for each possible virtualenv configuration and
source code version, instead of incrementing the version number of a single
package. This means that the production system can host multiple versions
at the same time, which is good for multi-tenancy and seamless migration from
one version to the next without interruption.

Out of date packages can be eventually removed automatically using debian
tools (i.e. apt-get autoremove).


Configuration
=============

Your code needs to define the following:

* requirements.txt
* venv-debian-requirements.txt (required debian packages for virtualenv packages)
* src-debian-requirements.txt (required debian packages for src)
* When running the script, you will need to provide arguments to communicate:

  - the software's name (used in package and script names, keep it short, no spaces etc)
  - the software's variant (optional, for multitenancy)
  - the version hash to be built
  - the build directory (see below for creating the build directory)

To create a build directory run eg ``sudo django-deb-deploy create --dir /path/to/build-dir/``. This will:

* create a debbootstrap instance in the given directory
* create the required system users and groups
* install schroot configuration to allow normal users to use the bootstrapped debian instance
* install any extra required debian packages for building

Then run ``django-deb-deploy init mysoftware --dir /path/to/build-dir/ --clone git+http://server.com/git/repository``. This will:

* clone your source code repository

Not that the build machine must be the same architecture and use the same debian variant (``jessie`` in the example) as the target system.

To create the required packages run eg ``django-deb-deploy build mysoftware --dir /path/to/build-dir --variant berlin --version 1a2b3c4d --settings path-to-settings-module``. This will:

* Install any required debian packages [1]_
* Run ``git fetch`` on the repository
* Checkout the requested version into its place
* Build the requirements package if necessary (or wait for it to be built)
* Build the software version package if necessary (or wait for it to be built)
* Run ``./manage.py collectstatic`` (saved into the site package's directory)
* Build the (variant's) site package

.. [1] If no other builds are running there will be no issues, but if another build is running and upgrades or package uninstalls are required, then it will wait for the other package build to finish before starting.


virtualenv package
==================
A package is generated that contains a virtualenv that is required for this version.

* a hash is generated from the ``requirements.txt`` file, after it is sorted and de-commented
* this hash will appear in the name of the debian package, e.g. ``{software name}-env-{hash}``
* the virtualenv is created and saved to /usr/lib/{software name}-env/{hash}/ in the build directory
* the requirements.txt file is saved to /usr/share/{software name}-env/{hash}/requirements.txt

This package will contain the (binary) files already in place for the debian machine. It will probably be large, but will not need to be installed for every upgrade, only the upgrades where the ``requirements.txt`` file has substantively changed. Because the python libraries will be compiled, you must build on the same machine type and debian install as the target system.


Source package
==============
The source is installed separately to the virtualenv because it is updated more often that the virtualenv package. This helps keep updates smaller, but means that the source needs to be included in the PYTHONPATH for it to be accessible.

The version number/hash of this chekout is used for the debian package name, eg ``{software name}-src-{hash}``.
The source code is checked out to eg ``/usr/lib/{software name}-src/{hash}/``.

To allow multitenancy, the site configuration and services are not included with the source package. This means multiple site packages can make use of the same (or of course multiple) source installs.


Site package
============
This debian package contains the configuration, static media, custom templates etc. Its installation also creates the relevant users, databases and upload directories. The following directories are created:

* ``/usr/lib/{software name}-site/{variant}``
* ``/usr/lib/{software name}-site/{variant}/static/``
* ``/var/lib/{software name}-site/{variant}/media/``
* ``/etc/{software name}-site/{variant}/``
* ``/var/log/{software name}-site/{variant}/``

They are owned by a user called ``{software name}-{variant}`` and a group of the same name with full access rights.

Also, a set of convenience symbolic links will be created in ``/src/{software name}-site/{variant}/``. These give you access to the logs, configuration, src, virtualenv, static media, dynamic media templates.

This package also installs and configures the necessary services:

* Postgresql database. The database name will be ``{software}-{variant}``, but will also be set in the ``DATABASE`` environment variable so it's best that your django settings make use of this.
* Queue server (eg rabbitmq, user/server added, service reloaded)
* Cache server (memcached, debian package as dependency)
* Celeryd workers (systemd script included, service started/restarted)
* gunicorn (systemd script included, service started/reloaded)
* nginx (debian package as dependency, config linked, service started/reloaded)

A server utility for this site is included to query and control the various services. It is named after your app (``{software}-{variant}``) and placed in ``/usr/bin``. It has the following command arguments:

* ``status`` quickly show the status of all services
* ``reload`` reload all services
* ``restart`` restart all services (including the database!)
* ``start`` try to start any stopped services
* ``offline`` replace site with maintenance page
* ``online`` replace maintenance page with site
