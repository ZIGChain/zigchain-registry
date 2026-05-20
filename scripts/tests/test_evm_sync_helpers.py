"""Unit tests for the EVM-sync helper functions.

Covers the pure / network-stub-friendly pieces — RPC probe, chainid.network
uniqueness check, fork-branch enumeration, URL parsing, PR-body template.

The end-to-end sync flow has its own integration test (test_evm_sync.sh).
"""

import io
import json
import socket
import subprocess
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest

from models import EvmChain
from scripts.generate_chain_registry import (
    CHAINID_NETWORK_CHAINS_URL,
    CHAINID_NETWORK_SHORTNAMES_URL,
    _assert_rpc_url_safe,
    _check_fork_branches,
    _check_upstream_existence,
    _check_upstream_uniqueness,
    _evm_pr_body_template,
    _http_get_json,
    _parse_github_url,
    _probe_rpc,
)


######################################################################
# Helpers
######################################################################


def _stub_urlopen_response(body: Any, status: int = 200) -> MagicMock:
    """Return a context-manager-compatible mock matching urllib.request.urlopen."""
    resp = MagicMock()
    resp.status = status
    resp.read.return_value = json.dumps(body).encode("utf-8")
    cm = MagicMock()
    cm.__enter__.return_value = resp
    cm.__exit__.return_value = False
    return cm


def _getaddrinfo_entries(*ips: str) -> List[tuple]:
    """Build a getaddrinfo-shaped result list for the given IP strings."""
    entries: List[tuple] = []
    for ip in ips:
        if ":" in ip:
            entries.append((socket.AF_INET6, socket.SOCK_STREAM, 0, "", (ip, 0, 0, 0)))
        else:
            entries.append((socket.AF_INET, socket.SOCK_STREAM, 0, "", (ip, 0)))
    return entries


def _patch_getaddrinfo(*ips: str):
    """Patch ``socket.getaddrinfo`` in the production module to return ``ips``."""
    return patch(
        "scripts.generate_chain_registry.socket.getaddrinfo",
        return_value=_getaddrinfo_entries(*ips),
    )


######################################################################
# _http_get_json
######################################################################


def test_http_get_json_happy_path() -> None:
    with patch("scripts.generate_chain_registry.urllib.request.urlopen") as urlopen:
        urlopen.return_value = _stub_urlopen_response({"foo": "bar"})
        result = _http_get_json("https://example.test/data.json")
    assert result == {"foo": "bar"}
    assert urlopen.call_count == 1


def test_http_get_json_retries_then_succeeds() -> None:
    """Transient failures retry with backoff and then succeed."""
    responses = [Exception("transient"), _stub_urlopen_response({"ok": True})]
    with patch("scripts.generate_chain_registry.urllib.request.urlopen", side_effect=responses), \
         patch("scripts.generate_chain_registry.time.sleep") as sleep:
        result = _http_get_json("https://example.test/data.json", max_retries=3)
    assert result == {"ok": True}
    assert sleep.call_count == 1  # one backoff between attempt 1 and attempt 2


def test_http_get_json_gives_up_after_max_retries() -> None:
    """All attempts fail → RuntimeError surfaces the underlying cause."""
    with patch("scripts.generate_chain_registry.urllib.request.urlopen", side_effect=Exception("nope")), \
         patch("scripts.generate_chain_registry.time.sleep"):
        with pytest.raises(RuntimeError, match="failed after 4 attempts"):
            _http_get_json("https://example.test/data.json", max_retries=3)


def test_http_get_json_4xx_treated_as_failure() -> None:
    with patch("scripts.generate_chain_registry.urllib.request.urlopen") as urlopen, \
         patch("scripts.generate_chain_registry.time.sleep"):
        urlopen.return_value = _stub_urlopen_response({}, status=404)
        with pytest.raises(RuntimeError, match="failed after"):
            _http_get_json("https://example.test/data.json", max_retries=1)


######################################################################
# _probe_rpc
######################################################################


def test_probe_rpc_success() -> None:
    """eth_chainId returns the expected hex chainId."""
    with _patch_getaddrinfo("1.1.1.1"), \
         patch("scripts.generate_chain_registry.urllib.request.urlopen") as urlopen:
        urlopen.return_value = _stub_urlopen_response({"jsonrpc": "2.0", "id": 1, "result": "0x3b0"})  # 944
        _probe_rpc("https://evm-rpc.test/", expected_chain_id=944)


