#!/usr/bin/env python

from distutils.core import setup

setup(
    name='chip',
    version="0.1.0",
    description='OpenKIM package distribution utilities.',
    author='Matt Bierbaum',
    author_email='mkb72@cornell.edu',
    url='http://www.python.org/sigs/distutils-sig/',
    packages=['chip'],
    scripts=['bin/chip']
)
