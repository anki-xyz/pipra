from setuptools import setup, find_packages

# read the contents of your README file
from os import path
this_directory = path.abspath(path.dirname(__file__))
with open(path.join(this_directory, 'README.md'), encoding='utf-8') as f:
    long_description = f.read()

setup(
    name="pipra",
    long_description=long_description,
    long_description_content_type='text/markdown',
    version="0.3.2",
    author="Andreas M Kist",
    author_email="andreas.kist@fau.de",
    license="GPLv3",
    packages=find_packages(),
    install_requires=[
        "pyqtgraph>=0.10.0",
        "numpy",
        "numba",
        "flammkuchen",
        "pyqt5",
        "scikit-image",
        "imageio",
        "imageio-ffmpeg",
        'opencv-python-headless'
    ],
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Science/Research",
        "License :: OSI Approved :: GNU General Public License v3 or later (GPLv3+)",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
    ],
    keywords="annotation, labelling",
    description="An annotation tool to allow binary px-based labels.",
    project_urls={
        "Source": "https://github.com/anki-xyz/pipra",
        "Tracker": "https://github.com/anki-xyz/pipra/issues",
    },
    entry_points = {
        'console_scripts': [
            'pipra = pipra.pipra:main'
        ]
    },
    include_package_data=True,
)