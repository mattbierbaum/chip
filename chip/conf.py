import os
import re
import json
import string
import subprocess

join = os.path.join

_HOME_DIR = os.path.expanduser("~")
_DEFAULT_CONF_DIR = join(_HOME_DIR, ".kim-chip")
_DEFAULT_CONF_FILE = join(_DEFAULT_CONF_DIR, "chip.json")
DEFAULT_LOG_PATH = join(_DEFAULT_CONF_DIR, 'chip.log')

from log import createLogger
logger = createLogger(DEFAULT_LOG_PATH)

#=============================================================================
# functions that handle the global configuration
#=============================================================================
_DEFAULT_FIELDS = {
    "url": "http://pipeline.openkim.org/packages",
    "home":  join(_HOME_DIR, "openkim-packages"),
    "pkfile": join(_HOME_DIR, "openkim-packages", "packages.json")
}

def initialize_conf_if_empty():
    if not os.path.exists(_DEFAULT_CONF_DIR):
        subprocess.check_call(['mkdir', '-p', _DEFAULT_CONF_DIR])

    if not os.path.exists(_DEFAULT_CONF_FILE):
        with open(_DEFAULT_CONF_FILE, 'w') as f:
            json.dump(_DEFAULT_FIELDS, f, indent=4)

def read_conf():
    initialize_conf_if_empty()

    with open(_DEFAULT_CONF_FILE) as f:
        conf = json.load(f)

    for key in _DEFAULT_FIELDS.keys():
        if not key in conf:
            raise KeyError("'%s' not found in chip.json" % key)

    return conf

#=============================================================================
# the section that deals with the user-frontend configuration
#=============================================================================
_DEFAULT_ENVS_DIR = join(_DEFAULT_CONF_DIR, "envs")
_STATUS_FILE = join(_DEFAULT_CONF_DIR, "status.json")
_CHOP_FILE = join(_DEFAULT_CONF_DIR, "chop")
_ENVEXT = '.json'

_DEFAULT_STATUS = {
    "current-env": "default",
}

def add_path_bashrc():
    bashrc = join(_HOME_DIR, '.bashrc')
    export = "export PATH="+_DEFAULT_CONF_DIR+":$PATH"

    if not os.path.exists(bashrc):
        raise Exception("Expecting bash, error!")
    else:
        with open(bashrc) as f:
            contents = f.read()

    if not re.search(re.escape(export), contents):
        with open(bashrc, 'a') as f:
            f.write('\n'+export)
            f.write('\n. chop\n')

def chop_on_path():
    try:
        loc = subprocess.check_output(['which', 'chop'])
    except subprocess.CalledProcessError as e:
        loc = ''
    return loc

def chop_write(stuff):
    with open(_CHOP_FILE, 'w') as f:
        f.write(stuff)

def env_path(env):
    return join(_DEFAULT_ENVS_DIR, env+_ENVEXT)

def initialize_status_if_empty():
    add_path_bashrc()

    if not os.path.exists(_DEFAULT_ENVS_DIR):
        subprocess.check_call(['mkdir', '-p', _DEFAULT_ENVS_DIR])

    if not os.path.exists(_STATUS_FILE):
        with open(_STATUS_FILE, 'w') as f:
            json.dump(_DEFAULT_STATUS, f, indent=4)

    if not os.path.exists(_CHOP_FILE):
        with open(_CHOP_FILE, 'w') as f:
            f.write('')

    defaultenv = env_path(_DEFAULT_STATUS['current-env'])
    if not os.path.exists(defaultenv):
        with open(defaultenv, 'w') as f:
            json.dump([], f, indent=4)

def read_status():
    initialize_status_if_empty()

    with open(_STATUS_FILE) as f:
        conf = json.load(f)

    for key in _DEFAULT_STATUS.keys():
        if not key in conf:
            raise KeyError("'%s' not found in status.json" % key)
    return conf

def get_env_all():
    envs = []
    cf = read_conf()
    for env in os.listdir(_DEFAULT_ENVS_DIR):
        if env.endswith(_ENVEXT):
            name, ext = os.path.splitext(env)
            envs.append(name)
    return envs

def get_env_current():
    cf = read_status()
    return cf.get("current-env")

def env_switch(env=''):
    env = env or 'default'
    cf = read_status()
    cf['current-env'] = env

    with open(_STATUS_FILE, 'w') as f:
        json.dump(cf, f, indent=4)

    if not os.path.exists(env_path(env)):
        with open(env_path(env), 'w') as f:
            json.dump([], f, indent=4)

def env_save(pks, env=''):
    env = env or get_env_current()
    with open(env_path(env), 'w') as f:
        json.dump(pks, f, indent=4)

def env_load(env=''):
    env = env or get_env_current()
    with open(env_path(env)) as f:
        pks = json.load(f)
    return pks

def env_put(pk, env=''):
    env = env or get_env_current()
    pks = env_load(env)
    pks.append(str(pk))
    env_save(pks, env)

def env_pull(pk, env=''):
    env = env or get_env_current()
    pks = env_load(env)
    try:
        pks.remove(pk)
    except ValueError as e:
        logger.error("Package %r is not part of environment %r" % (pk, env))
    env_save(pks, env)

def env_clear(env=''):
    env = env or get_env_current()
    with open(env_path(env),'w') as f:
        json.dump([], f, indent=4)


shellscript = \
"""
PS1="(chip:{env}) $PS1"
"""

def env_wrapper(env=''):
    env = env or get_env_current()
    return shellscript.format(env=env)
