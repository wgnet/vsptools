#!/usr/bin/env python
import argparse
import glob
import json
import logging
import os
import shutil
import sys
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from functools import reduce
from subprocess import Popen, PIPE

# from pyteamcity import TeamCity # NOTE: optionally import only for `get` command


class SpecialChar:
    END = '\x1b[0m'
    RED = '\x1b[91m'
    GREEN = '\x1b[92m'
    YELLOW = '\x1b[93m'
    BLUE = '\x1b[94m'


def add_color(msg, color):
    return "{}{}{}".format(color, msg, SpecialChar.END)


def make_git_sha(sha):
    if isinstance(sha, GitSha):
        return GitSha(sha.sha, sha.aliases, sha.info)
    return GitSha(sha, [])


def get_host_platform():
    return "Win64" if os.name == "nt" else "Linux"


class GitSha(object):
    def __init__(self, sha, aliases, info=None):
        self.sha = sha
        self.aliases = aliases
        self.info = info

    def __repr__(self):
        return "<GitSha: {}>".format(self.sha)


class Git(object):
    def __init__(self, git_path):
        self.git = git_path

    def git_clean(self, include_path, exclude_paths_list, wc_root):
        exclude = ""
        if exclude_paths_list:
            exclude = "-e " + " -e ".join(exclude_paths_list)
        cmd = "clean -x -f -d {} {}".format(exclude, include_path)
        output, _, _ = self.execute_git(cmd, cwd=wc_root)
        logging.debug(output)

    def get_sha_info(self, sha, cwd):
        git_log_params = {
            "Author": "%an %ae",
            "Commit Date": "%ai",
            "Title": "%f",
            "SHA": "%h",
        }
        # Author: %an %ae%nSHA: %h%nDate : %ai %nTitle: %f
        git_log_format = reduce(lambda result, kv: result + "{}: {}%n".format(kv[0], kv[1]),
                                iter(git_log_params.items()), "")
        command = 'log -n1 "--pretty=format:{}" {}'.format(git_log_format, sha)
        stdout, _, _ = self.execute_git(command, cwd=cwd)
        info = stdout.strip().split("\n")
        return info

    def execute_git(self, command, *args, **kwargs):
        cmd = "{} {}".format(self.git, command)
        return execute(cmd, *args, **kwargs)


class GitLog(object):
    def __init__(self, git_path, cwd, start_commit="HEAD", slice_size=10):
        self.git = Git(git_path)
        self.cwd = cwd
        self._start_commit = start_commit
        self._slice_size = slice_size

        self._on_master = False
        self._current_index = 0
        self._master_commit = ""
        self.reset()

    def reset(self):
        self._on_master = False
        self._current_index = 0
        self._master_commit = self._get_base_in_master()
        if self._master_commit == self._start_commit:
            self._on_master = True

    def _get_base_in_master(self):
        command = "merge-base remotes/origin/master {}".format(self._start_commit)
        stdout, _, _ = self.git.execute_git(command, cwd=self.cwd)
        return stdout.strip()

    def get_next_commits(self):
        from_commit = self._start_commit
        to_commit = self._master_commit
        if self._on_master:
            from_commit = self._master_commit
            to_commit = ""

        commits_list = self._get_commits_range(from_commit,
                                               to_commit,
                                               self._current_index,
                                               self._slice_size)

        if len(commits_list) < self._slice_size and not self._on_master:
            self._on_master = True
            self._current_index = 0
        else:
            self._current_index += self._slice_size

        commits_with_aliases = self._add_aliases_for_commits(commits_list, self._slice_size)
        return commits_with_aliases

    def _get_commits_range(self, from_commit, to_commit, index, count, use_fp=False):
        commit_range = from_commit
        if to_commit:
            commit_range = "{}..{}".format(to_commit, from_commit)
        command = "log --skip {} -n {} {} --pretty=format:%H {}".format(index,
                                                                        count,
                                                                        "--first-parent" if use_fp else "",
                                                                        commit_range)
        stdout, _, _ = self.git.execute_git(command, cwd=self.cwd)
        commits = stdout.strip().splitlines()
        return commits

    def _add_aliases_for_commits(self, commits_list, slice_size):
        commits_aliases = []
        for i in range(0, len(commits_list), slice_size):
            chunk = commits_list[i:i + slice_size]
            aliases = self._get_commits_aliases(chunk)
            for sha, alias in zip(chunk, aliases):
                commits_aliases.append(GitSha(sha=sha, aliases=[sha, alias]))
        return commits_aliases

    def _get_commits_aliases(self, commit_list):
        commit_list = ['"%s^{tree}"' % x for x in commit_list]
        command = "rev-parse %s" % ' '.join(commit_list)
        stdout, _, _ = self.git.execute_git(command, cwd=self.cwd)
        tree_list = stdout.strip().splitlines()
        return tree_list


