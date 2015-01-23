#!/usr/bin/env python

try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup

setup(
    name='chip',
    version="0.1.0",
    description='OpenKIM package handling utilities.',
    author='Matt Bierbaum',
    author_email='mkb72@cornell.edu',
    url='http://openkim.org',
    license='CDDL',
    long_description=open("./README.md").read(),
    packages=['chip'],
    scripts=['bin/chip'],
    install_requires=[
        "argcomplete==0.8.1",
        "argparse==1.2.1",
        "pip==1.5.6",
        "packaging==14.0"
    ],
    dependency_links=["https://github.com/pypa/packaging/archive/master.tar.gz#egg=packaging-14.0"]
)
