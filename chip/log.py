import os
import sys
import logging
import logging.handlers
import subprocess

FILELEVEL = logging.DEBUG

class NewlineFormatter(logging.Formatter):
    def format(self, record):
        rec = super(NewlineFormatter, self).format(record) 
        if len(rec) > 79:
            return rec[:75] + "..."
        return rec

def createLogger(path='', level=logging.INFO):
    path = path or "./chip.log"
    logger = logging.getLogger("chip")
    logger.setLevel(logging.DEBUG)

    if len(logger.handlers) > 0:
        return logger

    if not os.path.isdir(os.path.dirname(path)):
        subprocess.check_call(['mkdir', '-p', os.path.dirname(path)])

    file_log_formatter = logging.Formatter(
        '%(asctime)s - %(name)s-%(levelname)s: %(message)s'
    )
    log_formatter = logging.Formatter(
        '%(name)s-%(levelname)s: %(message)s'
    )

    #create a rotating file handler
    rotfile_handler = logging.handlers.RotatingFileHandler(path,
            mode='a', backupCount=5, maxBytes=10*1024*1024)
    rotfile_handler.setLevel(FILELEVEL)
    rotfile_handler.setFormatter(file_log_formatter)
    logger.addHandler(rotfile_handler)

    #create a console logger
    console_handler = logging.StreamHandler(stream=sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(log_formatter)
    logger.addHandler(console_handler)

    if os.environ.get("CHIPVERBOSE"):
        level = logging.DEBUG
    setLevel(level)

    return logger

def setLevel(level=logging.INFO):
    logger = logging.getLogger('chip')

    if not logger.handlers:
        raise Exception("Logging has not been established, cannot set level")

    if level == logging.DEBUG:
        format_cls = logging.Formatter
    else:
        format_cls = NewlineFormatter

    log_formatter = format_cls('%(name)s-%(levelname)s: %(message)s')
    for l in logger.handlers:
        if isinstance(l, logging.StreamHandler):
            l.setLevel(level)
            l.setFormatter(log_formatter)
