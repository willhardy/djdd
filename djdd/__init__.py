
import os

version_file = os.path.join(os.path.dirname(__file__), "VERSION")
with open(version_file, 'rb') as f:
    __version__ = f.read().decode('utf-8').strip()

from djdd.initialize_build import install_build_environment, uninstall_build_environment
from djdd.add_software import add_software, add_variant
