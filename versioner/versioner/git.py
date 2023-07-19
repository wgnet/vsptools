#!/usr/bin/env python3

# Utility functions for git
#
# Derived in a very large part from the gnome git hooks, themselves
# apparently adapted form git-bz.
#
# Original copyright header:
#
# | Copyright (C) 2008  Owen Taylor
# | Copyright (C) 2009  Red Hat, Inc
# |
# | This program is free software; you can redistribute it and/or
# | modify it under the terms of the GNU General Public License
# | as published by the Free Software Foundation; either version 2
# | of the License, or (at your option) any later version.
# |
# | This program is distributed in the hope that it will be useful,
# | but WITHOUT ANY WARRANTY; without even the implied warranty of
# | MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# | GNU General Public License for more details.
# |
# | You should have received a copy of the GNU General Public License
# | along with this program; if not, If not, see
# | http://www.gnu.org/licenses/.
# |
# | (These are adapted from git-bz)

import os
import re
import subprocess


def git_run(command, *args, **kwargs):
    """Run a git command.

    PARAMETERS
        Non-keyword arguments are passed verbatim as command line arguments
        Keyword arguments are turned into command line options
            <name>=True => --<name>
            <name>='<str>' => --<name>=<str>
        Special keyword arguments:
            _c=<list>: add -c <value> for each value
            _cwd=<str>: Run the git command from the given directory.
            _env=<dict>: Same as the "env" parameter of the Popen constructor.
            _input=<str>: Feed <str> to stdinin of the command
            _outfile=<file): Use <file> as the output file descriptor
            _split_lines: Return an array with one string per returned line
    """
    to_run = ['git'] 
    to_add_to_run = []
    config = {}
    cwd = None
    env = None
    input = None
    outfile = None
    do_split_lines = False
    for (k, v) in list(kwargs.items()):
        if k == '_cwd':
            cwd = v
        elif k == '_env':
            env = v
        elif k == '_input':
            input = v
        elif k == '_outfile':
            outfile = v
        elif k == '_split_lines':
            do_split_lines = True
        elif k == '_c':
            config = v
        elif v is True:
            if len(k) == 1:
                to_add_to_run.append("-" + k)
            else:
                to_add_to_run.append("--" + k.replace("_", "-"))
        else:
            to_add_to_run.append("--" + k.replace("_", "-") + "=" + v)

    for v in config:
        to_run.extend(["-c", v])

    to_run.append(command.replace("_", "-"))
    to_run.extend(to_add_to_run)
    to_run.extend(args)

    stdout = outfile if outfile else subprocess.PIPE
    stdin = None if input is None else subprocess.PIPE
    stderr = subprocess.STDOUT

    process = subprocess.Popen(to_run, stdout=stdout, stderr=stderr, stdin=stdin, cwd=cwd, env=env)
    output, error = process.communicate(input)

    output = output.decode("utf-8")
    # We redirected stderr to the same fd as stdout, so error should
    # not contain anything.
    assert not error
    if process.returncode != 0:
        raise subprocess.CalledProcessError(process.returncode, " ".join(to_run), output)

    if outfile:
        return None
    else:
        if do_split_lines:
            return output.strip().splitlines()
        else:
            return output.strip()


class Git:

    def __init__(self, git_path="git", cwd=""):
        self.git_path = git_path
        self.cwd = cwd


    """Wrapper to allow us to do git.<command>(...) instead of git_run()

    One difference: The `_outfile' parameter may be a string, in which
    case the output is redirected to that file (if the file is already
    present, it is overwritten).
    """
    def __getattr__(self, command):
        def f(*args, **kwargs):
            tmp_fd = None
            try:
                # If a string _outfile parameter was given, turn it
                # into a file descriptor.

                if '_cwd' not in kwargs and self.cwd:
                    kwargs['_cwd'] = self.cwd

                if (('_outfile' in kwargs and
                     isinstance(kwargs['_outfile'], str))):
                    tmp_fd = open(kwargs['_outfile'], 'w')
                    kwargs['_outfile'] = tmp_fd
                return git_run(command, *args, **kwargs)
            finally:
                if tmp_fd is not None:
                    tmp_fd.close()
        return f


git = Git()


def get_git_dir():
    """Return the full path to the repository's .git directory.

    This function is just a convenient short-cut for running
    "git rev-parse --git-dir", with an abspath call added to make
    sure that the returned path is always absolute.

    REMARK
        For bare repositories, there is no .git/ subdirectory.
        In that case, the function returns the equivalent, which
        is the path of the repository itself.
    """
    # Note: The abspath call seems to be needed when calling
    # git either from the repository root dir (in which case
    # it returns either '.' or '.git' depending on whether
    # this is a bare repository or not), or when calling it
    # from the .git directory itself (in which case it returns
    # '.').
    return os.path.abspath(git.rev_parse(git_dir=True))


def is_null_rev(rev):
    """Return True iff rev is the a NULL commit SHA1.
    """
    return re.match("0+$", rev) is not None


def empty_tree_rev():
    """Return the empty tree's SHA1.

    This is a SHA1 one can use as the parent of a commit that
    does not have a parent (root commit).
    """
    # To compute this SHA1 requires a call to git, so cache
    # the result in an attribute called 'cached_rev'.
    if not hasattr(empty_tree_rev, 'cached_rev'):
        empty_tree_rev.cached_rev = git.mktree(_input='')
    return empty_tree_rev.cached_rev


def is_valid_commit(rev):
    """Return True if rev is a valid commit.

    PARAMETERS
        rev: The commit SHA1 we want to test.
    """
    try:
        git.cat_file('-e', rev)
        return True
    except subprocess.CalledProcessError:
        return False


def get_object_type(rev):
    """Determine the object type of the given commit.

    PARAMETERS
        rev: The commit SHA1 that we want to inspect.

    RETURN VALUE
        The string returned by "git cat-file -t REV", or else "delete"
        if REV is a null SHA1 (all zeroes).
    """
    if is_null_rev(rev):
        rev_type = "delete"
    else:
        rev_type = git.cat_file(rev, t=True)
    return rev_type


def commit_rev(rev):
    """Resolve rev into a commit revision (SHA1).

    For commit revs, this is a no-op.  But of other types of revisions
    (such as a tag, for instance), this resolves the tag into the actual
    object it points to.

    PARAMETERS
        rev: A revision.
    """
    return git.rev_list('-n1', rev)


def commit_oneline(rev):
    """Return a short one-line summary of the commit.

    PARAMETERS
        rev: A commit revision (SHA1).
    """
    info = git.rev_list(rev, max_count='1', oneline=True)
    (short_rev, subject) = info.split(None, 1)
    return "%s... %s" % (short_rev, subject[0:59])


def get_module_name():
    """Return a short identifer name for the git repository.

    The identifier name is determined using the directory name where
    the git repository is stored, with the .git suffix stripped.
    """
    absdir = get_git_dir()
    if absdir.endswith(os.sep + '.git'):
        absdir = os.path.dirname(absdir)
    projectshort = os.path.basename(absdir)
    if projectshort.endswith(".git"):
        projectshort = projectshort[:-4]

    return projectshort


def file_exists(commit_rev, filename):
    """Return True if a file exists for a given commit.

    PARAMETERS
        commit_rev: The commit to inspect.
        filename: The filename to search for in the given commit_rev.
            The file name must be relative to the repository's root dir.

    RETURN VALUE
        A boolean.
    """
    try:
        git.cat_file('-e', '%s:%s' % (commit_rev, filename))
    except subprocess.CalledProcessError:
        # cat-file -e returned non-zero; the file does not exist.
        return False
    return True
