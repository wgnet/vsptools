#!/usr/bin/env python3

import subprocess
import re
from dataclasses import dataclass
from typing import Optional, Tuple

from pydantic import BaseModel

from versioner import logger
from versioner.git import Git
from versioner.utils import get_git, get_ref_sha

# consts
MASTER_BRANCH_NAME = "master"
RELEASE_BRANCH_NAME = "release"
RELEASE_BRANCH_ALIAS = "candidate"
HOTFIX_BRANCH_NAME = "hotfix"
DETACHED_LABEL = "detached"

NUMBER_PATTERN = "(0|[1-9][0-9]*)"
RELEASE_BRANCH_FILTER = re.compile(f"({RELEASE_BRANCH_NAME}/v\\d+\\.\\d+)", re.IGNORECASE)
BRANCH_SIMPLE_RE = re.compile("([^A-Za-z0-9])")
VERSION_TAG_FILTER = re.compile(f"^v{NUMBER_PATTERN}((\\.{NUMBER_PATTERN})?-master|(\\.{NUMBER_PATTERN}){{2}})$")
RELEASE_TAG_FILTER = re.compile(f"^v{NUMBER_PATTERN}(\\.{NUMBER_PATTERN}){{2}}$")

# config
_USE_REMOTE = True
_TRUSTED_BRANCH_SOURCE_REMOTE = "refs/remotes/"
_TRUSTED_BRANCH_SOURCE_REMOTE_NAME = "origin"
_TRUSTED_BRANCH_SOURCE_BARE = "refs/heads/"  # for local check or work on server


def set_use_remote(value: bool):
    global _USE_REMOTE
    _USE_REMOTE = value


def set_remote_name(value: str):
    global _TRUSTED_BRANCH_SOURCE_REMOTE_NAME
    _TRUSTED_BRANCH_SOURCE_REMOTE_NAME = value


def get_branch_trust_location() -> str:
    if _USE_REMOTE:
        return f"{_TRUSTED_BRANCH_SOURCE_REMOTE}{_TRUSTED_BRANCH_SOURCE_REMOTE_NAME}/"
    return _TRUSTED_BRANCH_SOURCE_BARE


def get_master_branch() -> str:
    return get_branch_trust_location() + MASTER_BRANCH_NAME


class CommitData(BaseModel):
    sha: str
    ref: Optional[str] = None


class DistanceData(BaseModel):
    commit: CommitData
    target_sha: CommitData
    in_commit: int
    in_target: int


def get_crossing_commit_to_branch(git: Git, commit: CommitData, branch: str) -> Tuple[CommitData, bool, bool]:
    sha_in_branch = False
    sha_on_branch = False
    path_from_master = git.name_rev(commit.sha, name_only=True, refs=branch)
    if path_from_master == "undefined":  # sha not in branch
        branch_sha = git.merge_base(branch, commit.sha)
    else:
        sha_in_branch = True
        if path_from_master.endswith("^0") or ("^" not in path_from_master):
            sha_on_branch = True
            branch_sha = commit.sha
        else:
            path_parts = path_from_master.split("~")
            if len(path_parts) == 1:  # if commit in last integrated branch
                back_steps = 1
            else:
                back_steps = int(path_parts[1].split("^")[0]) + 1
            branch_sha = git.rev_parse(f"{branch}~{back_steps}")

    data = CommitData(
        sha=branch_sha,
        ref=branch,
    )
    return data, sha_in_branch, sha_on_branch


def get_release_ref(git: Git, tag_name: str) -> Optional[str]:
    if not VERSION_TAG_FILTER.match(tag_name):
        logger.error(f"ERROR: Incorrect Tag [{tag_name}].")
        return None

    release_ref = None

    tag_version = ["0"] * 2
    tag_splitted = tag_name[1:].split("-")[0].split(".")
    for i in range(min(2, len(tag_splitted))):
        tag_version[i] = tag_splitted[i]
    branch_name = "{}{}/v{}.{}".format(get_branch_trust_location(), RELEASE_BRANCH_NAME, *tag_version)

    try:
        git.rev_parse(branch_name)
        release_ref = branch_name
    except subprocess.CalledProcessError:
        pass

    if release_ref is None:
        release_tags = git.tag("v{}.{}.*".format(*tag_version), list=True, sort="-v:refname").split("\n")
        for release_tag in release_tags:
            if VERSION_TAG_FILTER.match(release_tag):
                release_ref = release_tag
                break

    return release_ref


