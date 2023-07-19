# check synced changes in uassets & utxt
import os
from asyncio.log import logger
from collections import defaultdict
from configparser import ConfigParser
from enum import Enum
from pathlib import Path
from typing import Dict, List

from utils.git import git

ERROR_MSG_BASE_HEADER          = dict(error_code=700, message='UTXT Checker')
ERROR_MSG_DELETED_ONLY_UASSET  = dict(error_code=701, message='Deleted only UASSET file but UTXT exist: {file}')
ERROR_MSG_MODIFIED_ONLY_UASSET = dict(error_code=702, message='Modified only UASSET. No changes for UTXT: {file}')
ERROR_MSG_DIFFERENT_CHANGES    = dict(error_code=703, message='Different changes for UASSET and UTXT file: {file}')
ERROR_MSG_NO_HEAD              = dict(error_code=799, message='Can`t find HEAD')


class FileType(Enum):
    DT = 'DataTable'
    STT = 'StringTable'
    BPC = 'BlueprintCore'
    BPGC = 'BlueprintGeneratedClass'


PREFIXES = [
    FileType.DT.name,
    FileType.STT.name,
    FileType.BPC.name,
    FileType.BPGC.name,
]

UASSET_EXT = '.uasset'
UTXT_EXT = '.utxt'


class ModeType(Enum):
    UNKNOWN = 0
    MODIFICATION = 1
    DELETE = 2


MODE_TYPES = {
    "A": ModeType.MODIFICATION,
    "C": ModeType.MODIFICATION,
    "D": ModeType.DELETE,
    "M": ModeType.MODIFICATION,
    "R": ModeType.MODIFICATION,
}

CFG_HEADER = '[/Script/UnrealEd.EditorEngine]\n'
CFG_HEADER_IN_STR = '/Script/UnrealEd.EditorEngine'
NO_FOLDERS = 'NoFolders'


def _prepare_message(error_code: int, message: str, file: str = "") -> Dict[int, str]:
    if file:
        message = message.format(file=file)
    return dict(error_code=error_code, message=message)


class FileInfo:
    def __init__(self, mode: str, path: Path, old_path: Path):
        self.mode: str = mode
        self.path: Path = path
        self.old_path: Path = old_path

    def get_filename(self) -> str:
        return self.path.stem

    def get_prefix(self) -> str:
        return self.path.stem.split("_")[0]

    def get_ext(self) -> str:
        return self.path.suffix

    def get_id(self) -> str:
        return os.path.join(self.path.parent, self.path.stem)

    def get_mode_type(self):
        return MODE_TYPES.get(self.mode, ModeType.UNKNOWN)


def read_ini() -> List[str]:
    abs_repo_dir = Path(git.rev_parse(show_toplevel=True))
    rel_cfg_dir = Path('Config/DefaultEngine.ini')
    cfg_path = abs_repo_dir / rel_cfg_dir
    if not cfg_path.exists():
        logger.error('config file not found')

    with open(cfg_path) as file:
        logger.debug(f'file - "{cfg_path}" successfully read')
        result = [i for i in file.readlines()]
        if not len(result):
            logger.error('config file is empty')
        return result


def check_config_exist(read_ini_result: List[str]) -> bool:
    for i in read_ini_result:
        if i == CFG_HEADER:
            logger.debug(f'config for [{CFG_HEADER_IN_STR}] exist')
            return True
    return False


