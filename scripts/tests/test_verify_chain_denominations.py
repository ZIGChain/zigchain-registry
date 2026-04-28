"""Tests for the verify_chain_denominations script."""

import io
import json
import sys
import urllib.error
import urllib.request
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import Any

import pytest

from scripts.verify_chain_denominations import (
    _MAX_PAGES,
    AssetRef,
    detect_network,
    fetch_all_denominations,
    fetch_all_factory_denominations,
    http_get_json,
    iter_asset_json_files,
    load_all_assets,
    load_asset_ref,
    main,
    registry_denoms_for_network,
    run_factory_list_denom_query,
    run_total_supply_query,
    verify_assets,
)


######################################################################
# Fixtures
######################################################################

# Real bech32-shaped creator addresses — used in factory base_denoms throughout the suite.
CREATOR_A = "zig1mcvwss65nk0yl7mvh3d83vw48dq7ue20ey3aa790ku5a96dkk9kqldcx2z"
CREATOR_B = "zig1lp5zex6685kd22agzskhqsylpnssxnweyuvsz4edr4p4ta92qf3q0jdnz9"
# Realistic IBC denom — 64-hex hash prefixed by "ibc/" (cosmos convention).
IBC_HASH = "ibc/ABC0000000000000000000000000000000000000000000000000000000000001"


class FakeResponse:
    """Minimal context-manager-compatible stand-in for urlopen()'s response."""

    def __init__(self, data: bytes) -> None:
        self._data = data

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: Any) -> bool:
        return False

    def read(self) -> bytes:
        return self._data


def _write_asset_file(path: Path, data: dict[str, Any]) -> Path:
    """Serialize a dict to JSON and write it to `path` (creates parent dirs). """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


@pytest.fixture
def valid_native_asset_json() -> dict[str, Any]:
    """Minimal valid native asset payload — only the four fields load_asset_ref reads."""
    return {"network": "mainnet", "type": "native", "base_denom": "uzig", "asset_id": "zig"}


@pytest.fixture
def valid_factory_asset_json() -> dict[str, Any]:
    """Minimal valid factory asset payload — base_denom uses real bech32 creator."""
    base = f"coin.{CREATOR_A}.mdfta"
    return {"network": "mainnet", "type": "factory", "base_denom": base, "asset_id": base}


@pytest.fixture
def valid_ibc_asset_json() -> dict[str, Any]:
    """Minimal valid IBC asset payload — base_denom uses the standard ibc/<hash> form."""
    return {"network": "mainnet", "type": "ibc", "base_denom": IBC_HASH, "asset_id": IBC_HASH}


@pytest.fixture
def patch_get_api_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace get_api_endpoint with a stub so HTTP-layer tests don't read config.yaml."""
    monkeypatch.setattr(
        "scripts.verify_chain_denominations.get_api_endpoint",
        lambda network: "https://api.example.com",
    )


######################################################################
# Tests for detect_network
######################################################################