def get_commit_data(git: Git, reference: str) -> CommitData:
    ref_sha = get_ref_sha(git, reference)

    if not ref_sha.startswith(reference):
        branch_name = git.rev_parse(reference, abbrev_ref=True, symbolic_full_name=True)
    else:
        branch_name = None  # TODO: add logic to find ref name

    if branch_name == "HEAD":  # NOTE: HEAD not branch
        branch_name = None

    return CommitData(
        sha=ref_sha,
        ref=branch_name
    )


def is_commit_on_release_tag(git: Git, commit: CommitData) -> bool:
    tags = git.tag(list=True, sort="-v:refname", points_at=commit.sha).split("\n")
    for tag_version_name in tags:
        if RELEASE_TAG_FILTER.match(tag_version_name):
            return True
    return False


def find_tag(git: Git, commit: CommitData, re_find_tag: bool = True) -> CommitData:
    tag_name = git.describe(commit.sha, tags=True, match='v*', abbrev="0")
    tag_sha = git.rev_list(tag_name, max_count="1")  # NOTE: avoid annotated tag_name problem

    if (commit.sha == tag_sha) and re_find_tag:
        return find_tag(git, CommitData(sha=f"{commit.sha}~1"), False)

    data = CommitData(
        sha=tag_sha,
        ref=tag_name
    )
    return data


def get_distance(git: Git, commit: CommitData, target: CommitData) -> DistanceData:
    distance_to_target, distance_to_commit = git.rev_list(f"{commit.sha}...{target.sha}", left_right=True, count=True).split("\t")
    return DistanceData(
        commit=commit,
        target_sha=target,
        in_commit=int(distance_to_target),
        in_target=int(distance_to_commit)
    )


class Version(BaseModel):
    major: int = 0
    minor: int = 0
    patch: int = 0
    in_trunk: int = 0
    in_branch: int = 0
    label: str = ""
    sha: str = "00000000"

    def set_mmp(self, major: int = 0, minor: int = 0, patch: int = 0):
        self.major = major
        self.minor = minor
        self.patch = patch

    def set_label(self, label: Optional[str]):
        if label is not None:
            self.label = BRANCH_SIMPLE_RE.sub("-", label)
        else:
            self.label = ""

    def get_version(self, no_label: bool = False):
        in_branch_str = "" if self.in_branch == 0 else f"-{self.in_branch}"
        label_str = "" if self.label == "" or no_label else f"-{self.label}"
        return f"{self.major}.{self.minor}.{self.patch}.{self.in_trunk}{in_branch_str}{label_str}-{self.sha[:8]}"


def calculate_version(git: Git,
                      tag: CommitData,
                      commit: CommitData,
                      distance_cut_to_sha: int,
                      distance_tag_to_cut: int,
                      no_release_label_mode: bool = False,
                      release_branch: Optional[str] = None) -> Version:
    logger.debug("Tags calculation:")

    version = Version(in_trunk=distance_tag_to_cut, in_branch=distance_cut_to_sha, sha=commit.sha)

    tags = git.tag(list=True, sort="-v:refname", points_at=tag.sha).splitlines()
    tag_version = [-1] * 3
    master_tag_len = 0

    for tag_version_name in tags:
        if not VERSION_TAG_FILTER.match(tag_version_name):
            continue
        tag_version_splitted = tag_version_name[1:].split("-")[0].split(".")
        master_tag_len = len(tag_version_splitted)
        for i in range(len(tag_version_splitted)):
            if tag_version[i] == -1:
                tag_version[i] = int(tag_version_splitted[i])
            elif tag_version[i] != int(tag_version_splitted[i]):
                logger.warning(f"WARNING: Incorrect Tags group. Tags in group have different version. Tag [{tag_version_name}] "
                               f"ignored.")
                continue

    logger.debug(f"  tags: {tags}")
    logger.debug(f"  tag_version: {tag_version}")

    version_mmp = tag_version[:master_tag_len] + [0] * (3 - master_tag_len)
    version_mmp[master_tag_len - 1] += 1

    version.set_mmp(*version_mmp)

    logger.debug(f"  tag_version: {version_mmp}")

    internal_no_label_mode = False

    if is_commit_on_release_tag(git, commit):
        logger.debug("  commit on release tag")
        internal_no_label_mode = True

    version.in_branch = int(distance_cut_to_sha)

    if version.in_branch > 0 and commit.ref is None:
        commit.ref = DETACHED_LABEL

    if commit.ref is not None and internal_no_label_mode is False:
        if commit.ref == get_master_branch():
            version.set_label(MASTER_BRANCH_NAME)
        elif commit.ref == release_branch or RELEASE_BRANCH_FILTER.fullmatch(commit.ref):
            if no_release_label_mode is False:
                version.set_label(RELEASE_BRANCH_ALIAS)
        else:
            version.set_label(commit.ref)

    return version


