import os
import shutil
import platform
import glob
from os import path, walk
from pathlib import Path
from typing import List, Dict, Any

INI_BLACKLIST = ["DefaultEditor.ini", "DefaultPakFileRules.ini"]
PROJECT_NAME = "VSP"
BUILD_CONTENT_PATH = "Content/Paks"


class PathStr(str):
    def __new__(cls, value, resolve: bool = True) -> str:
        result = Path(super().__new__(cls, value))
        return result.resolve().as_posix() if resolve else result.as_posix()


class UnrealPacker:

    def __init__(self, project_dir, engine_dir):
        self.project_dir = PathStr(project_dir)
        if not path.exists(self.project_dir):
            raise BaseException(f"project_dir not found! '{self.project_dir}'")

        self.engine_dir = PathStr(engine_dir)
        if not path.exists(self.engine_dir):
            raise BaseException(f"engine_dir not found! '{self.engine_dir}'")

        if platform.system() == "Windows":
            os_subpath = "Win64"
        elif platform.system() == "Linux":
            os_subpath = "Linux"
        else:
            raise BaseException(f"'{platform.system()}' OS is not supported!")

        self.packer_path = PathStr(path.join(self.engine_dir, "Engine/Binaries", os_subpath, "UnrealPak"))
        packers = glob.glob(self.packer_path + ".*", recursive=False)
        if not len(packers):
            raise BaseException(f"packer_path not found by wildcard: '{self.packer_path}'")

        # Create and clear pak listing path
        self.pak_listing_path = PathStr(path.join(self.project_dir, "Saved", f"TmpConfigPatcher", "PakListing"))
        if not path.exists(self.pak_listing_path):
            os.makedirs(self.pak_listing_path)

        self.clear_folder(self.pak_listing_path)

    @staticmethod
    def clear_folder(folder: str):
        folder = PathStr(folder)
        if not path.exists(folder):
            return

        for filename in os.listdir(folder):
            file_path = os.path.join(folder, filename)
            try:
                if os.path.isfile(file_path) or os.path.islink(file_path):
                    os.unlink(file_path)
                elif os.path.isdir(file_path):
                    shutil.rmtree(file_path)
            except Exception as e:
                print('Failed to delete %s. Reason: %s' % (file_path, e))

    def package_all(self, pak_dest: str):
        import subprocess
        path_to_find = path.join(self.pak_listing_path, "**/*.txt")
        found_listing_files = glob.glob(path_to_find, recursive=True)

        for found_listing_file in found_listing_files:
            found_listing_file = PathStr(found_listing_file)
            found_file_name = path.basename(found_listing_file)
            file_name, file_ext = path.splitext(found_file_name)
            subdir = PathStr(path.dirname(found_listing_file.replace(self.pak_listing_path, "")), resolve=False)
            if subdir[0:1] == "/":
                subdir = subdir[1:]

            pak_full_path = PathStr(path.join(pak_dest, subdir, PROJECT_NAME, BUILD_CONTENT_PATH, file_name + ".pak"))

            if file_ext == ".txt":
                subprocess.run([self.packer_path,
                                pak_full_path,
                                f"-create={found_listing_file}",
                                f"-projectdir={self.project_dir}"])

    def gather_configs(self) -> Dict[str, str]:
        def gather(folder: str) -> Dict[str, str]:
            valid_files: Dict[str, str] = dict()
            for (gathered_root_path, gathered_dirs, gathered_files) in walk(folder):
                for gathered_file in gathered_files:
                    if gathered_file.startswith("Default") and gathered_file.endswith(".ini") \
                        and gathered_file not in INI_BLACKLIST:
                        file_to_pak = os.path.join(gathered_root_path, gathered_file).replace("\\", "/")
                        if file_to_pak.startswith(self.pak_listing_path):
                            file_dest = file_to_pak.replace(self.pak_listing_path,
                                                            '../../../' + PROJECT_NAME)
                        else:
                            file_dest = file_to_pak.replace(self.project_dir,
                                                            '../../../' + PROJECT_NAME)
                        valid_files[file_dest] = file_to_pak
                break
            return valid_files

        result = dict()

        result.update(gather(os.path.join(self.project_dir, "Config")))

        for (root_path, plugin_dirs, _) in walk(os.path.join(self.project_dir, "Plugins")):
            for plugin_dir in plugin_dirs:
                result.update(gather(os.path.join(root_path, plugin_dir, "Config")))
            break

        return result

    def create_pak_listing(self, files_to_pak: Dict[str, str], name: str):
        listing_file = PathStr(path.join(self.pak_listing_path, f"{name}.txt"))
        listing_path = os.path.dirname(listing_file)
        if not path.exists(listing_path):
            os.makedirs(listing_path)

        with open(listing_file, "w") as pak_listing:
            for destination_in_pak, file_to_pak in files_to_pak.items():
                pak_listing.write(f"\"{file_to_pak}\" \"{destination_in_pak}\"\n")