class Profile:
    config_name = 'gitArtifactsProfile.json'

    def __init__(self, profile, git_root):
        self.profile = profile
        self.gitroot = git_root
        self.full_config_path = os.path.abspath(os.path.join(self.gitroot, self.config_name))

    def read_local_profile(self):
        return load_json(self.full_config_path)

    def save_local_profile(self):
        data = {'profiles': self.profile}
        save_config(self.full_config_path, data)

    def get_local_profile(self):
        data = self.read_local_profile()
        return data.get('profiles')


class Project:
    def __init__(self, config):
        self.name = config.get("name")
        self.id = config.get("id")
        self.wc_root = config.get("wc_root")
        self.git = Git(config.get("git_path"))
        self.repo_url = config.get("repo_url")
        self.storage_pattern = config.get("storage_pattern")
        self.artifacts_pattern = config.get("artifacts_pattern")
        self.alias_suffix = config.get("alias_suffix")
        self.cache_path = config.get("cache_path")
        self.config = config.get("config")
        self.clean_build = config.get("clean_build")
        self.smart_clean_cache = config.get("smart_clean_cache")
        self.force_download = config.get("force_download")
        self.force_install = config.get("force_install")
        self.installed = config.get("installed")
        self.downloaded = config.get("downloaded")
        self.build_info = None
        self.build_path = None
        self.platform = get_host_platform()

    def __str__(self):
        return self.name

    def __repr__(self):
        return self.id

    def get_artifact_pattern(self, is_alias=False):
        return self.storage_pattern + self.artifacts_pattern + (self.alias_suffix if is_alias else "")

    def make_build_path(self, version):
        params = {
            "server_url": self.repo_url,
            "project": self.id,
            "build_id": version,
            "platform": self.platform,
        }
        path = self.get_artifact_pattern().format(**params)
        return path

    def make_alias_build_path(self, version):
        params = {
            "server_url": self.repo_url,
            "project": self.id,
            "build_id": version,
            "platform": self.platform,
        }
        path = self.get_artifact_pattern(True).format(**params)
        return path

    def get_build_info(self):

        content_list = []
        info = self.build_info['sha_details']
        sha = self.build_info['sha']
        info.append("Artifact name: {}-{}.zip".format(self.id, sha))
        content_list.append(pretty_logger("Build info:", level=0))
        for line in info:
            args = line.split(": ")
            args[0] = args[0] + ": "
            content_list.append(pretty_logger("{:<15} {}".format(*args), level=1))
        return "\n".join(content_list)

    def build_exists(self, git_sha):
        sha = make_git_sha(git_sha)
        commit = sha.sha
        aliases = sha.aliases
        aliases = list(map(self.make_alias_build_path, aliases))

        path = self.make_build_path(commit)
        path = check_build_path(path)
        if path:
            return path

        for alias in aliases:
            commit = check_alias_path(alias)
            if not commit:
                continue
            path = self.make_build_path(commit)
            path = check_build_path(path)
            if path:
                return path
        return False

    def download_file(self, url, dest):
        local_filename = url.split('/')[-1]
        local_filename = os.path.join(dest, local_filename)
        if os.path.isfile(local_filename) and not self.force_download:
            logging.info(pretty_logger("Build already downloaded", level=0, color=SpecialChar.BLUE))
            return local_filename
        if not os.path.isdir(dest):
            os.makedirs(dest)
        logging.info(pretty_logger("Downloading build...", level=0, color=SpecialChar.YELLOW))
        r = urllib.request.urlopen(url)
        with open(local_filename, 'wb') as f:
            while True:
                chunk = r.read(1024)
                if not chunk:
                    break
                f.write(chunk)
        logging.info(pretty_logger("Build downloaded", level=0, color=SpecialChar.GREEN))
        return local_filename

    def clean_paths(self):
        logging.debug(pretty_logger("Installed build cleaning:", level=0))
        clean_paths = self.config.get("clean_paths")
        exclude_paths = self.config.get("clean_exclude_paths", [])
        if not clean_paths:
            return
        if self.clean_build:
            exclude_paths = []
        for clean_path in clean_paths:
            for path in glob.glob(clean_path):
                logging.debug(pretty_logger("Remove: {}".format(path), level=1))
                self.git.git_clean(path, exclude_paths, self.wc_root)

    def clean_builds_cache(self, installed_build, cache_path):
        logging.debug(pretty_logger("Smart cache cleaning:", level=0))
        all_builds = os.listdir(cache_path)
        installed_build_basename = os.path.basename(installed_build)
        all_builds = [build for build in all_builds if build.startswith(self.id) and build != installed_build_basename]
        for build in all_builds:
            logging.debug(pretty_logger("Remove: {}".format(build), level=1))
            os.remove(os.path.join(cache_path, build))

    def install_build(self, build_path):
        unpack(build_path, self.wc_root)

    def get_artifact(self):
        if not self.build_path:
            logging.error(pretty_logger("Artifacts not found", level=0, color=SpecialChar.RED))
            return False

        success = True
        config_path = os.path.join(sys.path[0], "gitArtifacts.json")
        local_config = load_json(config_path)
        project_config = local_config.get(self.id, {})

        downloaded_file = self.download_file(self.build_path, self.cache_path)
        if project_config.get("installed_build") != downloaded_file or self.force_install:
            logging.info(pretty_logger("Installing build...", level=0, color=SpecialChar.YELLOW))
            self.clean_paths()
            self.install_build(downloaded_file)
            logging.info(pretty_logger("Build installed", level=0, color=SpecialChar.GREEN))
        else:
            logging.info(pretty_logger("Build already installed", level=0, color=SpecialChar.BLUE))
        if self.smart_clean_cache:
            self.clean_builds_cache(downloaded_file, self.cache_path)
        project_config["installed_build"] = downloaded_file
        local_config[self.id] = project_config
        save_config(config_path, local_config)
        return success


