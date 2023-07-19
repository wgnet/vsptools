import datetime
import json
import logging
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from string import Template
from typing import List, Dict, Union

import configargparse

PACKAGE_NAME = "extractor"
DEFORMER_APP_NAME = "deformer"

log = logging.getLogger(PACKAGE_NAME)


def _parse_args() -> configargparse.Namespace:
    p = configargparse.ArgParser(default_config_files=[f"{PACKAGE_NAME}.conf"])

    p.add_argument("-c", "--config", is_config_file=True, help="config file path")

    p.add_argument("-v", "--engine_version", help="Engine version", required=True)
    p.add_argument("-ed", "--engines_dir", help="Target dir for engine")

    p.add_argument('-p', "--plugins", help="List of plugins for target program", dest="plugins")

    p.add_argument("-n", "--name", help="program name", required=True)
    p.add_argument("-t", "--type", default="Development", help="build type")
    p.add_argument("-id", "--identifier",
                   help="build identifier (e.g. version name) will be added at the end of packed filename "
                        "(it will add current date and time if not provided)")
    p.add_argument("-a", "--archive", help="build type", action="store_true")
    p.add_argument("-l", "--log-level",
                   default="INFO",
                   choices=["DEBUG", "INFO", "WARNING", "ERROR"],
                   help="log level")
    configs = p.parse_args()
    if configs.engines_dir:
        os.environ["DEFORMER_ENGINES_DIR"] = configs.engines_dir
    return configs


def copy_files(root: str, dst: str, engine_path: str, pattern: str):
    log.info(f"Copying '{engine_path}' with {pattern=}")
    for path in Path(root).joinpath(engine_path).rglob(pattern):
        dest_path: Path = Path(dst).joinpath(path.relative_to(root))
        log.debug(f"Copying {str(dest_path)}")
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        shutil.copy(path, dest_path)


def copy_dirs(root: str, dst: str, engine_path: str, dirs: List):
    log.info(f"Copying '{engine_path}'")
    for d in dirs:
        shutil.copytree(Path(root).joinpath(engine_path, d), Path(dst).joinpath(engine_path, d))


def apply_templates(src: str, dst: str, keywords: Dict):
    for template in os.listdir(src):
        if template.endswith(".template"):
            with open(template, "r") as t:
                src = Template(t.read())
                with open(Path(dst).joinpath(template[:-len(".template")]), "w") as b:
                    b.write(src.substitute(keywords))


def copy_dlls(dst: Union[str, Path]):
    [shutil.copy(Path("C:/Windows/System32/").joinpath(f), dst) for f in [
        "D3D12.dll",
        "D3DCompiler_43.dll",
        "dsound.dll",
        "glu32.dll",
        "msvcp140.dll",
        "opengl32.dll",
        "vulkan-1.dll",
        "vcruntime140.dll",
        "vcruntime140_1.dll",
        "X3DAudio1_7.dll",
        "XAPOFX1_5.dll",
        "XAudio2_7.dll",
        "xinput1_3.dll"
    ]]


def make_deformer_start_command(configs: configargparse.Namespace) -> str:
    command = f"{sys.executable} -m {DEFORMER_APP_NAME} -m specific -e {configs.engine_version}"
    if configs.plugins:
        command += f" -p {configs.plugins}"
    return command


def set_enabled_by_default_for_plugin(uplugin_file_path: str):
    KEY_ENABLED_BY_DEFAULT = "EnabledByDefault"
    if os.path.isfile(uplugin_file_path):
        uplugin_file = open(uplugin_file_path)
        json_str = uplugin_file.read()
        plugin_params = json.loads(json_str)
        plugin_params[KEY_ENABLED_BY_DEFAULT] = True
        with open(uplugin_file_path, "w") as fp:
            json.dump(plugin_params, fp)


def postprocessing(app_name: str, target_dir: str):
    if app_name.lower() == "UnrealInsights".lower():
        uplugin_path = "Engine/Plugins/Deformer/VSPPerfCollector/VSPPerfCollector.uplugin"
        set_enabled_by_default_for_plugin(str(Path(target_dir).joinpath(uplugin_path).absolute()))


