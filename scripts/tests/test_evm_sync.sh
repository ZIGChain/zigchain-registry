#!/usr/bin/env bash
# Integration test for `python scripts/generate_chain_registry.py --sync-evm`.
#
# Uses local bare repos for upstream + fork (file:// URLs), so the test runs
# offline. Network-dependent preflight (RPC liveness, chainid.network) is
# bypassed via --sync-evm-skip-preflight.
#
# What we verify:
#   - --sync-evm-dry-run writes intermediate eip155-<id>.json under generated/evm/
#     and does NOT push to the fork.
#   - A full sync (without dry-run) pushes a zigchain-evm-sync-* branch to the
#     fork bare repo, with the expected EIP-155 file content.
#   - Open-branch detection refuses a second sync without
#     --sync-evm-force-new-branch.
#   - --sync-evm-force-new-branch overrides that gate.
#
# Mirrors the fixture style of test_sync_repos.sh (local bare repos, GIT_AUTHOR/
# COMMITTER overrides, no real network).

set -euo pipefail

# ---- Locate repo + script under test ----------------------------------------

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
GEN_SCRIPT="$REPO_ROOT/scripts/generate_chain_registry.py"

if [ ! -f "$GEN_SCRIPT" ]; then
  echo "FATAL: $GEN_SCRIPT not found" >&2
  exit 1
fi

