# Correct symbols Checks

import re
from utils.console_color import SpecialChar

#CORRECT_SYMBOLS_REGEX = re.compile("^[a-zA-Z0-9_/\-\.]+$")
IN_CORRECT_SYMBOLS_REGEX = re.compile("(?P<incorrect>[^a-zA-Z0-9_\/\-\.+]+)")
REPLACE_FORMAT = SpecialChar.BG_RED + r"\g<incorrect>" + SpecialChar.END
CORRECT_SYMBOLS_ERROR_MSG = 'File use unsupported symbols in name or path. Use only latin, numbers or `.` `_` `-` `+` in path or file name.'


def check_file(mode, file_path, old_file_path):
    errors = []
    if (mode != 'D'):
        if IN_CORRECT_SYMBOLS_REGEX.search(file_path):
            error_file_path = IN_CORRECT_SYMBOLS_REGEX.sub(REPLACE_FORMAT, file_path)
            errors.append(dict(error_code=101, mode=mode, file_name=error_file_path, message=CORRECT_SYMBOLS_ERROR_MSG))
    return errors
