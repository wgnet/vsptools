from typing import Dict, List
import yaml
from pydantic import BaseModel

from versioner import logger
from versioner.version import get_version
from versioner.utils import get_git, get_ref_sha


class ConfigData(BaseModel):

    class ComponentConfigData(BaseModel):
        source: List[str] = []
        dependencies: List[str] = []

    version: str = None
    components: Dict[str, ComponentConfigData] = {}


def load_config(config_path: str) -> ConfigData:
    with open(config_path) as config_file:
        config_data = yaml.load(config_file, Loader=yaml.SafeLoader)
    return ConfigData(**config_data)


def get_components_versions(config_path: str, repo_path: str = '.', ref: str = "HEAD", include_merges: bool = False)\
        -> Dict[str, Dict[str, str]]:

    components = {}
    config = load_config(config_path)
    git = get_git(repo_path)
    get_ref_sha(git, ref)
    logger.debug(f"Components version: {config_path}")

    for name, params in config.components.items():
        logger.debug(f"  {name} : {params.source}")
        logger.debug(f"    paths:")
        kparams = {
            "max_count": "1",
            "pretty": "format:%H",
        }
        if include_merges:
            kparams["full_history"] = True

        component_sha = git.log(ref, "--", *params.source, **kparams)

        logger.debug(f"    component_sha: {component_sha}")

        component_version = get_version(reference=component_sha, repo=repo_path).get_version(no_label=True)

        logger.debug(f"    version: {component_version}")
        components[name] = {"version": component_version, "sha": component_sha}

    return components
