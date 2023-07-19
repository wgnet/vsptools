import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field

from enum import Enum
from pathlib import Path
import urllib.parse
from tqdm.auto import tqdm

from .logger import log

DEFORMER_METAFILE = 'deformer_engine_metafile.json'
EMPTY_FOLDER_CRC = '00000000'

TQDM_BAR_FORMAT = '{l_bar}{bar:25}{r_bar}{bar:-10b}'

RE_7Z_INFO = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2} .{5}\s+([0-9]+)\s+([0-9]+)\s+(.*)$", flags=re.M)
RE_7Z_EXTRACT = re.compile(r"([0-9]+)%\s+([0-9]+) - .*")
R_7Z_KEYWORD = "Extracting archive: "

FILTERS_FOR_7Z = ' '.join(
    [
        '-xr!*.pdb',
        '-xr!Content',
        '-xr!Saved',
        '-xr!Deformer',
        '-xr!EditorRuns',
        '-xr!__pycache__',
        '-xr!Definitions.*',
    ]
)


class InstallationStatus(Enum):
    SUCCESS = 'success'
    FAILED = 'failed'
    IN_PROGRESS = 'in progress'
    UNKNOWN = 'unknown'


class UrlType(Enum):
    DriveLocation = 0
    WebLocation = 1


class Url:
    location: str
    type: UrlType
    info: urllib.parse.ParseResult

    def __init__(self, location: str = ""):
        self.location = location
        self.info = urllib.parse.urlparse(location)
        if self.info and self.info.scheme in ("http", "https"):
            self.type = UrlType.WebLocation
        else:
            self.type = UrlType.DriveLocation

    def join(self, path: str) -> 'Url':
        if self.type == UrlType.DriveLocation:
            return Url(str(Path(self.location) / path))
        else:
            return Url(f"{self.location}/{path}")

    def __str__(self):
        return self.location

    def __repr__(self):
        return f"<{self.location}>"


def combine_path(file: Path = None, path: Path = None, work_dir: Path = None) -> Path:
    result = path if path is not None else Path()
    if file is not None:
        result = result / file
    if work_dir is not None and not result.is_absolute():
        result = (work_dir / result).absolute()
    return result


def unpack_7zip(source: Path, destination: Path) -> int:
    info = subprocess.check_output(["7z", "l", "-ba", source], text=True).strip()
    file_info = RE_7Z_INFO.findall(info)
    file_components = {name: int(uncompressed) for (uncompressed, compressed, name) in file_info}
    total = sum(file_components.values())
    cmd = f'7z x -y -bso0 -bsp1 "{source}" -o"{destination}"'

    process = subprocess.Popen(
        cmd,
        bufsize=1,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=True,
        encoding='utf-8',
        text=True)

    with tqdm(total=total,
              desc=f"  Unzip {source.name}",
              bar_format=TQDM_BAR_FORMAT,
              unit="B",
              file=sys.stdout,
              unit_scale=True) as tqdm_counter:
        last_value = 0
        try:
            while process.poll() is None:
                try:
                    l_raw = process.stdout.readline()
                except IOError:
                    break
                ln = l_raw.strip()
                re_match = RE_7Z_EXTRACT.match(ln)
                if re_match:
                    new_value = int(int(re_match[1]) * 0.01 * total)
                    tqdm_counter.update(new_value - last_value)
                    last_value = new_value
                time.sleep(0.1)
            tqdm_counter.update(total - last_value)
        except KeyboardInterrupt:
            process.communicate()
            process.kill()
            log.warning("Installation canceled")
    return process.returncode


def remove_dir(path: Path) -> bool:
    files = []
    for dir_path, dir_names, filenames in os.walk(path.resolve()):
        for file in filenames:
            files.append(Path(dir_path) / file)
    res = True
    with tqdm(files,
              desc=f"  Deleting {path.name}",
              bar_format=TQDM_BAR_FORMAT,
              file=sys.stdout,
              ) as tqdm_rm:
        for file in tqdm_rm:
            try:
                file.unlink(missing_ok=True)
            except OSError as e:
                log.error(f"Can't remove file {file}: - {e}")
                res = False
    try:
        shutil.rmtree(path)
    except OSError as e:
        log.error(f"Can't remove folder {path}: - {e}")
        res = False
    return res


def get_sha1(file_in: Path) -> str:
    hasher = hashlib.sha1()
    if file_in.is_file():
        with open(file_in, 'rb') as read_file:
            with tqdm.wrapattr(read_file, "read",
                               total=file_in.stat().st_size,
                               desc=f"  Calculate Sha1 {file_in.name}",
                               bar_format=TQDM_BAR_FORMAT,
                               file=sys.stdout,
                               ) as tqdm_reader:
                while True:
                    chunk = tqdm_reader.read(1024 * 1024)
                    if not chunk:
                        break
                    hasher.update(chunk)
    return hasher.hexdigest()


def get_archive_crc(archive_path: Path) -> str:
    list_archive = subprocess.getoutput(f'7z l {FILTERS_FOR_7Z} -ba -slt "{archive_path}"')
    list_archive_split = list_archive.split('\n')
    hex_sum = "0"
    for line in list_archive_split:
        if line.startswith('CRC = '):
            line = line.replace('CRC = ', '')
            if line != '':
                hex_sum = hex(int(hex_sum, 16) + int(line, 16))
    return hex_sum[-8:].upper()


