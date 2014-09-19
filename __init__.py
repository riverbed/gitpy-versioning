# Copyright (c) 2014 Riverbed Technology, Inc.
#
# This software is licensed under the terms and conditions of the MIT License
# accompanying the software ("License").  This software is distributed "AS IS"
# as set forth in the License.

"""
This module contains code for interacting with git repositories. It is
used to determine an appropriate version number from either the local
git repository tags or from a version file.
"""

from __future__ import unicode_literals, print_function, division
import os
import inspect
import re
from subprocess import Popen, PIPE
from collections import namedtuple


ALPHA_NUM_PERIOD_UNDER_HYPHEN = '[A-Za-z0-9.\-\_]+$'
ALPHA_PERIOD_PLUS_UNDER_HYPHEN = '[A-Za-z.\+\-\_]+'


INTEGER = '[0-9]+'
FINAL = '{0}(?:\.{1})*'.format(INTEGER, INTEGER)
PRE = '(a|b|c){0}'.format(INTEGER)
POST = '\.post{0}'.format(INTEGER)
DEV = '\.dev{0}'.format(INTEGER)
# PEP440 = FINAL + '({0}|{1}|{2})*'.format(PRE, POST, DEV) + '$'
PEP440 = '{0}(?:{1})?(?:{2})?(?:{3})?\s*$'.format(FINAL, PRE, POST, DEV)


class InvalidString(Exception):
    """Invalid strings
    """
    def __init__(self, error):
        self.error = error


class InvalidTag(InvalidString):
    """Exception class for invalid tags
    """
    def __str__(self):
        return "Invalid tag {0}".format(self.error)


class InvalidBranch(InvalidString):
    """Exception class for invalid tags
    """
    def __str__(self):
        return "Invalid branch {0}".format(self.error)


class InvalidCommand(InvalidString):
    """Exception class for invalid git command"""

    def __str__(self):
        return ("Invalid command {0}, \n Exception {1}"
                .format(' '.join(self.error[0]), self.error[1]))


def git(cmd, dir=None, input=False):
    """Return a git command results. raise an EnvironmentError is not a git repo.

    :param cmd: a list of strings with 'git' in front form a git command
    :param dir: dir to change to before run the git command
    :param input: flag indicating whether the git command has man-input params.
                  If yes, stderr would mean the param is invalid
    """
    cwd = None
    try:
        if dir is not None:
            cwd = os.getcwd()
            os.chdir(dir)
        process = Popen(['git'] + cmd, stdout=PIPE, stderr=PIPE)
        stdout, stderr = process.communicate()
    finally:
        if cwd is not None:
            os.chdir(cwd)

    if stderr:
        if not input:
            # not a git repo
            raise EnvironmentError(stderr)
        else:
            raise InvalidCommand((['git'] + cmd, stderr))
    else:
        return stdout.strip()


def call_git_describe(abbrev=None):
    """Return 'git describe' output.

    :param abbrev: Integer to use as the --abbrev value for git describe
    """
    cmd = ['describe']

    # --abbrev and --long are mutually exclusive 'git describe' options
    if abbrev is not None:
        cmd.append('--abbrev={0}'.format(abbrev))
    else:
        cmd.append('--long')

    return git(cmd)


def get_branch():
    """Return the current branch's name."""
    input = git(['branch'])
    line = [ln for ln in input.split('\n') if ln.startswith('*')][0]
    return line.split()[-1]


def get_parent(branch):
    """ Return the parent branch

    :param branch: name of the current branch
    """
    input = git(['show-branch'])
    line = [ln for ln in input.split('\n')
            if ln.find('*') >= 0 and ln.find(branch) < 0][0]
    # line is in the form of '+ *++ [parent] commit message'
    return line.split('[')[1].split(']')[0]


def get_non_dev_tag(pkg_name):
    """Return the most recent non_development tag

    :param pkg_name: package name prefixing any tags, type: string
    """
    input = git(['for-each-ref', '--sort=taggerdate',
                 '--format', "'%(refname) %(taggerdate)'", 'refs/tags'])
    line = [ln for ln in input.split('\n')
            if ln.split()[0].find('.dev') < 0][-1]
    tag = line.split(' ')[0][11:]
    validate_tag(tag, pkg_name)
    return tag


def tag2cmt(tag):
    """Return the commit that the tag points to

    :param tag: the tag on the inquired commit, type:string
    """
    input = git(['rev-list', '{0}'.format(tag)], input=True)
    return input.split('\n')[0]


def get_commit():
    """Return the latest commit"""
    cmt = git(['log', '-n', '1', "--pretty=format:'%H'"])
    return cmt.replace("'", "")


def cmt2branch(commit):
    """return the origin branch of the commit

    :param commit: the inquired commit, type: string
    """
    input = git(['reflog', 'show', '--all'])

    line = [ln for ln in input.split('\n') if ln.find(commit[:7]) >= 0][0]
    # line is in the form of "bb994b4 refs/heads/master@{2}: pull: Fast-for"
    return line.split(' ')[1].split('/')[2][:-5]