def get_utxt_whitelist() -> Dict[FileType, List[str]]:
    if not check_config_exist(read_ini()):
        logger.debug('no config lines found')
        return {FileType.STT: [NO_FOLDERS], FileType.DT: [NO_FOLDERS]}

    def get_config_start_line(read_ini_result: List[str]) -> int:
        for i in read_ini_result:
            if i == CFG_HEADER:
                return read_ini_result.index(i)

    def filter_lines(read_ini_result: List[str]) -> str:
        cfg_as_list = read_ini_result[:]
        header_index = get_config_start_line(read_ini())
        config_line = cfg_as_list.pop(header_index)
        counter = 0
        while header_index <= len(cfg_as_list)-1:
            if not cfg_as_list[header_index] == '\n':
                config_line += str(counter)
                config_line += cfg_as_list.pop(header_index)
                counter +=1
            else:
                return config_line
        return config_line

    def read_config(cfg: str) -> List[str]:
        config = ConfigParser()
        config.read_string(cfg)
        options_list = config.options(CFG_HEADER_IN_STR)
        return [config.get(CFG_HEADER_IN_STR, i) for i in options_list]

    def parse_config(cfg: List[str]) -> Dict[FileType, List[str]]:
        cfg_result = {}
        for i in cfg:
            i = i.replace(')', '')
            i = i.replace('(', '')
            i = i.replace('"', '')
            line = i.split(',', maxsplit=1)
            if len(line) == 1:
                cfg_result[FileType(i.split('=')[1])] = f'\\{NO_FOLDERS}'
            elif len(line) == 2:
                cfg_result[FileType(line[0].split('=')[1])] = line[1].split('=')[1]
            else:
                logger.error('wrong utxt whitelist config format')

        for k, v in cfg_result.items():
            v = v.replace('/', '\\')
            v = v.replace(' ', '')
            if len(v) == 1:
                cfg_result[k] = [v[1:]]
            else:
                cfg_result[k] = [i.replace('Game', 'Content', 1)[1:] for i in v.split(',')]

        return cfg_result

    full_ini = read_ini()
    filtered_lines = filter_lines(full_ini)
    readed_config = read_config(filtered_lines)
    return parse_config(readed_config)


def check_config_not_empty() -> bool:
    white_list = get_utxt_whitelist()
    if white_list[FileType.STT] == [NO_FOLDERS] and white_list[FileType.DT] == [NO_FOLDERS]:
        logger.debug('no specified config-dirs for STT and DT')
        return False
    else:
        return True


def _get_list_of_files() -> Dict[str, List[FileInfo]]:
    files: Dict[str, List[FileInfo]] = defaultdict(list)

    head_ref = git.rev_parse("HEAD", verify=True)
    if "fatal:" in head_ref:
        logger.error('')
        return None

    white_list = get_utxt_whitelist()
    if white_list[FileType.STT] == [NO_FOLDERS] and white_list[FileType.DT] == [NO_FOLDERS]:
        config_exist = False
    else:
        config_exist = True

    raw_body = git.diff(cached=True, no_color=True, name_status=True, _c=['core.quotepath=false'])
    rows = raw_body.split("\n")
    for line in rows:
        if not len(line) or line.startswith('warning:'):
            continue
        line_parts = line.split("\t")

        if len(line_parts) == 2:
            mode, file_path = line_parts
            mode = mode[0]
            old_file_path = ""  # file_path
        elif len(line_parts) == 3:
            mode, old_file_path, file_path = line_parts
            mode = mode[0]
        else:
            raise ValueError(f'[{len(line_parts)}: {line_parts}] too many values to unpack')

        info = FileInfo(mode, Path(file_path), Path(old_file_path))

        if info.get_ext() not in [UASSET_EXT, UTXT_EXT]:
            continue

        if info.get_prefix() not in PREFIXES:
            continue

        if not config_exist:
            files[info.get_id()].append(info)
            continue

        elif info.get_prefix() == FileType.STT.name:

            for i in white_list[FileType.STT]:
                if i in info.get_id():
                    files[info.get_id()].append(info)

        elif info.get_prefix() == FileType.DT.name:
            for i in white_list[FileType.DT]:
                if i in info.get_id():
                    files[info.get_id()].append(info)

    return files


def check() -> List[Dict[int, str]]:
    errors = []

    files = _get_list_of_files()
    if files is None:
        errors.append(_prepare_message(**ERROR_MSG_NO_HEAD))
        return errors

    for id, files in files.items():
        mode = ModeType.UNKNOWN
        for file in files:
            if file.get_ext() == UASSET_EXT:
                if mode == ModeType.UNKNOWN:
                    mode = file.get_mode_type()
                if file.get_mode_type() == ModeType.DELETE:
                    if os.path.exists(f"{id}{UTXT_EXT}"):
                        errors.append(_prepare_message(**ERROR_MSG_DELETED_ONLY_UASSET, file=file.path))
                else:
                    if len(files) == 1:
                        errors.append(_prepare_message(**ERROR_MSG_MODIFIED_ONLY_UASSET, file=file.path))
            else:  # UTXT_EXT
                if mode == ModeType.UNKNOWN:
                    mode = file.get_mode_type()
                elif mode != file.get_mode_type():
                    errors.append(_prepare_message(**ERROR_MSG_DIFFERENT_CHANGES, file=file.path))

    if len(errors):
        errors.insert(0, _prepare_message(**ERROR_MSG_BASE_HEADER))

    return errors