def test_probe_rpc_wrong_chain_id_raises() -> None:
    """RPC returns a different chainId than we declared — refuse to sync."""
    with _patch_getaddrinfo("1.1.1.1"), \
         patch("scripts.generate_chain_registry.urllib.request.urlopen") as urlopen, \
         patch("scripts.generate_chain_registry.time.sleep"):
        urlopen.return_value = _stub_urlopen_response({"jsonrpc": "2.0", "id": 1, "result": "0x1"})  # 1, not 944
        with pytest.raises(RuntimeError, match="reports chainId 1, expected 944"):
            _probe_rpc("https://evm-rpc.test/", expected_chain_id=944, max_retries=0)


def test_probe_rpc_malformed_envelope_raises() -> None:
    """Missing 'result' key in JSON-RPC envelope is a hard failure."""
    with _patch_getaddrinfo("1.1.1.1"), \
         patch("scripts.generate_chain_registry.urllib.request.urlopen") as urlopen, \
         patch("scripts.generate_chain_registry.time.sleep"):
        urlopen.return_value = _stub_urlopen_response({"error": "method not supported"})
        with pytest.raises(RuntimeError, match="RPC probe failed"):
            _probe_rpc("https://evm-rpc.test/", expected_chain_id=944, max_retries=0)


def test_probe_rpc_invalid_hex_raises() -> None:
    """'result' that isn't valid hex should fail clearly."""
    with _patch_getaddrinfo("1.1.1.1"), \
         patch("scripts.generate_chain_registry.urllib.request.urlopen") as urlopen, \
         patch("scripts.generate_chain_registry.time.sleep"):
        urlopen.return_value = _stub_urlopen_response({"jsonrpc": "2.0", "id": 1, "result": "garbage"})
        with pytest.raises(RuntimeError, match="RPC probe failed"):
            _probe_rpc("https://evm-rpc.test/", expected_chain_id=944, max_retries=0)


def test_probe_rpc_retries_then_succeeds() -> None:
    """Transient HTTP failure recovers on retry."""
    responses = [
        Exception("network blip"),
        _stub_urlopen_response({"jsonrpc": "2.0", "id": 1, "result": "0x3b0"}),
    ]
    with _patch_getaddrinfo("1.1.1.1"), \
         patch("scripts.generate_chain_registry.urllib.request.urlopen", side_effect=responses), \
         patch("scripts.generate_chain_registry.time.sleep"):
        _probe_rpc("https://evm-rpc.test/", expected_chain_id=944)


######################################################################
# _assert_rpc_url_safe (SSRF guard)
######################################################################


def test_assert_rpc_url_safe_rejects_http_scheme() -> None:
    """Non-https schemes are refused before any DNS resolution."""
    with patch("scripts.generate_chain_registry.socket.getaddrinfo") as gai:
        with pytest.raises(RuntimeError, match="scheme must be https"):
            _assert_rpc_url_safe("http://rpc.example.com/")
        gai.assert_not_called()  # rejected before resolution


def test_assert_rpc_url_safe_rejects_missing_host() -> None:
    with pytest.raises(RuntimeError, match="has no host"):
        _assert_rpc_url_safe("https:///path-only")


def test_assert_rpc_url_safe_rejects_loopback_literal() -> None:
    with pytest.raises(RuntimeError, match="loopback/link-local/private/multicast/reserved"):
        _assert_rpc_url_safe("https://127.0.0.1/")


def test_assert_rpc_url_safe_rejects_link_local_imds() -> None:
    """The cloud-metadata canonical SSRF target."""
    with pytest.raises(RuntimeError, match="loopback/link-local"):
        _assert_rpc_url_safe("https://169.254.169.254/latest/meta-data")


@pytest.mark.parametrize("ip", ["10.0.0.1", "172.16.0.1", "192.168.1.1"])
def test_assert_rpc_url_safe_rejects_rfc1918_literals(ip: str) -> None:
    with pytest.raises(RuntimeError, match="loopback/link-local"):
        _assert_rpc_url_safe(f"https://{ip}/")


def test_assert_rpc_url_safe_rejects_ipv6_loopback() -> None:
    with pytest.raises(RuntimeError, match="loopback/link-local"):
        _assert_rpc_url_safe("https://[::1]/")


