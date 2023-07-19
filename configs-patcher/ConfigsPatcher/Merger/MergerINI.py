# Merger realization for *.ini files

import configparser
from collections import defaultdict
from typing import Dict, List, Tuple, Optional, MutableMapping, Iterator

from .Merger import Merger


class INICategoriesHolder(MutableMapping):
    KeyValue = Tuple[str, Optional[str]]
    _data: Dict[str, List[KeyValue]]

    def __init__(self) -> None:
        self._data = defaultdict()
        super().__init__()

    def set(self, category: str, key: str, value: Optional[str] = None):
        if not key:
            return

        key = key.rstrip()
        value = value.rstrip() if value is not None else None

        if category not in self._data:
            self._data[category] = [(key, value)]
            return

        if key.strip().startswith(("+", "-", "!")):
            self._data[category].append((key, value))
            return

        index = self._find_key_index(category, key)
        if index is None:
            self._data[category].append((key, value))
        else:
            self._data[category][index] = (key, value)

    def _find_key_index(self, category: str, key: str) -> Optional[int]:
        for i, (line_key, line_value) in enumerate(self._data[category]):
            if key == line_key:
                return i
        return None

    def __getitem__(self, item: str) -> List[KeyValue]:
        return self._data[item]

    def __setitem__(self, key: str, value: List[KeyValue]):
        self._data[key] = value

    def __contains__(self, item: str) -> bool:
        return item in self._data

    def __iter__(self) -> Iterator[Tuple[str, List[KeyValue]]]:
        return self._data.items().__iter__()

    def __len__(self) -> int:
        return len(self._data)

    def __delitem__(self, key: str):
        del self._data[key]


class MergerINI(Merger, extension=".ini"):

    # Patching of the provided file by the provided patch file
    def get_patched_as_str(self) -> str:
        config_patch = configparser.ConfigParser(strict=False)
        config_patch.optionxform = str  # to enable CaseSensitivity
        config_patch.read_file(self._patch_file)
        if not len(config_patch.sections()):
            raise Exception(f"Patch file is empty ({self._patch_path})")

        full_data = INICategoriesHolder()
        category = ""
        for line in self._base_file:
            if line.startswith('['):
                category = line[1:line.find(']')]
                continue

            line_stripped = line.strip()
            if not line_stripped or line_stripped.startswith(("\n", "\r\n")):
                continue
            if line_stripped.startswith(";"):
                full_data.set(category, line)
                continue

            values = line.split('=', 1)
            if len(values) == 2:
                full_data.set(category, values[0], values[1])
                continue

            full_data.set(category, line)

        for category in config_patch.sections():
            if len(config_patch.items(category)):
                for missing in config_patch[category]:
                    full_data.set(category, missing, config_patch[category][missing])

        result = ""
        for category, lines in full_data:
            result += f"[{category}]\n"
            result += "\n".join([f"{key + '=' + value if value is not None else key}" for key, value in lines])
            result += "\n\n"

        return result