def parse_args(default_action):
    parser = argparse.ArgumentParser()
    parser.add_argument("-v", "--verbose", help="verbose (debug) logging", action="store_const", const=logging.DEBUG,
                        dest="logLevel")

    sub_parser = parser.add_subparsers(dest="action", help="Commands")
    get_parser = sub_parser.add_parser("get", help="Get Artifacts")
    make_parser = sub_parser.add_parser("make", help="Make Artifacts")

    get_parser.add_argument("-i", "--interactive", help="Enables Interactive mode where you can select wanted options",
                            action='store_true', default=False,
                            dest="interactive")
    get_parser.add_argument("--clean-cache", help="cleanup local binaries cache", action='store_true', default=False,
                            dest="clean_cache")
    get_parser.add_argument("--smart-clean-cache", help="cleanup local binaries cache excluding the installed builds",
                            action='store_true', default=False,
                            dest="smart_clean_cache")
    get_parser.add_argument("--clean-build", help="cleanup installed binaries builds without excludes", action='store_true',
                            default=False,
                            dest="clean_build")
    get_parser.add_argument("--force-download", help="force download binaries", action='store_true', default=False,
                            dest="force_download")
    get_parser.add_argument("--force-install", help="force install binaries", action='store_true', default=False,
                            dest="force_install")
    get_parser.add_argument("--setup", help="configure mode", action='store_true', default=False, dest="setup")
    get_parser.add_argument("--git-path", help="Git executable path", action='store', default='git', dest="git_path")
    get_parser.add_argument("-p", "--project", help="Custom project", action='append', default=None, dest="project")
    get_parser.add_argument("--set-profile", help="Profile id", action='append', default=[], dest="profile")
    get_parser.add_argument("--reset-profile", help="Reset local profile config", action='store_true', default=False,
                            dest="profile_reset")
    get_parser.add_argument("--list-profiles", help="List profiles", action='store_true', default=False, dest="profile_list")
    get_parser.add_argument("--list-projects", help="List project", action='store_true', default=False, dest="project_list")
    get_parser.add_argument("--ignore-processing-builds", help="Ignore builds with running or queued status",
                            action='store_true',
                            default=False, dest="ignore_processing_builds")

    make_parser.add_argument("--artifacts-dir", default=os.environ.get("ARTIFACTS_DIR", None),
                             help="Where to put artifacts archive")
    make_parser.add_argument("--artifacts-ver", default=os.environ.get("ARTIFACTS_VER", "0000000000"), help="Artifacts version")
    make_parser.add_argument("--version-aliases", default=os.environ.get("ARTIFACTS_ALIASES", ""),
                             help="Artifacts version aliases")
    make_parser.add_argument("--custom-project", default=os.environ.get("GIT_ARTIFACTS_CUSTOM_PROJECT", ""),
                             help="Custom project to make artifacts archive")

    arguments, _ = parser.parse_known_args()
    if not arguments.action:
        arguments.action = default_action
        if default_action == "get":
            arguments, _ = get_parser.parse_known_args(namespace=arguments)
        else:
            arguments, _ = make_parser.parse_known_args(namespace=arguments)
    return arguments


