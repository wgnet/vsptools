#!/usr/bin/env python3

import argparse
import json
import logging
import os
import platform
from typing import Any, List, Dict, Tuple

from UnrealPacker.UnrealPacker import UnrealPacker, PROJECT_NAME

from Merger.Merger import Merger as IMerger
import Merger.MergerINI  # Hook up *.ini support
import Merger.MergerJSON  # Hook up *.json support

# Globals

FILE_DIRECTORY = os.path.dirname(os.path.abspath(__file__))
PAKCHUNK_PREFIX = 'pakchunk3'

# Logger

log_formatter = logging.Formatter("[%(asctime)s][%(levelname)s]: %(message)s")
console_handler = logging.StreamHandler()
console_handler.setFormatter(log_formatter)
logger = logging.getLogger("ConfigsPatcher")
logger.addHandler(console_handler)
logger.setLevel("INFO")


def arg_parse():
    # Top-level parser
    parser = argparse.ArgumentParser(prog='ConfigPatcher.py')

    # Add base arguments
    parser.add_argument('-q', '--quite', dest='quite', default=False, action='store_true', help='Suppress logging')
    parser.add_argument('-v', '--verbose', dest='verbose', default=False, action='store_true',
                        help='Print all information (include debug)')

    # Subparsers

    subparsers = parser.add_subparsers(help='Patching modes')

    # 'patch' mod parser
    parser_patch = subparsers.add_parser('patch', help='Patching base files with theirs patches')
    parser_patch.set_defaults(func=patch)
    parser_patch.add_argument('-p', '--profile', dest='profile', required=True,
                              help='Determines profile of config to be patched. E.g.: "development", "steam"')
    parser_patch.add_argument('-t', '--type', dest='type', required=True,
                              help='Determines type of profile\'s config to be patched. E.g.: "server", "client_shipping"')

    # 'copy_patched' mod parser
    parser_copy = subparsers.add_parser('copy_patched', help='Copying patched copies of base files to provided path')
    parser_copy.set_defaults(func=copy_patched)
    parser_copy.add_argument('-cp', '--copy_path', dest='copy_path', required=True,
                             help='Set path to save patched files')
    parser_copy.add_argument('-cf', '--copy_flat', dest='copy_flat', default=False, action='store_true',
                             help="Copies all patched files into '{copy_path}/{profile}/{type}/' folder (also removes “Default” at the beginning of a word)")
    parser_copy.add_argument('-p', '--profile', dest='profile', default='',
                             help='Determines profile of config to be patched. E.g.: "development", "steam"')
    parser_copy.add_argument('-t', '--type', dest='type', default='',
                             help='Determines type of profile\'s config to be patched. E.g.: "server", "client"')

    # 'copy_patched_pak' mod parser
    parser_copy = subparsers.add_parser('copy_patched_pak',
                                        help='Copying patched copies of base files to provided path')
    parser_copy.set_defaults(func=copy_patched_pak)
    parser_copy.add_argument('-cp', '--copy_path', dest='copy_path', required=True,
                             help='Set path to save patched files')
    parser_copy.add_argument('-ep', '--engine_path', dest='engine_path', required=True,
                             help='Set path to the engine')
    parser_copy.add_argument('-p', '--profile', dest='profile', default='',
                             help='Determines profile of config to be patched. E.g.: "development", "steam"')
    parser_copy.add_argument('-t', '--type', dest='type', default='',
                             help='Determines type of profile\'s config to be patched. E.g.: "server", "client"')
    parser_copy.add_argument('-ap', '--always_pak_profile', type=str, dest='always_pak_profile',
                             help='Collect config files even if there are no patches. Required --type.')
    parser_copy.add_argument('-df', '--delete_files', dest='delete_files', default=False, action='store_true',
                             help='Delete default config files from game repository. Needed for creating packchunk withot config files.')

    # Add non-unique arguments to all subparsers
    handled_subparsers = []  # Aliases guard
    for subparser in subparsers.choices.values():
        if subparser not in handled_subparsers:
            handled_subparsers.append(subparser)
        else:
            continue

        subparser.add_argument('-rd', '--root_directory', dest='root_directory', default='',
                               help='Set custom root directory for base and patch files')
        subparser.add_argument('-rp', '--recursive_paths', dest="recursive_paths", default=False, action='store_true',
                               help='Script will scan files in paths down recursively instead of scanning only provided directory')
        subparser.add_argument('paths', nargs='*', help="TODO")

    args = parser.parse_args()
    return args


def set_logger_level(verbose, quite):
    if quite:
        logger.setLevel("WARNING")
    elif verbose:
        logger.setLevel("DEBUG")


