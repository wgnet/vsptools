import logging
import os
import sys
import getpass
from logstash_async.formatter import LogstashFormatter
from logstash_async.handler import AsynchronousLogstashHandler

os.system('')  # Hack to use colour output


class LevelFilter(logging.Filter):

    def __init__(self, up=logging.CRITICAL + 1, down=logging.NOTSET):
        super().__init__()
        self.up = logging._checkLevel(up)
        self.down = logging._checkLevel(down)

    def filter(self, record):
        if self.up > record.levelno >= self.down:
            return True
        return False


def setup_logger(logger, config):
    if len(logger.handlers) == 0:
        console_handler_base = logging.StreamHandler(sys.stdout)
        console_handler_base.setFormatter(logging.Formatter("%(message)s"))
        console_handler_base.addFilter(LevelFilter(up=logging.WARNING))
        logger.addHandler(console_handler_base)

        console_handler_warning = logging.StreamHandler(sys.stdout)
        console_handler_warning.setFormatter(logging.Formatter("\x1b[93m%(levelname)s: %(message)s\x1b[0m"))
        console_handler_warning.addFilter(LevelFilter(up=logging.ERROR, down=logging.WARNING))
        logger.addHandler(console_handler_warning)

        console_handler_err = logging.StreamHandler(sys.stderr)
        console_handler_err.setFormatter(logging.Formatter("\x1b[91m%(levelname)s: %(message)s\x1b[0m"))
        console_handler_err.addFilter(LevelFilter(down=logging.ERROR))
        logger.addHandler(console_handler_err)

    if config:
        logger.level = logging.getLevelName(config.log.level)

        if config.log.host != "":
            logstash_handler = AsynchronousLogstashHandler(config.log.host, config.log.port, None)
            logstash_formatter = LogstashFormatter(
                extra_prefix='dev',
                extra=dict(application='deformer', user=f"{getpass.getuser}"))
            logstash_handler.setFormatter(logstash_formatter)
            logger.addHandler(logstash_handler)
    else:
        logger.level = logging.INFO


log = logging.getLogger("Deformer")
setup_logger(log, None)


class SpecialChar:
    END = '\x1b[0m'
    RED = '\x1b[91m'
    GREEN = '\x1b[92m'
    YELLOW = '\x1b[93m'
    BLUE = '\x1b[94m'


def add_color(msg: str, color: str) -> str:
    return "{}{}{}".format(color, msg, SpecialChar.END)


def pretty_logger(string: str, level=0, color=None) -> str:
    levels = ["{:<0}", "{:<4}", "{:<8}", "{:<12}"]
    formatter = levels[level]
    formatter = formatter.format("")
    if color is not None:
        string = add_color(string, color)
    return formatter + string
