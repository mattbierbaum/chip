"""
A package manager to deal with different library dependencies of tests and
models.  This library downloads, installs and uses packages of the OpenKIM
system

The basic functions that need to be implemented:
    install
    uninstall
    activate
    deactivate

Package descriptions are kept in a file in the root directory
called package.json which contains:
    {
        "name":     "<package-name>",
        "author":   "<author-name>",
        "desc":     "<some description>",
        "type":     "(python|binary|apt|custom)",
        "version":  "<semver version>",
        "date":     "creation date",
        "url":      "location of package to download",
        "data":     "<See more info>",
        "requires": {
            "package-name-1":  "<version>",
            "package-name-2":  "<version>"
        }
    }

Most of these items are self explanatory but if they are not obvious, will be
described below.

There are several ways to mark the directives of a package.  By default, the
minimal amount of information to specify a package can be placed in the data
field.  If this field is occupied then it is assumed that no other additinoal
files are necessary to define a package.

APTPackage:
    "data":  {
        "commands": [
           "command 1",
           "commmand 2"
        ]
    }
"""
import os
import re
import json
import sys
import shutil
import subprocess
import functools
import argparse
import inspect
import itertools
from string import Template
from contextlib import contextmanager, nested
from pip.index import Link
from pip.download import (unpack_vcs_link, is_vcs_url, is_file_url,
                          unpack_file_url, unpack_http_url)

import conf
import util
from log import createLogger
logger = createLogger()
cf = conf.read_conf()
join = os.path.join

def wrap_install(func):
    def newinstall(self):
        if self.isinstalled():
            return True

        self.bootstrap()

        for dep in self.dependencies():
            dep.install()

        managers = [o.active() for o in self.dependencies()]
        with nested(*managers):
            logger.info("Installing %s ..." % self.fullname)
            func(self)

        self.finalize_install()
        logger.debug("Finalized installation for %s" % self.fullname)
        return True

    return newinstall

def wrap_default(action):
    def wrapper(func):
        @functools.wraps(func)
        def newdec(self):
            actions = ['activate', 'deactivate']
            if action not in actions:
                raise util.PackageSupportError(
                        "Cannot wrap actions that are not %s" % actions
                    )

            if action == 'activate':
                for dep in self.dependencies():
                    dep.activate()
                logger.debug("Activating %s" % self.fullname)
            if action == 'deactivate' and self.isactive():
                for dep in self.dependencies():
                    dep.deactivate()
                logger.debug("Deactivating %s" % self.fullname)

            func(self)

            if action == 'activate':
                self.activated = True
            if action == 'deactivate':
                self.activated = False
        return newdec
    return wrapper

