import os
from setuptools import setup, find_packages

NAME = "morphsuit"
VERSION = "1.0"

REQUIRES = [
'gimpformats',
#'pillow', - implied by gimpformats
'tabulate',
'opencv-contrib-python',
'pygame',
]

setup(
    name=NAME,
    version=VERSION,
    description="gimp external manipulation tool",
    url="",
    install_requires=REQUIRES,
    packages=find_packages(),
    package_data={'': []},
    include_package_data=True,
    long_description="""\
    Yes, indeed
    """
)