def test_assert_rpc_url_safe_rejects_ipv4_mapped_ipv6() -> None:
    """IPv4-mapped IPv6 form must not smuggle a private IPv4 past the guard."""
    with pytest.raises(RuntimeError, match="loopback/link-local"):
        _assert_rpc_url_safe("https://[::ffff:169.254.169.254]/")


def test_assert_rpc_url_safe_rejects_dns_to_private() -> None:
    """A public-looking hostname that resolves to RFC 1918 is refused."""
    with _patch_getaddrinfo("10.0.0.1"):
        with pytest.raises(RuntimeError, match="loopback/link-local"):
            _assert_rpc_url_safe("https://rpc.example.com/")


def test_assert_rpc_url_safe_rejects_multi_a_with_one_private() -> None:
    """Every resolved address is inspected — a single bad entry rejects the URL."""
    with _patch_getaddrinfo("1.1.1.1", "10.0.0.1"):
        with pytest.raises(RuntimeError, match="loopback/link-local"):
            _assert_rpc_url_safe("https://rpc.example.com/")


def test_assert_rpc_url_safe_propagates_resolution_failure() -> None:
    """An unresolvable host surfaces as a RuntimeError, not a leaked OSError."""
    with patch(
        "scripts.generate_chain_registry.socket.getaddrinfo",
        side_effect=OSError("no such host"),
    ):
        with pytest.raises(RuntimeError, match="Could not resolve 'nope.example.com'"):
            _assert_rpc_url_safe("https://nope.example.com/")


def test_assert_rpc_url_safe_accepts_public_https() -> None:
    """Happy path: public https URL whose host resolves to a public IP passes."""
    with _patch_getaddrinfo("1.1.1.1"):
        _assert_rpc_url_safe("https://rpc.example.com/")  # no raise


def test_probe_rpc_ssrf_guard_runs_before_urlopen() -> None:
    """_probe_rpc must reject a bad URL before opening any network connection."""
    with patch("scripts.generate_chain_registry.urllib.request.urlopen") as urlopen:
        with pytest.raises(RuntimeError, match="loopback/link-local"):
            _probe_rpc("https://127.0.0.1/", expected_chain_id=944, max_retries=0)
        urlopen.assert_not_called()


######################################################################
# _check_upstream_uniqueness
######################################################################


def test_check_upstream_uniqueness_no_collisions() -> None:
    chains_json: List[Dict[str, Any]] = [
        {"chainId": 1, "shortName": "eth"},
        {"chainId": 137, "shortName": "matic"},
    ]
    shortnames: Dict[str, str] = {"eth": "eip155:1", "matic": "eip155:137"}

    def fake_get(url: str, **kwargs: Any) -> Any:
        if url == CHAINID_NETWORK_CHAINS_URL:
            return chains_json
        if url == CHAINID_NETWORK_SHORTNAMES_URL:
            return shortnames
        raise AssertionError(f"unexpected URL: {url}")

    with patch("scripts.generate_chain_registry._http_get_json", side_effect=fake_get):
        result = _check_upstream_uniqueness([944, 2061], ["zigchain", "zigchain-testnet"])
    assert result == []


def test_check_upstream_uniqueness_chain_id_collision() -> None:
    """An existing entry with our chainId surfaces as an actionable error."""
    chains_json = [{"chainId": 944}]
    shortnames: Dict[str, str] = {}

    def fake_get(url: str, **kwargs: Any) -> Any:
        return chains_json if url == CHAINID_NETWORK_CHAINS_URL else shortnames

    with patch("scripts.generate_chain_registry._http_get_json", side_effect=fake_get):
        result = _check_upstream_uniqueness([944], ["zigchain"])
    assert len(result) == 1
    assert "chainId 944 already claimed" in result[0]
    assert "--sync-evm-update" in result[0]


def test_check_upstream_uniqueness_short_name_collision() -> None:
    chains_json: List[Dict[str, Any]] = []
    shortnames = {"zigchain": "eip155:999"}

    def fake_get(url: str, **kwargs: Any) -> Any:
        return chains_json if url == CHAINID_NETWORK_CHAINS_URL else shortnames

    with patch("scripts.generate_chain_registry._http_get_json", side_effect=fake_get):
        result = _check_upstream_uniqueness([944], ["zigchain"])
    assert len(result) == 1
    assert "shortName 'zigchain' already claimed" in result[0]
    assert "eip155:999" in result[0]


