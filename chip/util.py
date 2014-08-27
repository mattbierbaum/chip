import re
import json
import time
import datetime
from packaging.version import Version, Specifier

import conf
from log import createLogger
logger = createLogger()
cf = conf.read_conf()

VERSIONSEP = "@"

def date_to_iso():
    return time.strftime("%Y-%m-%d %H:%M:%S")

def iso_to_date():
    return datetime.strptime("2010-06-04 21:08:12", "%Y-%m-%d %H:%M:%S")

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
def getpk(pkfile=None):
    pkfile = pkfile or cf['pkfile']
    with open(pkfile) as f:
        pks = json.load(f)
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
    pks = getpk(pkfile)

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
    pks = getpk(pkfile)

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
    pks = getpk(pkfile)
    n, v = separate_fullname(fullname)

    for pk in pks:
        if n == pk.get('name') and v == pk.get('version'):
            return pk
    raise PackageNotFound("Package %s was not found." % fullname)

#==============================================================================
# gathering complete lists, triming, and checking consistency
#==============================================================================
class CompatibleVersionDict(dict):
    def __init__(self, pklist=[], *args, **kwargs):
        super(CompatibleVersionDict, self).__init__(*args, **kwargs)
        if pklist:
            self.fromlist(pklist)

    def __setitem__(self, key, value):
        done = False

        vers = []
        if self.get(key):
            vers = self.get(key)
            for i in xrange(len(vers)):
                ver = vers[i]
                if compatible(ver, v2s(value)):
                    if later(value, ver):
                        vers[i] = value
                    done = True

            if not done:
                vers.append(value)
        else:
            vers.append(value)

        super(CompatibleVersionDict, self).update({key: vers})

    def tolist(self):
        thelist = []
        for k,v in self.iteritems():
            thelist.extend([format_pk_name(k, vt) for vt in v])
        return thelist

    def fromlist(self, pks):
        for pk in pks:
            if not isinstance(pk, basestring):
                pk = str(pk)
            name, ver = separate_fullname(pk)
            self.__setitem__(name, ver)

    def compatible(self):
        good, bads = True, []
        for k,v in self.iteritems():
            if len(v) > 1:
                bads.extend([format_pk_name(k, vt) for vt in v])
                good = False
        return good, bads


class PathDict(dict):
    def __init__(self, paths=[], *args, **kwargs):
        super(PathDict, self).__init__(*args, **kwargs)
        if paths:
            for k,v in paths:
                self.__setitem__(k,v)

    def __setitem__(self, key, value):
        if self.get(key):
            super(PathDict, self).update({key: value+":"+self.get(key)})
        else:
            super(PathDict, self).update({key: value})