def check_build_status(commit_sha) -> int:
    from pyteamcity import TeamCity
    tc = TeamCity('VSP-tc-user', 'VSP-tc-user', 'VSP-teamcity-01', 8111)
    target_build_type = f"VSP_Project_Game_DevelopmentEditor{get_host_platform()}"

    def get_revision_builds(state):
        state = f"state:{state}," if state else ""
        info_revision = tc._get_all_builds_locator(locator=f'{state}revision:{commit_sha},hanging:false,lookupLimit:10000')
        return info_revision['build']

    for build_info in get_revision_builds("queued"):  # ready
        build_type = build_info['buildTypeId']
        if build_type == target_build_type:
            logging.error(
                pretty_logger(
                    f"\nBuild is {build_info['state']}. Please run get_binaries.bat later. "
                    f"Or check teamcity: {build_info['webUrl']}",
                    level=0,
                    color=SpecialChar.RED
                )
            )
            return 100

    for build_info in get_revision_builds("running"):
        build_type = build_info['buildTypeId']
        if build_type == target_build_type:
            logging.error(
                pretty_logger(
                    f"\nBuild is {build_info['state']}, {build_info['percentageComplete']}% complited. "
                    f"Please run get_binaries.bat later. Or check teamcity: {build_info['webUrl']}",
                    level=0,
                    color=SpecialChar.RED
                )
            )
            return 200

    failed_build_types = {"FAILURE": "FAILURE",
                          "UNKNOWN": "CANCELED"}
    for build_info in get_revision_builds(""):
        build_type = build_info['buildTypeId']
        build_status = build_info['status']
        if build_status in failed_build_types and build_type == target_build_type:
            logging.warning(
                pretty_logger(
                    f"Warning! Build is {failed_build_types[build_status]}.  №{build_info['number']}: {build_info['webUrl']}",
                    level=0,
                    color=SpecialChar.YELLOW
                )
            )
    return 0