def test_check_upstream_uniqueness_propagates_network_failure() -> None:
    """If chainid.network is unreachable, the helper raises rather than passing silently."""
    with patch(
        "scripts.generate_chain_registry._http_get_json",
        side_effect=RuntimeError("network down"),
    ):
        with pytest.raises(RuntimeError, match="network down"):
            _check_upstream_uniqueness([944], ["zigchain"])


def test_check_upstream_uniqueness_handles_unexpected_shape() -> None:
    """Surface bad upstream shapes loudly — better than silently 'passing'."""
    with patch(
        "scripts.generate_chain_registry._http_get_json",
        return_value="not-a-list",
    ):
        with pytest.raises(RuntimeError, match="Unexpected chains.json shape"):
            _check_upstream_uniqueness([944], ["zigchain"])


######################################################################
# _check_upstream_existence
######################################################################


def test_check_upstream_existence_all_present() -> None:
    """Every chainId in our payload is already registered upstream → no errors."""
    chains_json = [{"chainId": 944}, {"chainId": 2061}, {"chainId": 1}]
    with patch(
        "scripts.generate_chain_registry._http_get_json",
        return_value=chains_json,
    ):
        assert _check_upstream_existence([944, 2061]) == []


def test_check_upstream_existence_missing_chain_id() -> None:
    """A chainId absent upstream surfaces as an actionable error pointing at --sync-evm."""
    chains_json = [{"chainId": 944}]
    with patch(
        "scripts.generate_chain_registry._http_get_json",
        return_value=chains_json,
    ):
        result = _check_upstream_existence([944, 2061])
    assert len(result) == 1
    assert "chainId 2061 is not registered upstream" in result[0]
    assert "--sync-evm (without --sync-evm-update)" in result[0]


def test_check_upstream_existence_propagates_network_failure() -> None:
    """chainid.network unreachable → raise instead of passing silently."""
    with patch(
        "scripts.generate_chain_registry._http_get_json",
        side_effect=RuntimeError("network down"),
    ):
        with pytest.raises(RuntimeError, match="network down"):
            _check_upstream_existence([944])


def test_check_upstream_existence_handles_unexpected_shape() -> None:
    """Surface bad upstream shapes loudly."""
    with patch(
        "scripts.generate_chain_registry._http_get_json",
        return_value={"not": "a list"},
    ):
        with pytest.raises(RuntimeError, match="Unexpected chains.json shape"):
            _check_upstream_existence([944])


######################################################################
# _check_fork_branches
######################################################################


def _fake_completed_process(stdout: str, returncode: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr="")


def test_check_fork_branches_parses_ls_remote_output() -> None:
    """Standard `git ls-remote --heads` output parses cleanly."""
    stdout = (
        "deadbeef\trefs/heads/zigchain-evm-sync-20260515-101010\n"
        "cafebabe\trefs/heads/zigchain-evm-sync-20260516-200000\n"
    )
    with patch(
        "scripts.generate_chain_registry._run",
        return_value=_fake_completed_process(stdout),
    ):
        branches = _check_fork_branches("https://github.com/ZIGChain/chains", prefix="zigchain-evm-sync")
    assert branches == [
        "zigchain-evm-sync-20260515-101010",
        "zigchain-evm-sync-20260516-200000",
    ]


def test_check_fork_branches_empty_when_no_matches() -> None:
    with patch(
        "scripts.generate_chain_registry._run",
        return_value=_fake_completed_process(""),
    ):
        result = _check_fork_branches("https://github.com/ZIGChain/chains", prefix="zigchain-evm-sync")
    assert result == []


def test_check_fork_branches_missing_fork_raises_actionable_error() -> None:
    """exit 128 from ls-remote → fork creation prompt."""
    err = subprocess.CalledProcessError(returncode=128, cmd=["git", "ls-remote"], output="repository not found")
    with patch("scripts.generate_chain_registry._run", side_effect=err):
        with pytest.raises(RuntimeError, match="Could not access fork"):
            _check_fork_branches(
                "https://github.com/ZIGChain/does-not-exist",
                prefix="zigchain-evm-sync",
            )