#=============================================================================
# The main package class - subclasses made with decorators
#=============================================================================
class Package(object):
    def __init__(self, name, versionrange='', pkfile=None, search=True):
        metadata = None

        self.pkfile = pkfile or cf['pkfile']
        self.name, self.version = util.separate_fullname(name)

        if not self.version and search:
            if versionrange:
                match = util.get_match_version(
                            self.name, versionrange, self.pkfile
                        )
            else:
                match = util.get_latest_version(self.name, self.pkfile)
        else:
            match = name

        self.name, self.version = util.separate_fullname(match)
        self.fullname = util.format_pk_name(self.name, self.version)
        self.metadata = util.get_metadata(self.fullname)
        self.shortname = self.name

        self.base_path = join(cf['home'], self.fullname)
        self.install_path = join(self.base_path, "install")
        self.build_path = join(self.base_path, "build")
        self.log_path = join(self.base_path, "log")
        self.log = join(self.log_path, "chip.log")

        self.pkgfile = join(self.base_path, 'package.json')
        self.pkgpy = join(self.build_path, 'package.py')

        self.ptype = self.metadata.get('type')
        self.url = self.metadata.get('url')
        self.requirements = self.metadata.get("requires")
        self.data = self.metadata.get('data')

        self.env = {}
        self.activated = False

        consistent, bads = self.consistent()
        if not consistent:
            raise util.PackageInconsistent(
                "Package is inconsistent, these versions don't match:\n%r" % bads
            )

    def bootstrap(self):
        self.mkdir_ext(self.base_path)
        self.mkdir(self.log_path)
        self.mkdir(self.build_path)
        self.mkdir(self.install_path)

        if not os.path.exists(self.pkgfile):
            with open(self.pkgfile, 'w') as f:
                json.dump(self.metadata, f, indent=4)

        if self.url:
            logger.info("Downloading %s" % self.url)
            shutil.rmtree(self.build_path)
            self.download_url(Link(self.url))

    def download_url(self, link, location=None):
        cache = join(self.base_path, '.cache')
        self.mkdir(cache)

        location = location or self.build_path
        if is_vcs_url(link):
            return unpack_vcs_link(link, location, only_download=False)
        elif is_file_url(link):
            return unpack_file_url(link, location)
        else:
            return unpack_http_url(link, location,
                    cache, False)

    def dependencies(self):
        deps = []
        for req, ver_req in self.requirements.iteritems():
            pkg = pkg_obj(name=req, versionrange=ver_req, pkfile=self.pkfile)
            deps.extend([pkg]+pkg.dependencies())

        a = CompatibleVersionDict(deps)
        return a.tolist()

    def consistent(self):
        dep = self.dependencies()
        a = CompatibleVersionDict(dep)
        return a.compatible()

    def isinstalled(self):
        return os.path.exists(join(self.base_path, 'installed'))

    def isactive(self):
        return self.activated

    def path_exists(self, path, pathvar='PATH'):
        return re.search(path, os.environ.get(pathvar,'')) is not None

    def path_push(self, newpath, pathvar='PATH'):
        if not self.path_exists(newpath, pathvar):
            sep = os.path.pathsep
            self.env[pathvar] = newpath+sep+self.env.get(pathvar,'')
            os.environ[pathvar] = newpath+sep+os.environ.get(pathvar,'')

    def path_pull(self, path, pathvar='PATH'):
        sep = os.path.pathsep
        self.env[pathvar] = re.subn(path+sep, '', self.env.get(pathvar,''))[0]
        os.environ[pathvar] = re.subn(path+sep, '', os.environ.get(pathvar,''))[0]

    def path_print(self):
        with self.active():
            print json.dumps(self.env)

    def path_dict(self):
        with self.active():
            paths = self.env.copy()
        return paths

    def mkdir(self, path):
        if not os.path.isdir(path):
            os.mkdir(path)

    def mkdir_ext(self, extendedpath):
        if not os.path.isdir(extendedpath):
            subprocess.check_call(['mkdir', '-p', extendedpath])

    def run(self, cmd):
        with open(self.log, 'a') as log:
            logger.info('  '+' '.join(cmd))
            if 'sudo' in cmd:
                p = subprocess.Popen(cmd, stderr=log, stdout=log, stdin=sys.stdin)
                p.communicate()
            else:
                subprocess.check_call(cmd, stdout=log, stderr=log)

    def haspy(self):
        return os.path.exists(self.pkgpy)

    def finalize_install(self):
        open(join(self.base_path, 'installed'), 'a').close()

    @wrap_install
    def install(self):
        pass

    @wrap_default("activate")
    def activate(self):
        pass

    @wrap_default("deactivate")
    def deactivate(self):
        pass

    def uninstall(self):
        logger.info("Deleting package %s" % self.fullname)
        shutil.rmtree(self.base_path)

    @contextmanager
    def active(self):
        managers = [o.active() for o in self.dependencies()]
        with nested(*managers):
            self.activate()
            try:
                yield
            except Exception as e:
                raise e
            finally:
                self.deactivate()

    @contextmanager
    def indir(self, path):
        cwd = os.getcwd()
        os.chdir(path)
        try:
            yield
        except Exception as e:
            raise e
        finally:
            os.chdir(cwd)

    def __str__(self):
        return self.fullname

    def __repr__(self):
        return self.__str__()

    def __eq__(self, right):
        if right:
            return self.fullname == right.fullname
        return False

    def __hash__(self):
        return hash(self.fullname)

