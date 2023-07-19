#!/usr/bin/env python3

import sys
import os
import re
import logging

from utils.git import git
from utils.console_color import SpecialChar
from settings import INIT_SHA, PRE_COMMIT_CHECKERS, PRE_COMMIT_FILE_CHECKERS

COMMIT_ERROR_TEMPLATE = SpecialChar.RED + 'ERROR: VSP-GIT-HPCC#{error_code}' + SpecialChar.END + ': {message}'
FILE_ERROR_TEMPLATE = SpecialChar.RED + 'ERROR: VSP-GIT-HPCC#{error_code}' + SpecialChar.END + ': [{mode}] [{file_name}]: {message}'

# Logger

console_handler = logging.StreamHandler()
logger = logging.getLogger("PreCommitChecker")
logger.addHandler(console_handler)
logger.setLevel("INFO")

# Core function

def get_list_of_files():
    files=[]

    head_ref = git.rev_parse("HEAD", verify=True)
    if "fatal:" in head_ref:
        head_ref = INIT_SHA

    raw_body = git.diff(cached=True, no_color=True, name_status=True, _c=["core.quotepath=false"])
    rows = raw_body.split("\n")
    for line in rows:
        if not len(line) or line.startswith("warning:"):
            continue
        line_parts = line.split("\t")

        if len(line_parts) == 2:
            mode, file_path = line_parts
            old_file_path = file_path
        elif len(line_parts) == 3:
            mode, old_file_path, file_path = line_parts
        else:
            raise ValueError("[{}: {}] too many values to unpack".format(len(line_parts), line_parts))

        files.append((mode, file_path, old_file_path))

    return files


def main():
    logger.debug("Pre-commit checker:")
    run_result = 0

    for checker in PRE_COMMIT_CHECKERS:
        errors = checker()
        if len(errors):
            run_result = run_result | 1
            for error_data in errors:
                logger.error(COMMIT_ERROR_TEMPLATE.format(**error_data))

    files = get_list_of_files()
    logger.debug(f" Files {len(files)}")

    for file_params in files:
        file_errors = []
        for checker in PRE_COMMIT_FILE_CHECKERS:
            logger.debug(file_params)
            file_errors += checker(*file_params)

        if len(file_errors):
            for error_data in file_errors:
                logger.error(FILE_ERROR_TEMPLATE.format(**error_data))
            run_result = run_result | 2

    if run_result == 0:
        logger.debug("  All file checked. No errors found.")

    return run_result

# Entry point

if __name__ == "__main__":
    exit(main())
