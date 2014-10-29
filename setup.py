# encoding: utf8

from setuptools import setup, find_packages


with open('djdd/VERSION', 'rb') as f:
    version = f.read().decode('utf-8').strip()


setup(
    name='django-deb-deploy',
    author='Will Hardy',
    author_email='django@willhardy.com.au',
    version=version,
    url='http://github.com/willhardy/django-deb-deploy',
    packages=find_packages(),
    include_package_data=True,
    install_requires=['click'],
    entry_points='''
        [console_scripts]
        django-deb-deploy=djdd.ui:cli
    ''',
    description='A tool for creating deploy debian packages for '
                'django-based sites.',
    classifiers=[
        'License :: OSI Approved :: BSD License',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
    ],
)
