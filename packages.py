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
called package.edn which contains:
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
import subprocess
from contextlib import contextmanager

#import time, datetime
#time.strftime("%Y-%m-%d %H:%M:%S")
#datetime.strptime("2010-06-04 21:08:12", "%Y-%m-%d %H:%M:%S")

join = os.path.join

DIR_HOME = os.environ['HOME']
DIR_PACKAGES = join(DIR_HOME, "packages")
PACKAGE_URL = "http://pipeline.openkim.org/packages"
versionsep = "@"

class Package(object):
    def __init__(self, name='', pkfile=None):
        if pkfile:
            if isinstance(pkfile, basestring):
                if os.path.exists(pkfile):
                    self.metadata = json.load(open(pkfile))
            elif isinstance(pkfile, file):
                self.metadata = json.load(pkfile)

            self.name = self.metadata.get('name')
            self.version = self.metadata.get('version')

        elif name:
            self.name, self.version = name.split(versionsep)

        self.shortname = self.name
        self.fullname = self.name+versionsep+self.version

        self.base_path = join(DIR_PACKAGES, self.fullname)
        self.install_path = join(self.base_path, "install")
        self.build_path = join(self.base_path, "build")
        self.log_path = join(self.base_path, "log")
        self.log = join(self.log_path, "chip.log")

        self.mkdir_ext(self.base_path)
        self.mkdir(self.log_path)

        self.pkgfile = join(self.base_path, 'package.json')
        self.pkgpy = join(self.base_path, 'package.py')

        if not self.metadata:
            self.metadata = json.load(open(self.pkgfile))

        self.ptype = self.metadata.get('type')
        self.url = self.metadata.get('url')
        self.requirements = self.metadata.get("requires")
        self.data = self.metadata.get('data')

        self.cmdprefix = []

    def bootstrap(self):
        if not os.path.exists(self.pkgfile):
            with open(self.pkgfile, 'w') as f:
                json.dump(self.metadata, f, indent=4)

        if self.url:
            tarname = self.fullname+".tar.gz"
            outname = join(self.base_path, tarname)
            untarname = join(self.base_path, self.fullname)

            dl = PACKAGE_URL+"/"+self.shortname+"/"+tarname
            urllib.urlretrieve(dl, outname)
            
            tar = tarfile.open(outname)
            tar.extractall(path=untarname)
            tar.close()

            shutil.copytree(untarname, self.build_path)
            shutil.rmtree(untarname)

        self.mkdir(self.build_path)
        self.mkdir(self.install_path)

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

    def install(self):
        return self.pkg_run('install')

    def uninstall(self):
        return self.pkg_run('uninstall')

    def activate(self):
        return self.pkg_run('activate')

    def deactivate(self):
        return self.pkg_run('deactivate')

    def isactive(self):
        return self.pkg_run('install')

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

class PythonPackage(Package):
    def __init__(self, *args, **kwargs):
        super(PythonPackage, self).__init__(*args, **kwargs)
        self.url = self.data.get('url') if self.data else None
        self.pythonpath = join(self.install_path, 'lib/python2.7/site-packages')

    def install(self):
        if super(PythonPackage, self).install():
            return

        self.mkdir(self.install_path)
        self.mkdir(self.build_path)

        if os.path.exists(join(self.build_path, 'setup.py')):
            with self.active():
                self.run(['python', 'setup.py', 'install',
                    '--prefix='+self.install_path])
            
        elif self.data:
            with self.active():
                self.run(['pip', 'install', self.url, '--ignore-installed',
                    '-b', self.build_path,
                    '--install-option=--prefix='+self.install_path+''])

        else:
            print "Could not setup package %s" % self.fullname

    def activate(self):
        self.path_push(self.install_path, "PYTHONPATH")
        sys.path.append(self.pythonpath)

    def deactivate(self):
        self.path_pull(self.install_path, "PYTHONPATH")
        sys.path.remove(self.pythonpath)

    def isactive(self):
        pass

class BinaryPackage(Package):
    def __init__(self, *args, **kwargs):
        super(PythonPackage, self).__init__(*args, **kwargs)

        if self.data:
            self.linkname = self.data.get('linkname')

    def install(self):
        if super(PythonPackage, self).install():
            return

        exe = None
        for f in os.listdir(self.build_path):
            full = join(f, self.build_path)
            if os.access(full, os.X_OK):
                exe = full
                break

        if not exe:
            raise Exception

        self.run(['ln', '-s', exe, join(self.install_path, self.linkname)])

    def activate(self):
        self.path_push(self.install_path, "PATH")

    def deactivate(self):
        self.path_pull(self.install_path, "PATH")

    def isactive(self):
        pass

class APTPackage(Package):
    pass