#=============================================================================
# Python package class
#=============================================================================
class PythonPackage(Package):
    def __init__(self, *args, **kwargs):
        super(PythonPackage, self).__init__(*args, **kwargs)
        self.pythonpath = join(self.install_path, 'lib/python2.7/site-packages')
        self.pythonbinpath = join(self.install_path, 'bin')

    @wrap_install
    def install(self):
        if os.path.exists(join(self.build_path, 'setup.py')):
            self.mkdir_ext(self.pythonpath)
            self.mkdir_ext(self.pythonbinpath)

            with self.active(), self.indir(self.build_path):
                self.run(['python', 'setup.py', 'install',
                    '--prefix='+self.install_path])
        else:
            raise util.PackageError(
                "No setup.py found for package %s" % self.fullname
            )

    @wrap_default('activate')
    def activate(self):
        self.path_push(self.pythonpath, "PYTHONPATH")
        self.path_push(self.pythonbinpath, "PATH")
        sys.path.append(self.pythonpath)

    @wrap_default('deactivate')
    def deactivate(self):
        self.path_pull(self.pythonpath, "PYTHONPATH")
        self.path_pull(self.pythonbinpath, "PATH")
        sys.path.remove(self.pythonpath)

#=============================================================================
#=============================================================================
class BinaryPackage(Package):
    def __init__(self, *args, **kwargs):
        super(BinaryPackage, self).__init__(*args, **kwargs)

        if self.data:
            self.linkname = self.data.get('linkname')

    @wrap_install
    def install(self):
        exe = None
        for f in os.listdir(self.build_path):
            full = join(self.build_path, f)
            if os.access(full, os.X_OK):
                exe = full
                break

        if not exe:
            raise Exception

        self.run(['ln', '-s', exe, join(self.install_path, self.linkname)])

    @wrap_default('activate')
    def activate(self):
        self.path_push(self.install_path, "PATH")

    @wrap_default('deactivate')
    def deactivate(self):
        self.path_pull(self.install_path, "PATH")

#=============================================================================
#=============================================================================
class KIMAPIPackageV1(Package):
    def __init__(self, *args, **kwargs):
        super(KIMAPIPackageV1, self).__init__(*args, **kwargs)

        self.bindir = join(self.install_path, 'bin')
        if self.data:
            self.buildcommands = self.data['build-commands']

    @wrap_install
    def install(self):
        with self.indir(self.build_path):
            with open("Makefile.KIM_Config.example") as f:
                cts = f.read()
            cts = re.sub(r'(?m)^\KIM_DIR.*\n?', 'KIM_DIR='+self.build_path+'\n', cts)
            cts = re.sub(r'(?m)^\#prefix.*\n?', 'prefix='+self.install_path+'\n', cts)
            with open("Makefile.KIM_Config", 'w') as f:
                f.write(cts)

            for c in self.buildcommands:
                nc = c.split()
                self.run(nc)

    @wrap_default('activate')
    def activate(self):
        self.path_push(self.bindir, "PATH")

    @wrap_default('deactivate')
    def deactivate(self):
        self.path_pull(self.bindir, "PATH")

#=============================================================================
#=============================================================================
class APTPackage(Package):
    def __init__(self, *args, **kwargs):
        super(APTPackage, self).__init__(*args, **kwargs)
        if self.data:
            self.commands = self.data['commands']

    @wrap_install
    def install(self):
        for c in self.commands:
            nc = c.split()
            self.run(nc)

    @wrap_default('activate')
    def activate(self):
        pass

    @wrap_default('deactivate')
    def deactivate(self):
        pass

def pkg_obj(name, *args, **kwargs):
    typedict = {
        "meta": Package,
        "apt": APTPackage,
        "pip": APTPackage,
        "python": PythonPackage,
        "binary": BinaryPackage,
        'kimapi-v1': KIMAPIPackageV1,
    }
    p = Package(name=name, *args, **kwargs)

    if p.ptype == 'custom':
        if not os.path.exists(p.pkgpy):
            p.bootstrap()

        sys.path.append(p.build_path)
        import package
        cls = package.pkg
        sys.path.remove(p.build_path)
    else:
        cls = typedict[p.ptype]

    return cls(name, *args, **kwargs)


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

        pks = []
        if self.get(key):
            pks = self.get(key)
            for i in xrange(len(pks)):
                ver = pks[i].version
                if util.compatible(ver, util.v2s(value.version)):
                    if util.later(value.version, ver):
                        pks[i] = value
                    done = True

            if not done:
                pks.append(value)
        else:
            pks.append(value)

        super(CompatibleVersionDict, self).update({key: pks})

    def tolist(self):
        return list(itertools.chain.from_iterable([v for k,v in self.iteritems()]))

    def fromlist(self, pks):
        for pk in pks:
            self.__setitem__(pk.name, pk)

    def compatible(self):
        good, bads = True, []
        for k,v in self.iteritems():
            if len(v) > 1:
                bads.extend(v)
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

