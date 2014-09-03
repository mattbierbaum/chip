import os
import re
import json
import stat
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
    "url": "https://raw.githubusercontent.com/mattbierbaum/chip/master/tests/packages.json",
    "home":  join(_HOME_DIR, "openkim-packages"),
    "pkfile": join(_HOME_DIR, "openkim-packages", "packages.json")
}

def write_conf(cf):
    with open(_DEFAULT_CONF_FILE, 'w') as f:
        logger.debug("Writing conf to %s" % _DEFAULT_CONF_FILE)
        json.dump(cf, f, indent=4)

def initialize_conf_if_empty():
    logger.debug("Initializing configuration file with defaults.")

    if not os.path.exists(_DEFAULT_CONF_DIR):
        subprocess.check_call(['mkdir', '-p', _DEFAULT_CONF_DIR])

    if not os.path.exists(_DEFAULT_CONF_FILE):
        write_conf(_DEFAULT_FIELDS)

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
_BASHRC = join(_HOME_DIR, '.bashrc')
_ENVEXT = '.json'

_DEFAULT_STATUS = {
    "current-env": "default",
}

def add_path_bashrc():
    export = "export PATH="+_DEFAULT_CONF_DIR+":$PATH"

    if not os.path.exists(_BASHRC):
        raise Exception("Expecting bash, error!")
    else:
        with open(_BASHRC) as f:
            contents = f.read()

    if not re.search(re.escape(export), contents):
        with open(_BASHRC, 'a') as f:
            f.write('\n'+export+'\n')

def chop_on_path():
    try:
        loc = subprocess.check_output(['which', 'chop'])
    except subprocess.CalledProcessError as e:
        loc = ''
    return loc

def chop_write(stuff):
    with open(_CHOP_FILE, 'w') as f:
        f.write(stuff)
    st = os.stat(_CHOP_FILE)
    os.chmod(_CHOP_FILE, st.st_mode | stat.S_IEXEC)

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

def env_del(env=''):
    if not env:
        raise util.ChipRuntimeError("Must specify env to delete")

    os.remove(env_path(env))

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
command -v chip-deactivate >/dev/null 2>&1 && chip-deactivate

function chip-deactivate {{
    echo "Deactivating chip environment {env}..."
    {resets}
}}

{saves}

{prompt}
{exports}

echo "Exporting chip environment {env}..."
"""

def format_saves(paths, form='bash'):
    if form == 'bash':
        ps = "export _CHIPOLD_PS1=$PS1\n"

    if form == 'bash':
        return ps+"\n".join([
            "export _CHIPOLD_%s=$%s" % (k,k) for k,v in paths.iteritems()
        ])

def format_resets(paths, form='bash'):
    if form == 'bash':
        ps = "export PS1=$_CHIPOLD_PS1\n"

    if form == 'bash':
        return ps+"\n".join([
            "export %s=$_CHIPOLD_%s" % (k,k) for k,v in paths.iteritems()
        ])

def format_exports(paths, form='bash'):
    if form == 'bash':
        return "\n".join([
            "export %s=%s:$%s" % (k, v, k) for k,v in paths.iteritems()
        ])
    if form == 'csh':
        return "\n".join([
            "setenv %s %s:$%s" % (k, v, k) for k,v in paths.iteritems()
        ])

def format_prompt(env, form='bash'):
    if form == 'bash':
        return 'export PS1="(chip:{env}) $PS1"'.format(env=env)
    if form == 'csh':
        return 'setenv PS1 "(chip:{env}) $PS1"'.format(env=env)

def format_chop(paths, env='', form='bash'):
    env = env or get_env_current()
    pks = env_load(env)
    resets = format_resets(paths, form)
    saves = format_saves(paths, form)
    exports = format_exports(paths, form)
    prompt = format_prompt(env, form)

    return shellscript.format(resets=resets, exports=exports,
            bashrc=_BASHRC, prompt=prompt, env=env, saves=saves)
