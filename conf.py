import os
import json
import subprocess

from log import createLogger
logger = createLogger("./chip.log")
join = os.path.join

HOME_DIR = os.path.expanduser("~")
DEFAULT_CONF_DIR = join(HOME_DIR, ".kim-chip")
DEFAULT_CONF_FILE = join(DEFAULT_CONF_DIR, "chip.json")

DEFAULT_FIELDS = {
    "url": "http://pipeline.openkim.org/packages",
    "home":  join(HOME_DIR, "openkim-packages"),
    "pkfile": join(HOME_DIR, "openkim-package", "packages.json")
}

def initialize_conf_if_empty():
    if not os.path.exists(DEFAULT_CONF_DIR):
        subprocess.check_call(['mkdir', '-p', DEFAULT_CONF_DIR])

    if not os.path.exists(DEFAULT_CONF_FILE):
        with open(DEFAULT_CONF_FILE, 'w') as f:
            json.dump(DEFAULT_FIELDS, f, indent=4)

def read_conf():
    initialize_conf_if_empty()

    with open(DEFAULT_CONF_FILE) as f:
        conf = json.load(f)

    for key in DEFAULT_FIELDS.keys():
        if not key in conf:
            raise KeyError("'%s' not found in chip.json" % key)

    return conf
