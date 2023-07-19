# AssetsController Checks

import os
import sys

# hack to work with AssetsController
MODULE_PATH = os.path.join('Tools','AssetsController')
ABS_MODULE_PATH = os.path.abspath(os.path.join(os.curdir, MODULE_PATH))
sys.path.append(ABS_MODULE_PATH)
import AssetsController

EXCLUDE_PATHS = [
    os.path.join("Content", "RestrictedAssets"),
    os.path.join("Content", "StarterContent"),
]

CONFIG_PATH = os.path.join(MODULE_PATH, 'config.json')
ASSETS_CONTROLLER_ERROR_MSG = 'AssetsController found errors:'


def check_in_assets_controller(mode, file_path, old_file_path):
    errors = []
    if mode != 'D' and file_path.startswith("Content/"):
        problem_files = AssetsController.run('.', file_path, True, EXCLUDE_PATHS, CONFIG_PATH, verbose=False, quite=True)
        if len(problem_files):
            file_info = next(iter(problem_files))
            msg = [ASSETS_CONTROLLER_ERROR_MSG, ]
            msg.append('  {0}'.format(file_info.data()))
            for err in file_info.errors:
                msg.append('  - {0} :: {1}'.format(*err))
            
            errors.append(dict(error_code=201, mode=mode, file_name=file_path, message='\n'.join(msg)))
        
    return errors
