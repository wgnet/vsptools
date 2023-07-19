import os
import argparse
import re
from pathlib import Path
from typing import Dict, Tuple, Optional
import yaml
from dataclasses import dataclass, field
from enum import Enum
import pkgutil

from .logger import log, setup_logger
from .utils import combine_path, Url, UrlType, VersionSelector

DEFAULT_CONFIG_NAME = "deformer.yml"
PLUGINS_CONFIG = Path(".plugins")


class Action(Enum):
    CHECK = "check"
    REINSTALL = "reinstall"
    VERIFY = "verify"
    PROFILE = "profile"

    def __str__(self):
        return self.value


class Mode(Enum):
    PROJECT = "project"
    SPECIFIC = "specific"

    def __str__(self):
        return self.value


@dataclass
class LoggingConfig:
    level: str = "INFO"
    host: str = ""
    port: int = 10050


@dataclass
class PluginConfig:
    name: str
    version: VersionSelector


@dataclass
class Config:
    project_name: str
    engines_dir: Path
    engines_cache: Path
    engines_storage: Url
    plugins_storage: Url
    plugins_dir: Path
    plugins: Dict[str, PluginConfig]
    access_key: str
    access_key_type: str
    development_mode: bool
    plugins_dev_storage: Url
    log: LoggingConfig = field(default_factory=LoggingConfig)

    def get_engines_cache(self):
        return combine_path(self.engines_cache)

    def get_engines_dir(self):
        return combine_path(path=self.engines_dir)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("-c", "--config",
                        help="Set path to config",
                        action="store",
                        default="",
                        dest="config")

    parser.add_argument('-m', "--mode",
                        help="Mode of work",
                        choices=[Mode.PROJECT, Mode.SPECIFIC],
                        default=Mode.PROJECT,
                        type=Mode,
                        dest="mode")

    parser.add_argument('-e', "--engine",
                        help="Engine version for mode=specific",
                        dest="engine_version")

    parser.add_argument('-p', "--plugins",
                        help="List of plugins for mode=specific",
                        dest="plugins")

    parser.add_argument("-s", "--engines-storage",
                        help="Path to storage with Engine",
                        type=Url,
                        dest="engines_storage")

    parser.add_argument("-u", "--plugins-storage",
                        help="Path to storage with Plugins",
                        type=Url,
                        dest="plugins_storage")

    sub_parser = parser.add_subparsers(dest="action", help="Commands")

    sub_parser.add_parser(Action.CHECK.value, help='Check & install Engine & Plugins.')
    sub_parser.add_parser(Action.REINSTALL.value, help='Force reinstall an Engine & Plugins.')
    sub_parser.add_parser(Action.VERIFY.value, help='Checking crc32 hash for installed engine')
    sub_parser.add_parser(Action.PROFILE.value, help='Select engine profile')

    args = parser.parse_args()
    args.action = Action(args.action if args.action else Action.CHECK)

    return args


def get_loader():
    tag = '!ENV'
    pattern = re.compile(r".*?\${(\w+)(:([^}]+)?)?}.*?")
    loader = yaml.SafeLoader
    loader.add_implicit_resolver(tag, pattern, None)

    def constructor_env_variables(in_loader, node):
        value = in_loader.construct_scalar(node)
        match = pattern.findall(value)
        if match:
            for g in match:
                value = value.replace(
                    f'${{{g[0]}{g[1]}}}', os.environ.get(g[0], g[2])
                )
        return value

    loader.add_constructor(tag, constructor_env_variables)
    return loader


def parse_config(path):
    loader = get_loader()
    with open(path) as conf_data:
        return yaml.load(conf_data, Loader=loader)


def load_default_config():
    loader = get_loader()
    data = pkgutil.get_data(__name__, DEFAULT_CONFIG_NAME)
    return yaml.load(data, Loader=loader)


def load_plugins_file() -> Dict[str, PluginConfig]:
    file_path = combine_path(PLUGINS_CONFIG)
    if not file_path.is_file():
        log.info(f"Plugins config file not founded: {file_path}")
        return dict()

    plugins = dict()

    with open(file_path) as conf_data:
        raw_config = yaml.load(conf_data, Loader=yaml.SafeLoader)

    log.info(f"Plugins config file founded: {file_path}")

    raw_plugins = raw_config['plugins']
    for name, value in raw_plugins.items():
        plugins[name] = PluginConfig(
            name=name,
            version=VersionSelector(value.get('version', '')),
        )

    return plugins


def get_plugins_configs(args) -> Tuple[bool, Dict[str, PluginConfig]]:
    plugins: Dict[str, PluginConfig] = {}
    error = False
    if args.plugins:
        log.info(f"Plugins specified by argument")
        for raw_plugin in args.plugins.split(","):
            plugin_data = raw_plugin.split("=")
            if len(plugin_data) == 0:
                log.warn(f"Empty plugin data")
                continue

            if len(plugin_data) > 2:
                log.error(f"Incorrect format. To many `=` in {raw_plugin}")
                error = True
                continue

            name = plugin_data[0]
            if not name:
                log.warn(f"Empty plugin name [{raw_plugin}]")
                continue

            plugins[plugin_data[0]] = PluginConfig(
                name=plugin_data,
                version=VersionSelector(plugin_data[1] if len(plugin_data) > 1 else ""),
            )
    else:
        plugins = load_plugins_file()

    return error, plugins


def build_config(args) -> Optional[Config]:
    raw_config = load_default_config()

    config_path = combine_path(args.config if args.config else DEFAULT_CONFIG_NAME)
    if config_path.is_file():
        config_file = parse_config(config_path)
        raw_config.update(config_file)
        log.info(f"Load config: {config_path}")

    err, plugins = get_plugins_configs(args)
    if err:
        return None

    config = Config(
        project_name=raw_config["project_name"],
        engines_dir=Path(raw_config["engines_dir"]),
        engines_cache=Path(raw_config["engines_cache"]),
        engines_storage=args.engines_storage if args.engines_storage else Url(raw_config["engines_storage"]),
        plugins_storage=args.plugins_storage if args.plugins_storage else Url(raw_config["plugins_storage"]),
        access_key=raw_config["access_key"],
        access_key_type=raw_config["access_key_type"],
        plugins_dir=Path(raw_config["plugins_dir"]),
        plugins=plugins,
        development_mode=True if raw_config.get("development_mode", 'False') == 'True' else False,
        plugins_dev_storage=Url(raw_config["plugins_dev_storage"]),
        log=LoggingConfig(
            level=raw_config["log"]["level"],
            host=raw_config["log"]["host"],
            port=int(raw_config["log"]["port"]),
        )
    )
    if config.plugins_dev_storage.type == UrlType.DriveLocation and not Path(config.plugins_dev_storage.location).is_absolute():
        config.plugins_dev_storage = config.plugins_storage.join(config.plugins_dev_storage.location)

    setup_logger(log, config)

    configs = "Configuration:"
    for param in dir(config):
        if not param.startswith('__') and not callable(getattr(config, param)) and param != "plugins":
            configs += f"\n  {param}: {getattr(config, param)}"
    log.info(configs)
    return config
