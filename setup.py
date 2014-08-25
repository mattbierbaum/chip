#!/usr/bin/env python

from distutils.core import setup
from __init__ import __version__

setup(
    name='chip',
    version=__version__,
    description='OpenKIM package distribution utilities.',
    author='Matt Bierbaum',
    author_email='mkb72@cornell.edu',
    url='http://www.python.org/sigs/distutils-sig/',
    packages=['chip'],
    scripts=['chip']
)
