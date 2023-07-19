#!/usr/bin/env python3

import datetime
import json
import os
from pathlib import Path
from typing import Optional, Dict

from .config import Action, Mode, build_config, Config, parse_args
from .engine import collect_engines_data, install_engine, EngineInfo, engine_crc_compare
from .engine_components import set_engine_profile
from .logger import log
from .plugins import install_plugins
from .utils import write_metafile, combine_path, get_metafile_path, InstallationStatus


def get_project_engine_version(config: Config) -> Optional[str]:
    project_path = combine_path(Path(f"{config.project_name}.uproject"))

    try:
        with open(project_path) as project_file:
            project_data = json.load(project_file)
    except OSError as e:
        log.error(f"Project file not exist: {project_path} - {e}")
        return None
    except json.JSONDecodeError as e:
        log.error(f"Project file can't be parsed: {project_path} - {e}")
        return None

    engine_version = project_data.get("EngineAssociation", None)
    if engine_version is None:
        log.error(f"Engine version not found in project file {project_path}.")
    return engine_version


def check_mode_specific_args(engine_version: Optional[str]) -> Optional[str]:
    if engine_version is None:
        log.error(f"Engine version not specified. For mode `specific` use argument '--engine' for specify version.")
    return engine_version


def main() -> int:
    start_time = datetime.datetime.now()
    args = parse_args()

    log.info(f"Action: {args.action}")
    config = build_config(args)

    if not config:
        return 2

    # TODO: In the future remove the OS check
    if os.name == 'nt':
        engines = collect_engines_data()
        msg = f"Found {len(engines)} engines in Register:"
        for _, engine in engines.items():
            msg += f"\n  {engine.name}: {engine.path} - Installation status={engine.status.value}"
        log.info(msg)
    else:
        engines: Dict[str, EngineInfo] = {}

    if args.mode == Mode.PROJECT:
        engine_version = get_project_engine_version(config)
    else:
        engine_version = check_mode_specific_args(args.engine_version)

    if engine_version is None:
        return 1

    log.info(f"Project {config.project_name} use UE4 version `{engine_version}`")

    if args.action == Action.VERIFY:
        if engine_crc_compare(engine_version, config):
            log.info('Engine files successfully validated.')
            return 0
        else:
            log.error('Engine files failed to validate.')
            return 1

    if args.action == Action.PROFILE:
        set_engine_profile(engine_version, config)
        return 0

    force_install = args.action == Action.REINSTALL
    if os.name == 'nt':
        need_install = False

        if engine_version not in engines:
            log.warn(f"UE4 version `{engine_version}` not found.")
            need_install = True

        elif engines[engine_version].status != InstallationStatus.SUCCESS:
            log.warning(f"Installation was not finished properly. Engine re-install required")
            force_install = True

        if need_install or force_install:
            log.info(f"Installation UE4 version `{engine_version}` started")

            if not install_engine(engine_version, config, force_install):
                return 1

            log.info("Engine installation succeeded")

            engines[engine_version] = collect_engines_data()[engine_version]  # TODO - add method for collect data about 1 engine
        else:
            log.info(f"UE4 version `{engine_version}` exist")
        engine = engines[engine_version]
    else:
        engine_path = config.engines_dir / engine_version
        metafile_path = get_metafile_path(engine_path)
        engine = EngineInfo(name=engine_version,
                            path=engine_path,
                            status=InstallationStatus.SUCCESS,
                            metafile_path=metafile_path)

    write_metafile(engine.metafile_path, date=datetime.date.today().isoformat())

    log.info("Check plugins")
    res = install_plugins(force_install, config, engine)
    log.info(f"Work time: {datetime.datetime.now() - start_time}")
    return 0 if res else 1
