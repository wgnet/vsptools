#!/usr/bin/env python3

import argparse
import sys

import yaml

from versioner.component_versioner import get_components_versions
from versioner import logger
from versioner.version import get_version
from versioner.utils import VersionerIncorrectRepoPathError, VersionerUnknownReferenceError


def parse_args():
    parser = argparse.ArgumentParser()

    parser.add_argument("--components-config", default=None, dest="components_config", help="Components config yaml-file")
    parser.add_argument("--components-out-file", default=None, dest="components_out_file", help="Write components result to file")
    parser.add_argument("--components-include-merges", default=False, dest="components_include_merges", action="store_true",
                        help="Include merge commits in components versioning")

    parser.add_argument("-v", "--verbose", default=False, dest="verbose", action="store_true", help="Show debug output")
    parser.add_argument("-r", "--repo", default=".", dest="repo", help="Repository path")
    parser.add_argument("-b", "--bare", default=False, dest="bare", action="store_true",
                        help="Use local branches. For bare repo or on server without remote. If set, remote not used")
    parser.add_argument("--remote", default="origin", dest="remote", help="Remote name")
    parser.add_argument("-n", "--no-label", default=False, dest="no_label_mode", action="store_true",
                        help="No label mode - all version without label")
    parser.add_argument("--no-release-label", default=False, dest="no_release_label_mode", action="store_true",
                        help="No label for release branch")
    parser.add_argument("reference", default="HEAD", nargs='?', help="Git Reference")

    return parser.parse_args()


def main():
    args = parse_args()
    if args.verbose:
        logger.setLevel("DEBUG")

    version = get_version(args.reference, args.repo, args.bare, args.remote, args.no_release_label_mode)
    print(version.get_version(args.no_label_mode))

    if args.components_config is not None:
        components = get_components_versions(args.components_config, args.repo, args.reference, args.components_include_merges)
        if args.components_out_file is not None:
            with open(args.components_out_file, 'w') as outfile:
                yaml.dump(components, outfile)
        else:
            print(yaml.dump(components))


if __name__ == "__main__":
    try:
        main()
    except VersionerIncorrectRepoPathError as ex:
        logger.error(str(ex))
        sys.exit(100)
    except VersionerUnknownReferenceError as ex:
        logger.error(str(ex))
        sys.exit(110)
    except Exception:
        raise
