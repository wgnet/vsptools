#!/usr/bin/env python3

from email import message
import sys
import os
import logging
from utils.console_color import SpecialChar
import re
from utils.git import git

COMMIT_ERROR_TEMPLATE = SpecialChar.RED + 'ERROR: VSP-GIT-HCMC#{error_code}' + SpecialChar.END + ': {message}'

PROJECT_NAME="VSP"
ISSUE_NUMBER_RE = re.compile(f"^(\[{PROJECT_NAME}-[\d]+\])|([Ww][Ii][Pp])|fixup!|amend!")

# Logger
console_handler = logging.StreamHandler()
logger = logging.getLogger("CommitMsgChecker")
logger.addHandler(console_handler)
logger.setLevel("INFO")


def main():
    logger.debug("Commit-msg checker:")

    file_path = sys.argv[1]
    merge_commits_messages = git.log(pretty="%s", merges=True)
    merge_commits_messages = merge_commits_messages.strip().split('\n')

    if not os.path.isfile(file_path):
        logger.error(COMMIT_ERROR_TEMPLATE.format(error_code=400, message="Message file not exist"))
        return 1

    with open(file_path, "r", encoding="utf-8") as fl:
        commit_msg = fl.read()

    if ISSUE_NUMBER_RE.match(commit_msg) is None and commit_msg not in merge_commits_messages:
        logger.error(COMMIT_ERROR_TEMPLATE.format(error_code=401, message=f"No issue number. Commit message should start with '[{PROJECT_NAME}-<number>]' with no spaces before.\n\nCorrect message example:\n[{PROJECT_NAME}-1000] Add new feature\n\nYour message:\n{commit_msg}"))
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
