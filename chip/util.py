import os
import re
import json
import time
import datetime
import subprocess
from packaging.version import Version, Specifier
from pip.download import get_file_content

import conf
from log import createLogger
logger = createLogger()
cf = conf.read_conf()

VERSIONSEP = "@"

def date_to_iso():
    return time.strftime("%Y-%m-%d %H:%M:%S")

def iso_to_date():
    return datetime.strptime("2010-06-04 21:08:12", "%Y-%m-%d %H:%M:%S")

class ChipRuntimeError(Exception):
    pass

class PackageError(Exception):
    pass

class PackageNotFound(Exception):
    pass

class PackageInconsistent(Exception):
    pass

class PackageSupportError(Exception):
    pass

#=============================================================================
# general util functions
#=============================================================================
def download_pkfile():
    if not os.path.isdir(cf['home']):
        subprocess.check_call(['mkdir', '-p', cf['home']])

    if not os.path.exists(cf['pkfile']):
        logger.info("Downloading package file %s" % cf['url'])
        url, content = get_file_content(cf['url'])
        with open(cf['pkfile'], 'w') as f:
            f.write(content)

gpks = None

def getpk(pkfile=None):
    global gpks
    pkfile = pkfile or cf['pkfile']
    download_pkfile()

    with open(pkfile) as f:
        pks = json.load(f)
        gpks = pks 
    return pks

def is_fullname(name):
    return re.findall(VERSIONSEP, name)

def format_pk_name(name, version):
    return name+VERSIONSEP+version

def separate_fullname(fullname):
    if is_fullname(fullname):
        return fullname.split(VERSIONSEP)
    return fullname, None

#=============================================================================
# dependency resolution and consistency checks
#=============================================================================
def compatible(ver, versionrange):
    return Version(ver) in Specifier(versionrange)

def later(ver1, ver2):
    return Version(ver1) > Version(ver2)

def v2s(v):
    return "~= "+v

#=============================================================================
# version searching and formatting routines
#=============================================================================
def get_latest_version(name, pkfile=None):
    pks = gpks or getpk(pkfile)

    currver = ''
    for pk in pks:
        tname = pk.get('name')
        ver = pk.get('version')

        if (tname == name and (not currver or later(ver, currver))):
            currver = ver

    if not currver:
        raise PackageNotFound("Package %s was not found." % name)
    return format_pk_name(name, currver)

def get_match_version(name, versionrange, pkfile=None):
    pks = gpks or getpk(pkfile)

    currver = ''
    for pk in pks:
        tname = pk.get('name')
        ver = pk.get('version')

        if (tname == name and compatible(ver, versionrange) and
                (not currver or later(ver, currver))):
            currver = ver

    if not currver:
        raise PackageNotFound("Package %s compatible with %s was not found." %
                (name, versionrange))
    return format_pk_name(name, currver)

def get_metadata(fullname, pkfile=None):
    pks = gpks or getpk(pkfile)
    n, v = separate_fullname(fullname)

    for pk in pks:
        if n == pk.get('name') and v == pk.get('version'):
            return pk
    raise PackageNotFound("Package %s was not found." % fullname)