# Apply configs from provided args
def init_configs(args):
    set_logger_level(args.verbose, args.quite)

    if "root_directory" in args and len(args.root_directory):
        IMerger.set_custom_root_directory(args.root_directory)


# Try to catch .json files from provided paths or add one default path
def get_env_configs_from_paths(paths: list, recursive_paths):
    env_configs_files = []
    if not len(paths):
        return [os.path.join(FILE_DIRECTORY, 'configs', 'EnvironmentConfigs.json')]

    for path in paths:
        if os.path.isfile(path):
            if path.endswith(".json"):
                env_configs_files.append(path)

        elif os.path.isdir(path):
            for inner_path_name in os.listdir(path=path):
                inner_path = os.path.join(path, inner_path_name)
                if os.path.isfile(inner_path):
                    env_configs_files.extend(get_env_configs_from_paths([inner_path], recursive_paths))  # Recursion

                elif recursive_paths and os.path.isdir(inner_path):
                    env_configs_files.extend(get_env_configs_from_paths([inner_path], recursive_paths))  # Recursion

    return env_configs_files


def default(args):
    logger.warning(
        f"No patching modes provided! Available modes: 'patch' / 'copy_patched' / 'copy_patched_pak'. Run with -h or --help for help. Current {args}")


def get_package_name(target):
    if target.lower() == "server":
        package_postfix = "Server"
    else:
        package_postfix = "NoEditor"

    return f"{PAKCHUNK_PREFIX}-{platform.system()}{package_postfix}"


# Patching base files with related patches
def patch(args):
    for env_configs_path in get_env_configs_from_paths(args.paths, args.recursive_paths):
        with open(env_configs_path) as env_configs_file:
            try:
                env_configs = json.load(env_configs_file)
            except BaseException as e:
                logger.warning(f"JSON error: Invalid json or empty settings file: {env_configs_path}. // {e}")
                continue

            profile_lower = args.profile.lower()
            if profile_lower not in env_configs:
                logger.warning(f"There are no '{profile_lower}' profile in {env_configs_path}")
                continue

            type_lower = args.type.lower()
            if type_lower not in env_configs[profile_lower]:
                logger.warning(
                    f"There are no '{type_lower}' type under '{profile_lower}' profile in {env_configs_path}")
                continue

            logger.info(f"Applying settings from '{env_configs_path}'")

            for config in env_configs[profile_lower][type_lower]:
                logger.debug(f'Processing: {config["base_path"]}')
                try:
                    IMerger.merge(config['base_path'], config['patch_path'])
                except BaseException as e:
                    logger.warning(f"Merger errors: {e.args}")
                else:
                    logger.debug('Succeed.')


# Copying patched copies of base files to provided path
def copy_patched(args):
    for env_configs_path in get_env_configs_from_paths(args.paths, args.recursive_paths):
        with open(env_configs_path) as env_configs_file:
            try:
                env_configs = json.load(env_configs_file)
            except BaseException as e:
                logger.warning(f"JSON error: Invalid json or empty settings file: {env_configs_path}. // {e}")
                return

            profiles = {}
            profile_lower = args.profile.lower()
            if len(profile_lower):
                if profile_lower not in env_configs:
                    logger.warning(f'There are no configs for {profile_lower} profile')
                    return
                profiles[profile_lower] = env_configs[profile_lower]
            else:
                profiles = dict(env_configs)

            filtered_types = {}
            type_lower = args.type.lower()
            if len(type_lower):
                for profile_name in profiles:
                    for type_name in profiles[profile_name]:
                        if type_lower == type_name:
                            filtered_types[f"{profile_name}/{type_name}"] = profiles[profile_name][type_name]
            else:
                for profile_name in profiles:
                    for type_name in profiles[profile_name]:
                        filtered_types[f"{profile_name}/{type_name}"] = profiles[profile_name][type_name]

            logger.info(f"Applying settings from '{env_configs_path}'")

            for type_specifier, patch_items in filtered_types.items():
                for patch_item in patch_items:
                    logger.debug(f"Processing: {os.path.join(type_specifier, patch_item['base_path'])}")
                    try:
                        new_path = os.path.join(args.copy_path, type_specifier)
                        if args.copy_flat:
                            file_basename = os.path.basename(patch_item['base_path'])
                            if file_basename.startswith("Default"):
                                file_basename = file_basename[7:]
                            new_path = os.path.join(new_path, file_basename)
                        else:
                            new_path = os.path.join(new_path, patch_item['base_path'])

                        new_dir = os.path.dirname(new_path)
                        if not os.path.exists(new_dir):
                            os.makedirs(new_dir)

                        with open(new_path, mode='w') as new_file:
                            new_file.write(IMerger.get_merged_str(patch_item['base_path'],
                                                                  patch_item['patch_path']))
                    except BaseException as e:
                        logger.warning(f"Merger errors: {e.args}")
                    else:
                        logger.debug('Succeed.')


