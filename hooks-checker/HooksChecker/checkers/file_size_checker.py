import json
import logging
import os
from fnmatch import fnmatch
from typing import Dict, List

from utils.git import git
from utils.read_config import read_config

LFS_LINK_SIZE = 133
DEFAULT_MIN_SIZE = int(LFS_LINK_SIZE + LFS_LINK_SIZE * 0.2)
DEFAULT_MAX_SIZE = 1024 ** 2

MIN = 'min'
MAX = 'max'
ERROR = 'error'

ERROR_MSG_SIZE_CHECK_FAILED = dict(error_code=800, message="Size check failed: {file}")

WorkingFilesList = List[str]
RulesDict = Dict[str, Dict[str, int]]

ABS_PATH_TO_FILE_SIZE_CHECKER = os.path.dirname(__file__)
REL_PATH_TO_CONFIG = 'configs/file_size_checker.json'  # relative path from file_size_checker to config
CONFIG_PATH: str = os.path.normcase(os.path.join(ABS_PATH_TO_FILE_SIZE_CHECKER, REL_PATH_TO_CONFIG))
SIZE_RULES: RulesDict = read_config(CONFIG_PATH)

logger = logging.getLogger()


def _prepare_message(error_code: int, message: str, failed_file_check: str = "") -> Dict[int, str]:
    if failed_file_check:
        message = message.format(file=failed_file_check)
    return dict(error_code=error_code, message=message)


def validate_rules_values(rules) -> None:
    validate_errors = []
    for rule in rules:
        current_rule_sizes = rules[rule]
        if len(current_rule_sizes) == 2 and current_rule_sizes[MAX] < current_rule_sizes[MIN]:
            validate_errors.append(f"maxsize for rule '{rule}' can't be smaller than minsize")
    if validate_errors:
        logger.error(validate_errors)


def get_size_edges(dict_with_rules: RulesDict, rule: str) -> Dict[str, int]:
    len_of_rule_sizes: int = len(dict_with_rules[rule])
    res: Dict[str, int] = {MAX: DEFAULT_MAX_SIZE, MIN: DEFAULT_MIN_SIZE}
    msg: str = f'used default parameters for "{rule}"'

    if len_of_rule_sizes == 1:
        contained_key: str = list(dict_with_rules[rule].keys())[0]
        if contained_key == MAX:
            msg = f'used default parameter for min size'
            max_size: int = dict_with_rules[rule][contained_key]
            res = {MAX: max_size, MIN: DEFAULT_MIN_SIZE}
        elif contained_key == MIN:
            msg = f'used default parameter for max size'
            min_size: int = dict_with_rules[rule][contained_key]
            res = {MAX: DEFAULT_MAX_SIZE, MIN: min_size}
    elif len_of_rule_sizes == 2:
        res = dict_with_rules[rule]
        msg = f'valid parameters for {rule}'

    logger.info(msg)
    return res


def compare_sizes(diffed_files_list: WorkingFilesList) -> List:
    rules_list = list(SIZE_RULES.keys())
    errors = []

    for file in diffed_files_list:
        for rule in rules_list:
            if fnmatch(file, rule):
                sizes = get_size_edges(SIZE_RULES, rule)
                file_size = os.path.getsize(file)
                max_size = sizes[MAX]
                min_size = sizes[MIN]
                if file_size > max_size:
                    errors.append(
                        f"'{file}'= {file_size} bytes, can't be bigger than maxsize={max_size}.Rule for '{rule}'-type files")
                elif file_size < min_size:
                    errors.append(
                        f"'{file}' ={file_size} bytes, can't be smaller than minsize={min_size}.Rule for '{rule}'-type files")
                break
    return errors


def get_lfs_files_in_commit() -> WorkingFilesList:
    lfs_files = git.lfs('status', '--json')
    dict_of_lfs_files = json.loads(lfs_files)
    dict_of_lfs_files = dict_of_lfs_files.get('files', ERROR)
    if dict_of_lfs_files == ERROR:
        logger.error('get lfs-files dict problem. No "files"-key found')
        exit(1)

    list_of_lfs_files = list(dict_of_lfs_files.keys())
    return list_of_lfs_files


def delete_lfs_files_from_list(list_of_lfs: WorkingFilesList, list_of_diff: WorkingFilesList) -> WorkingFilesList:
    list_of_diff_copy = list_of_diff[:]
    for lfs_file in list_of_lfs:
        if lfs_file in list_of_diff_copy:
            list_of_diff_copy.remove(lfs_file)
    return list_of_diff_copy


def check() -> List:
    errors = []
    validate_rules_values(SIZE_RULES)

    list_of_diffed_files = git.diff(cached=True, no_color=True, name_only=True, diff_filter="ACMR")
    list_of_diffed_files = list_of_diffed_files.split()
    lfs_files_in_commit = get_lfs_files_in_commit()
    list_of_diffed_files = delete_lfs_files_from_list(lfs_files_in_commit, list_of_diffed_files)
    compare_result_errors = compare_sizes(list_of_diffed_files)

    if len(compare_result_errors):
        for this_error in compare_result_errors:
            errors.append(_prepare_message(**ERROR_MSG_SIZE_CHECK_FAILED, failed_file_check=this_error))
    return errors
