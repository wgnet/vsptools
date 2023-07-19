import json

from .config import Config
from .logger import log, SpecialChar, pretty_logger
from .storage import get_storage
from .utils import write_metafile, get_metadata_file_path

ENGINE_PROFILES_FILE = 'engine_profiles.json'
ROOT_COMPONENT = "engine"
DEFAULT_PROFILE = {
    "Default": [
        ROOT_COMPONENT
    ],
    "Programmers": [
        ROOT_COMPONENT,
        "debug"
    ]
}


def __get_available_components(engine_version: str, config: Config) -> list:
    components = []
    storage = get_storage(config.engines_storage, config.access_key, config.access_key_type)
    build_files = storage.get_files_list()

    for file in build_files:
        if not file.startswith(engine_version):
            continue
        component_name = file[len(engine_version):]
        if file.endswith(".zip"):
            component_name = component_name[:-4]
        elif file.endswith(".7z"):
            component_name = component_name[:-3]
        else:
            continue

        if not component_name:
            component_name = ROOT_COMPONENT
        else:
            component_name = component_name[1:]
        components.append(component_name)

    if ROOT_COMPONENT not in components:
        log.error(f'Root component for engine {engine_version} not found')
        exit(1)

    return components


def __get_engine_profiles(config: Config) -> dict:
    path_to_profiles = config.engines_storage.join(ENGINE_PROFILES_FILE)
    cache_path = config.get_engines_cache() / ENGINE_PROFILES_FILE

    storage = get_storage(path_to_profiles, config.access_key, config.access_key_type)
    if storage.download_file_to(cache_path):
        with open(cache_path, 'r') as profiles:
            try:
                return json.load(profiles)
            except json.JSONDecodeError as e:
                log.warning(f"Incorrect Profiles description format: {e}")

    return DEFAULT_PROFILE


def set_engine_profile(engine_version: str, config: Config):
    engine_profiles = __get_engine_profiles(config)
    engine_components = __get_available_components(engine_version, config)

    log.info(pretty_logger(f'Available engine components: {", ".join(engine_components)}'))

    while True:
        index = 0
        engine_profile_dict = {}
        log.info(pretty_logger('\nAvailable engine profiles:', color=SpecialChar.BLUE))
        for profiles in engine_profiles:
            index += 1
            engine_profile_dict[index] = profiles
            log.info(pretty_logger(f'{index} - {profiles}: {" + ".join(engine_profiles[profiles])}', level=1))
        select_profile = str(input('\nSelect the profile on engine for install (0 for exit): '))
        if select_profile == '0':
            return
        for profile in engine_profile_dict:
            if select_profile == str(profile):
                deformer_metafile_path = get_metadata_file_path()
                write_metafile(
                    deformer_metafile_path,
                    engine_profile=engine_profile_dict[profile],
                    engine_components=engine_profiles[engine_profile_dict[profile]])
                log.info(pretty_logger(
                    f'{engine_profile_dict[profile]} profile set successfully.\n'
                    f'Please run with `reinstall` action '
                    f'for installing new profile for engine',
                    color=SpecialChar.GREEN))
                return