# Copying patched copies of base files to provided path
def copy_patched_pak(args):
    for env_configs_path in get_env_configs_from_paths(args.paths, args.recursive_paths):
        with open(env_configs_path) as env_configs_file:
            try:
                env_configs = json.load(env_configs_file)
            except BaseException as e:
                logger.warning(f"JSON error: Invalid json or empty settings file: {env_configs_path}. // {e}")
                return

            profiles = {}
            profile_lower = args.profile.lower()
            if len(profile_lower):
                if profile_lower not in env_configs:
                    logger.warning(f'There are no configs for {profile_lower} profile')
                    return
                profiles[profile_lower] = env_configs[profile_lower]
            else:
                profiles = dict(env_configs)

            filtered_types: Dict[str, Dict[str, List[Any]]] = dict()
            type_lower = args.type.lower()
            if len(type_lower):
                for profile_name in profiles:
                    for type_name in profiles[profile_name]:
                        if type_lower == type_name:
                            for type_inst in profiles[profile_name][type_name]:
                                if profile_name not in filtered_types:
                                    filtered_types[profile_name] = {type_name: [type_inst]}
                                elif type_name not in filtered_types[profile_name]:
                                    filtered_types[profile_name][type_name] = [type_inst]
                                else:
                                    filtered_types[profile_name][type_name].append(type_inst)
            else:
                for profile_name in profiles:
                    for type_name in profiles[profile_name]:
                        for type_inst in profiles[profile_name][type_name]:
                            if profile_name not in filtered_types:
                                filtered_types[profile_name] = {type_name: [type_inst]}
                            elif type_name not in filtered_types[profile_name]:
                                filtered_types[profile_name][type_name] = [type_inst]
                            else:
                                filtered_types[profile_name][type_name].append(type_inst)

            logger.info(f"Applying settings from '{env_configs_path}'")

            up = UnrealPacker(os.path.join(FILE_DIRECTORY, "../../../"), args.engine_path)

            patched_path = os.path.join(up.pak_listing_path, "../Patched")
            up.clear_folder(patched_path)

            for filtered_profile_name, filtered_profile_value in filtered_types.items():
                for filtered_type_name, filtered_data in filtered_profile_value.items():

                    config_files = up.gather_configs()

                    for exact_patch in filtered_data:
                        logger.debug(
                            f"Processing: {os.path.join(filtered_profile_name, filtered_type_name, exact_patch['base_path'])}")
                        try:
                            new_path = os.path.join(patched_path, filtered_profile_name, filtered_type_name)
                            new_path = os.path.join(new_path, exact_patch['base_path'])

                            new_dir = os.path.dirname(new_path)
                            if not os.path.exists(new_dir):
                                os.makedirs(new_dir)

                            with open(new_path, mode='w') as new_file:
                                new_file.write(IMerger.get_merged_str(exact_patch['base_path'],
                                                                      exact_patch['patch_path']))
                        except BaseException as e:
                            logger.warning(f"Merger errors: {e.args}")
                        else:
                            logger.debug('Succeed.')

                            file_name = os.path.basename(new_path).lower()

                            for destination_in_pak, file_to_pak in config_files.items():
                                if os.path.basename(file_to_pak).lower() == file_name:
                                    config_files[destination_in_pak] = os.path.normpath(new_path)
                                    break

                    up.create_pak_listing(config_files,
                                          os.path.join(filtered_profile_name,
                                                       filtered_type_name,
                                                       get_package_name(filtered_type_name)))
            if args.always_pak_profile and not os.path.exists(
                os.path.join(args.copy_path, args.always_pak_profile, args.type)):
                config_files = up.gather_configs()
                up.create_pak_listing(config_files,
                                      os.path.join(args.always_pak_profile, args.type, get_package_name(args.type)))

    up.package_all(args.copy_path)

    if args.delete_files:
        try:
            for rel_path, abs_path in config_files.items():
                os.remove(abs_path)
        except OSError as e:
            logger.error(f"Delete error: {e}")
            exit(1)


def main():
    args = arg_parse()

    init_configs(args)

    if "always_pak_profile" in args and args.always_pak_profile and ("type" not in args or not args.type):
        logger.error('Argument "always_pak_profile" required "type". Please specify argument "type".')
        exit(1)

    logger.debug(f"Starting with {args}")

    if "func" in args:
        args.func(args)
    else:
        default(args)

    logger.info("I'm done with this!..")


# Entry point
if __name__ == "__main__":
    exit(main())