def get_version(reference: str,
                repo: str = ".",
                bare: bool = False,
                remote: str = "origin",
                no_release_label_mode: bool = False) -> Version:

    git = get_git(repo)

    set_use_remote(not bare)
    set_remote_name(remote)

    commit = get_commit_data(git, reference)

    master, sha_in_master, sha_on_master = get_crossing_commit_to_branch(git, commit, get_master_branch())

    if sha_on_master and not RELEASE_BRANCH_FILTER.fullmatch(commit.ref):
        commit.ref = get_master_branch()

    logger.debug("Base Data:")
    logger.debug(f"  repo_root: {git.git_path}")
    logger.debug(f"  ref: {reference}")
    logger.debug(f"  sha: {commit}")

    commit_to_master = get_distance(git, commit, master)

    logger.debug("Master Data:")
    logger.debug(f"  Flags: In: {sha_in_master}, On: {sha_on_master}")
    logger.debug(f"  cross with {get_master_branch()}: {master}")
    logger.debug(f"  distance Commit to Master: {commit_to_master.in_commit} {commit_to_master.in_target}")

    # Check Tag
    tag = find_tag(git, commit)
    is_tag_master = tag.ref.endswith("-master")

    tag_to_master = get_distance(git, tag, master)
    commit_to_tag = get_distance(git, commit, tag)

    logger.debug("Tag Data:")
    logger.debug(f"  tag: {tag}")
    logger.debug(f"  is_tag_master: {is_tag_master}")
    logger.debug(f"  distance Tag to Master: {tag_to_master.in_commit} {tag_to_master.in_target}")
    logger.debug(f"  distance Commit to Tag: {commit_to_tag.in_commit} {commit_to_tag.in_target}")

    if sha_in_master:
        return calculate_version(
            git,
            tag,
            commit,
            commit_to_master.in_commit,
            tag_to_master.in_target,
            no_release_label_mode
        )

    # Release Branch
    logger.debug("Release Branch Check:")

    release_ref = get_release_ref(git, tag.ref)
    logger.debug(f"  release_ref: {release_ref}")

    if release_ref is not None:
        release, sha_in_release, sha_on_release = get_crossing_commit_to_branch(git, commit, release_ref)

        commit_to_release = get_distance(git, commit, release)
        tag_to_release = get_distance(git, tag, release)

        logger.debug(f"  Flags: In: {sha_in_release}, On: {sha_on_release}")
        logger.debug(f"  cross with {release_ref}: {release}")
        logger.debug(f"  distance Commit to Release: {commit_to_release.in_commit} {commit_to_release.in_target}")
        logger.debug(f"  distance Tag to Release: {tag_to_release.in_commit} {tag_to_release.in_target}")

        if sha_in_release \
                or (commit_to_release.in_commit < commit_to_master.in_commit) \
                or (commit_to_release.in_commit == commit_to_master.in_commit
                    and commit.ref and commit.ref.startswith(HOTFIX_BRANCH_NAME)):

            if sha_on_release:
                commit.ref = release_ref

            if is_tag_master:
                tag = find_tag(git, tag)
                tag_to_release = get_distance(git, tag, release)
                logger.debug(f"Change Tag to: {tag}")
                logger.debug(f"  distance Tag to Release: {tag_to_release.in_commit} {tag_to_release.in_target}")

            return calculate_version(git, tag, commit, commit_to_release.in_commit, tag_to_release.in_target,
                                     no_release_label_mode, release_ref)

    # Common case
    return calculate_version(git, tag, commit, commit_to_master.in_commit, tag_to_master.in_target,
                             no_release_label_mode, release_ref)
