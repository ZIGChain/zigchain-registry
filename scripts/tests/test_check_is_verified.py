"""Tests for scripts/ci/check_is_verified.py.

Each test spins up a throwaway git repo under tmp_path, arranges a base and
head commit, then invokes the script as a subprocess so the git/env contract
is exercised exactly as GitHub Actions invokes it.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, Optional

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "ci" / "check_is_verified.py"


def _git(repo: Path, *args: str, check: bool = True, env: Optional[Dict[str, str]] = None) -> subprocess.CompletedProcess:
    """Run a git command rooted at `repo`. Deterministic author/committer for reproducible SHAs."""
    full_env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "Test",
        "GIT_AUTHOR_EMAIL": "test@example.com",
        "GIT_COMMITTER_NAME": "Test",
        "GIT_COMMITTER_EMAIL": "test@example.com",
        # Suppress global config interference.
        "HOME": str(repo),
        **(env or {}),
    }
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=check,
        capture_output=True,
        text=True,
        env=full_env,
    )


def _init_repo(repo: Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "commit.gpgsign", "false")


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _commit(repo: Path, message: str) -> str:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", message)
    return _git(repo, "rev-parse", "HEAD").stdout.strip()


def _run_script(repo: Path, base: str, head: str) -> subprocess.CompletedProcess:
    """Invoke check_is_verified.py with BASE_SHA/HEAD_SHA set, cwd at repo."""
    env = {
        **os.environ,
        "BASE_SHA": base,
        "HEAD_SHA": head,
    }
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=str(repo),
        capture_output=True,
        text=True,
        env=env,
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """Fresh git repo with an empty baseline commit."""
    r = tmp_path / "repo"
    _init_repo(r)
    (r / "README.md").write_text("baseline\n", encoding="utf-8")
    _commit(r, "initial")
    return r


# --------------------------------------------------------------------------- #
# Detection                                                                   #
# --------------------------------------------------------------------------- #


def test_new_file_with_is_verified_true_fails(repo: Path) -> None:
    """A new assets/**/*.json containing `is_verified: true` triggers a violation."""
    base = _git(repo, "rev-parse", "HEAD").stdout.strip()
    _write_json(repo / "assets" / "factory" / "coin.new.json", {"is_verified": True})
    head = _commit(repo, "add verified factory asset")

    result = _run_script(repo, base, head)

    assert result.returncode == 1
    assert "coin.new.json" in result.stderr


def test_flipped_false_to_true_fails(repo: Path) -> None:
    """Flipping `is_verified` from false → true on an existing file triggers a violation."""
    _write_json(repo / "assets" / "ibc" / "tok.json", {"is_verified": False})
    base = _commit(repo, "add unverified token")
    _write_json(repo / "assets" / "ibc" / "tok.json", {"is_verified": True})
    head = _commit(repo, "flip verified")

    result = _run_script(repo, base, head)

    assert result.returncode == 1
    assert "tok.json" in result.stderr


def test_added_is_verified_true_on_existing_file_fails(repo: Path) -> None:
    """Adding the `is_verified` key as true on a file that previously lacked it is flagged."""
    _write_json(repo / "assets" / "native" / "nat.json", {"symbol": "NAT"})
    base = _commit(repo, "add native without verified")
    _write_json(repo / "assets" / "native" / "nat.json", {"symbol": "NAT", "is_verified": True})
    head = _commit(repo, "set verified")

    result = _run_script(repo, base, head)

    assert result.returncode == 1
    assert "nat.json" in result.stderr


def test_flipped_true_to_false_passes(repo: Path) -> None:
    """Removing verification (true → false) is not a violation — the check only guards true-ward flips."""
    _write_json(repo / "assets" / "ibc" / "tok.json", {"is_verified": True})
    base = _commit(repo, "add verified token")
    _write_json(repo / "assets" / "ibc" / "tok.json", {"is_verified": False})
    head = _commit(repo, "unflip verified")

    result = _run_script(repo, base, head)

    assert result.returncode == 0, result.stderr


def test_unrelated_changes_pass(repo: Path) -> None:
    """Changes to files outside `assets/` (or to non-is_verified keys) don't trigger the check."""
    base = _git(repo, "rev-parse", "HEAD").stdout.strip()
    (repo / "README.md").write_text("changed\n", encoding="utf-8")
    _write_json(repo / "assets" / "factory" / "coin.meta.json", {"symbol": "COIN"})
    head = _commit(repo, "docs + non-verified factory asset")

    result = _run_script(repo, base, head)

    assert result.returncode == 0, result.stderr


# --------------------------------------------------------------------------- #
# Bypass                                                                      #
# --------------------------------------------------------------------------- #


def test_bypass_token_in_commit_message_passes(repo: Path) -> None:
    """[allow-verified] anywhere in any commit message bypasses the check."""
    base = _git(repo, "rev-parse", "HEAD").stdout.strip()
    _write_json(repo / "assets" / "factory" / "coin.new.json", {"is_verified": True})
    head = _commit(repo, "verify new coin\n\nReviewed with stakeholders [allow-verified]")

    result = _run_script(repo, base, head)

    assert result.returncode == 0, result.stderr
    assert "bypass token" in result.stdout.lower()
    assert "(acknowledged) assets/factory/coin.new.json" in result.stdout


def test_bypass_token_in_earlier_commit_passes(repo: Path) -> None:
    """Bypass applies across the entire PR range, not just the tip commit."""
    base = _git(repo, "rev-parse", "HEAD").stdout.strip()
    _write_json(repo / "assets" / "factory" / "coin.a.json", {"is_verified": True})
    _commit(repo, "wip: verify a\n\n[allow-verified]")
    _write_json(repo / "assets" / "factory" / "coin.b.json", {"is_verified": True})
    head = _commit(repo, "also verify b")  # no token here

    result = _run_script(repo, base, head)

    assert result.returncode == 0, result.stderr


# --------------------------------------------------------------------------- #
# Edge cases                                                                  #
# --------------------------------------------------------------------------- #


def test_malformed_json_exits_with_code_2(repo: Path) -> None:
    """A broken JSON in head surfaces a script error (exit 2), not a silent pass."""
    base = _git(repo, "rev-parse", "HEAD").stdout.strip()
    broken = repo / "assets" / "factory" / "broken.json"
    broken.parent.mkdir(parents=True, exist_ok=True)
    broken.write_text("{ not json", encoding="utf-8")
    head = _commit(repo, "add broken json")

    result = _run_script(repo, base, head)

    assert result.returncode == 2
    assert "malformed JSON" in result.stderr


def test_missing_env_vars_exits_with_code_2(repo: Path) -> None:
    """Missing BASE_SHA/HEAD_SHA fails with a script-error exit."""
    env = {k: v for k, v in os.environ.items() if k not in ("BASE_SHA", "HEAD_SHA")}
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=str(repo),
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 2
    assert "BASE_SHA" in result.stderr
