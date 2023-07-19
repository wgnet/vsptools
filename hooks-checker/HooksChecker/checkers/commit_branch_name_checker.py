# Correct symbols Checks

import re

from utils.git import git

#
# Config section
#

EXCEPTIONS = [
    'HEAD',
]

ROOTS = [
    "feature",
    "bugfix",
    "hotfix",
    "refactor", # server exception
    "local",    # for local-only branch
]

GROUPS = [
    # ART groups
    "Art",
    "Maps",
    # TECH groups
    "Build",
    "Deploy",
    "Tech",
    "Tools",
    # Other groups
    "Backend",
    "GD",
    "Prototype",
]

FOLDER_NAME = re.compile("^[a-zA-Z0-9_\-.]+$")

DOC_LINK = "https://confluence.local.net/x/HRmkJw"

#
# Work section
#

ERROR_MSG_BRANCH_NAME_INCORRECT        = dict(error_code=300, message='Commit into incorrect Branch Name "{branch}"')
ERROR_MSG_BRANCH_NAME_FORMAT_INCORRECT = dict(error_code=301, message='Incorrect branch name format. Must be `<branch_type>/<group>/<feature_name>` no more no less')
ERROR_MSG_ROOT_FOLDER_INCORRECT        = dict(error_code=302, message='Incorrect Root folder [{branch}]. Must be one of [{roots}]'.format(branch="{branch}", roots=', '.join(ROOTS)))
ERROR_MSG_GROUP_NAME_INCORRECT         = dict(error_code=303, message='Incorrect Group name [{branch}]. Must be one of [{groups}]'.format(branch="{branch}", groups=', '.join(GROUPS)))
ERROR_MSG_FEATURE_NAME_INCORRECT       = dict(error_code=304, message='Incorrect Feature name [{branch}]. Must be use only latin symbol, numbers and symbols `-` `_` `.`')
ERROR_MSG_COMMON_NOTES                 = dict(error_code=300, message="For more info check documentation - {link}".format(link=DOC_LINK))


def _prepare_message(branch, error_code, message):
    message = message.format(branch=branch)
    return dict(error_code=error_code, message=message)


def _check_format(branch_name):
    errors = []

    if branch_name in EXCEPTIONS:
        return errors

    name_parts = branch_name.split('/')

    if len(name_parts) != 3:
        errors.append(ERROR_MSG_BRANCH_NAME_FORMAT_INCORRECT)
        return errors

    root_folder = name_parts.pop(0)
    if root_folder not in ROOTS:
        errors.append(_prepare_message(root_folder, **ERROR_MSG_ROOT_FOLDER_INCORRECT))

    group_name = name_parts.pop(0)
    if group_name not in GROUPS:
        errors.append(_prepare_message(group_name, **ERROR_MSG_GROUP_NAME_INCORRECT))

    feature_name = name_parts.pop(0)
    if (FOLDER_NAME.match(feature_name) is None):
        errors.append(_prepare_message(feature_name, **ERROR_MSG_FEATURE_NAME_INCORRECT))

    return errors


def check():
    branch_name = git.rev_parse("HEAD", abbrev_ref=True)

    errors = _check_format(branch_name)

    if len(errors):
        errors.insert(0,_prepare_message(branch_name, **ERROR_MSG_BRANCH_NAME_INCORRECT))
        errors.append(ERROR_MSG_COMMON_NOTES)
    return errors
