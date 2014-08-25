import os
import json
import subprocess

from log import createLogger
logger = createLogger("./chip.log")
join = os.path.join

_HOME_DIR = os.path.expanduser("~")
_DEFAULT_CONF_DIR = join(_HOME_DIR, ".kim-chip")
_DEFAULT_CONF_FILE = join(_DEFAULT_CONF_DIR, "chip.json")

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
_ENVEXT = '-env.json'

def get_env_all():
    pass

def get_env_current():
    pass

def get_env_active():
    pass

def save_env(envname=''):
    pass

def load_env(envname=''):
    pass

def env_wrapper():
    # add nice shell magic, etc.
    pass