# Use venv python if present (covers stale-shebang case in pytest)
PYTHON_BIN="${PYTHON_BIN:-$REPO_ROOT/.venv/bin/python3}"
if [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN="$(command -v python3)"
fi

TEST_TMP="$(mktemp -d -t evm-sync-test-XXXXXX)"
trap 'rm -rf "$TEST_TMP"' EXIT

PASS_COUNT=0
FAIL_COUNT=0

pass() { PASS_COUNT=$((PASS_COUNT + 1)); printf '  ✅ %s\n' "$1"; }
fail() { FAIL_COUNT=$((FAIL_COUNT + 1)); printf '  ❌ %s\n' "$1"; }

# ---- Fixture setup ----------------------------------------------------------

# Mimic the minimal ethereum-lists/chains layout: a _data/chains/ directory
# with one pre-existing chain, plus _data/icons/. The bare upstream is what
# the script clones; the bare fork is what it pushes to.
setup_fixtures() {
  local upstream_work="$TEST_TMP/upstream_work"
  local upstream_bare="$TEST_TMP/upstream.git"
  local fork_bare="$TEST_TMP/fork.git"

  # Clean between test invocations so each test starts from a known state.
  rm -rf "$upstream_work" "$upstream_bare" "$fork_bare" "$TEST_TMP/fork_seed" "$TEST_TMP/fork_checkout"

  git init --quiet --bare --initial-branch=master "$upstream_bare"
  git init --quiet --bare --initial-branch=master "$fork_bare"

  git init --quiet --initial-branch=master "$upstream_work"
  (
    cd "$upstream_work"
    git config user.email "upstream@example.com"
    git config user.name "Upstream Maintainer"

    mkdir -p _data/chains _data/icons
    cat > _data/chains/eip155-1.json <<'JSON'
{
  "name": "Ethereum Mainnet",
  "chain": "ETH",
  "rpc": ["https://mainnet.example/"],
  "faucets": [],
  "nativeCurrency": {"name": "Ether", "symbol": "ETH", "decimals": 18},
  "infoURL": "https://ethereum.org",
  "shortName": "eth",
  "chainId": 1,
  "networkId": 1
}
JSON
    printf '# ethereum-lists/chains (test fixture)\n' > README.md

    git add -A
    git commit --quiet -m "initial fixture: eip155-1.json"
    git push --quiet "$upstream_bare" master
  )

  # Pre-populate the fork bare with master so push-with-rebase semantics work.
  git clone --quiet "$upstream_bare" "$TEST_TMP/fork_seed"
  (
    cd "$TEST_TMP/fork_seed"
    git push --quiet "$fork_bare" master
  )
  rm -rf "$TEST_TMP/fork_seed"
}

# Run the script under test in EVM-sync mode against the fixture repos.
# Args: $1 = extra args (space-separated). Output is captured to $TEST_TMP/run.out.
run_evm_sync() {
  local extra_args="$1"
  cd "$REPO_ROOT"
  # shellcheck disable=SC2086
  env \
    GIT_AUTHOR_EMAIL="test@example.com" \
    GIT_AUTHOR_NAME="EVM Sync Test" \
    GIT_COMMITTER_EMAIL="test@example.com" \
    GIT_COMMITTER_NAME="EVM Sync Test" \
    "$PYTHON_BIN" "$GEN_SCRIPT" \
      --sync-evm \
      --sync-evm-skip-preflight \
      --sync-evm-upstream-repo "file://$TEST_TMP/upstream.git" \
      --sync-evm-fork-repo "file://$TEST_TMP/fork.git" \
      $extra_args \
      >"$TEST_TMP/run.out" 2>&1
}

# ---- Test cases -------------------------------------------------------------

test_dry_run_writes_intermediates_no_push() {
  echo "▶ test_dry_run_writes_intermediates_no_push"
  setup_fixtures
  rm -rf "$REPO_ROOT/generated/evm"

  if ! run_evm_sync "--sync-evm-dry-run"; then
    cat "$TEST_TMP/run.out"
    fail "dry-run failed"
    return
  fi

  # Intermediate payloads must exist
  if [ -f "$REPO_ROOT/generated/evm/eip155-944.json" ] && \
     [ -f "$REPO_ROOT/generated/evm/eip155-2061.json" ]; then
    pass "intermediates written to generated/evm/"
  else
    fail "intermediates missing from generated/evm/"
    ls -la "$REPO_ROOT/generated/evm/" 2>&1 || true
  fi

  # No branches must have been pushed to the fork
  local pushed
  pushed=$(git --git-dir="$TEST_TMP/fork.git" for-each-ref --format='%(refname:short)' refs/heads/ | grep -c '^zigchain-evm-sync-' || true)
  if [ "$pushed" = "0" ]; then
    pass "dry-run did not push to fork"
  else
    fail "dry-run pushed $pushed branch(es) — should have been 0"
  fi

  # Output contains the dry-run banner
  if grep -q "sync-evm-dry-run" "$TEST_TMP/run.out"; then
    pass "dry-run banner printed"
  else
    fail "dry-run banner missing from output"
    cat "$TEST_TMP/run.out"
  fi
}

test_full_sync_pushes_branch_with_expected_payload() {
  echo "▶ test_full_sync_pushes_branch_with_expected_payload"
  setup_fixtures

  if ! run_evm_sync ""; then
    cat "$TEST_TMP/run.out"
    fail "full sync failed"
    return
  fi

  # Find the pushed branch (exactly one expected)
  local branch
  branch=$(git --git-dir="$TEST_TMP/fork.git" for-each-ref --format='%(refname:short)' refs/heads/ | grep '^zigchain-evm-sync-' | head -1 || true)
  if [ -z "$branch" ]; then
    fail "no zigchain-evm-sync-* branch on fork"
    cat "$TEST_TMP/run.out"
    return
  fi
  pass "branch pushed to fork: $branch"

  # Check out the pushed branch and verify the EIP-155 files
  local checkout_dir="$TEST_TMP/fork_checkout"
  rm -rf "$checkout_dir"
  git clone --quiet --branch "$branch" "$TEST_TMP/fork.git" "$checkout_dir"

  if [ -f "$checkout_dir/_data/chains/eip155-944.json" ] && \
     [ -f "$checkout_dir/_data/chains/eip155-2061.json" ]; then
    pass "EIP-155 files committed under _data/chains/"
  else
    fail "EIP-155 files missing from pushed branch"
  fi

  # Payload sanity: chainId 944 file actually claims chainId 944,
  # has no repo-local extensions, and uses camelCase
  local mainnet_payload
  mainnet_payload="$checkout_dir/_data/chains/eip155-944.json"
  if "$PYTHON_BIN" -c "
import json, sys
d = json.load(open('$mainnet_payload'))
assert d.get('chainId') == 944, 'chainId mismatch'
assert d.get('shortName') == 'zigchain', 'shortName mismatch'
assert 'cosmos_chain_id' not in d, 'cosmos_chain_id leaked'
assert 'icon_path' not in d, 'icon_path leaked'
assert 'is_verified' not in d, 'is_verified leaked'
assert 'chain_id' not in d, 'snake_case key leaked'
print('OK')
" >/dev/null 2>&1; then
    pass "mainnet payload shape is correct (camelCase, extensions stripped)"
  else
    fail "mainnet payload has wrong shape"
    "$PYTHON_BIN" -c "import json; print(json.dumps(json.load(open('$mainnet_payload')), indent=2))" || true
  fi

  # Upstream eip155-1.json (the fixture) must NOT have been deleted
  if [ -f "$checkout_dir/_data/chains/eip155-1.json" ]; then
    pass "existing upstream chain (eip155-1.json) preserved"
  else
    fail "existing upstream chain deleted by sync"
  fi

  # Commit message convention check
  cd "$checkout_dir"
  local commit_msg
  commit_msg=$(git log -1 --format='%s')
  cd - >/dev/null
  if echo "$commit_msg" | grep -q "ZIGChain EVM chains"; then
    pass "commit message follows convention: $commit_msg"
  else
    fail "commit message unexpected: $commit_msg"
  fi
}

test_open_branch_detection_blocks_second_sync() {
  echo "▶ test_open_branch_detection_blocks_second_sync"
  setup_fixtures

  # First sync should succeed
  if ! run_evm_sync ""; then
    cat "$TEST_TMP/run.out"
    fail "first sync failed"
    return
  fi
  pass "first sync succeeded"

  # Second sync (without --force-new-branch) must refuse
  if run_evm_sync ""; then
    fail "second sync should have failed but succeeded"
    return
  fi
  if grep -q "Existing sync branches on fork" "$TEST_TMP/run.out"; then
    pass "open-branch detection refused second sync"
  else
    fail "expected 'Existing sync branches on fork' error"
    cat "$TEST_TMP/run.out"
  fi
}

test_force_new_branch_overrides_block() {
  echo "▶ test_force_new_branch_overrides_block"
  setup_fixtures

  # First sync
  if ! run_evm_sync ""; then
    cat "$TEST_TMP/run.out"
    fail "first sync failed"
    return
  fi
  local first_branch_count
  first_branch_count=$(git --git-dir="$TEST_TMP/fork.git" for-each-ref --format='%(refname)' refs/heads/ | grep -c '^refs/heads/zigchain-evm-sync-' || true)

  # Force-new-branch must allow a second push. Sleep 1s so the timestamped
  # branch differs from the first.
  sleep 1
  if ! run_evm_sync "--sync-evm-force-new-branch"; then
    cat "$TEST_TMP/run.out"
    fail "force-new-branch sync failed"
    return
  fi
  local second_branch_count
  second_branch_count=$(git --git-dir="$TEST_TMP/fork.git" for-each-ref --format='%(refname)' refs/heads/ | grep -c '^refs/heads/zigchain-evm-sync-' || true)
  if [ "$second_branch_count" -gt "$first_branch_count" ]; then
    pass "force-new-branch added another branch ($first_branch_count → $second_branch_count)"
  else
    fail "force-new-branch did not add a new branch (still $second_branch_count)"
  fi
}

# ---- Driver ------------------------------------------------------------------

echo
echo "EVM sync integration test"
echo "  REPO_ROOT=$REPO_ROOT"
echo "  PYTHON_BIN=$PYTHON_BIN"
echo "  TEST_TMP=$TEST_TMP"
echo

test_dry_run_writes_intermediates_no_push
test_full_sync_pushes_branch_with_expected_payload
test_open_branch_detection_blocks_second_sync
test_force_new_branch_overrides_block

echo
echo "Results: $PASS_COUNT passed, $FAIL_COUNT failed."
exit $((FAIL_COUNT > 0 ? 1 : 0))