def git_info(pkg_name):
    """Return an git_info object, which contains attributes:
        pkg_name: package name prefixing any tags, type: string
        branch: branch's name, type: string
        parent: parent branch's name, type: string
        tag: most recent tag, type: string
        commits: number of commits since most recent tag, type: int
        sha: short form hash of latest commit, type: string
        tagged_cmt: the commit that the most recent tag points to, type: string
        cmt: latest commit of the current branch, type:string
    """
    branch = get_branch()
    # A typical full git tag contains four pieces of information: the repo name
    # the version, the number of commits since the last tag, and the SHA-1 hash
    # that identifies the commit.
    long_tag = call_git_describe()
    base_tag = call_git_describe(abbrev=0)

    validate_tag(base_tag, pkg_name)

    # Parse number of commits and sha
    try:
        raw_version_str = long_tag.replace(base_tag, '')
        commits, sha = [part for part in raw_version_str.split('-') if part]
    except ValueError:
        # Tuple unpacking failed, so probably an incorrect tag format was used.
        raise InvalidTag('Parsing error: The git tag seems to be malformed: '
                         'base {0} long {1}\n---'.format(base_tag, long_tag))

    GitInfo = namedtuple('GitInfo', 'branch tag commits sha tagged_cmt cmt')
    return GitInfo(branch=branch,
                   tag=base_tag,
                   commits=int(commits),
                   sha=sha[1:],
                   tagged_cmt=tag2cmt(base_tag),
                   cmt=get_commit())


def verify_repository(pkg_file):
    """Raise an error if this source file is not in tracked by git.

    :param pkg_file: pkig_file to be tested
    """
    dirname = os.path.dirname(pkg_file)
    basename = os.path.basename(pkg_file)

    git(['ls-files', basename, '--error-unmatch'], dir=dirname)
    return


def valid_local_ver(version):
    """check if a version is valid.
       the version needs to consist of ASCII numbers, letters and periods

       :param version: version string to be validated
    """
    return True if re.match(ALPHA_NUM_PERIOD_UNDER_HYPHEN, version) else False


def increment_rightmost(version, number):
    """ increment the rightmost number of the version by the number

    :param version: the version string
    :param number: the number by which the rightmost number is incremented
    """
    num_str = re.split(ALPHA_PERIOD_PLUS_UNDER_HYPHEN, version)[-1]
    return version[:-len(num_str)] + str(int(num_str) + number)


def is_dev(version):
    """Return True if the passed-in version is a development version

    :param version: version string
    """
    return version.find(".dev") > 0


def validate_tag(tag, pkg_name):
    """Validate if version is a valid pep440 public release string

    :param tag: tag string
    :param pkg_name: package_name prefixing tag
    """
    if pkg_name is None:
        if not re.match(PEP440, tag):
            # pkg_name does not prefix the tag raise Exception
            raise InvalidTag("'{0}' does not follow PEP440".format(tag))
    else:  # pkg_name is not None
        if tag.startswith('{0}-'.format(pkg_name)):
            # tag starts with pkg_name
            if not re.match(PEP440, tag[(len(pkg_name) + 1):]):
                # the rest of tag is a valid PEP440 release string, use the tag
                raise InvalidTag("'{0}' does not follow '{1}-' + PEP440"
                                 .format(tag, pkg_name))
        else:
            raise InvalidTag("'{0}' does not start with '{1}-'"
                             .format(tag, pkg_name))


def get_version(pkg_name=None, pkg_file=None, v_file='RELEASE-VERSION'):

    """Return PEP440 style version string.

    :param pkg_name: package name, if not None, tags should be
       prefixed with pkg_name.

    :param pkg_file: Some filename in the package, used to test if this
       is a live git repostitory (defaults to caller's file)

    :param v_file: Fallback path name to a file where release_version is saved
    """
    if pkg_file is None:
        parent_frame = inspect.stack()[1]
        pkg_file = inspect.getabsfile(parent_frame[0])

    try:
        verify_repository(pkg_file)

        info = git_info(pkg_name)

        if info.cmt == info.tagged_cmt:
            # latest commit is tagged
            version = info.tag
        elif cmt2branch(info.tagged_cmt) == get_parent(info.branch):
            # the most recent tag is on parent branch
            if valid_local_ver(info.branch):
                # current branch name is a valid local version
                version = ('{0}+git.{1}.{2}.{3}'
                           .format(get_non_dev_tag(pkg_name), info.branch,
                                   info.commits, info.sha))
            else:
                raise InvalidBranch("'{0}' is not a valid local version"
                                    .format(info.branch))

        elif is_dev(info.tag):
            # the most recent tag is development tag
            # increment the N in devN and use the tag
            version = increment_rightmost(info.tag, info.commits)

        else:
            # the most recent tagged commit is non-dev, increment the least
            # significant number in the version string and append .devN where N
            # is the number of commits since the tag
            version = ('{0}.dev{1}'
                       .format(increment_rightmost(info.tag, 1),
                               info.commits))

        with open(v_file, 'w') as f:
            f.write(version)

    except EnvironmentError:
        # Not a git repository, so fall back to reading RELEASE-VERSION
        if (os.path.exists(v_file)):
            with open(v_file, 'r') as f:
                version = f.read().strip()
        else:
            version = 'unknown'

    return version