def get_folder_crc(folder_path: Path) -> str:
    crc_folder = subprocess.getoutput(f'7z h {FILTERS_FOR_7Z} "{folder_path}"')
    a = re.findall(r'CRC32\s+for\s+data:\s*(\w+)', crc_folder)
    return a[0]


def get_folder_engine_crc(folder_path: Path) -> str:
    log.info('Validating engine files...')
    crc_folder = subprocess.getoutput(
        f'7z h -x!{DEFORMER_METAFILE} {FILTERS_FOR_7Z} "{folder_path}/*"')
    log.info('Validation completed.')
    a = re.findall(r'CRC32 for data:\s*(\w+)', crc_folder)
    if a[0] == EMPTY_FOLDER_CRC:
        log.warning('Engine folder is empty')
    return a[0]


def get_metadata_file_path() -> Path:
    user_home = Path(os.getenv('USERPROFILE') if os.name == 'nt' else "~")
    return user_home / '.deformer-config'


def write_metafile(metafile_path: Path, **kwargs) -> None:
    if metafile_path.exists():
        with open(metafile_path, 'r') as read_file:
            metadata = json.load(read_file)
    else:
        metadata = {}

    metadata = {**metadata, **kwargs}

    metafile_path.parent.mkdir(parents=True, exist_ok=True)

    with open(metafile_path, 'w') as write_file:
        json.dump(metadata, write_file, indent=4)


def get_engine_installation_status(path: Path) -> InstallationStatus:
    if path.exists():
        with open(path) as file:
            json_data: dict = json.load(file)
            return InstallationStatus(json_data.get('InstallationStatus', InstallationStatus.SUCCESS))
    else:
        return InstallationStatus.UNKNOWN


def get_metafile_path(path_to_engine_dir: Path) -> Path:
    return path_to_engine_dir / Path(DEFORMER_METAFILE)


@dataclass
class Version:
    major: int = 0
    minor: int = 0
    patch: int = 0
    details: str = ""

    def __init__(self, version: str = None):
        if not version:
            version = "0"
        version = str(version)
        parts = version.split('.', maxsplit=4)
        self.major = int(parts[0])
        self.minor = int(parts[1]) if len(parts) > 1 else 0
        self.patch = int(parts[2]) if len(parts) > 2 else 0
        self.details = parts[3] if len(parts) > 3 else ""

    def __str__(self):
        version = ""
        if self.major >= 0:
            version += f'v{self.major}'
            if self.minor >= 0:
                version += f'.{self.minor}'
                if self.patch >= 0:
                    version += f'.{self.patch}'
                if self.details != "":
                    version += f'.{self.details}'
        else:
            version = "Version unknown"
        return version

    def __eq__(self, other):
        if self.major != other.major \
                or self.minor != other.minor \
                or self.patch != other.patch \
                or self.details != other.details:
            return False
        return True

    def __gt__(self, other):
        if self.major < other.major:
            return False
        if self.major > other.major:
            return True

        if self.minor < other.minor:
            return False
        if self.minor > other.minor:
            return True

        if self.patch < other.patch:
            return False
        if self.patch > other.patch:
            return True

        if self.details < other.details:
            return False
        if self.details > other.details:
            return True
        return False

    def __ge__(self, other):
        if self.major < other.major:
            return False
        if self.major > other.major:
            return True

        if self.minor < other.minor:
            return False
        if self.minor > other.minor:
            return True

        if self.patch < other.patch:
            return False
        if self.patch > other.patch:
            return True

        if self.details < other.details:
            return False
        if self.details >= other.details:
            return True
        return False

    def __lt__(self, other):
        return not (self > other)


@dataclass
class VersionSelector:
    major: int = -1
    minor: int = -1
    patch: int = -1
    details: str = '-1'

    def __init__(self, version: str = ""):
        version = str(version if version else "-1")
        parts = version.split('.', maxsplit=4)
        self.major = int(parts[0]) if len(parts) > 0 else -1
        self.minor = int(parts[1]) if len(parts) > 1 else -1
        self.patch = int(parts[2]) if len(parts) > 2 else -1
        self.details = parts[3] if len(parts) > 3 else '-1'

    def __str__(self):
        return f"vs<{self.major if self.major >= 0 else '*'}" \
               f".{self.minor if self.minor >= 0 else '*'}" \
               f".{self.patch if self.patch >= 0 else '*'}" \
               f".{self.details if self.details != '-1' else '*'}>"

    def check(self, version: Version) -> bool:
        if self.major < 0:
            return True
        if self.major != version.major:
            return False
        if self.minor < 0:
            return True
        if self.minor != version.minor:
            return False
        if self.patch < 0:
            return True
        if self.patch != version.patch:
            return False
        if self.details == '-1':
            return True
        if self.details != self.details:
            return False
        return True


@dataclass
class ArtifactInfo:
    name: str
    location: Url = Url("")
    file_name: str = ""
    version: Version = field(default_factory=Version)

    def exist(self) -> bool:
        return self.location.location != ""
