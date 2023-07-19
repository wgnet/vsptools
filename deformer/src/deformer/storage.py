import functools
import os
import sys
from pathlib import Path
import re
import shutil
from abc import ABC, abstractmethod
from typing import List

import requests
from tqdm.auto import tqdm

from .utils import (
    Url,
    UrlType,
    get_archive_crc,
    get_sha1,
    TQDM_BAR_FORMAT,
)
from .logger import log


class BuildStorage(ABC):
    location: Url
    key: str
    _is_correct: bool = False

    def __init__(self, location: Url, key: str = None, key_type: str = None):
        self.location = location
        self.key = key
        self.key_type = key_type

    def is_correct(self):
        return self._is_correct

    @abstractmethod
    def get_files_list(self, additional_path: str = None) -> List[str]:
        raise NotImplementedError()

    @abstractmethod
    def download_file_to(self, destination: Path) -> bool:
        raise NotImplementedError()


class ArtifactoryStorage(BuildStorage):
    _ARTIFACTORY_REG = re.compile(r"/artifactory/([a-zA-Z0-9.\-_]+)/?([a-zA-Z0-9.\-_/]*)")

    host: str
    repo_name: str
    plugins_folder: str

    def __init__(self, location: Url, key: str = None, key_type: str = None):
        super().__init__(location, key, key_type)
        if location.type != UrlType.WebLocation:
            return

        match = re.match(self._ARTIFACTORY_REG, location.info.path)
        if match:
            self._is_correct = True
            self.scheme = location.info.scheme
            self.host = location.info.netloc
            self.repo_name, self.plugins_folder = match.groups()

    def __get_headers(self):
        headers = {}
        if self.key:
            if self.key_type == "token":
                headers['Authorization'] = f'Bearer {self.key}'
            elif self.key_type == "apikey":
                headers['X-JFrog-Art-Api'] = f'{self.key}'
            # TODO add support login+pass
        return headers

    def get_files_list(self, additional_path: str = None) -> List[str]:
        results = set()
        url = f"{self.scheme}://{self.host}/artifactory/api/search/aql"
        path = self.plugins_folder + ('/' + additional_path if additional_path else '')
        post_text = 'items.find({ "repo": { "$eq": "' + self.repo_name + '" }, "path": { "$eq": "' + path + '" } })'
        if self.scheme == "https":  # NOTE: hack to detect artifactory v6 ()
            post_text += '.transitive()'  # NOTE: work only artifactory 7.15+
        try:
            response = requests.post(url, headers=self.__get_headers(), data=post_text.encode('utf-8'))
            json_data = response.json()
            for json_result in json_data.get('results', []):
                results.add(json_result['name'])
        except requests.exceptions.RequestException as e:
            log.warning(f'HTTP request failed with exception {e}')

        return list(results)

    def download_file_to(self, destination: Path) -> bool:

        destination = destination.expanduser().resolve()
        if destination.is_dir():
            log.error(f"  Incorrect destination {destination}. Remove this directory end repeat again.")
            return False

        result = False
        try:
            destination_hash = get_sha1(destination)
            url = self.location.location
            response = requests.get(url, headers=self.__get_headers(), stream=True, allow_redirects=True)
            if response.status_code == 200:
                source_hash = response.headers.get('X-Checksum-Sha1', '')

                if source_hash == destination_hash:
                    log.info(f"  Artifact `{destination.name}` exist in cache")
                    result = True
                else:
                    file_size = int(response.headers.get('Content-Length', 0))
                    destination.expanduser().resolve()
                    destination.parent.mkdir(parents=True, exist_ok=True)

                    response.raw.read = functools.partial(response.raw.read, decode_content=True)
                    with tqdm.wrapattr(response.raw,
                                       "read",
                                       total=file_size,
                                       desc=f"  Downloading {destination.name}",
                                       bar_format=TQDM_BAR_FORMAT,
                                       file=sys.stdout,
                                       ) as r_raw:
                        with destination.open("wb") as f:
                            shutil.copyfileobj(r_raw, f)
                    result = True
            else:
                log.warning(f'  Failed to get build from Artifactory - error {response.status_code}')
            response.close()
        except requests.exceptions.RequestException as e:
            log.warning(f'  HTTP request failed with exception {e}')
        except OSError as e:
            log.warning(f'  File open failed with exception {e}')
        return result


class NetDriveStorage(BuildStorage):

    path: Path

    def __init__(self, location: Url, key: str = None, key_type: str = None):
        super().__init__(location, key, key_type)
        if location.type != UrlType.DriveLocation:
            return

        self.path = Path(self.location.location)
        if self.path.is_absolute() and self.path.is_dir():
            self._is_correct = True

    def get_files_list(self, additional_path: str = None) -> List[str]:
        result = []
        if self.is_correct():
            search_path = self.path / (additional_path if additional_path else "")
            for file_name in os.listdir(search_path):
                if (search_path / file_name).is_file():
                    result.append(file_name)
        return result

    def download_file_to(self, destination: Path) -> bool:
        if destination.is_dir():
            log.error(f"  Incorrect destination {destination}. Remove this directory end repeat again.")
            return False

        if not self.path.is_file():
            log.error(f"  Artifact '{destination}' does not exist in storage")
            return False

        log.info(f"  Compare checksum")
        source_crc = get_archive_crc(self.path)
        destination_crc = get_archive_crc(destination)

        if any([
                not destination.exists(),
                source_crc != destination_crc,
        ]):
            log.info(f"  Start download `{self.path}` to `{destination}`")
            with self.path.open("rb") as read_file:
                with tqdm.wrapattr(read_file, "read",
                                   total=self.path.stat().st_size,
                                   desc=f"  Downloading {destination.name}",
                                   bar_format=TQDM_BAR_FORMAT,
                                   file=sys.stdout,
                                   ) as tqdm_reader:
                    with destination.open("wb") as write_file:
                        shutil.copyfileobj(tqdm_reader, write_file)
            res = source_crc == get_archive_crc(destination)
            return res
        else:
            log.info(f"  Artifact `{self.path.name}` exist in cache")
            return True


def get_storage(location: Url, key: str, key_type: str) -> BuildStorage:
    plugin_storage = ArtifactoryStorage(location, key, key_type)
    if location.type == UrlType.WebLocation and plugin_storage.is_correct():
        return plugin_storage
    elif location.type == UrlType.DriveLocation and Path(location.location).is_absolute():
        return NetDriveStorage(location)
    else:
        storage_error_name = f"Unsupported storage {location.location}"
        log.error(storage_error_name)
        raise NotImplementedError(storage_error_name)