def find_build(project_list, wc_root, git_path, ignore_processing_builds):
    logging.debug("find_build: {}, {}, {}".format(project_list, wc_root, git_path))
    history_deep = 400  # Commits history limit
    chunk_size = 10
    i = 0
    commit_count = 0

    git_log = GitLog(git_path, wc_root, slice_size=chunk_size)
    while (i < history_deep) and [x for x in project_list if not x.build_info]:
        commits_list = git_log.get_next_commits()
        for commit in commits_list:
            for project in [x for x in project_list if not x.build_info]:
                path = project.build_exists(commit)

                if path:
                    project.build_path = path
                    project.build_info = {
                        'sha': commit.sha,
                        'commits_checked': commit_count,
                        'sha_details': Git(git_path).get_sha_info(commit.sha, wc_root),
                    }
            write_to_one_line(
                pretty_logger("Commits checked: ({}/{})\n".format(commit_count, history_deep * chunk_size), level=0))

            build_status = check_build_status(commit.sha)

            if build_status and ignore_processing_builds:
                logging.info(pretty_logger(
                    "Found build which satisfy requirements, processing build will be ignored",
                    level=0,
                    color=SpecialChar.YELLOW
                ))
                break

            elif build_status and not ignore_processing_builds:
                logging.info(pretty_logger(
                    "Found build which satisfy requirements, but another build in progress, exit",
                    level=0,
                    color=SpecialChar.YELLOW
                ))
                exit(build_status)

            commit_count += 1
            logging.debug("")
            if all([x.build_info for x in project_list]):
                break
            i += 1
    logging.info("")


def execute(command, *args, **kwargs):
    cwd = kwargs.pop("cwd", None)
    failonerror = kwargs.pop("failonerror", False)
    logging.debug(pretty_logger("Run: " + command, level=1))
    proc = Popen(command, stdout=PIPE, stderr=PIPE, shell=True, cwd=cwd, *args, **kwargs)
    stdout, stderr = proc.communicate()
    stdout, stderr = stdout.decode("utf-8"), stderr.decode("utf-8")
    returncode = proc.returncode
    if returncode != 0 and failonerror:
        logging.error(stderr + stdout)
        raise Exception("Execute {} failed".format(command))
    # logging.debug(stdout)
    return stdout, stderr, returncode


def load_json(path):
    data = {}
    if os.path.isfile(path):
        with open(path, "r") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                logging.warning(
                    pretty_logger(
                        f"WARNING: Failed to load JSON {path}",
                        level=0,
                        color=SpecialChar.YELLOW
                    )
                )
    return data


def save_config(path, data):
    with open(path, "w") as f:
        json.dump(data, f, sort_keys=True, indent=4)


def url_exists(url):
    try:
        r = urllib.request.urlopen(urllib.request.Request(url))
        if r.getcode() == 200:
            return True
    except:
        return False
    return False


def read_alias_content(url):
    try:
        r = urllib.request.urlopen(urllib.request.Request(url))
        if r.getcode() == 200:
            return r.read()
    except:
        return False
    return False


def check_build_path(path):
    logging.debug(pretty_logger("Check {}".format(path), level=0))
    if url_exists(path):
        return path
    return False


def check_alias_path(alias):
    logging.debug(pretty_logger("Check {}".format(alias), level=0))
    sha = read_alias_content(alias)
    if sha:
        return sha
    return False


def unpack(path, dest):
    logging.debug(pretty_logger("Unpack {} to {}".format(path, dest), level=0))

    try:
        z = zipfile.ZipFile(path, "r")
        z.extractall(path=dest)
    except zipfile.BadZipfile as e:
        logging.error(pretty_logger("Errors happened while unpacking", level=0, color=SpecialChar.RED))
        logging.error(pretty_logger("Bad archive was downloaded. Removing it.", level=0, color=SpecialChar.RED))
        os.remove(path)
        logging.error(pretty_logger("" + str(e), level=0, color=SpecialChar.RED))
        exit(1)
    except IOError as e:
        logging.error(pretty_logger("Errors happened while unpacking", level=0, color=SpecialChar.RED))
        logging.error(pretty_logger("Check running tools in working copy", level=0, color=SpecialChar.RED))
        logging.error(pretty_logger("" + str(e), level=0, color=SpecialChar.RED))
        exit(1)


def write_to_one_line(string):
    sys.stdout.write("\r" + string)
    sys.stdout.flush()


def pretty_logger(string, level=0, color=None):
    levels = ["{:<5}", "{:<10}", "{:<15}", "{:<20}"]
    formatter = levels[level]
    formatter = formatter.format("")
    if color is not None:
        string = add_color(string, color)
    return formatter + string