def test_check_fork_branches_other_git_errors_propagate() -> None:
    """Non-128 git failures bubble up untouched — operator decides what to do."""
    err = subprocess.CalledProcessError(returncode=1, cmd=["git"], output="some other failure")
    with patch("scripts.generate_chain_registry._run", side_effect=err):
        with pytest.raises(subprocess.CalledProcessError):
            _check_fork_branches(
                "https://github.com/ZIGChain/chains",
                prefix="zigchain-evm-sync",
            )


######################################################################
# _parse_github_url
######################################################################


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://github.com/ethereum-lists/chains", ("ethereum-lists", "chains")),
        ("https://github.com/ethereum-lists/chains.git", ("ethereum-lists", "chains")),
        ("https://github.com/ZIGChain/chains/", ("ZIGChain", "chains")),
        ("git@github.com:ZIGChain/chains.git", ("ZIGChain", "chains")),
        ("git@github.com:ZIGChain/chains", ("ZIGChain", "chains")),
    ],
)
def test_parse_github_url(url: str, expected: tuple) -> None:
    assert _parse_github_url(url) == expected


def test_parse_github_url_rejects_unrecognized() -> None:
    with pytest.raises(ValueError, match="Unrecognized GitHub URL"):
        _parse_github_url("https://example.com/foo/bar")


######################################################################
# _evm_pr_body_template
######################################################################


@pytest.fixture
def mainnet_chain() -> EvmChain:
    return EvmChain.model_validate({
        "chain_id": 944,
        "network_id": 944,
        "name": "ZIGChain",
        "short_name": "zigchain",
        "chain": "ZIG",
        "native_currency": {"name": "ZIG", "symbol": "ZIG", "decimals": 18},
        "rpc": ["https://evm-rpc.zigchain.com"],
        "info_url": "https://zigchain.com",
        "explorers": [{
            "name": "ZIGChain Explorer",
            "url": "https://explorer.zigchain.com",
            "standard": "EIP3091",
        }],
    })


@pytest.fixture
def testnet_chain() -> EvmChain:
    return EvmChain.model_validate({
        "chain_id": 2061,
        "network_id": 2061,
        "name": "ZIGChain Testnet",
        "short_name": "zigchain-testnet",
        "chain": "ZIG",
        "native_currency": {"name": "ZIG", "symbol": "ZIG", "decimals": 18},
        "rpc": ["https://evm-rpc-testnet.zigchain.com"],
        "faucets": ["https://faucet-testnet.zigchain.com"],
        "info_url": "https://zigchain.com",
        "status": "incubating",
    })


def test_pr_body_single_chain(mainnet_chain: EvmChain) -> None:
    body = _evm_pr_body_template([mainnet_chain])
    assert "ZIGChain" in body
    assert "944" in body
    assert "zigchain" in body
    assert "evm-rpc.zigchain.com" in body
    assert "explorer.zigchain.com" in body
    assert "eth_chainId" in body  # mentions liveness verification


def test_pr_body_multiple_chains(mainnet_chain: EvmChain, testnet_chain: EvmChain) -> None:
    body = _evm_pr_body_template([mainnet_chain, testnet_chain])
    assert "944" in body
    assert "2061" in body
    assert "faucet-testnet.zigchain.com" in body  # testnet faucet listed
    assert body.count("- **") >= 2  # one bullet per chain


def test_pr_body_empty_rpc_uses_reservation_language() -> None:
    """When rpc[] is empty (chainId-locking pattern), the PR body explains the
    reservation strategy and references the upstream precedent."""
    incubating = EvmChain.model_validate({
        "chain_id": 944,
        "network_id": 944,
        "name": "ZIGChain",
        "short_name": "zigchain",
        "chain": "ZIG",
        "native_currency": {"name": "ZIG", "symbol": "ZIG", "decimals": 18},
        "rpc": [],
        "info_url": "https://zigchain.com",
        "status": "incubating",
    })
    body = _evm_pr_body_template([incubating])
    # Bullet shows the chain with status and no RPC
    assert "944" in body
    assert "incubating" in body
    assert "RPC: _(none yet" in body
    # Footer references the reservation pattern + upstream precedent
    assert "Reserving chainId" in body
    assert "eip155-152" in body  # Redbelly Devnet reference
    # Liveness language is NOT in the empty-rpc variant
    assert "verified locally" not in body
