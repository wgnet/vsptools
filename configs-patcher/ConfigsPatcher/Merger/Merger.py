# Merger interface and some related utils

import os
from typing import Any, Dict


class Merger:
    subclasses: Dict[str, Any] = {}
    # TODO: Move this variable to config file. For now it's good as it is - hardcoded or can be changed by function
    root_directory = os.path.realpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../../../"))

    def __init_subclass__(cls, extension="?") -> None:
        super().__init_subclass__()
        cls.subclasses[extension] = cls

    def __init__(self, base_path: str, patch_path: str) -> None:
        self._base_path = os.path.normpath(base_path)
        self._patch_path = os.path.normpath(patch_path)

        success, self._base_file = Merger.open_file(self._base_path, 'r+')
        if not success:
            raise Exception(self._base_file)

        success, self._patch_file = Merger.open_file(self._patch_path, 'r')
        if not success:
            raise Exception(self._patch_file)

    def __str__(self) -> str:
        return f"{__class__}: \"{self._base_path}\" with patch \"{self._patch_path}\"."

    # Wrapper for searching files in current or relative folder
    @classmethod
    def open_file(cls, file_path, mode) -> (bool, Any):
        if not os.path.exists(file_path):
            file_path = os.path.join(cls.root_directory, file_path)
        if not os.path.exists(file_path):
            raise Exception(f"File not found '{file_path}'!")

        try:
            return True, open(file_path, mode)
        except BaseException as instance:
            return False, f"Can't open file: '{file_path}'! {instance}"

    @classmethod
    def set_custom_root_directory(cls, custom_root_path: str):
        cls.root_directory = custom_root_path

    @classmethod
    def is_file_supported(cls, file_path: str) -> bool:
        _, extension = os.path.splitext(file_path)
        return extension in cls.subclasses

    @classmethod
    def is_extension_supported(cls, extension: str) -> bool:
        return extension in cls.subclasses

    @classmethod
    def merge(cls, base_path: str, patch_path: str) -> (bool, Any):
        _, base_ext = os.path.splitext(base_path)
        _, patch_ext = os.path.splitext(patch_path)

        if base_ext != patch_ext:
            raise Exception(f"Base file ({base_path}) and patch file ({patch_path}) have different extensions!")

        if not cls.is_extension_supported(base_ext):
            raise Exception(f"Got unsupported extension {base_ext} ({base_path})!")

        cls.subclasses[base_ext](base_path, patch_path).patch()

    @classmethod
    def get_merged_str(cls, base_path: str, patch_path: str) -> str:
        _, base_ext = os.path.splitext(base_path)
        _, patch_ext = os.path.splitext(patch_path)

        if base_ext != patch_ext:
            raise Exception(f"Base file ({base_path}) and patch file ({patch_path}) have different extensions!")

        if not cls.is_extension_supported(base_ext):
            raise Exception(f"Got unsupported extension {base_ext} ({base_path})!")

        return cls.subclasses[base_ext](base_path, patch_path).get_patched_as_str()

    # Patching of the provided file by the provided patch file
    def patch(self):
        base_string = self.get_patched_as_str()
        self._base_file.truncate(0)
        self._base_file.seek(0)
        self._base_file.write(base_string)

    # Prepare patching of the provided file by the provided patch file and returns patched base file as string
    def get_patched_as_str(self) -> str:
        pass
