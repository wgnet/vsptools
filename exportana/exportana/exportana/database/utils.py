import functools
import inspect
import logging
from typing import Callable

import pymongo.errors


def retry_on_mongo_exception(func: Callable):
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        log = logging.getLogger(inspect.getmodulename(inspect.getfile(func)))
        while True:
            try:
                return await func(*args, **kwargs)
            except pymongo.errors.OperationFailure as e:
                log.debug(f"[{func.__name__}] Caught pymongo.OperationFailure! Retrying whole request... {e}")
            except pymongo.errors.PyMongoError as e:
                log.warning(f"[{func.__name__}] Caught PyMongoError! Retrying whole request... {type(e).__name__} {e}")

    return wrapper
