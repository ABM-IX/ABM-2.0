"""
abm/companion/git_pipeline.py
==============================
Local Git Integration Pipeline — Phase v0.2 Developer Companion Node
Spec Reference: ABM_SPEC.md sections 2 and 10 (item 2)

Reads a local Git repository using GitPython — no network calls, no remote
access. Provides commit history, per-commit diffs, and branch state to the
IngestionCoordinator for Stream A and Stream C ingestion.

Design contract:
  - get_commit_file_chunks() calls the existing v0.1
    chunk_stream_a_code_topologies() function. It does NOT re-implement
    chunking logic.
  - get_commit_telemetry_event() returns a dict shaped exactly for Stream C
    metadata: {epoch_timestamp: int, active_repository: str, device_source: str}.
  - Only added/modified lines from diffs are returned (deletions are not
    stored — they are not useful for style-matching).
  - All operations are read-only. Nothing is written to the Git repo.
  - GitPipelineError is raised for any Git operation that fails so
    callers can handle it without catching generic exceptions.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import git
from git import InvalidGitRepositoryError, NoSuchPathError, Repo

from abm.memory.chunking import chunk_stream_a_code_topologies
from abm.companion.file_watcher import _is_excluded

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Map file extensions to spec-supported language strings.
_EXTENSION_TO_LANGUAGE: dict[str, str] = {
    ".py": "python",
    ".dart": "dart",
    ".kt": "kotlin",
    ".java": "kotlin",   # structural chunker handles Java as Kotlin (brace-depth)
    ".js": "python",     # fallback: python AST will fail, structural chunker takes over
    ".html": "python",
    ".css": "python",
}

#: device_source per spec hardware-agnostic update (section 10 addendum).
DEVICE_SOURCE: str = "dynamic_mobile_node"

#: Default maximum commits to read in list_commits / ingest_git_tree.
DEFAULT_MAX_COMMITS: int = 50


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class GitPipelineError(RuntimeError):
    """
    Raised when any Git operation in GitPipeline fails.

    Subclasses RuntimeError so callers that catch RuntimeError still handle
    it, but tests can assert specifically on GitPipelineError.
    """


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class CommitRecord:
    """
    A lightweight summary of a single Git commit.

    Attributes
    ----------
    sha : str
        Full 40-character commit SHA.
    message : str
        First line of the commit message.
    author : str
        Commit author name.
    epoch_timestamp : int
        Unix timestamp of the commit (authored time).
    files_changed : list[str]
        Relative paths of all files touched by the commit.
    """

    sha: str
    message: str
    author: str
    epoch_timestamp: int
    files_changed: list[str] = field(default_factory=list)


@dataclass
class FileDiff:
    """
    The added/modified lines from a single file in a commit diff.

    Attributes
    ----------
    path : str
        Relative path of the file within the repository.
    language : str
        Language string detected from the file extension.
        Falls back to ``"python"`` for unrecognised extensions so the
        structural chunker can still process the file.
    added_lines : str
        All added lines in the diff joined into a single string, suitable
        for passing directly to ``chunk_stream_a_code_topologies()``.
    """

    path: str
    language: str
    added_lines: str


# ---------------------------------------------------------------------------
# GitPipeline
# ---------------------------------------------------------------------------


class GitPipeline:
    """
    Read-only interface to a local Git repository.

    Parameters
    ----------
    repo_path : str
        Absolute or relative path to the root of a Git repository
        (the directory that contains ``.git``).

    Raises
    ------
    GitPipelineError
        If ``repo_path`` is not a valid Git repository.
    """

    def __init__(self, repo_path: str) -> None:
        try:
            self._repo = Repo(repo_path, search_parent_directories=True)
        except (InvalidGitRepositoryError, NoSuchPathError) as exc:
            raise GitPipelineError(
                f"GitPipeline: '{repo_path}' is not a valid Git repository."
            ) from exc
        self._repo_path = str(Path(self._repo.working_dir).resolve())
        logger.info(
            "GitPipeline: opened repository at '%s' (branch: %s).",
            self._repo_path,
            self._safe_branch(),
        )

    # ------------------------------------------------------------------
    # Repository metadata
    # ------------------------------------------------------------------

    def repo_name(self) -> str:
        """
        Return the basename of the repository root directory.

        Returns
        -------
        str
        """
        return Path(self._repo_path).name

    def current_branch(self) -> str:
        """
        Return the name of the currently active branch.

        Returns ``"HEAD"`` (detached HEAD state) when no branch is checked out.

        Returns
        -------
        str
        """
        return self._safe_branch()

    def head_commit_sha(self) -> str:
        """
        Return the full SHA of the HEAD commit.

        Returns
        -------
        str

        Raises
        ------
        GitPipelineError
            If the repository has no commits.
        """
        try:
            return self._repo.head.commit.hexsha
        except Exception as exc:
            raise GitPipelineError(
                "GitPipeline: could not read HEAD commit (repository may be empty)."
            ) from exc

    # ------------------------------------------------------------------
    # Commit history
    # ------------------------------------------------------------------

    def list_commits(self, max_count: int = DEFAULT_MAX_COMMITS) -> list[CommitRecord]:
        """
        Return a list of the most recent commits from HEAD, newest first.

        Parameters
        ----------
        max_count : int
            Maximum number of commits to return. Defaults to ``50``.

        Returns
        -------
        list[CommitRecord]
            Commit records in reverse-chronological order.

        Raises
        ------
        GitPipelineError
            If the repository has no commits or the walk fails.
        ValueError
            If ``max_count`` is less than 1.
        """
        if max_count < 1:
            raise ValueError("max_count must be at least 1.")
        try:
            records: list[CommitRecord] = []
            for commit in self._repo.iter_commits(max_count=max_count):
                records.append(self._commit_to_record(commit))
            return records
        except git.GitCommandError as exc:
            raise GitPipelineError(
                f"GitPipeline.list_commits: Git command failed — {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # Diff reading
    # ------------------------------------------------------------------

    def get_commit_diff(self, commit_sha: str) -> list[FileDiff]:
        """
        Return the added/modified lines for each file changed in a commit.

        Only additions are returned — deleted lines are not stored because
        they carry no value for style-matching.

        Parameters
        ----------
        commit_sha : str
            Full or abbreviated SHA of the commit to inspect.

        Returns
        -------
        list[FileDiff]
            One ``FileDiff`` per file that had added lines in the commit.
            Files with only deletions are excluded.

        Raises
        ------
        GitPipelineError
            If the commit SHA is unknown or the diff operation fails.
        """
        try:
            commit = self._repo.commit(commit_sha)
        except git.BadName as exc:
            raise GitPipelineError(
                f"GitPipeline.get_commit_diff: unknown commit SHA '{commit_sha}'."
            ) from exc

        parent = commit.parents[0] if commit.parents else None

        try:
            diffs = commit.diff(parent, create_patch=True)
        except Exception as exc:
            raise GitPipelineError(
                f"GitPipeline.get_commit_diff: diff failed for '{commit_sha}' — {exc}"
            ) from exc

        results: list[FileDiff] = []
        for diff_item in diffs:
            path = diff_item.b_path or diff_item.a_path or ""
            if not path or _is_excluded(path):
                continue
            added = self._extract_added_lines(diff_item)
            if not added.strip():
                continue
            language = self._detect_language(path)
            results.append(FileDiff(path=path, language=language, added_lines=added))

        logger.debug(
            "GitPipeline.get_commit_diff: %s — %d files with additions.",
            commit_sha[:8], len(results),
        )
        return results

    def get_commit_file_chunks(
        self,
        commit_sha: str,
        language: str,
    ) -> list[str]:
        """
        Return AST/structural code chunks for all files in a commit that
        match the given language.

        This method calls the existing v0.1 ``chunk_stream_a_code_topologies()``
        function — it does NOT re-implement chunking.

        Parameters
        ----------
        commit_sha : str
            Full or abbreviated commit SHA.
        language : str
            Language to filter by. One of ``"dart"``, ``"kotlin"``, ``"python"``.

        Returns
        -------
        list[str]
            Flat list of code chunks across all matching files in the commit,
            in the order the files appear in the diff.

        Raises
        ------
        GitPipelineError
            If the commit or diff read fails.
        ValueError
            If ``language`` is not supported by ``chunk_stream_a_code_topologies``.
        """
        diffs = self.get_commit_diff(commit_sha)
        all_chunks: list[str] = []
        for diff in diffs:
            if diff.language != language:
                continue
            chunks = chunk_stream_a_code_topologies(diff.added_lines, language)
            all_chunks.extend(chunks)
        logger.debug(
            "GitPipeline.get_commit_file_chunks: %s / %s → %d chunks.",
            commit_sha[:8], language, len(all_chunks),
        )
        return all_chunks

    # ------------------------------------------------------------------
    # Telemetry
    # ------------------------------------------------------------------

    def get_commit_telemetry_event(self, commit_sha: str) -> dict[str, Any]:
        """
        Build a Stream C telemetry event dict for a given commit.

        The returned dict contains exactly the three Stream C metadata keys
        from spec section 3: ``epoch_timestamp``, ``active_repository``,
        ``device_source``. It also includes a ``text`` key with the commit
        message for embedding.

        Parameters
        ----------
        commit_sha : str
            Full or abbreviated commit SHA.

        Returns
        -------
        dict[str, Any]
            Keys: ``epoch_timestamp`` (int), ``active_repository`` (str),
            ``device_source`` (str), ``text`` (str), ``sha`` (str).

        Raises
        ------
        GitPipelineError
            If the commit SHA is unknown.
        """
        try:
            commit = self._repo.commit(commit_sha)
        except git.BadName as exc:
            raise GitPipelineError(
                f"GitPipeline.get_commit_telemetry_event: unknown SHA '{commit_sha}'."
            ) from exc

        return {
            "epoch_timestamp": int(commit.authored_date),
            "active_repository": self.repo_name(),
            "device_source": DEVICE_SOURCE,
            "text": f"git commit {commit.hexsha[:8]}: {commit.message.strip()[:200]}",
            "sha": commit.hexsha,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _safe_branch(self) -> str:
        try:
            return self._repo.active_branch.name
        except TypeError:
            return "HEAD"

    @staticmethod
    def _commit_to_record(commit: git.Commit) -> CommitRecord:
        files_changed = list(commit.stats.files.keys())
        return CommitRecord(
            sha=commit.hexsha,
            message=commit.message.strip().splitlines()[0][:200],
            author=str(commit.author),
            epoch_timestamp=int(commit.authored_date),
            files_changed=files_changed,
        )

    @staticmethod
    def _detect_language(path: str) -> str:
        ext = Path(path).suffix.lower()
        return _EXTENSION_TO_LANGUAGE.get(ext, "python")

    @staticmethod
    def _extract_added_lines(diff_item: Any) -> str:
        """Extract only the '+' lines from a unified diff patch."""
        try:
            patch = diff_item.diff.decode("utf-8", errors="replace")
        except Exception:
            return ""
        added: list[str] = []
        for line in patch.splitlines():
            if line.startswith("+") and not line.startswith("+++"):
                added.append(line[1:])  # strip the leading '+'
        return "\n".join(added)
