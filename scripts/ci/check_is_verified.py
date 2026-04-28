#!/usr/bin/env python3
"""
CI check: fail if a PR introduces a new `is_verified: true` on any asset JSON.

Detects any `assets/**/*.json` file in the PR diff where `is_verified` goes
from false/null/missing to true (newly-added files with `is_verified: true`
included). Flipping true → false is not flagged.

Bypass: include the literal token `[allow-verified]` anywhere in any commit
message in the PR range. The choice of a commit-message token (rather than
a PR label) is deliberate: the `pull_request` trigger only grants read
permissions to `GITHUB_TOKEN` on fork PRs, so label/comment-based bypasses
would not work cross-repo. A commit-message bypass works for any PR source
and leaves a durable audit trail.

Environment variables:
    BASE_SHA  base commit of the PR (github.event.pull_request.base.sha)
    HEAD_SHA  head commit of the PR (github.event.pull_request.head.sha)

Exit codes:
    0  pass (no new verified, or bypass present)
    1  violation (newly-true is_verified and no bypass)
    2  script error (git invocation failed or malformed JSON on the head side)

Usable from a local shell too:
    BASE_SHA=$(git merge-base origin/main HEAD) HEAD_SHA=HEAD \\
        python3 scripts/ci/check_is_verified.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import PurePosixPath
from typing import Iterable, List, Tuple

BYPASS_TOKEN = "[allow-verified]"
ASSETS_PREFIX = "assets/"


def _run(args: List[str]) -> str:
    """Run a git command and return stdout. Raises on non-zero exit."""
    result = subprocess.run(args, check=True, capture_output=True, text=True)
    return result.stdout


def _changed_asset_files(base: str, head: str) -> List[str]:
    """Names of files under `assets/` added/modified between base and head."""
    # --diff-filter=AM restricts to Added/Modified — deletions can't add is_verified.
    out = _run(["git", "diff", "--name-only", "--diff-filter=AM", base, head, "--", "assets/"])
    return [line for line in out.splitlines() if line.strip().endswith(".json")]


class MalformedJson(Exception):
    """Raised by _is_verified_in_blob when the JSON at head is unparseable."""


def _is_verified_in_blob(base_or_head: str, path: str) -> bool:
    """Read `is_verified` from `<sha>:<path>`. Missing file/key → False."""
    try:
        content = _run(["git", "show", f"{base_or_head}:{path}"])
    except subprocess.CalledProcessError:
        # File didn't exist at that sha.
        return False
    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise MalformedJson(f"malformed JSON at {base_or_head}:{path}: {exc}") from exc
    return bool(data.get("is_verified"))


def _bypass_present(base: str, head: str) -> Tuple[bool, str]:
    """Scan commit subjects + bodies in base..head for the bypass token."""
    out = _run(["git", "log", "--format=%H%n%B%n---END---", f"{base}..{head}"])
    # Split on the sentinel so we can report the first matching commit.
    for chunk in out.split("---END---"):
        chunk = chunk.strip()
        if not chunk:
            continue
        if BYPASS_TOKEN in chunk:
            sha = chunk.splitlines()[0]
            return True, sha
    return False, ""


def find_violations(base: str, head: str) -> List[str]:
    """Return the list of files that newly set `is_verified: true` between base..head."""
    violations: List[str] = []
    for path in _changed_asset_files(base, head):
        if not PurePosixPath(path).as_posix().startswith(ASSETS_PREFIX):
            # Defensive: --diff-filter already scopes to assets/, but enforce explicitly.
            continue
        before = _is_verified_in_blob(base, path)
        after = _is_verified_in_blob(head, path)
        if after and not before:
            violations.append(path)
    return violations


def main() -> int:
    base = os.environ.get("BASE_SHA")
    head = os.environ.get("HEAD_SHA")
    if not base or not head:
        print("ERROR: BASE_SHA and HEAD_SHA environment variables are required.", file=sys.stderr)
        return 2

    try:
        violations = find_violations(base, head)
    except subprocess.CalledProcessError as exc:
        print(f"ERROR: git command failed: {exc.stderr or exc}", file=sys.stderr)
        return 2
    except MalformedJson as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if not violations:
        print("OK: no new `is_verified: true` introduced.")
        return 0

    bypassed, bypass_sha = _bypass_present(base, head)
    if bypassed:
        print(f"OK: {len(violations)} file(s) flipped is_verified=true, but bypass "
              f"token {BYPASS_TOKEN} found in commit {bypass_sha[:12]}.")
        for path in violations:
            print(f"  (acknowledged) {path}")
        return 0

    print("FAIL: the following files introduce `is_verified: true` without bypass:", file=sys.stderr)
    for path in violations:
        print(f"  {path}", file=sys.stderr)
    print(
        f"\nTo acknowledge the change intentionally, include the token "
        f"{BYPASS_TOKEN} anywhere in a commit message in this PR.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
