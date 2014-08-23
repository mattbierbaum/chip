import os
import logging
import logging.handlers

FILELEVEL = logging.INFO

def createLogger(path='', level=logging.INFO):
    logger = logging.getLogger("chip")
    logger.setLevel(logging.INFO)

    if len(logger.handlers) > 0:
        return logger
    
    file_log_formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s'
    )
    log_formatter = logging.Formatter(
        '%(levelname)s - %(message)s'
    )

    #create a rotating file handler
    rotfile_handler = logging.handlers.RotatingFileHandler(path,
            mode='a', backupCount=5, maxBytes=10*1024*1024)
    rotfile_handler.setLevel(FILELEVEL)
    rotfile_handler.setFormatter(file_log_formatter)
    logger.addHandler(rotfile_handler)

    if os.environ.get("CHIPVERBOSE"):
        level = logging.DEBUG

    #create a console logger
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(log_formatter)
    logger.addHandler(console_handler)

    return logger
