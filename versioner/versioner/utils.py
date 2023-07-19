import subprocess
from versioner.git import Git
from versioner import logger


class VersionerIncorrectRepoPathError(Exception):
    pass


class VersionerUnknownReferenceError(Exception):
    pass


def get_git(repo) -> Git:
    try:
        git = Git(cwd=repo)
        repo_root = git.rev_parse(show_toplevel=True)
        return Git(cwd=repo_root)
    except (subprocess.CalledProcessError, NotADirectoryError):
        raise VersionerIncorrectRepoPathError(f"Path [{repo}] is not git repo.")


def get_ref_sha(git, reference) -> str:
    try:
        return git.rev_list(reference, max_count="1")
    except subprocess.CalledProcessError:
        raise VersionerUnknownReferenceError(f"Unknown ref [{reference}].")
