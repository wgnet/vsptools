# Configs Patcher

The script is designed to apply patches to settings files.
Currently works with `*.ini` and `*.json` files.
#### Important features:
##### `*.ini`
* Preserves the structure and order of the categories of the base file
* Saves comments in the base file
##### `*.json`
* Keys **are case-sensitive**
* Completely replaces the array of the base file with the array from the patch

## Installation

### Python requirements

You need to apply requirements from `requirements.txt `by using command `python -m pip install -r requirements.txt `

### Script settings file format

This is a JSON file with three levels of nesting objects (you can specify any names for profiles and types in lowercase):

* **_1 nesting level** (specified by the parameters: `--profile=development` or `-p=production`)
* Initially implies a build profile, for example: `development` or `prodaction`
* **_2 nesting level** (specified by the parameters: `--type=server` or `-t=client`)
* Initially implies a more specific type of assembly, for example: `server` or `client`
* **_3 nesting level** (this data array is always processed completely)
* An array of objects with data for patching. Each element of this array is a JSON object with two fields:
* base_path: path to the file to which the patch will be applied
* patch_path: path to the patch file

## Startup Parameters

#### `--help` (`-h`)
Shows help for all commands. You can also use `patch -h` to get detailed information on the selected mod (for example, `patch`)

### Logging modes

#### `--quite` (`-q`)
Runs the program in "quiet" mode. So only error information is written to the log.
> * Takes precedence over `--verbose`
> * Sets the minimum logging level to `warning`

#### `--verbose` (`-v')
Starts the program in the "detailed logs" mode.
>Sets the minimum logging level to `debug`

### Operating modes

#### `patch`
Basic file paging mode

#### `copy_patched`
The mode in which the packages of the base files are copied to the directory specified in the `--copy_path` parameter

#### `copy_patched_pak`
The mode in which a new package with patched configs is created and copied to the directory specified in the `--copy_path` parameter

### Common params

#### `--profile` (`-p`)
Sets the "profile" of the selected array of settings in JSON. (_1 level of nesting)
> In the `patch` mode is **mandatory**
* Examples: `development', `steam`.
* Important: In JSON, types must be written in lowercase (there is no such restriction for launch parameters)

#### `--type` (`-t`)
Sets the "type" of the selected array of settings in JSON. (_2 nesting level)
> In the `patch` mode is **mandatory**
* Example of types: `server', `shipping_client'.
* Important: In JSON, types must be written in lowercase (there is no such restriction for launch parameters)

#### `--copy_path` (`-cp`)
Sets the path where the patched files will be saved.
> The unique parameter of the `copy_patched` and `copy_patched_pak` modes is **mandatory**
>
#### `--engine_path` (`-ep`)
Sets the path to the engine (needed to work with UnrealPack)
> Unique parameter of the `copy_patched_pak` mode, is **mandatory**

#### `--copy_flat` (`-cf`)
The mode in which the patched files will be copied directly to the folder `{copy_path}/{profile}/{type}/`, regardless of which paths they were located before (additionally: removes the “Default” prefix from the patched file)
> The unique parameter of the `copy_patched` mode

#### `--root_directory` (`-rd`)
Sets the directory where the base files and patch files will be searched (if they are not specified by absolute paths).

#### `--recursive_paths` (`-rp`)
Enables recursive search of script settings files if a path is passed to the `paths` parameter.
If the parameter is not passed, the script will search for the script settings only in the specified folder.

#### `[paths]`

You can specify as many JSON files of settings as you want, for this you need to write their paths as parameters at startup.
If you run without parameters, by default it looks for settings in the file `configs\EnvironmentConfigs.json`
Paths can be specified both absolute and relative to the game's root directory file, or relative to the specified `-rd` / `--root_directory`

Examples:
* `python ConfigsPatcher.py`
* Only the default script setting `configs\EnvironmentConfigs' will be used.json`
* `python ConfigsPatcher.py "configs/MyFile.json"`
* Only the script configuration specified in the parameter `"configs/MyFile will be used.json"`
* `python ConfigsPatcher.py "../../..configs/MyFile.json" "C:/configs/MyFile.json"`
* Only the settings specified in the script settings `"../../..configs/MyFile will be used.json" "C:/configs/MyFile.json"`