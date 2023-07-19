import json
import os
import shutil
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Dict, Optional

from .storage import get_storage, BuildStorage
from .utils import ArtifactInfo, Version, unpack_7zip, get_folder_crc, get_archive_crc
from .config import Config, PluginConfig
from .engine import EngineInfo
from .logger import log


class PluginStatus(Enum):
    NotInstalled = 0
    Installed = 1


@dataclass
class UPluginData:
    name: str
    version: Version
    path: Path
    status: PluginStatus


@dataclass
class PluginInfo:
    name: str
    config: Optional[PluginConfig]
    uplugin: UPluginData


def __load_plugins_data(plugins_configs: Dict[str, PluginConfig],
                        engine_path: Path,
                        plugins_dir: Path,
                        ) -> Dict[str, PluginInfo]:
    plugins = dict()

    plugins_path = (engine_path / plugins_dir).absolute()

    for name, plugin_config in plugins_configs.items():
        plugins[name] = PluginInfo(name, plugin_config, __get_uplugin_data(plugins_path, name))

    for name in os.listdir(plugins_path):
        if name in plugins:
            continue
        plugins[name] = PluginInfo(name, plugins_configs.get(name, None), __get_uplugin_data(plugins_path, name))

    return plugins


def __log_plugin_data(plugin: PluginInfo):
    msg = f"{plugin.name}:" \
          f"\n  - installation: {'installed' if plugin.uplugin.status == PluginStatus.Installed else 'not installed'}" \
          f"\n    - version: {plugin.uplugin.version}" \
          f"\n    - path: {plugin.uplugin.path}"

    if plugin.config is None:
        msg += f"\n  - config: None"
    else:
        msg += f"\n  - config:" \
               f"\n    - version: {plugin.config.version}"
    log.info(msg)


def install_plugins(force_install: bool, config: Config, engine: EngineInfo) -> bool:
    plugins_dir = (engine.path / config.plugins_dir).absolute()
    plugins_dir.mkdir(parents=True, exist_ok=True)

    plugins_cache_dir = config.get_engines_cache() / engine.name
    plugins_cache_dir.mkdir(parents=True, exist_ok=True)

    plugins = __load_plugins_data(config.plugins, engine.path, config.plugins_dir)

    storage = get_storage(config.plugins_storage.join(engine.name), config.access_key, config.access_key_type)
    dev_storage = get_storage(config.plugins_dev_storage.join(engine.name), config.access_key, config.access_key_type)

    log.info(f"Found configs for {len(config.plugins)} plugins.")
    for name, plugin in plugins.items():
        __log_plugin_data(plugin)

        if plugin.config is None:
            log.warn(f'Plugin {plugin.name} not specified in plugins configuration. Plugin will removed')
            shutil.rmtree(plugins_dir / plugin.name)
            continue

        artifact = __find_version(storage, plugin)

        if config.development_mode:
            artifact_dev = __find_version(dev_storage, plugin)
            if artifact_dev.version > artifact.version:
                log.warning(f'Pre-release version of plugin will be used - {artifact_dev.name} version {artifact_dev.version}')
                artifact = artifact_dev

        if artifact.exist():
            log.info(f'  {name}: Found version: {artifact.version}')
            cached_artifact: Path = plugins_cache_dir / artifact.file_name
            artifact_storage = get_storage(artifact.location, config.access_key, config.access_key_type)
            if artifact_storage.download_file_to(cached_artifact) and \
                (
                    plugin.uplugin.status == PluginStatus.NotInstalled or
                    artifact.version != plugin.uplugin.version or
                    force_install or
                    get_folder_crc(plugin.uplugin.path) != get_archive_crc(cached_artifact)
            ):
                __install(artifact, plugins_cache_dir, engine.path, config.plugins_dir)
            else:
                log.info(f'  {artifact.name}: Version in engine are OK: {artifact.version}')
        else:
            log.error(f'{artifact.name}: Artifact not found in storage & cache')

    return True


def __find_version(storage: BuildStorage, plugin: PluginInfo) -> ArtifactInfo:
    artifact = ArtifactInfo(plugin.name, version=plugin.uplugin.version)
    files_list = storage.get_files_list(plugin.name)

    for file_name in files_list:
        if not file_name.startswith(plugin.name + '.'):
            continue
        version_str = file_name[len(plugin.name) + 1:]
        if version_str.endswith(".zip"):
            version_str = version_str[:-4]
        elif version_str.endswith(".7z"):
            version_str = version_str[:-3]
        else:
            continue
        try:
            version = Version(version_str)
        except ValueError:
            log.warning(f"{plugin.name} has incorrect version value {version_str}. Will used default values.")
            version = Version()

        if plugin.config.version.check(version):
            if version >= artifact.version:
                location = storage.location.join(plugin.name).join(file_name)
                artifact = ArtifactInfo(plugin.name, location, file_name, version)

        log.debug(f"{file_name} : {plugin.config.version} :- {plugin.uplugin.version} - {version}")

    return artifact


def __install(artifact: ArtifactInfo, plugins_cache: Path, engine_path: Path, plugins_dir: Path) -> bool:
    artifact_source = plugins_cache / artifact.file_name

    if artifact_source.is_file():
        plugins_path = engine_path / plugins_dir / artifact.name

        if plugins_path.is_dir():
            try:
                log.info(f"  {artifact.name}: Remove prev. version from `{plugins_path}`")
                shutil.rmtree(plugins_path)
            except PermissionError as e:
                log.error(f"  {artifact.name}: can't remove`{plugins_path}`: {e}")
                return False

        if unpack_7zip(artifact_source, plugins_path.parent) == 0:
            log.info(f"  {artifact.name}: Latest version installed")
            return True
        else:
            log.warning(f"  {artifact.name}: Failed to unzip archive")
            return False
    else:
        log.warning(f"  {artifact.name}: Failed to acquire plugin")
        return False


def __get_uplugin_data(plugins_path: Path, plugin_name: str) -> UPluginData:
    plugin_path = plugins_path / plugin_name
    uplugin_path = plugin_path / f"{plugin_name}.uplugin"
    status = PluginStatus.NotInstalled
    version = Version()
    if uplugin_path.is_file():
        with open(uplugin_path, "r", encoding="utf-8") as plugin_file:
            try:
                raw_plugin_data = json.load(plugin_file)
                version_str = raw_plugin_data.get("VersionName", None)
                version = Version(version_str)
                status = PluginStatus.Installed
            except json.JSONDecodeError as e:
                log.warning(f"{plugin_name} has error in uplugin file. Will used default values. - {e}")
            except ValueError:
                log.warning(f"{plugin_name} has unsupported version value {version_str}. Will used default values.")

    return UPluginData(plugin_name, version, plugin_path, status)
