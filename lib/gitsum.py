from dataclasses import dataclass
from pathlib import Path
from pygit2 import Remote, Repository  # type: ignore
from typing import TypeVar
import argparse
import os
import pygit2  # type: ignore
import sys


T = TypeVar("T")


@dataclass
class RepoStatus:
    name: str
    head: str
    is_local: bool
    has_changes: bool
    branch_has_upstream: bool
    local_ahead: int
    local_behind: int

    def is_up_to_date(self) -> bool:
        return not self.has_changes and (
            not self.branch_has_upstream or (
                self.local_ahead == 0 and self.local_behind == 0
            )
        )

    def to_string(self, name_width: int, head_width: int) -> str:
        return f"{'!' if not self.is_up_to_date() else ' '}  {self.name:<{name_width}}  {'[LR]' if self.is_local else '[LB]' if not self.branch_has_upstream else '    '}  {self.head:<{head_width}} {' *' if self.has_changes else '  '}{f' >{self.local_ahead}' if self.local_ahead > 0 else '   '}{f' <{self.local_behind}' if self.local_behind > 0 else '   '}"

    def __str__(self) -> str:
        return self.to_string(0, 0)


def _warn(msg: str) -> None:
    print(f"WARN: {msg}", file=sys.stderr)


def _flatten(l: list[list[T]]) -> list[T]:
    return [x for sublist in l for x in sublist]


def _do_get_git_repos(dir: Path) -> tuple[list[Repository], list[Path]]:
    # TODO: for this specific folder, pygit2.discover_repository() returns a path but the Repository constructor rejects that same path. Why???
    if "Special Characters" in str(dir):
        return ([], [])
    if not os.path.isdir(dir):
        return ([], [dir])
    repo_path = pygit2.discover_repository(str(dir))
    if repo_path:
        return ([Repository(repo_path)], [])
    results = [_do_get_git_repos(subdir) for subdir in dir.iterdir()]
    # If there are no Git repos within this directory, just say that this entire directory is an outside file
    repos = _flatten([repos for (repos, _) in results])
    outside_files = _flatten([outside_files for (_, outside_files) in results])
    if len(repos) != 0:
        return (repos, outside_files)
    else:
        return (repos, [dir])


def _get_git_repos(dir: Path, list_outside_files: bool) -> list[Repository]:
    """
    Recursively searches for git repos starting in (and including) the given directory.
    """
    (repos, outside_files) = _do_get_git_repos(dir)
    if list_outside_files:
        outside_files.sort()
        for f in outside_files:
            relative_path = f.relative_to(dir).as_posix()
            path_str = relative_path + "/" if f.is_dir() else relative_path
            print(f"OUTSIDE: {path_str}")
    return repos


def _get_repo_name(repo: Repository, working_dir: Path) -> str:
    # Remove .git folder
    path = Path(repo.path)
    if path.match(".git"):
        path = path.parent
    return path.relative_to(working_dir).as_posix()


def _try_fetch(remote: Remote, repo_name: str) -> None:
    try:
        remote.fetch()  # type: ignore
    except pygit2.GitError:
        # TODO: Check credentials? Skip?
        _warn(f"Failed to fetch repo '{repo_name}'")


def _get_status(repo: Repository, name: str, fetch: bool) -> RepoStatus:
    branch_has_upstream = False
    (local_ahead, local_behind) = (0, 0)
    if repo.head_is_unborn:
        branch_name = "(no commits)"
    elif repo.head_is_detached:
        branch_name = f"({repo.head.target.hex[:6]})"  # type: ignore
    else:
        branch_name = repo.head.shorthand
        local_branch = repo.lookup_branch(branch_name)
        upstream_branch = local_branch.upstream
        if upstream_branch:
            branch_has_upstream = True
            if fetch:
                remote = repo.remotes[upstream_branch.remote_name]
                _try_fetch(remote, name)
            (local_ahead, local_behind) = repo.ahead_behind(local_branch.target, upstream_branch.target) # type: ignore
    is_local = not len(repo.remotes) > 0
    has_changes = len(repo.status()) > 0
    return RepoStatus(name, branch_name, is_local, has_changes, branch_has_upstream, local_ahead, local_behind)


def _get_git_summary(fetch: bool, list_outside_files: bool, only_outside_files: bool) -> None:
    cwd = Path(os.getcwd())
    repos = _get_git_repos(cwd, list_outside_files or only_outside_files)
    if not only_outside_files:
        print(f"Found {len(repos)} Git repositories.")
        statuses = [_get_status(r, _get_repo_name(r, cwd), fetch) for r in repos]
        name_width = max([len(s.name) for s in statuses])
        head_width = max([len(s.head) for s in statuses])
        statuses.sort(key=lambda s: s.name)
        [print(s.to_string(name_width, head_width)) for s in statuses]


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="gitsum",
        description="View a summary of statuses for multiple Git repositories."
    )
    parser.add_argument("-f", "--fetch", action="store_true", help="fetch before getting status")
    parser.add_argument("-o", "--outside-files", action="store_true", help="list files and directories that are not inside a Git repository")
    parser.add_argument("-O", "--only-outside-files", action="store_true", help="list files and directories that are not inside a Git repository and exit")
    args = parser.parse_args()
    _get_git_summary(args.fetch, args.outside_files, args.only_outside_files)


if __name__ == "__main__":
    main()