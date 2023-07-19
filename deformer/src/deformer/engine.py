import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict

from .config import Config
from .logger import log
from .storage import get_storage
from .utils import (
    combine_path,
    unpack_7zip,
    get_archive_crc,
    get_folder_engine_crc,
    get_metadata_file_path,
    write_metafile,
    get_metafile_path,
    get_engine_installation_status,
    InstallationStatus,
    remove_dir,
)

if os.name == 'nt':
    import winreg

REG_KEY_PATH = r'Software\Epic Games\Unreal Engine\Builds'


@dataclass
class EngineInfo:
    name: str
    path: Path
    status: InstallationStatus
    metafile_path: Path


def collect_engines_data() -> Dict[str, EngineInfo]:
    engines = {}
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, REG_KEY_PATH) as key:
        index = 0
        while True:
            try:
                values = winreg.EnumValue(key, index)
                metafile_path = get_metafile_path(values[1])
                engine = EngineInfo(values[0], Path(values[1]), get_engine_installation_status(metafile_path), metafile_path)
                engines[engine.name] = engine
                index += 1
            except WindowsError:
                break
    return engines


def __registration_engine(engine_version: str, engine_path: Path):
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_KEY_PATH, 0, winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, engine_version, 0, winreg.REG_SZ, str(engine_path))
        winreg.FlushKey(key)


def __get_engine_path(engine_version: str, config: Config) -> Path:  # TODO move to config
    return combine_path(Path(engine_version), config.get_engines_dir()).resolve().absolute()


def engine_crc_compare(engine_version: str, config: Config) -> bool:
    engine_path = __get_engine_path(engine_version, config)
    engine_cache_path = config.get_engines_cache()
    if engine_cache_path is None:
        log.error("Engine archive not found")
        return False
    return get_archive_crc(engine_cache_path) == get_folder_engine_crc(engine_path)


def __get_component_file_name(component: str, engine_version: str) -> str:
    is_engine = component == 'engine'
    return f'{engine_version}{"." + component if not is_engine else ""}.zip'


def install_engine(engine_version: str, config: Config, force_install: bool) -> bool:
    # Check installation dir
    engine_path = __get_engine_path(engine_version, config)
    engine_cache_path = config.get_engines_cache()
    metafile_path = get_metafile_path(engine_path)

    if not force_install and metafile_path.exists():  # TODO check status
        log.warning(f'Engine build version `{engine_version}` exist but not registered. If there is problem with this '
                    f'installation run with `reinstall` argument.')
    else:
        # Get component list
        try:
            with open(get_metadata_file_path()) as deformer_vars:
                components = json.load(deformer_vars).get('engine_components', ['engine'])
        except json.JSONDecodeError:
            components = ['engine']

        # Cache components
        log.info(f'Download engine to cache ...')
        for component in components:
            component_filename = __get_component_file_name(component, engine_version)
            storage = get_storage(config.engines_storage.join(component_filename), config.access_key, config.access_key_type)
            if not storage.download_file_to(engine_cache_path / component_filename):
                if component == 'engine':
                    log.error(f'Engine root component `{engine_version}` can be downloaded')
                    return False

        # Delete any existing folder
        if engine_path.is_dir():
            log.info(f'Clear location for installation ...')
            if not remove_dir(engine_path):
                write_metafile(metafile_path, InstallationStatus=InstallationStatus.FAILED.value)
                return False

        # Start installation
        log.info(f'Install engine to "{engine_path}"...')
        write_metafile(metafile_path, InstallationStatus=InstallationStatus.IN_PROGRESS.value)

        for component in components:
            component_filename = __get_component_file_name(component, engine_version)
            component_cache_path = engine_cache_path / component_filename
            if unpack_7zip(component_cache_path, engine_path.parent) != 0:
                log.error(f'Engine `{engine_version}` is not installed correctly')
                write_metafile(metafile_path, InstallationStatus=InstallationStatus.FAILED.value)
                return False

    # registration
    __registration_engine(engine_version, engine_path)
    log.info(f'Engine version `{engine_version}` registered')
    write_metafile(metafile_path, InstallationStatus=InstallationStatus.SUCCESS.value)
    return True
