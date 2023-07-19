#!/usr/bin/env python3

import checkers

INIT_SHA = '<initial commit>' # Initial commit for this repo

# Settings

PRE_COMMIT_CHECKERS = [
    checkers.commit_branch_name_checker.check,
    checkers.utxt_checker.check,
    checkers.file_size_checker.check,
]

PRE_COMMIT_FILE_CHECKERS = [
    checkers.basic_file_name_checker.check_file,
]