def interactive(args, projects):
    def ask_question(question):
        enable_list = ["Y", "YES"]
        disable = ["N", "NO"]
        value = None
        # return choose in enable_list
        while True:
            try:
                value = str(input(pretty_logger(question, level=1))).upper()
                if value not in enable_list + disable:
                    logging.info(pretty_logger("Please choose the correct option.", level=2))
                    logging.info(pretty_logger("Correct options: {}".format(",".join(enable_list + disable)), level=2))
                    continue
            except Exception as e:
                logging.error(e)
                logging.info(pretty_logger("Please choose the correct option", level=2))
                continue
            else:
                break
        return value in enable_list

    logging.info("Interactive mode")
    logging.info("Choose the option you want")
    logging.info("Press y + Enter if you want choose option")
    if ask_question("Enable custom mode (Y/N): "):
        if ask_question("Enable force downloading (Y/N): "):
            args.force_download = True
        if ask_question("Enable force installing (Y/N): "):
            args.force_install = True
        if ask_question("Enable cleanup artifacts cache (Y/N): "):
            args.clean_cache = True
        if ask_question("Enable smart cleanup artifacts cache (Y/N): "):
            args.smart_clean_cache = True
        if ask_question("Enable force cleanup for installed artifact builds (Y/N): "):
            args.clean_build = True
        if ask_question("Reset profile config (Y/N): "):
            args.profile_reset = True
        if ask_question("Ignore processing builds (Y/N): "):
            args.ignore_processing_builds = True
        if ask_question("Do you want to choose custom projects?: "):
            project_ids = [x["id"] for x in projects]
            logging.info(pretty_logger("Enter comma separated projects list:", level=2))
            for idx, val in enumerate(project_ids):
                logging.info(pretty_logger("[{}] {}".format(idx, val), level=2))
            choose = str(input(pretty_logger("You choose: ", level=2))).split(",")
            choose = [x for x in choose if x.isdigit()]
            choose = [int(x) for x in choose]
            choose = [x for x in choose if x < len(project_ids)]

            args.project = []
            for idx in choose:
                args.project.append(project_ids[idx])
            if not args.project:
                logging.info(pretty_logger("Failed to select a suitable option, default settings will be used", level=1))
                args.project = project_ids
            logging.info(pretty_logger("Your selected projects: {}".format(" ".join(args.project)), level=1))
    return args


def get_param(param_name, config):
    value = config[param_name]
    value = os.environ.get(param_name, value)
    return value


def get_profile(args, git_root):
    profile = Profile(args.profile, git_root)
    local_profile = profile.get_local_profile()
    if local_profile:
        profile.profile = local_profile
    if args.profile:
        profile.profile = args.profile
    if args.profile_reset:
        profile.profile = ['default']
    if not profile.profile:
        logging.info("Profile config not found")
        profile.profile = ['default']
    profile.save_local_profile()
    return list(set(profile.get_local_profile()))


def filter_projects_by_profiles(profiles, config):
    uniq_project_ids = []
    for profile in profiles:
        uniq_project_ids += config["profiles"][profile]
    uniq_project_ids = list(set(uniq_project_ids))
    result_projects = [p for p in config["projects"] if p["id"] in uniq_project_ids]
    return result_projects


def init_logger(arguments):
    log_fmt = "%(message)s"
    logging.basicConfig(format=log_fmt, stream=sys.stdout, level=arguments.logLevel or logging.INFO)


def load_config():
    config_file_local = os.path.join(sys.path[0], "config.json")
    config_file = os.environ.get("GIT_ARTIFACTS_CONFIG_PATH", config_file_local)

    config = load_json(config_file)
    wc_root = get_param("GIT_ARTIFACTS_WC_ROOT", config)

    if not os.path.isabs(wc_root):
        wc_root = os.path.abspath(os.path.join(sys.path[0], wc_root))

    config["wc_root"] = wc_root
    os.chdir(wc_root)

    artifacts_cache_dir = get_param("GIT_ARTIFACTS_CACHE_DIR", config)
    if not os.path.isabs(artifacts_cache_dir):
        artifacts_cache_dir = os.path.abspath(os.path.join(wc_root, artifacts_cache_dir))
    config["artifacts_cache_dir"] = artifacts_cache_dir

    config["repository_url"] = get_param("GIT_ARTIFACTS_REPOSITORY_URL", config)
    config["storage_pattern"] = get_param("GIT_ARTIFACTS_STORAGE_PATTERN", config)
    config["artifacts_pattern"] = get_param("GIT_ARTIFACTS_ARTIFACTS_PATTERN", config)
    config["alias_suffix"] = get_param("GIT_ARTIFACTS_ALIAS_SUFFIX", config)
    return config


