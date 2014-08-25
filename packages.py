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

PythonPackage:
    "data":  {
        "url": "<standalone url for pip>"
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
            logger.info("Installing %r ..." % self.fullname)
            if self.pkg_run('install'):
                self.finalize_install()
                return True
            else:
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
                        "Cannot wrap actions that are not %r" % actions
                    )

            if action == 'activate':
                for dep in self.dependencies():
                    dep.activate()
                logger.debug("Activating %s" % self.fullname)
                open(join(self.base_path, 'active'), 'a').close()
            if action == 'deactivate' and self.isactive():
                for dep in self.dependencies():
                    dep.deactivate()
                logger.debug("Deactivating %s" % self.fullname)
                os.remove(join(self.base_path, 'active'))

            if self.pkg_run(action):
                pass
            else:
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
        self.pkgpy = join(self.base_path, 'package.py')

        self.ptype = self.metadata.get('type')
        self.url = self.metadata.get('url')
        self.requirements = self.metadata.get("requires")
        self.data = self.metadata.get('data')

        self.cmdprefix = []
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
            logger.info("Downloading %r" % self.url)
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
            pkname = util.format_pk_name(req, ver_req)
            pkg = pkg_obj(name=req, versionrange=ver_req, pkfile=self.pkfile)
            deps.extend([pkg]+pkg.dependencies())
        return list(set(deps))

    def version_matches(self, pks):
        nomatch = []
        allmatch = True
        for req, ver in self.requirements.iteritems():
            for pk in pks:
                if (req == pk.name and not util.compatible(pk.version, ver)):
                    nomatch.append((pk.name, pk.version,  req, ver))
                    allmatch = False

        return allmatch, nomatch

    def consistent(self):
        nomatch = []
        allmatch = True

        deps = self.dependencies()
        for i in xrange(len(deps)):
            ok, bads = deps[i].version_matches(deps)
            if not ok:
                nomatch.extend(bads)
                allmatch = False

        return allmatch, nomatch

    def isinstalled(self):
        return os.path.exists(join(self.base_path, 'installed'))

    def isactive(self):
        return self.activated
        #return os.path.exists(join(self.base_path, 'active'))

    def path_exists(self, path, pathvar='PATH'):
        return re.search(path, os.environ[pathvar]) is not None

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

    def mkdir(self, path):
        if not os.path.isdir(path):
            os.mkdir(path)

    def mkdir_ext(self, extendedpath):
        if not os.path.isdir(extendedpath):
            subprocess.check_call(['mkdir', '-p', extendedpath])

    @contextmanager
    def sudo(self):
        self.cmdprefix = ['sudo']
        try:
            yield
        except Exception as e:
            raise e
        finally:
            self.cmdprefix = []

    def run(self, cmd):
        with open(self.log, 'a') as log:
            cmd = self.cmdprefix + cmd
            logger.info('  '+' '.join(cmd))
            subprocess.check_call(cmd, stdout=log, stderr=log)

    def haspy(self):
        return os.path.exists(self.pkgpy)

    def pkg_run(self, cmd):
        if self.haspy():
            if not isinstance(cmd, list):
                cmd = [cmd]
            with self.indir(self.base_path):
                logger.debug(
                    "Running %s's package.py with argument %r" 
                    % (self.fullname, cmd)
                )
                self.run(['python', self.pkgpy] + cmd)
                return True
        return False

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

    def export(self, form='bash'):
        with self.active():
            paths = self.env.copy()
        if form == 'bash':
            return "\n".join([
                "export %s=%s:$%s" % (k, v, k) for k,v in paths.iteritems()
            ])
        if form == 'csh':
            return "\n".join([
                "setenv %s %s:${%s}" % (k, v, k) for k,v in paths.iteritems()
            ])

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

    def main(self):
        parser = argparse.ArgumentParser(description=
            """Package setup script.  These are default options
            provided through the chip interface.  More can be
            made by overriding the run method""")
        action = parser.add_mutually_exclusive_group(required=True)
        action.add_argument('activate', action='store_true')
        action.add_argument('deactivate', action='store_true')
        action.add_argument('export', action='store_true')
        action.add_argument('install', action='store_true')
        action.add_argument('uninstall', action='store_true')

        args = parser.parse_args()
        if args.get('install'):
            self.install()
        if args.get('uninstall'):
            self.uninstall()
        if args.get('activate'):
            self.activate()
        if args.get('deactivate'):
            self.deactivate()
        if args.get('export'):
            self.export()

#=============================================================================
# Python package class
#=============================================================================
class PythonPackage(Package):
    def __init__(self, *args, **kwargs):
        super(PythonPackage, self).__init__(*args, **kwargs)
        self.pipurl = self.data.get('url') if self.data else None
        self.pythonpath = join(self.install_path, 'lib/python2.7/site-packages')
        self.pythonbinpath = join(self.install_path, 'bin')

    @wrap_install
    def install(self):
        if os.path.exists(join(self.build_path, 'setup.py')):
            with self.active():
                self.run(['python', 'setup.py', 'install',
                    '--prefix='+self.install_path])

        elif self.data:
            with self.active():
                self.run(['pip', 'install', self.pipurl, '--ignore-installed',
                    '-b', self.build_path,
                    '--install-option=--prefix='+self.install_path])
        else:
            with self.active():
                try:
                    self.run(['pip', 'install', self.name+"=="+self.version,
                        '-b', self.build_path, '--ignore-installed',
                        '--install-option=--prefix='+self.install_path])
                except:
                    raise util.PackageError("Could not setup package %s" % self.fullname)

    @wrap_default('activate')
    def activate(self):
        self.path_push(self.install_path, "PYTHONPATH")
        self.path_push(self.pythonbinpath, "PATH")
        sys.path.append(self.pythonpath)

    @wrap_default('deactivate')
    def deactivate(self):
        self.path_pull(self.install_path, "PYTHONPATH")
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
        with self.sudo():
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
        "python": PythonPackage, "binary": BinaryPackage,
        "apt": APTPackage, 'kimapi-v1': KIMAPIPackageV1,
        "meta": Package,
    }
    p = Package(name=name, *args, **kwargs)
    return typedict[p.ptype](name, *args, **kwargs)

