import asyncio
import inspect
import logging
import os
import platform
import re
import traceback
from contextlib import contextmanager
from functools import wraps
from time import perf_counter
from typing import Dict, Any, List

import dns.name
import dns.resolver
import dns.reversename
from dns.exception import DNSException
from exportana.configs import Configs
from exportana.exporter.constants import PATH_DELIMITER
from exportana.utils.compatibility import removesuffix

log = logging.getLogger(__name__)
EXCLUDED_KEYS = ["_Children", "_Duration", "_Editor", "_Budgets"]


def timing(msg: str, log_level=logging.DEBUG):
    def duration(func):
        @contextmanager
        def wrapping_logic():
            ts = perf_counter()
            yield
            te = perf_counter()
            log.log(log_level, f"{msg} took: {te - ts:2.2f}s")

        @wraps(func)
        def wrapper(*args, **kwargs):
            if not asyncio.iscoroutinefunction(func):
                with wrapping_logic():
                    return func(*args, **kwargs)
            else:
                async def tmp():
                    with wrapping_logic():
                        return await func(*args, **kwargs)

                return tmp()

        return wrapper

    return duration


def get_hostname_from_ip(ip, full_dns=False) -> str:
    try:  # try to back resolve the name
        answer = dns.resolver.Resolver().resolve(dns.reversename.from_address(ip), "PTR")
        ip = str(answer[0])
        if full_dns is False:
            ip = ip.split(".")[0]
        ip = ip.lower()
    except DNSException as e:
        log.warning(f"Can't back resolve {ip}. {type(e).__name__}: {e}")
    return ip


def human_read_to_byte(size: str):
    size_name = ("b", "kb", "mb", "gb", "tb", "pb", "eb", "zb", "yb")
    size = re.findall(r"[A-Za-z]+|\d+", size.lower())
    num, unit = int(size[0]), size[1]
    idx = size_name.index(unit)
    factor = 1024 ** idx
    return num * factor


def get_path_creation_date(path_to_file: str) -> float:
    """
    Try to get the date that a path was created, falling back to when it was
    last modified if that isn't possible.
    See http://stackoverflow.com/a/39501288/1709587 for explanation.
    """
    if platform.system() == "Windows":
        return os.path.getctime(path_to_file)
    else:
        stat = os.stat(path_to_file)
        try:
            return stat.st_birthtime
        except AttributeError:
            # We're probably on Linux. No easy way to get creation dates here,
            # so we'll settle for when its content was last modified.
            return stat.st_mtime


def print_trace():
    frame = inspect.currentframe()
    stack_trace = traceback.format_stack(frame)
    log.info(stack_trace[-2].replace("\n", "").strip().replace("print_trace()", ""))


def make_entrypoint_address(url: str, subpaths: list):
    result = PATH_DELIMITER.join(
        [removesuffix(url, PATH_DELIMITER), *[part for path in subpaths for part in path.split(PATH_DELIMITER)]]
    )
    return result


def make_url(*subpaths):
    result = make_entrypoint_address(
        f"{Configs.manager_url}",
        ["manager", *[part for path in subpaths for part in path.split(PATH_DELIMITER)]]
    )
    return result


def flatten_dict(data: Dict[str, Any], excluded_keys=None) -> Dict[str, Any]:
    if excluded_keys is None:
        excluded_keys = EXCLUDED_KEYS

    def items():
        for key, value in data.items():
            if isinstance(value, dict):
                for sub_key, sub_value in flatten_dict(value, excluded_keys).items():
                    new_sub_key = f"{key}_{sub_key}"
                    if excluded_keys:
                        for excluded_key in excluded_keys:
                            new_sub_key = new_sub_key.replace(excluded_key, "")
                    yield new_sub_key, sub_value
            else:
                yield key, value

    return dict(items())