def process_args(arguments, config):
    projects = config["projects"]
    wc_root = config["wc_root"]
    artifacts_cache_dir = config["artifacts_cache_dir"]
    repository_url = config["repository_url"]
    storage_pattern = config["storage_pattern"]
    artifacts_pattern = config["artifacts_pattern"]
    alias_suffix = config["alias_suffix"]

    if arguments.interactive:
        arguments = interactive(arguments, projects)
    if arguments.clean_cache:
        clean_cache(artifacts_cache_dir)
    if arguments.project:
        projects = [x for x in projects if x["id"] in arguments.project]

    git = Git(arguments.git_path)
    stdout, error, _ = git.execute_git("rev-parse --git-dir", cwd=wc_root)
    git_root = stdout.strip().split("\n")[0]

    if projects == config["projects"]:
        unexpected_profiles = [prof for prof in arguments.profile if prof not in list(config["profiles"].keys())]
        assert not unexpected_profiles, "Unexpected profiles: {}".format(unexpected_profiles)
        arguments.profile = get_profile(arguments, git_root)
    else:
        logging.debug("Detect custom projects list, profiles disabled")
        arguments.profile = ['default']

    projects = filter_projects_by_profiles(arguments.profile, config)

    logging.info("Profile: {}".format(' '.join(arguments.profile)))
    logging.debug("Default Projects: {}".format([x["id"] for x in config["projects"]]))
    logging.debug("Input Projects: {}".format(arguments.project))
    logging.debug("Selected Projects: {}".format([x["id"] for x in projects]))
    logging.debug("wc_root: {}".format(wc_root))
    logging.debug("artifacts_cache_dir: {}".format(artifacts_cache_dir))

    params = {
        "artifacts_cache_dir": artifacts_cache_dir,
        "repository_url": repository_url,
        "storage_pattern": storage_pattern,
        "artifacts_pattern": artifacts_pattern,
        "alias_suffix": alias_suffix,
        "wc_root": wc_root,
        "setup_mod": arguments.setup,
        "modes": get_modes(arguments, config),
    }

    return params, projects


def get_modes(arguments, config):
    modes = ""
    if arguments.profile_list:
        profiles = list(config["profiles"].keys())
        modes += pretty_logger("Profiles: {}\n".format(", ".join(profiles)), level=0)
    if arguments.project_list:
        modes += pretty_logger("Projects:\n", level=0)
        modes += pretty_logger("{:<25} {:<10}\n".format("Name", "Id"), level=1)
        for project in config["projects"]:
            modes += pretty_logger("{:<25} {:<10}\n".format(project["name"], project["id"]), level=1)
    return modes


def clean_cache(path):
    logging.info("Cleanup cache")
    logging.debug(pretty_logger("Remove: {}".format(path), level=1))
    if os.path.isdir(path):
        shutil.rmtree(path)