@pytest.mark.parametrize(
    "chain_id,expected",
    [
        ("zig-test-2", "testnet"),                # canonical testnet chain ID
        ("zigchain-1", "mainnet"),                # canonical mainnet chain ID
        ("", "mainnet"),                          # empty string falls back to mainnet
        ("  zig-test-2  ", "testnet"),            # whitespace stripped before matching
        ("unknown", "mainnet"),                   # any unrecognized value defaults to mainnet
    ],
    ids=["testnet", "mainnet", "empty-defaults-mainnet", "strip-whitespace", "unknown-defaults-mainnet"],
)
def test_detect_network(
    chain_id: str,
    expected: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """detect_network maps ZIGCHAIN_CHAIN_ID env var to a network name with mainnet as default."""
    # Arrange: set the env var to the parametrized value
    monkeypatch.setenv("ZIGCHAIN_CHAIN_ID", chain_id)

    # Act
    result = detect_network()

    # Assert
    assert result == expected


def test_detect_network_env_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """When ZIGCHAIN_CHAIN_ID is not set at all, detect_network defaults to mainnet."""
    # Arrange: ensure the env var is absent (raising=False so delenv doesn't fail if missing)
    monkeypatch.delenv("ZIGCHAIN_CHAIN_ID", raising=False)

    # Act
    result = detect_network()

    # Assert
    assert result == "mainnet"


######################################################################
# Tests for http_get_json
######################################################################

# ----------------
# Positive tests for http_get_json
# ----------------

def test_http_get_json_returns_parsed_json(monkeypatch: pytest.MonkeyPatch) -> None:
    """Happy path: bytes from urlopen are decoded UTF-8 and parsed as JSON."""
    # Arrange: realistic supply response payload
    payload = {"supply": [{"denom": "uzig", "amount": "1000"}]}

    # Fake urlopen returns FakeResponse (which supports the `with` block)
    def fake_urlopen(req: Any, timeout: int) -> FakeResponse:
        return FakeResponse(json.dumps(payload).encode("utf-8"))

    monkeypatch.setattr(
        "scripts.verify_chain_denominations.urlopen",
        fake_urlopen,
    )

    # Act
    result = http_get_json("https://api.example.com/path")

    # Assert: full equality — verifies decode + parse round-trip preserves structure
    assert result == payload


# ----------------
# Negative tests for http_get_json
# ----------------

def test_http_get_json_raises_on_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """HTTPError (4xx/5xx response) is wrapped in RuntimeError with status + URL + body."""
    # Arrange: urlopen raises HTTPError carrying a response body via io.BytesIO
    # (HTTPError's `fp` argument requires a readable file-like object)
    url = "https://api.example.com/bad"

    def fake_urlopen(req: Any, timeout: int) -> Any:
        raise urllib.error.HTTPError(
            url=url, code=500, msg="Server Error", hdrs=None, fp=io.BytesIO(b"boom body")
        )

    monkeypatch.setattr("scripts.verify_chain_denominations.urlopen", fake_urlopen)

    # Act + Assert
    with pytest.raises(RuntimeError) as exc:
        http_get_json(url)

    # Full-message equality — catches any change to the error format
    assert str(exc.value) == f"HTTP error 500 for {url}: boom body"


def test_http_get_json_raises_on_url_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """URLError (DNS / connection failure / refused) is wrapped in RuntimeError."""
    # Arrange: simulate DNS failure
    url = "https://api.example.com/dns-fail"

    def fake_urlopen(req: Any, timeout: int) -> Any:
        raise urllib.error.URLError("name resolution failed")

    monkeypatch.setattr("scripts.verify_chain_denominations.urlopen", fake_urlopen)

    # Act + Assert
    with pytest.raises(RuntimeError) as exc:
        http_get_json(url)

    # startswith() — the suffix is `from URLError(...)` which varies by Python version
    assert str(exc.value).startswith(f"Network error for {url}:")


def test_http_get_json_raises_on_invalid_json(monkeypatch: pytest.MonkeyPatch) -> None:
    """Successful HTTP response with non-JSON body raises RuntimeError. """
    # Arrange: response body is HTML, not JSON
    url = "https://api.example.com/not-json"

    def fake_urlopen(req: Any, timeout: int) -> FakeResponse:
        return FakeResponse(b"<html>not json</html>")

    monkeypatch.setattr("scripts.verify_chain_denominations.urlopen", fake_urlopen)

    # Act + Assert
    with pytest.raises(RuntimeError) as exc:
        http_get_json(url)

    # startswith() — the suffix is the JSONDecodeError detail (line/col), Python-version dependent
    assert str(exc.value).startswith(f"Invalid JSON from {url}:")


######################################################################
# Tests for run_total_supply_query
######################################################################

def test_run_total_supply_query_builds_url_without_pagination(
    patch_get_api_endpoint: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Default call constructs the canonical bank-supply URL with default limit."""
    # Captures the URL that http_get_json receives so we can assert on it
    captured: list[str] = []

    def fake_http_get_json(url: str) -> dict[str, Any]:
        captured.append(url)
        return {}

    monkeypatch.setattr("scripts.verify_chain_denominations.http_get_json", fake_http_get_json)

    # Act
    run_total_supply_query("mainnet")

    # Assert: full URL — base + cosmos bank path + default pagination.limit=1000
    assert captured[0] == "https://api.example.com/cosmos/bank/v1beta1/supply?pagination.limit=1000"


def test_run_total_supply_query_includes_page_key_when_provided(
    patch_get_api_endpoint: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Passing page_key appends &pagination.key=<key> for fetching subsequent pages."""
    # Capture the URL via inline lambda fake (returns {} so query loop terminates)
    captured: list[str] = []
    monkeypatch.setattr(
        "scripts.verify_chain_denominations.http_get_json",
        lambda url: captured.append(url) or {},
    )

    # Act
    run_total_supply_query("mainnet", page_key="abc123")

    # Assert: both query params present (order unimportant)
    assert "pagination.limit=1000" in captured[0]
    assert "pagination.key=abc123" in captured[0]


@pytest.mark.parametrize("limit", [0, -1], ids=["zero", "negative"])
def test_run_total_supply_query_omits_limit_when_not_positive(
    patch_get_api_endpoint: None,
    monkeypatch: pytest.MonkeyPatch,
    limit: int,
) -> None:
    """limit <= 0 means "use server default" — pagination.limit param is omitted entirely.

    The source uses `if limit > 0` to decide whether to add the param. Both 0 and -1
    fall through, producing a URL with no query string at all.
    """
    captured: list[str] = []
    monkeypatch.setattr(
        "scripts.verify_chain_denominations.http_get_json",
        lambda url: captured.append(url) or {},
    )

    # Act
    run_total_supply_query("mainnet", limit=limit)

    # Assert: no query string — just base + path
    assert captured[0] == "https://api.example.com/cosmos/bank/v1beta1/supply"


def test_run_total_supply_query_strips_trailing_slash_from_base(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Trailing slash in the API base URL does not become "//" in the final URL.

    A misconfigured config.yaml might end the API URL with "/". The source uses
    `.rstrip("/")` to defend against this — the test pins it.
    """
    # Arrange: get_api_endpoint returns a URL with a trailing slash
    monkeypatch.setattr(
        "scripts.verify_chain_denominations.get_api_endpoint",
        lambda network: "https://api.example.com/",
    )
    captured: list[str] = []
    monkeypatch.setattr(
        "scripts.verify_chain_denominations.http_get_json",
        lambda url: captured.append(url) or {},
    )

    # Act
    run_total_supply_query("mainnet")

    # Assert: the slash between "com" and "/cosmos" is single, not double
    assert captured[0] == "https://api.example.com/cosmos/bank/v1beta1/supply?pagination.limit=1000"


######################################################################
# Tests for run_factory_list_denom_query
######################################################################

def test_run_factory_list_denom_query_builds_url_without_pagination(
    patch_get_api_endpoint: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Default call constructs the canonical factory-denom URL with default limit."""
    # Arrange: capture buffer for the URL that run_factory_list_denom_query builds
    captured: list[str] = []

    # Fake http_get_json: record the URL and return {} to end the loop without hitting the network
    monkeypatch.setattr(
        "scripts.verify_chain_denominations.http_get_json",
        lambda url: captured.append(url) or {},
    )

    # Act: no page_key — exercises the default (first-page) URL construction path
    run_factory_list_denom_query("mainnet")

    # Assert: full URL — base + /zigchain/factory/denom path + default pagination.limit=1000
    assert captured[0] == "https://api.example.com/zigchain/factory/denom?pagination.limit=1000"


def test_run_factory_list_denom_query_includes_page_key_when_provided(
    patch_get_api_endpoint: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Passing page_key appends &pagination.key=<key> for fetching subsequent pages."""
    # Arrange: same capture+stub pattern as the no-pagination test;
    captured: list[str] = []
    monkeypatch.setattr(
        "scripts.verify_chain_denominations.http_get_json",
        lambda url: captured.append(url) or {},
    )

    # Act: supply a page_key — mimics how fetch_all_factory_denominations requests page 2+
    run_factory_list_denom_query("mainnet", page_key="page2-key")

    # Assert: the key was URL-encoded into pagination.key; order doesn't matter so use `in`
    assert "pagination.key=page2-key" in captured[0]


######################################################################
# Tests for fetch_all_factory_denominations
######################################################################

# ----------------
# Edge-case tests for fetch_all_factory_denominations
# ----------------


def test_fetch_all_factory_denominations_infinite_pagination_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Loop terminates with RuntimeError when API returns the same next_key forever."""
    # Monkeypatch _MAX_PAGES to a small value so the test runs quickly
    monkeypatch.setattr("scripts.verify_chain_denominations._MAX_PAGES", 3)

    infinite_page = {"denom": [{"denom": "coin.a.x"}], "pagination": {"next_key": "stuck"}}

    monkeypatch.setattr(
        "scripts.verify_chain_denominations.run_factory_list_denom_query",
        lambda network, page_key=None: infinite_page,
    )

    with pytest.raises(RuntimeError, match="Pagination did not terminate"):
        fetch_all_factory_denominations("mainnet")


# ----------------
# Positive tests for fetch_all_factory_denominations
# ----------------

def test_fetch_all_factory_denominations_aggregates_across_pages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Denoms from multiple pages are combined into a single set."""
    # Arrange: iter of two scripted responses — page 1 has next_key="k2" so the loop
    # fetches again; page 2 has next_key=None so the loop terminates
    pages = iter([
        {"denom": [{"denom": "coin.a.one"}, {"denom": "coin.a.two"}],
         "pagination": {"next_key": "k2"}},
        {"denom": [{"denom": "coin.b.three"}], "pagination": {"next_key": None}},
    ])
    monkeypatch.setattr(
        "scripts.verify_chain_denominations.run_factory_list_denom_query",
        lambda *a, **kw: next(pages),
    )

    # Act: exercises the full pagination loop (two iterations)
    result = fetch_all_factory_denominations("mainnet")

    # Assert: set union of both pages — confirms nothing was lost between iterations
    assert result == {"coin.a.one", "coin.a.two", "coin.b.three"}



def test_fetch_all_factory_denominations_deduplicates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Same denom appearing twice in the response collapses to one entry in the result set."""
    # Arrange: single page with the same denom listed twice
    monkeypatch.setattr(
        "scripts.verify_chain_denominations.run_factory_list_denom_query",
        lambda *a, **kw: {"denom": [{"denom": "coin.a.one"}, {"denom": "coin.a.one"}]},
    )

    # Act
    result = fetch_all_factory_denominations("mainnet")

    # Assert: Set dedup kicks in — two identical inputs produce one entry
    assert result == {"coin.a.one"}


def test_fetch_all_factory_denominations_skips_non_dict_items(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-dict entries in the denom array are silently skipped (defensive `isinstance(item, dict)`)."""
    # Arrange: mix one valid dict with string, None, and int
    monkeypatch.setattr(
        "scripts.verify_chain_denominations.run_factory_list_denom_query",
        lambda *a, **kw: {"denom": [{"denom": "coin.a.one"}, "string", None, 42]},
    )

    # Act
    result = fetch_all_factory_denominations("mainnet")

    # Assert: only the well-formed dict is kept; no exception raised for the others
    assert result == {"coin.a.one"}


def test_fetch_all_factory_denominations_skips_empty_or_non_string_denom(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Dict items with missing/empty/non-string denom field are silently skipped."""
    # Arrange: one valid entry + three invalid shapes (empty string, int, missing key)
    monkeypatch.setattr(
        "scripts.verify_chain_denominations.run_factory_list_denom_query",
        lambda *a, **kw: {
            "denom": [
                {"denom": "coin.a.one"},
                {"denom": ""},
                {"denom": 42},
                {"creator": "missing-denom-field"},
            ],
        },
    )

    # Act
    result = fetch_all_factory_denominations("mainnet")

    # Assert: only the well-formed entry is kept
    assert result == {"coin.a.one"}


def test_fetch_all_factory_denominations_handles_missing_denom_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Response with no 'denom' key defaults to an empty list — loop exits cleanly with empty set."""
    # Arrange: response is shaped like a terminal page but omits the 'denom' key entirely
    # (the source's `response.get("denom", [])` default kicks in → iterates nothing)
    monkeypatch.setattr(
        "scripts.verify_chain_denominations.run_factory_list_denom_query",
        lambda *a, **kw: {"pagination": {"next_key": None}},
    )

    # Act
    result = fetch_all_factory_denominations("mainnet")

    # Assert: no crash, empty result — graceful handling of the missing key
    assert result == set()


def test_fetch_all_factory_denominations_handles_missing_pagination_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Response with no 'pagination' key is treated as a terminal page (loop ends)."""
    # Arrange: response has denoms but no pagination block — the source's
    # `response.get("pagination") or {}` defaults to {}, then next_key is None → break
    monkeypatch.setattr(
        "scripts.verify_chain_denominations.run_factory_list_denom_query",
        lambda *a, **kw: {"denom": [{"denom": "coin.a.one"}]},
    )

    # Act: must not infinite-loop — falls out after the first iteration
    result = fetch_all_factory_denominations("mainnet")

    # Assert: denoms captured, loop terminated cleanly
    assert result == {"coin.a.one"}


def test_fetch_all_factory_denominations_prints_progress(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Progress lines announce start, total rows fetched, and unique count."""
    # Arrange: single-page response with two distinct denoms
    monkeypatch.setattr(
        "scripts.verify_chain_denominations.run_factory_list_denom_query",
        lambda *a, **kw: {"denom": [{"denom": "coin.a.one"}, {"denom": "coin.a.two"}]},
    )

    # Act
    fetch_all_factory_denominations("mainnet")

    # Assert: all three expected lines appear in stdout
    out = capsys.readouterr().out
    assert "Fetching factory denoms from mainnet REST API..." in out
    assert "Total factory denoms fetched: 2" in out
    assert "Unique factory denoms discovered: 2" in out


# ----------------
# Negative tests for fetch_all_factory_denominations
# ----------------

def test_fetch_all_factory_denominations_returns_empty_on_runtime_error(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Graceful degradation: if the query raises, return empty set and warn (never raise)."""
    # Arrange: fake query raises RuntimeError — simulates the factory module being
    # unavailable on a chain that doesn't have it
    def fake_query(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("factory module unavailable")

    monkeypatch.setattr("scripts.verify_chain_denominations.run_factory_list_denom_query", fake_query)

    # Act: must NOT propagate the exception — caller (main) expects to continue
    result = fetch_all_factory_denominations("mainnet")

    # Assert: empty set + warning printed so the user knows factory verification was skipped
    assert result == set()
    out = capsys.readouterr().out
    assert "Warning: Could not fetch factory denoms: factory module unavailable" in out
    assert "Factory tokens will be verified against bank supply only." in out


def test_fetch_all_factory_denominations_raises_when_denom_not_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Malformed response where 'denom' is not a list raises ValueError (not silently skipped)."""
    # Arrange: response has a 'denom' key but its value is a string
    monkeypatch.setattr(
        "scripts.verify_chain_denominations.run_factory_list_denom_query",
        lambda *a, **kw: {"denom": "not-a-list"},
    )

    # Act + Assert: full-message equality locks the exact error string
    with pytest.raises(ValueError) as exc:
        fetch_all_factory_denominations("mainnet")

    assert exc.value.args[0] == "Unexpected response: 'denom' is not a list"


######################################################################
# Tests for fetch_all_denominations
######################################################################

# ----------------
# Edge-case tests for fetch_all_denominations
# ----------------


def test_fetch_all_denominations_infinite_pagination_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Loop terminates with RuntimeError when API returns the same next_key forever."""
    monkeypatch.setattr("scripts.verify_chain_denominations._MAX_PAGES", 3)

    infinite_page = {"supply": [{"denom": "uzig", "amount": "1"}], "pagination": {"next_key": "stuck"}}

    monkeypatch.setattr(
        "scripts.verify_chain_denominations.run_total_supply_query",
        lambda network, page_key=None: infinite_page,
    )

    with pytest.raises(RuntimeError, match="Pagination did not terminate"):
        fetch_all_denominations("mainnet")


# ----------------
# Positive tests for fetch_all_denominations
# ----------------

def test_fetch_all_denominations_aggregates_across_pages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bank-supply denoms from multiple pages are combined into a single set."""
    # Arrange: iter of two scripted responses — page 1 has next_key="k2" so the loop
    # fetches again; page 2 has next_key=None so the loop terminates. Supply entries
    # include "amount" fields to match real bank responses (only "denom" is used).
    pages = iter([
        {"supply": [{"denom": "uzig", "amount": "1"}, {"denom": "uother", "amount": "2"}],
         "pagination": {"next_key": "k2"}},
        {"supply": [{"denom": "ibc/HASH"}], "pagination": {"next_key": None}},
    ])
    monkeypatch.setattr(
        "scripts.verify_chain_denominations.run_total_supply_query",
        lambda *a, **kw: next(pages),
    )

    # Act: exercises the full pagination loop (two iterations)
    result = fetch_all_denominations("mainnet")

    # Assert: set union of both pages — the "amount" field is discarded, only denoms kept
    assert result == {"uzig", "uother", "ibc/HASH"}


def test_fetch_all_denominations_skips_non_dict_and_invalid_denom(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Defensive filters: non-dict items and dicts with invalid denom fields are skipped."""
    # Arrange: one valid entry + three invalid shapes — non-dict string, int-denom, and {}
    monkeypatch.setattr(
        "scripts.verify_chain_denominations.run_total_supply_query",
        lambda *a, **kw: {"supply": [{"denom": "uzig"}, "string-item", {"denom": 42}, {}]},
    )

    # Act
    result = fetch_all_denominations("mainnet")

    # Assert: only the well-formed entry survives; no exception raised for the others
    assert result == {"uzig"}


def test_fetch_all_denominations_deduplicates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Same denom appearing twice in the supply response collapses to one entry in the result set."""
    # Arrange: single page with the same denom listed twice
    monkeypatch.setattr(
        "scripts.verify_chain_denominations.run_total_supply_query",
        lambda *a, **kw: {"supply": [{"denom": "uzig"}, {"denom": "uzig"}]},
    )

    # Act
    result = fetch_all_denominations("mainnet")

    # Assert: Set dedup kicks in — two identical inputs produce one entry
    assert result == {"uzig"}


def test_fetch_all_denominations_handles_missing_supply_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Response with no 'supply' key defaults to an empty list — loop exits cleanly with empty set."""
    # Arrange: response shaped like a terminal page but omits the 'supply' key entirely
    # (the source's `response.get("supply") or []` fallback kicks in → iterates nothing)
    monkeypatch.setattr(
        "scripts.verify_chain_denominations.run_total_supply_query",
        lambda *a, **kw: {"pagination": {"next_key": None}},
    )

    # Act
    result = fetch_all_denominations("mainnet")

    # Assert: no crash, empty result — graceful handling of the missing key
    assert result == set()


def test_fetch_all_denominations_handles_missing_pagination_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Response with no 'pagination' key is treated as a terminal page (loop ends)."""
    # Arrange: response has supply but no pagination block — `response.get("pagination") or {}`
    # defaults to {}, then next_key is None → break
    monkeypatch.setattr(
        "scripts.verify_chain_denominations.run_total_supply_query",
        lambda *a, **kw: {"supply": [{"denom": "uzig"}]},
    )

    # Act: must not infinite-loop — falls out after the first iteration
    result = fetch_all_denominations("mainnet")

    # Assert: denoms captured, loop terminated cleanly
    assert result == {"uzig"}


def test_fetch_all_denominations_prints_progress(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Progress lines announce start, total supply rows fetched, and unique count."""
    # Arrange: single-page response with two distinct denoms — keeps counts trivially 2 == 2
    monkeypatch.setattr(
        "scripts.verify_chain_denominations.run_total_supply_query",
        lambda *a, **kw: {"supply": [{"denom": "uzig"}, {"denom": "uother"}]},
    )

    # Act
    fetch_all_denominations("mainnet")

    # Assert: all three expected progress lines appear in stdout
    out = capsys.readouterr().out
    assert "Fetching bank supply denoms from mainnet REST API..." in out
    assert "Total supply rows fetched: 2" in out
    assert "Unique denoms discovered: 2" in out


# ----------------
# Negative tests for fetch_all_denominations
# ----------------

def test_fetch_all_denominations_raises_when_supply_not_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Malformed response where 'supply' is not a list raises ValueError (not silently skipped)."""
    # Arrange: response has a 'supply' key but its value is a string
    monkeypatch.setattr(
        "scripts.verify_chain_denominations.run_total_supply_query",
        lambda *a, **kw: {"supply": "not-a-list"},
    )

    # Act + Assert: full-message equality locks the exact error string
    with pytest.raises(ValueError) as exc:
        fetch_all_denominations("mainnet")

    assert exc.value.args[0] == "Unexpected response: 'supply' is not a list"


######################################################################
# Tests for iter_asset_json_files
######################################################################


def test_iter_asset_json_files_finds_files_in_three_subdirs(tmp_path: Path) -> None:
    """Yields JSON files from all three hardcoded subdirs (native, factory, ibc)."""
    # Arrange: one file in each of the three subdirs the function iterates over
    _write_asset_file(tmp_path / "assets" / "native" / "zig.json", {})
    _write_asset_file(tmp_path / "assets" / "factory" / "coin.json", {})
    _write_asset_file(tmp_path / "assets" / "ibc" / "ibc_usdc.json", {})

    # Act: iter_asset_json_files is a generator; list() consumes all yields
    files = list(iter_asset_json_files(tmp_path))

    # Assert: one file per subdir — confirms the loop covers all three
    assert len(files) == 3


def test_iter_asset_json_files_recurses_into_nested_subdirs(tmp_path: Path) -> None:
    """rglob descends into nested directories (e.g. ibc/noble/) — not just the top level."""
    # Arrange: file placed inside ibc/noble/ rather than directly in ibc/
    # (the script's `d.rglob("*.json")` walks the full tree, not just immediate children)
    _write_asset_file(tmp_path / "assets" / "ibc" / "noble" / "usdc.json", {})

    # Act
    files = list(iter_asset_json_files(tmp_path))

    # Assert: rglob found the nested file — pins the recursive walk behaviour
    assert len(files) == 1
    assert files[0].name == "usdc.json"


def test_iter_asset_json_files_skips_missing_subdirs(tmp_path: Path) -> None:
    """Missing asset subdirs are silently skipped via `if not d.exists(): continue`."""
    # Arrange: create only native/; factory/ and ibc/ are absent —
    # exercises the `continue` branch on the two missing subdirs
    (tmp_path / "assets" / "native").mkdir(parents=True)
    _write_asset_file(tmp_path / "assets" / "native" / "zig.json", {})

    # Act: must not crash when factory/ibc paths don't exist
    files = list(iter_asset_json_files(tmp_path))

    # Assert: only the native file — missing dirs produced no error and no extra files
    assert len(files) == 1


def test_iter_asset_json_files_skips_non_files(tmp_path: Path) -> None:
    """rglob can return directories matching the pattern — filtered out by `if p.is_file()`."""
    # Arrange: a directory named like a JSON file; rglob("*.json") matches by name alone,
    (tmp_path / "assets" / "native" / "not-a-file.json").mkdir(parents=True)
    _write_asset_file(tmp_path / "assets" / "native" / "real.json", {})

    # Act
    files = list(iter_asset_json_files(tmp_path))

    # Assert: the directory is filtered out, only the real file is yielded
    assert len(files) == 1
    assert files[0].name == "real.json"


def test_iter_asset_json_files_skips_symlinks(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Symlinks in the assets/ tree are rejected — blocks arbitrary file-read via PR-supplied symlinks."""
    # Arrange: one real asset file + one symlink pointing to a file outside the repo root.
    _write_asset_file(tmp_path / "assets" / "native" / "real.json", {})
    outside_file = tmp_path.parent / "outside.json"
    outside_file.write_text("{}", encoding="utf-8")
    symlink_path = tmp_path / "assets" / "native" / "evil.json"
    symlink_path.symlink_to(outside_file)

    # Act
    files = list(iter_asset_json_files(tmp_path))

    # Assert: only the real file is yielded; symlink is skipped with a stderr warning.
    assert [p.name for p in files] == ["real.json"]
    assert "skipping symlink" in capsys.readouterr().err


######################################################################
# Tests for load_asset_ref
######################################################################

# ----------------
# Positive tests for load_asset_ref
# ----------------

def test_load_asset_ref_returns_asset_ref_for_valid_native(
    tmp_path: Path,
    valid_native_asset_json: dict[str, Any],
) -> None:
    """Valid native asset JSON produces an AssetRef with all fields populated."""
    # Arrange: write the canonical valid native payload (4 required fields) to disk
    path = _write_asset_file(tmp_path / "native.json", valid_native_asset_json)

    # Act
    result = load_asset_ref(path)

    # Assert: full dataclass equality — every field mapped correctly from JSON
    assert result == AssetRef(
        path=path,
        network="mainnet",
        asset_type="native",
        base_denom="uzig",
        asset_id="zig",
    )


def test_load_asset_ref_strips_schema_key_before_validation(
    tmp_path: Path,
    valid_factory_asset_json: dict[str, Any],
) -> None:
    """$schema key is popped so the manual validation does not see it."""
    # Arrange: inject $schema alongside the real fields (common in committed asset files)
    data = dict(valid_factory_asset_json)
    data["$schema"] = "../../schemas/asset.factory.schema.json"
    path = _write_asset_file(tmp_path / "factory.json", data)

    # Act: must not fail — the `.pop("$schema", None)` strips the key before any check
    result = load_asset_ref(path)

    # Assert: fields still parsed correctly despite $schema being on disk
    assert result.asset_type == "factory"
    assert result.base_denom == f"coin.{CREATOR_A}.mdfta"


def test_load_asset_ref_allows_missing_asset_id(
    tmp_path: Path,
    valid_native_asset_json: dict[str, Any],
) -> None:
    """asset_id is optional — when absent, the resulting AssetRef.asset_id is None."""
    # Arrange: remove the optional asset_id key (network/type/base_denom remain required)
    data = dict(valid_native_asset_json)
    del data["asset_id"]
    path = _write_asset_file(tmp_path / "native.json", data)

    # Act
    result = load_asset_ref(path)

    # Assert: asset_id defaults to None, everything else still loads
    assert result.asset_id is None


# ----------------
# Negative tests for load_asset_ref
# ----------------

def test_load_asset_ref_raises_when_json_not_object(tmp_path: Path) -> None:
    """JSON root must be an object — lists/scalars at root raise ValueError."""
    # Arrange: write a JSON list at root (bypasses _write_asset_file which expects a dict)
    path = tmp_path / "bad.json"
    path.write_text(json.dumps([1, 2, 3]), encoding="utf-8")

    # Act + Assert: full-message equality pins the exact error text
    with pytest.raises(ValueError) as exc:
        load_asset_ref(path)

    assert exc.value.args[0] == "Asset JSON root must be an object"


@pytest.mark.parametrize(
    "bad_value",
    [None, "", 42, True],
    ids=["none", "empty-string", "int", "bool"],
)
def test_load_asset_ref_raises_when_network_invalid(
    tmp_path: Path,
    valid_native_asset_json: dict[str, Any],
    bad_value: Any,
) -> None:
    """Missing, empty, or non-string network raises ValueError."""
    # Arrange: overwrite network with each invalid shape per parametrize case
    data = dict(valid_native_asset_json)
    data["network"] = bad_value
    path = _write_asset_file(tmp_path / "bad.json", data)

    # Act + Assert: same error message regardless of which bad shape triggered it
    with pytest.raises(ValueError) as exc:
        load_asset_ref(path)

    assert exc.value.args[0] == "Missing or invalid 'network'"


@pytest.mark.parametrize(
    "bad_value",
    [None, "", 42, True],
    ids=["none", "empty-string", "int", "bool"],
)
def test_load_asset_ref_raises_when_type_invalid(
    tmp_path: Path,
    valid_native_asset_json: dict[str, Any],
    bad_value: Any,
) -> None:
    """Missing, empty, or non-string type raises ValueError."""
    # Arrange: overwrite type with each invalid shape per parametrize case
    data = dict(valid_native_asset_json)
    data["type"] = bad_value
    path = _write_asset_file(tmp_path / "bad.json", data)

    # Act + Assert
    with pytest.raises(ValueError) as exc:
        load_asset_ref(path)

    assert exc.value.args[0] == "Missing or invalid 'type'"


@pytest.mark.parametrize(
    "bad_value",
    [None, "", 42, True],
    ids=["none", "empty-string", "int", "bool"],
)
def test_load_asset_ref_raises_when_base_denom_invalid(
    tmp_path: Path,
    valid_native_asset_json: dict[str, Any],
    bad_value: Any,
) -> None:
    """Missing, empty, or non-string base_denom raises ValueError."""
    # Arrange: overwrite base_denom with each invalid shape per parametrize case
    data = dict(valid_native_asset_json)
    data["base_denom"] = bad_value
    path = _write_asset_file(tmp_path / "bad.json", data)

    # Act + Assert
    with pytest.raises(ValueError) as exc:
        load_asset_ref(path)

    assert exc.value.args[0] == "Missing or invalid 'base_denom'"


@pytest.mark.parametrize(
    "bad_value",
    [42, True, []],
    ids=["int", "bool", "list"],
)
def test_load_asset_ref_raises_when_asset_id_non_string(
    tmp_path: Path,
    valid_native_asset_json: dict[str, Any],
    bad_value: Any,
) -> None:
    """asset_id, if present, must be a string (None is allowed — handled by the positive test)."""
    # Arrange: overwrite asset_id with a non-None, non-string value (the key is present, just wrong type)
    data = dict(valid_native_asset_json)
    data["asset_id"] = bad_value
    path = _write_asset_file(tmp_path / "bad.json", data)

    # Act + Assert
    with pytest.raises(ValueError) as exc:
        load_asset_ref(path)

    assert exc.value.args[0] == "Invalid 'asset_id'"


######################################################################
# Tests for load_all_assets
######################################################################

# ----------------
# Positive tests for load_all_assets
# ----------------

def test_load_all_assets_returns_assets_and_empty_errors_when_valid(
    tmp_path: Path,
    valid_native_asset_json: dict[str, Any],
    valid_factory_asset_json: dict[str, Any],
) -> None:
    """Valid asset files are loaded into AssetRef list, errors list stays empty."""
    # Arrange: one native + one factory file — both valid JSON with required fields
    _write_asset_file(tmp_path / "assets" / "native" / "zig.json", valid_native_asset_json)
    _write_asset_file(tmp_path / "assets" / "factory" / "mdfta.json", valid_factory_asset_json)

    # Act: walks all three subdirs and loads each .json file via load_asset_ref
    assets, errors = load_all_assets(tmp_path)

    # Assert: both loaded, zero errors — clean state for verify_assets to consume
    assert len(assets) == 2
    assert errors == []


def test_load_all_assets_returns_empty_when_no_asset_files(tmp_path: Path) -> None:
    """Missing assets/ directory returns ([], []) — not an error, just nothing to load."""
    # Act: tmp_path has no assets/ dir — iter_asset_json_files yields nothing
    assets, errors = load_all_assets(tmp_path)

    # Assert: empty tuple elements, no crash
    assert assets == []
    assert errors == []


# ----------------
# Negative tests for load_all_assets
# ----------------

def test_load_all_assets_collects_errors_and_continues(
    tmp_path: Path,
    valid_native_asset_json: dict[str, Any],
) -> None:
    """Corrupt files are recorded as error strings; valid files still load — no short-circuit."""
    # Arrange: one valid JSON + one malformed JSON — tests the except branch in the loop
    good_path = _write_asset_file(tmp_path / "assets" / "native" / "good.json", valid_native_asset_json)
    bad_path = tmp_path / "assets" / "native" / "bad.json"
    bad_path.write_text("{ broken json", encoding="utf-8")

    # Act: must process both files despite the bad one raising
    assets, errors = load_all_assets(tmp_path)

    # Assert: good file loaded, bad file's error captured with the file path as prefix
    assert len(assets) == 1
    assert assets[0].path == good_path
    assert len(errors) == 1
    assert errors[0].startswith(f"{bad_path}:")


######################################################################
# Tests for verify_assets
######################################################################

# ----------------
# Positive tests for verify_assets
# ----------------

def test_verify_assets_checks_only_selected_network(tmp_path: Path) -> None:
    """Assets on a different network are skipped — only the requested network is checked."""
    # Arrange: one mainnet asset (in chain_denoms) + one testnet asset (not checked)
    assets = [
        AssetRef(path=tmp_path / "a", network="mainnet", asset_type="native", base_denom="uzig"),
        AssetRef(path=tmp_path / "b", network="testnet", asset_type="native", base_denom="uatom"),
    ]

    # Act: verify mainnet only — testnet asset should be invisible
    missing, warnings, checked = verify_assets(assets, {"uzig"}, set(), "mainnet")

    # Assert: checked==1 proves the testnet asset was skipped, not counted
    assert checked == 1
    assert missing == []
    assert warnings == []


def test_verify_assets_all_present_returns_empty(tmp_path: Path) -> None:
    """Clean bill of health: all three asset types present on-chain → no missing, no warnings."""
    # Arrange: native in bank supply, factory in factory module, IBC in bank supply
    base_factory = f"coin.{CREATOR_A}.mdfta"
    assets = [
        AssetRef(path=tmp_path / "n", network="mainnet", asset_type="native", base_denom="uzig"),
        AssetRef(path=tmp_path / "f", network="mainnet", asset_type="factory", base_denom=base_factory),
        AssetRef(path=tmp_path / "i", network="mainnet", asset_type="ibc", base_denom=IBC_HASH),
    ]
    chain_denoms = {"uzig", IBC_HASH}
    factory_denoms = {base_factory}

    # Act: all denoms found in their respective sets
    missing, warnings, checked = verify_assets(assets, chain_denoms, factory_denoms, "mainnet")

    # Assert: all 3 checked, nothing flagged
    assert checked == 3
    assert missing == []
    assert warnings == []


def test_verify_assets_native_missing_is_warning_not_failure(tmp_path: Path) -> None:
    """Native assets absent from bank supply get a warning (they may have zero supply)."""
    # Arrange: native not in chain_denoms — legitimate for native tokens
    path = tmp_path / "zig.json"
    assets = [AssetRef(path=path, network="mainnet", asset_type="native", base_denom="uzig")]

    # Act: bank supply is empty, so "uzig" is absent
    missing, warnings, checked = verify_assets(assets, set(), set(), "mainnet")

    # Assert: warning (not missing) — native tokens get softer treatment
    assert checked == 1
    assert missing == []
    assert len(warnings) == 1
    assert warnings[0] == f"{path}: native base_denom 'uzig' not present in total-supply"


def test_verify_assets_factory_falls_back_to_bank_when_factory_module_unavailable(
    tmp_path: Path,
) -> None:
    """When factory_denoms is empty (module query failed), factory tokens degrade to bank check with warning."""
    # Arrange: empty factory_denoms signals the factory module was unreachable; bank also empty
    path = tmp_path / "mdfta.json"
    base = f"coin.{CREATOR_A}.mdfta"
    assets = [AssetRef(path=path, network="mainnet", asset_type="factory", base_denom=base)]

    # Act: both sets empty — factory falls back to the bank-supply warning path
    missing, warnings, checked = verify_assets(assets, set(), set(), "mainnet")

    # Assert: warning (not missing) — can't be sure it's absent since factory module was down
    assert checked == 1
    assert missing == []
    assert len(warnings) == 1
    assert warnings[0] == (
        f"{path}: factory base_denom '{base}' not present in bank supply "
        "(factory module query unavailable, may have zero supply)"
    )


def test_verify_assets_factory_in_bank_when_factory_module_unavailable(
    tmp_path: Path,
) -> None:
    """Factory module empty but factory denom IS in bank supply → passes silently (no warning)."""
    # Arrange: factory_denoms empty (module down), but bank supply has the denom
    base = f"coin.{CREATOR_A}.mdfta"
    assets = [AssetRef(path=tmp_path / "mdfta.json", network="mainnet", asset_type="factory", base_denom=base)]

    # Act: factory_denoms is empty so the bank-fallback path runs; denom IS in chain_denoms
    missing, warnings, checked = verify_assets(assets, {base}, set(), "mainnet")

    # Assert: no warning, no missing — denom found in bank supply, silent pass
    assert checked == 1
    assert missing == []
    assert warnings == []


def test_verify_assets_empty_assets_list(tmp_path: Path) -> None:
    """Empty assets list → returns ([], [], 0) with no errors."""
    # Act: nothing to check
    missing, warnings, checked = verify_assets([], {"uzig"}, set(), "mainnet")

    # Assert: all counts zero, no side effects
    assert checked == 0
    assert missing == []
    assert warnings == []


# ----------------
# Negative tests for verify_assets
# ----------------

def test_verify_assets_factory_missing_from_factory_module_is_missing(tmp_path: Path) -> None:
    """Factory module is available but doesn't list this asset → hard failure (missing)."""
    # Arrange: factory_denoms has one entry, but NOT our asset's base_denom
    path = tmp_path / "mdfta.json"
    base = f"coin.{CREATOR_A}.mdfta"
    assets = [AssetRef(path=path, network="mainnet", asset_type="factory", base_denom=base)]

    # Act: factory_denoms is non-empty (module is working) but doesn't include our asset
    missing, warnings, checked = verify_assets(assets, set(), {"coin.other.one"}, "mainnet")

    # Assert: reported missing (authoritative check failed) — no soft warning here
    assert checked == 1
    assert len(missing) == 1
    assert missing[0] == assets[0]
    assert warnings == []


def test_verify_assets_ibc_missing_is_failure(tmp_path: Path) -> None:
    """IBC assets absent from bank supply are always a hard failure — no soft warning path."""
    # Arrange: IBC asset not in bank supply (there's no factory-module fallback for IBC)
    path = tmp_path / "ibc.json"
    assets = [AssetRef(path=path, network="mainnet", asset_type="ibc", base_denom=IBC_HASH)]

    # Act: empty bank supply — IBC has no alternative verification path
    missing, warnings, checked = verify_assets(assets, set(), set(), "mainnet")

    # Assert: missing (not warning) — IBC must be in bank supply or it's gone
    assert checked == 1
    assert len(missing) == 1
    assert missing[0] == assets[0]
    assert warnings == []


######################################################################
# Tests for registry_denoms_for_network
######################################################################

def test_registry_denoms_for_network_filters_by_network(tmp_path: Path) -> None:
    """Only base_denoms belonging to the requested network are included in the result set."""
    # Arrange: one mainnet asset + one testnet asset — only mainnet should appear
    assets = [
        AssetRef(path=tmp_path / "a", network="mainnet", asset_type="native", base_denom="uzig"),
        AssetRef(path=tmp_path / "b", network="testnet", asset_type="native", base_denom="utestnet"),
    ]

    # Act: ask for mainnet
    result = registry_denoms_for_network(assets, "mainnet")

    # Assert: testnet's base_denom excluded — only mainnet's "uzig" present
    assert result == {"uzig"}


def test_registry_denoms_for_network_returns_both_when_same_network(tmp_path: Path) -> None:
    """Two assets on the same network with different base_denoms → both in the result set."""
    # Arrange: two distinct mainnet assets
    assets = [
        AssetRef(path=tmp_path / "a", network="mainnet", asset_type="native", base_denom="uzig"),
        AssetRef(path=tmp_path / "b", network="mainnet", asset_type="ibc", base_denom=IBC_HASH),
    ]

    # Act: ask for mainnet
    result = registry_denoms_for_network(assets, "mainnet")

    # Assert: both denoms present — different base_denoms, same network
    assert result == {"uzig", IBC_HASH}


def test_registry_denoms_for_network_returns_empty_when_wrong_network(tmp_path: Path) -> None:
    """Assets exist but all belong to a different network → empty set returned."""
    # Arrange: two mainnet assets
    assets = [
        AssetRef(path=tmp_path / "a", network="mainnet", asset_type="native", base_denom="uzig"),
        AssetRef(path=tmp_path / "b", network="mainnet", asset_type="ibc", base_denom=IBC_HASH),
    ]

    # Act: ask for testnet — neither asset matches
    result = registry_denoms_for_network(assets, "testnet")

    # Assert: empty set — no mainnet denoms leak into a testnet query
    assert result == set()


def test_registry_denoms_for_network_deduplicates(tmp_path: Path) -> None:
    """Same base_denom from multiple assets collapses to one entry (set comprehension dedup)."""
    # Arrange: two separate AssetRefs with identical base_denom "uzig"
    assets = [
        AssetRef(path=tmp_path / "a", network="mainnet", asset_type="native", base_denom="uzig"),
        AssetRef(path=tmp_path / "b", network="mainnet", asset_type="native", base_denom="uzig"),
    ]

    # Act
    result = registry_denoms_for_network(assets, "mainnet")

    # Assert: set comprehension produces one entry, not two
    assert result == {"uzig"}


######################################################################
# Tests for main
######################################################################

# ----------------
# Positive tests for main
# ----------------

def test_main_success_exits_zero(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    valid_native_asset_json: dict[str, Any],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Happy path: all registry assets found on-chain → exit 0 with success message."""
    # Arrange: native 'uzig' in registry; mock chain supply also has 'uzig'
    _write_asset_file(tmp_path / "assets" / "native" / "zig.json", valid_native_asset_json)
    # Set CLI args — default network (no --network flag)
    monkeypatch.setattr(sys, "argv", ["prog", "--repo-root", str(tmp_path)])
    # Fake bank supply — returns {"uzig"} so the native asset is found on-chain
    monkeypatch.setattr(
        "scripts.verify_chain_denominations.fetch_all_denominations",
        lambda *a, **kw: {"uzig"},
    )
    # Fake factory module — empty set (no factory assets in this test)
    monkeypatch.setattr(
        "scripts.verify_chain_denominations.fetch_all_factory_denominations",
        lambda *a, **kw: set(),
    )

    # Act: main() always calls sys.exit() — pytest.raises catches it
    with pytest.raises(SystemExit) as exc:
        main()

    # Assert: exit 0 with full success output
    assert exc.value.code == 0
    out = capsys.readouterr().out

    assert "Loaded asset files: 1" in out
    assert "Results:" in out
    assert "Assets checked (network=mainnet): 1" in out
    assert "Missing denoms: 0" in out
    assert "All assets verified successfully for this network." in out
    assert "(Factory tokens verified against factory module, others against bank supply)" in out


def test_main_network_flag_overrides_env_var(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    valid_native_asset_json: dict[str, Any],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """--network flag takes precedence over ZIGCHAIN_CHAIN_ID env var."""
    # Arrange: env says mainnet (zigchain-1), but flag says testnet — asset is testnet
    testnet_asset = {**valid_native_asset_json, "network": "testnet"}
    _write_asset_file(tmp_path / "assets" / "native" / "zig.json", testnet_asset)
    # Env var points to mainnet — should be overridden by --network testnet
    monkeypatch.setenv("ZIGCHAIN_CHAIN_ID", "zigchain-1")
    # CLI args with explicit --network testnet
    monkeypatch.setattr(
        sys, "argv", ["prog", "--network", "testnet", "--repo-root", str(tmp_path)],
    )
    # Fake bank supply — has uzig so the testnet asset passes verification
    monkeypatch.setattr(
        "scripts.verify_chain_denominations.fetch_all_denominations",
        lambda *a, **kw: {"uzig"},
    )
    # Fake factory module — empty (not needed for this test)
    monkeypatch.setattr(
        "scripts.verify_chain_denominations.fetch_all_factory_denominations",
        lambda *a, **kw: set(),
    )

    # Act
    with pytest.raises(SystemExit) as exc:
        main()

    # Assert: flag wins — "testnet" printed, not "mainnet" from env (readouterr captures stdout)
    assert exc.value.code == 0
    assert "Using network: testnet" in capsys.readouterr().out


def test_main_uses_detect_network_when_no_flag(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    valid_native_asset_json: dict[str, Any],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """No --network flag → main falls back to detect_network() which reads the env var."""
    # Arrange: env var says testnet; no --network flag passed
    testnet_asset = {**valid_native_asset_json, "network": "testnet"}
    _write_asset_file(tmp_path / "assets" / "native" / "zig.json", testnet_asset)
    # Env var maps to testnet — detect_network() will resolve it
    monkeypatch.setenv("ZIGCHAIN_CHAIN_ID", "zig-test-2")
    # CLI args without --network — forces detect_network() fallback path
    monkeypatch.setattr(sys, "argv", ["prog", "--repo-root", str(tmp_path)])
    # Fake bank supply — has uzig so verification passes
    monkeypatch.setattr(
        "scripts.verify_chain_denominations.fetch_all_denominations",
        lambda *a, **kw: {"uzig"},
    )
    # Fake factory module — empty (not needed for this test)
    monkeypatch.setattr(
        "scripts.verify_chain_denominations.fetch_all_factory_denominations",
        lambda *a, **kw: set(),
    )

    # Act
    with pytest.raises(SystemExit) as exc:
        main()

    # Assert: detect_network() resolved env var to "testnet"
    assert exc.value.code == 0
    assert "Using network: testnet" in capsys.readouterr().out


def test_main_factory_query_failure_is_warning_not_fatal(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    valid_native_asset_json: dict[str, Any],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Factory module failure is a warning, not fatal — main still exits 0."""
    # Arrange: valid asset on disk, bank supply is fine, but factory query raises
    _write_asset_file(tmp_path / "assets" / "native" / "zig.json", valid_native_asset_json)
    # CLI args — default network
    monkeypatch.setattr(sys, "argv", ["prog", "--repo-root", str(tmp_path)])
    # Fake bank supply — has uzig so verification passes
    monkeypatch.setattr(
        "scripts.verify_chain_denominations.fetch_all_denominations",
        lambda *a, **kw: {"uzig"},
    )

    # Fake factory query — raises RuntimeError (simulates factory module being unreachable)
    def raise_factory(*args: Any, **kwargs: Any) -> set[str]:
        raise RuntimeError("factory module down")

    monkeypatch.setattr(
        "scripts.verify_chain_denominations.fetch_all_factory_denominations", raise_factory
    )

    # Act
    with pytest.raises(SystemExit) as exc:
        main()

    # Assert: still exits 0 — factory failure is non-blocking; warning in stderr
    assert exc.value.code == 0
    assert "Warning: Could not fetch factory denoms: factory module down" in capsys.readouterr().err


def test_main_max_missing_registry_caps_output_lines(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    valid_native_asset_json: dict[str, Any],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """--max-missing-registry truncates the list of chain-only denoms in stdout."""
    # Arrange: chain has 10 extra denoms not in registry; limit set to 2
    _write_asset_file(tmp_path / "assets" / "native" / "zig.json", valid_native_asset_json)
    # CLI args — cap the missing-registry list to 2 entries
    monkeypatch.setattr(sys, "argv", [
        "prog", "--repo-root", str(tmp_path), "--max-missing-registry", "2",
    ])
    # Fake bank supply — uzig (in registry) + 10 extras (not in registry → triggers the list)
    extras = {f"extra-{i}" for i in range(10)}
    monkeypatch.setattr(
        "scripts.verify_chain_denominations.fetch_all_denominations",
        lambda *a, **kw: extras | {"uzig"},
    )
    # Fake factory module — empty (not needed for this test)
    monkeypatch.setattr(
        "scripts.verify_chain_denominations.fetch_all_factory_denominations",
        lambda *a, **kw: set(),
    )

    # Act
    with pytest.raises(SystemExit) as exc:
        main()

    # Assert: only 2 denoms shown, then the truncation line — prevents flooding CI logs
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "On-chain denoms missing from registry (base_denom):" in out
    assert "... and 8 more" in out


def test_main_fail_on_missing_registry_flag_exits_one(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    valid_native_asset_json: dict[str, Any],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """--fail-on-missing-registry makes chain-only denoms a hard failure (exit 1)."""
    # Arrange: chain has "extra-on-chain" which is not in the single-asset registry
    _write_asset_file(tmp_path / "assets" / "native" / "zig.json", valid_native_asset_json)
    # CLI args — enable --fail-on-missing-registry to make extras a hard failure
    monkeypatch.setattr(
        sys, "argv", ["prog", "--repo-root", str(tmp_path), "--fail-on-missing-registry"],
    )
    # Fake bank supply — "uzig" + "extra-on-chain" (the extra triggers the failure)
    monkeypatch.setattr(
        "scripts.verify_chain_denominations.fetch_all_denominations",
        lambda *a, **kw: {"uzig", "extra-on-chain"},
    )
    # Fake factory module — empty (not needed for this test)
    monkeypatch.setattr(
        "scripts.verify_chain_denominations.fetch_all_factory_denominations",
        lambda *a, **kw: set(),
    )

    # Act
    with pytest.raises(SystemExit) as exc:
        main()

    # Assert: exits 1 with the --fail-on-missing-registry failure message (line 441)
    assert exc.value.code == 1
    out = capsys.readouterr().out
    assert "Verification failed: on-chain denoms missing from registry (--fail-on-missing-registry enabled)" in out


def test_main_prints_warnings_section_when_native_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    valid_native_asset_json: dict[str, Any],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """When verify_assets returns warnings (e.g. native absent from bank), main prints the Warnings section."""
    # Arrange: native "uzig" in registry but NOT in bank supply → warning from verify_assets
    _write_asset_file(tmp_path / "assets" / "native" / "zig.json", valid_native_asset_json)
    # CLI args — default network
    monkeypatch.setattr(sys, "argv", ["prog", "--repo-root", str(tmp_path)])
    # Fake bank supply — empty, so native "uzig" absent triggers a warning (not a failure)
    monkeypatch.setattr(
        "scripts.verify_chain_denominations.fetch_all_denominations",
        lambda *a, **kw: set(),
    )
    # Fake factory module — empty (not needed for this test)
    monkeypatch.setattr(
        "scripts.verify_chain_denominations.fetch_all_factory_denominations",
        lambda *a, **kw: set(),
    )

    # Act
    with pytest.raises(SystemExit) as exc:
        main()

    # Assert: exits 0 (native missing is a warning, not a failure) and warnings section printed
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "Warnings:" in out
    assert "native base_denom 'uzig' not present in total-supply" in out


def test_main_max_missing_registry_zero_suppresses_printing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    valid_native_asset_json: dict[str, Any],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """--max-missing-registry 0 means don't print the chain-only denoms list at all."""
    # Arrange: chain has an extra denom not in registry; limit set to 0 (suppress)
    _write_asset_file(tmp_path / "assets" / "native" / "zig.json", valid_native_asset_json)
    monkeypatch.setattr(sys, "argv", [
        "prog", "--repo-root", str(tmp_path), "--max-missing-registry", "0",
    ])
    monkeypatch.setattr(
        "scripts.verify_chain_denominations.fetch_all_denominations",
        lambda *a, **kw: {"uzig", "extra-on-chain"},
    )
    monkeypatch.setattr(
        "scripts.verify_chain_denominations.fetch_all_factory_denominations",
        lambda *a, **kw: set(),
    )

    # Act
    with pytest.raises(SystemExit) as exc:
        main()

    # Assert: exits 0; summary count line still prints but the denom LIST is suppressed
    assert exc.value.code == 0
    out = capsys.readouterr().out
    # Summary line (always printed) mentions the count — that's expected
    assert "On-chain denoms missing from registry (network=mainnet): 1" in out
    # The actual denom list header and individual denoms should NOT appear
    assert "On-chain denoms missing from registry (base_denom):" not in out
    assert "extra-on-chain" not in out


# ----------------
# Negative tests for main
# ----------------

def test_main_repo_root_missing_exits_one(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Nonexistent --repo-root exits 1 before any chain queries run."""
    # Arrange: point to a path that doesn't exist
    monkeypatch.setattr(sys, "argv", ["prog", "--repo-root", "/nonexistent/path/xyz"])

    # Act
    with pytest.raises(SystemExit) as exc:
        main()

    # Assert: early exit with descriptive error on stderr
    assert exc.value.code == 1
    assert "Error: Repository root does not exist:" in capsys.readouterr().err


def test_main_load_errors_exit_one(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Corrupt asset files cause load_all_assets to collect errors → main exits 1."""
    # Arrange: write a malformed JSON file that load_asset_ref can't parse
    bad_path = tmp_path / "assets" / "native" / "bad.json"
    bad_path.parent.mkdir(parents=True)
    bad_path.write_text("{ broken json", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["prog", "--repo-root", str(tmp_path)])

    # Act: main detects the load errors and exits before querying the chain
    with pytest.raises(SystemExit) as exc:
        main()

    # Assert: exit 1 with error list printed to stderr, includes the bad file path
    assert exc.value.code == 1
    err = capsys.readouterr().err
    assert "Errors while reading asset files:" in err
    assert str(bad_path) in err


def test_main_chain_query_failure_exits_one(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    valid_native_asset_json: dict[str, Any],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Bank-supply query failure is fatal — main exits 1 with traceback."""
    # Arrange: valid asset on disk, but the bank-supply query raises
    _write_asset_file(tmp_path / "assets" / "native" / "zig.json", valid_native_asset_json)
    # CLI args — default network; assets load fine, but chain query will fail
    monkeypatch.setattr(sys, "argv", ["prog", "--repo-root", str(tmp_path)])

    # Fake bank query — raises RuntimeError (unlike factory, bank failure is fatal)
    def raise_boom(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("chain unreachable")

    # Replace fetch_all_denominations so it raises instead of hitting the network
    monkeypatch.setattr(
        "scripts.verify_chain_denominations.fetch_all_denominations", raise_boom
    )

    # Act
    with pytest.raises(SystemExit) as exc:
        main()

    # Assert: exit 1 with the exception message in stderr
    assert exc.value.code == 1
    assert "Fatal error while querying chain: chain unreachable" in capsys.readouterr().err


def test_main_missing_denoms_exit_one(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    valid_ibc_asset_json: dict[str, Any],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Registry asset not on-chain → main prints the missing list and exits 1."""
    # Arrange: IBC asset in registry but bank supply is empty — IBC has no fallback path
    path = _write_asset_file(tmp_path / "assets" / "ibc" / "usdc.json", valid_ibc_asset_json)
    # CLI args — default network
    monkeypatch.setattr(sys, "argv", ["prog", "--repo-root", str(tmp_path)])
    # Fake bank supply — empty, so IBC asset is missing (triggers exit 1)
    monkeypatch.setattr(
        "scripts.verify_chain_denominations.fetch_all_denominations",
        lambda *a, **kw: set(),
    )
    # Fake factory module — empty (IBC doesn't use factory module anyway)
    monkeypatch.setattr(
        "scripts.verify_chain_denominations.fetch_all_factory_denominations",
        lambda *a, **kw: set(),
    )

    # Act
    with pytest.raises(SystemExit) as exc:
        main()

    # Assert: exit 1 with the missing-assets section printed, including the file path
    assert exc.value.code == 1
    out = capsys.readouterr().out
    assert "Missing assets (base_denom not found in bank total-supply):" in out
    assert str(path.relative_to(tmp_path)) in out


def test_main_missing_asset_without_asset_id_omits_id_in_output(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """When a missing asset has no asset_id, the output line omits the ' asset_id=...' part."""
    # Arrange: asset JSON without asset_id — load_asset_ref allows it (asset_id is optional)
    no_id_asset = {"network": "mainnet", "type": "ibc", "base_denom": IBC_HASH}
    path = _write_asset_file(tmp_path / "assets" / "ibc" / "usdc.json", no_id_asset)
    # CLI args — default network
    monkeypatch.setattr(sys, "argv", ["prog", "--repo-root", str(tmp_path)])
    # Fake bank supply — empty, so IBC asset is missing (triggers exit 1)
    monkeypatch.setattr(
        "scripts.verify_chain_denominations.fetch_all_denominations",
        lambda *a, **kw: set(),
    )
    # Fake factory module — empty (IBC doesn't use it)
    monkeypatch.setattr(
        "scripts.verify_chain_denominations.fetch_all_factory_denominations",
        lambda *a, **kw: set(),
    )

    # Act
    with pytest.raises(SystemExit) as exc:
        main()

    # Assert: exit 1; output line has no "asset_id=" (the f-string produces empty string)
    assert exc.value.code == 1
    out = capsys.readouterr().out
    assert "asset_id=" not in out
    assert f"(ibc) base_denom={IBC_HASH}" in out


######################################################################
# Tests for AssetRef dataclass
######################################################################

def test_asset_ref_is_frozen(tmp_path: Path) -> None:
    """AssetRef is a frozen dataclass — mutation after construction raises FrozenInstanceError."""
    # Arrange: construct a valid AssetRef
    ref = AssetRef(path=tmp_path, network="mainnet", asset_type="native", base_denom="uzig")

    # Act + Assert: attempting to overwrite a field raises FrozenInstanceError
    with pytest.raises(FrozenInstanceError) as exc:
        ref.network = "testnet"  # type: ignore[misc]

    # Assert: error message names the field that was mutated
    assert "network" in str(exc.value)

