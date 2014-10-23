
import os

version_file = os.path.join(os.path.dirname(__file__), "VERSION")
with open(version_file, 'rb') as f:
    __version__ = f.read().decode('utf-8').strip()

from .initialize_build import initialize_build_directory