def process_builds(arguments, params, projects):
    exit_code = 0
    projects_list = []
    for project_base_config in projects:
        p_config = {
            "name": project_base_config["name"],
            "id": project_base_config["id"],
            "wc_root": params["wc_root"],
            "git_path": arguments.git_path,
            "repo_url": params["repository_url"],
            "storage_pattern": params["storage_pattern"],
            "artifacts_pattern": params["artifacts_pattern"],
            "alias_suffix": params["alias_suffix"],
            "cache_path": params["artifacts_cache_dir"],
            "clean_build": arguments.clean_build,
            "smart_clean_cache": arguments.smart_clean_cache,
            "force_download": arguments.force_download,
            "force_install": arguments.force_install,
            "config": project_base_config,
        }
        project = Project(p_config)
        projects_list.append(project)

    find_build(projects_list, params["wc_root"], arguments.git_path, arguments.ignore_processing_builds)
    successful_projects = [x for x in projects_list if x.build_info]
    failed_projects = [x for x in projects_list if not x.build_info]
    successful_projects_str = ["{} ({})".format(proj.name, proj.build_info["commits_checked"]) for proj in successful_projects]
    failed_project_names = [x.name for x in failed_projects]

    logging.info(pretty_logger("Builds found: {}".format(", ".join(successful_projects_str)), level=0, color=SpecialChar.GREEN))
    logging.info("")

    for project in successful_projects:
        logging.info("Processing: {}".format(project.name))
        logging.info(project.get_build_info())
        if not project.get_artifact():
            failed_project_names.append(project.name)
        logging.info("")

    if failed_project_names:
        logging.info("Failed projects:")
        for project in failed_project_names:
            logging.error(pretty_logger("{}".format(project), level=1))
        exit_code = 1
    return exit_code


def get_artifacts(args, config):
    params, projects = process_args(args, config)

    if params["modes"]:
        logging.info(params["modes"])
        return 0
    if params["setup_mod"]:
        logging.info("Setup mode")
        return 0
    return process_builds(args, params, projects)


def get_paths(root, includes_config, platform):
    includes = includes_config.get("default", [])
    includes.extend(includes_config.get(platform, []))
    includes_paths = [os.path.normpath(os.path.join(root, x)) for x in includes]
    return includes_paths


def zip_dir(root, destination, includes_config, platform):
    includes_paths = get_paths(root, includes_config, platform)
    logging.debug("SRC: {}".format(root))
    logging.debug("DEST: {}".format(destination))
    logging.debug("INCLUDES: \n{}".format("\n".join(includes_paths)))
    logging.debug("FOUND PATHS:")
    with zipfile.ZipFile(destination, "a", zipfile.ZIP_DEFLATED) as zipf:
        for path in includes_paths:
            for full_path in glob.glob(path):
                logging.debug(full_path)
                zipf.write(full_path, arcname=full_path[len(root) + 1:])
    # Remove empty archive
    if os.stat(destination).st_size <= 22:
        os.remove(destination)
        return False
    return True


def make_aliases(version, aliases, destination):
    aliases = aliases.split(",")
    for alias in aliases:
        destination = "{}.alias".format(destination.replace(version, alias))
        with open(destination, "w") as f:
            f.write(version)


def make_project_artifacts(project, args, config, platform):
    project_id = project["id"]
    project_name = project["name"]
    logging.info(f"Project: {project_name}")
    if not os.path.isdir(os.path.join(args.artifacts_dir, project_id)):
        os.makedirs(os.path.join(args.artifacts_dir, project_id))

    pattern = config["artifacts_pattern"]
    params = {
        "project": project_id,
        "build_id": args.artifacts_ver,
        "platform": platform,
    }
    result_file = os.path.abspath(os.path.join(args.artifacts_dir, project_id, pattern.format(**params)))
    if os.path.isfile(result_file):
        os.remove(result_file)
    logging.info("Making: {}".format(result_file))
    if zip_dir(config["wc_root"], result_file, project["paths"], platform):
        make_aliases(args.artifacts_ver, args.version_aliases, result_file)


def make_artifacts(args, config):
    platform = get_host_platform()

    if not args.artifacts_dir:
        args.artifacts_dir = config["artifacts_cache_dir"]

    projects = config["projects"]
    if args.custom_project != "":
        projects = [proj for proj in projects if proj["id"] == args.custom_project]

    for project in projects:
        make_project_artifacts(project, args, config, platform)
    return 0


def main(default_action):
    os.system('')

    args = parse_args(default_action)
    init_logger(args)
    logging.info("gitArtifacts Start")
    logging.info("**" * 10)
    logging.info("Args: {}".format(" ".join(sys.argv[1:])))

    config = load_config()

    if args.action == "get":
        result = get_artifacts(args, config)
    else:
        result = make_artifacts(args, config)

    logging.info("**" * 10)
    return result


if __name__ == "__main__":
    exit(main(default_action="get"))
