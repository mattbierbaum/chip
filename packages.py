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
import urllib
import subprocess
import functools
from contextlib import contextmanager, nested
from packaging.version import Version, Specifier

#import time, datetime
#time.strftime("%Y-%m-%d %H:%M:%S")
#datetime.strptime("2010-06-04 21:08:12", "%Y-%m-%d %H:%M:%S")

join = os.path.join

DIR_HOME = os.environ['HOME']
DIR_PACKAGES = join(DIR_HOME, "packages")
PACKFILE_NAME = "packages.json"
PACKFILE = join(DIR_PACKAGES, PACKFILE_NAME)
PACKAGE_URL = "http://pipeline.openkim.org/packages"
VERSIONSEP = "@"

def format_pk_name(name, version):
    return name+VERSIONSEP+version

class PackageError(Exception):
    pass

class PackageNotFound(Exception):
    pass

class PackageInconsistent(Exception):
    pass

class PackageSupportError(Exception):
    pass

def wrap_install(func):
    def newinstall(self):
        if self.isinstalled():
            return True

        self.bootstrap()

        for dep in self.dependencies():
            dep.install()

        if self.pkg_run('install'):
            self.finialize_install()
            return True

        managers = [o.active() for o in self.dependencies()]
        with nested(*managers):
            func(self)

        self.finialize_install()

    return newinstall

def wrap_default(action):
    def wrapper(func):
        @functools.wraps(func)
        def newdec(self):
            actions = ['activate', 'deactivate']
            if action not in actions:
                raise PackageSupportError("Cannot wrap actions that are not %r")

            if action == 'activate':
                open(join(self.base_path, 'active'), 'a').close()
            if action == 'deactivate' and self.isactive():
                os.remove(join(self.base_path, 'active'))

            if self.pkg_run(action):
                return
            return func(self)
        return newdec
    return wrapper

class Package(object):
    def __init__(self, name, versionrange='', pkfile=None, search=True):
        metadata = None

        self.pkfile = pkfile or PACKFILE
        with open(self.pkfile) as f:
            pks = json.load(f)

        if re.match(VERSIONSEP, name):
            self.name, self.version = name.split(VERSIONSEP)
        else:
            self.name, self.version = name, None

        if self.version:
            for pk in pks:
                if (pk.get('name') == self.name and
                    pk.get('version') == self.version):
                    metadata = pk
        elif search:
            latest_match_version = ''

            for pk in pks:
                tname = pk.get('name')
                ver = pk.get('version')

                if tname != self.name:
                    continue

                if versionrange:
                    if (Version(ver) in Specifier(versionrange) and
                            (not latest_match_version or
                            (Version(ver) > Version(latest_match_version)))):
                        latest_match_version = ver
                        metadata = pk
                else:
                    if (not latest_match_version or Version(ver) > Version(latest_match_version)):
                        latest_match_version = ver
                        metadata = pk

            self.version = latest_match_version

        if not metadata:
            if versionrange:
                name = name + " " + versionrange
            raise PackageNotFound("%s not found in %s" % (name, self.pkfile))

        self.metadata = metadata
        self.shortname = self.name
        self.fullname = format_pk_name(self.name, self.version)

        self.base_path = join(DIR_PACKAGES, self.fullname)
        self.install_path = join(self.base_path, "install")
        self.build_path = join(self.base_path, "build")
        self.log_path = join(self.base_path, "log")
        self.log = join(self.log_path, "chip.log")

        self.mkdir_ext(self.base_path)
        self.mkdir(self.log_path)

        self.pkgfile = join(self.base_path, 'package.json')
        self.pkgpy = join(self.base_path, 'package.py')

        self.ptype = self.metadata.get('type')
        self.url = self.metadata.get('url')
        self.requirements = self.metadata.get("requires")
        self.data = self.metadata.get('data')

        self.cmdprefix = []

        consistent, bads = self.consistent()
        if not consistent:
            raise PackageInconsistent(
                "Package is inconsistent, the following versions don't match: %r" % bads
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
            dl = self.url
            urllib.urlretrieve(self.url, outname)

            tar = tarfile.open(outname)
            tar.extractall(path=untarname)
            tar.close()

            shutil.rmtree(self.build_path)
            shutil.copytree(untarname, self.build_path)
            shutil.rmtree(untarname)

    def dependencies(self):
        deps = []
        for req, ver_req in self.requirements.iteritems():
            pkname = format_pk_name(req, ver_req)
            pkg = pkg_obj(name=req, versionrange=ver_req, pkfile=self.pkfile)
            deps.extend([pkg]+pkg.dependencies())
        return deps

    def version_matches(self, pks):
        nomatch = []
        allmatch = True
        for req, ver in self.requirements.iteritems():
            for pk in pks:
                if (req == pk.name and Version(pk.version) not in Specifier(ver)):
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

    def path_exists(self, path, pathvar='PATH'):
        return re.search(path, os.environ[pathvar]) is not None

    def path_push(self, newpath, pathvar='PATH'):
        if not self.path_exists(newpath, pathvar):
            os.environ[pathvar] = newpath+os.path.pathsep+os.environ[pathvar]

    def path_pull(self, path, pathvar='PATH'):
        os.environ[pathvar] = re.subn(path+os.path.pathsep, '', os.environ[pathvar])[0]

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
        print ' '.join(cmd)
        with open(self.log, 'w') as log:
            subprocess.check_call(self.cmdprefix + cmd, stdout=log, stderr=log)

    def haspy(self):
        return os.path.exists(self.pkgpy)

    def pkg_run(self, cmd):
        if self.haspy():
            if not isinstance(cmd, list):
                cmd = [cmd]
            with self.indir(self.base_path):
                self.run(['python', self.pkgpy] + cmd)
                return True
        return False

    def finialize_install(self):
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

    def isactive(self):
        return os.path.exists(join(self.base_path, 'active'))

    def uninstall(self):
        pass

    @contextmanager
    def active(self):
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

class PythonPackage(Package):
    def __init__(self, *args, **kwargs):
        super(PythonPackage, self).__init__(*args, **kwargs)
        self.pipurl = self.data.get('url') if self.data else None
        self.pythonpath = join(self.install_path, 'lib/python2.7/site-packages')

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
                    raise PackageError("Could not setup package %s" % self.fullname)

    @wrap_default('activate')
    def activate(self):
        self.path_push(self.install_path, "PYTHONPATH")
        sys.path.append(self.pythonpath)

    @wrap_default('deactivate')
    def deactivate(self):
        self.path_pull(self.install_path, "PYTHONPATH")
        sys.path.remove(self.pythonpath)


class BinaryPackage(Package):
    def __init__(self, *args, **kwargs):
        super(PythonPackage, self).__init__(*args, **kwargs)

        if self.data:
            self.linkname = self.data.get('linkname')

    @wrap_install
    def install(self):
        exe = None
        for f in os.listdir(self.build_path):
            full = join(f, self.build_path)
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

class KIMAPIPackage(Package):
    def __init__(self, *args, **kwargs):
        super(KIMAPIPackage, self).__init__(*args, **kwargs)

    @wrap_install
    def install(self):
        with self.indir(self.build_path):
            self.run(["make"])

class APTPackage(Package):
    pass

def pkg_obj(name, *args, **kwargs):
    typedict = {
        "python": PythonPackage, "binary": BinaryPackage,
        "apt": APTPackage, 'kimapi': KIMAPIPackage,
    }
    p = Package(name=name, *args, **kwargs)
    return typedict[p.ptype](name, *args, **kwargs)

