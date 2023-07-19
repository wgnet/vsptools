# Merger realization for *.json files
import os

from Merger.Merger import Merger
import json


class MergerJSON(Merger, extension=".json"):

    # Patching of the provided file by the provided patch file
    def get_patched_as_str(self) -> str:
        patch_string = self._patch_file.read()
        if len(patch_string) < 2:
            raise Exception(f"Patch file is empty {self._patch_path}")

        base_string = self._base_file.read()
        if len(base_string) > 0:
            base_json = json.loads(base_string)
        else:
            base_json = {}

        patch_json = json.loads(patch_string)

        # Notes:
        # 1. Case-insensitive
        # 2. Completely rewrites any array with patched data
        base_json.update(patch_json)

        return json.dumps(base_json, indent=4)