def main() -> int:
    configs = _parse_args()

    log_level = logging.getLevelName(configs.log_level)
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(f"{PACKAGE_NAME}.log"),
            logging.StreamHandler()
        ]
    )
    log.info(f"Deformer started...")
    deformer_start_command = make_deformer_start_command(configs)
    result = subprocess.run(deformer_start_command,
                            shell=True,
                            stdout=subprocess.PIPE,
                            encoding="utf-8")

    if result.returncode != 0:
        log.error(f"Error when the application Deformer is running. returncode == {result.returncode}")
        return result.returncode

    configs.type = configs.type.capitalize()
    if configs.type in ["Debug", "Shipping", "Test"]:
        build_type_str = f"-Win64-{configs.type}"
    else:
        build_type_str = ""

    start = time.time()

    dst = f"{configs.name}-{configs.type}-"
    dst += configs.identifier if configs.identifier else f"{datetime.datetime.now().strftime('%Y.%m.%d-%H.%M.%S')}"

    os.makedirs(Path(dst).joinpath("Engine/Binaries/Win64"), exist_ok=True)

    root = os.sep.join([configs.engines_dir, configs.engine_version])

    copy_dirs(
        root,
        dst,
        "Engine/Binaries/ThirdParty",
        [
            "DbgHelp",
            "NVIDIA",
            "Oculus",
            "Ogg",
            "OpenVR",
            "PhysX3",
            "Vorbis",
            "Windows",
        ])

    copy_dirs(
        root,
        dst,
        "Engine/Content",
        [
            "Animation",
            # 'ArtTools',
            # 'BasicShapes',
            "Certificates",
            "Editor",
            # 'EditorBlueprintResources',
            # 'EditorLandscapeResources',
            # 'EditorMaterials',
            # 'EditorMeshes',
            # 'EditorResources',
            "EngineDamageTypes",
            # 'EngineDebugMaterials',
            "EngineFonts",
            # 'EngineMaterials',
            # 'EngineMeshes',
            # 'EngineResources',
            # 'EngineSky',
            # 'EngineSounds',
            # 'Functions',
            "Internationalization",
            "Maps",
            "Slate",
            "SlateDebug",
            "Splash",
            # 'Tutorial',
            # 'VREditor'
        ])

    # we don't need anything except English
    copy_dirs(root, dst, "Engine/Content/Localization/Category", ["en"])
    copy_dirs(root, dst, "Engine/Content/Localization/Editor", ["en"])
    copy_dirs(root, dst, "Engine/Content/Localization/EditorTutorials", ["en"])
    copy_dirs(root, dst, "Engine/Content/Localization/Engine", ["en"])
    copy_dirs(root, dst, "Engine/Content/Localization/Keywords", ["en"])
    copy_dirs(root, dst, "Engine/Content/Localization/PropertyNames", ["en"])
    copy_dirs(root, dst, "Engine/Content/Localization/ToolTips", ["en"])

    # won't run without this
    copy_files(root, dst, "Engine/Plugins", "*.uplugin")
    if configs.name.lower() == "UnrealInsights".lower():
        copy_files(root, dst, "Engine/Plugins/Developer/VisualStudioSourceCodeAccess/Binaries", "*.*")
        copy_files(root, dst, "Engine/Plugins/Deformer/VSPPerfCollector/Binaries", "*.*")
        # perfcollector configuration files
        copy_dirs(root, dst, "Engine/Plugins/Deformer/VSPPerfCollector", ["Config"])

    copy_dirs(root, dst, "Engine", ["Shaders"])

    copy_files(root, dst, "Engine/Binaries/Win64", f"{configs.name}{build_type_str}.*")
    for extension in ["dll", "pdb"]:
        copy_files(root, dst, "Engine/Binaries/Win64", f"{configs.name}-*{build_type_str}.{extension}")

    copy_dirs(root, dst, "Engine", ["Config"])

    apply_templates(".", dst, {"program": f"{configs.name}{build_type_str}.exe"})

    if configs.archive:
        log.info(f"Making an archive: {dst}")
        shutil.make_archive(dst, "zip", dst)

    try:
        copy_dlls(Path(dst).joinpath("Engine/Binaries/Win64"))
    except FileNotFoundError as e:
        log.error(f"{e}")
        return 1

    postprocessing(configs.name, dst)

    end = time.time()
    log.info(f"Completed in: {end - start}s")

    return 0


if __name__ == "__main__":
    exit(main())
