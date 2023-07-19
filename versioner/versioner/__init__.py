import sys
import logging


class LevelFilter(logging.Filter):

    def __init__(self, up=logging.CRITICAL + 1, down=logging.NOTSET):
        super().__init__()
        self.up = logging._checkLevel(up)
        self.down = logging._checkLevel(down)

    def filter(self, record):
        if record.levelno >= self.up or record.levelno <= self.down:
            return False
        return True


def setup_logger(in_logger):
    if len(in_logger.handlers) == 0:
        console_handler_base = logging.StreamHandler(sys.stdout)
        console_handler_base.setFormatter(logging.Formatter("%(message)s"))
        console_handler_base.addFilter(LevelFilter(up=logging.WARNING))
        in_logger.addHandler(console_handler_base)

        console_handler_err = logging.StreamHandler(sys.stderr)
        console_handler_err.setFormatter(logging.Formatter("\x1b[91m%(levelname)s: %(message)s\x1b[0m"))
        console_handler_err.addFilter(LevelFilter(down=logging.INFO))
        in_logger.addHandler(console_handler_err)

        in_logger.level = logging.INFO


logger = logging.getLogger("Versioner")
setup_logger(logger)
