"""Tests for the config script."""

from pathlib import Path
from typing import Any

import pytest

from scripts.config import (
    DEFAULT_NETWORKS,
    NetworkEndpoints,
    _get_default_endpoints,
    _get_endpoints_from_config,
    _load_config,
    _read_yaml,
    _repo_root,
    get_api_endpoint,
    get_rpc_endpoint,
)


######################################################################
# Fixtures
######################################################################

# Reusable full config with custom endpoints — used to assert config.yaml values
# override DEFAULT_NETWORKS. Values are fake but shaped like real URLs.
VALID_CONFIG = {
    "networks": {
        "mainnet": {
            "rpc": "https://custom-mainnet-rpc.example.com:443",
            "api": "https://custom-mainnet-api.example.com",
        },
        "testnet": {
            "rpc": "https://custom-testnet-rpc.example.com:443",
            "api": "https://custom-testnet-api.example.com",
        },
    }
}


def _write_yaml(path: Path, data: Any) -> Path:
    """Serialize a Python dict to YAML and write it to `path`.

    Used by tests that need a config.yaml/config.yml file on disk. Saves repeating
    the mkdir + yaml.safe_dump + write_text boilerplate in every test.
    """
    import yaml
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


@pytest.fixture
def patched_repo_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect config.py's `_repo_root()` to pytest's `tmp_path`.

    Without this, `_load_config()` would search the real repo for config.yaml and
    pollute/be polluted by the actual working tree. Every test that exercises
    config-file discovery must use this fixture.
    """
    monkeypatch.setattr("scripts.config._repo_root", lambda: tmp_path)
    return tmp_path


######################################################################
# Tests for _repo_root
######################################################################

def test_repo_root_returns_parent_of_scripts_directory() -> None:
    """_repo_root returns the directory that contains scripts/."""
    # Act: resolves via __file__ — no inputs needed
    root = _repo_root()

    # Assert: structural check — the returned path must contain scripts/config.py,
    # otherwise config.py is looking in the wrong place for config.yaml
    assert (root / "scripts").is_dir()
    assert (root / "scripts" / "config.py").is_file()


######################################################################
# Tests for _read_yaml
######################################################################

# ----------------
# Positive tests for _read_yaml
# ----------------

def test_read_yaml_returns_parsed_dict(tmp_path: Path) -> None:
    """_read_yaml parses a valid YAML mapping into a dict."""
    # Arrange: nested structure exercises both top-level and nested dict handling
    config_path = _write_yaml(tmp_path / "config.yaml", {"foo": "bar", "nested": {"x": 1}})

    # Act
    result = _read_yaml(config_path)

    # Assert: full equality — confirms both top-level and nested values parsed correctly
    assert result == {"foo": "bar", "nested": {"x": 1}}


def test_read_yaml_returns_empty_dict_when_file_empty(tmp_path: Path) -> None:
    """An empty YAML file returns {} thanks to the `... or {}` fallback in _read_yaml."""
    # Arrange: zero-byte file — yaml.safe_load returns None for empty input
    config_path = tmp_path / "config.yaml"
    config_path.write_text("", encoding="utf-8")

    # Act
    result = _read_yaml(config_path)

    # Assert: the fallback converts None → {} before the isinstance check,
    # so empty files don't raise "Invalid config root"
    assert result == {}


# ----------------
# Negative tests for _read_yaml
# ----------------

@pytest.mark.parametrize(
    "content",
    [
        "- item\n- another",   # valid YAML list at root — syntactically fine, structurally wrong
        '"just a string"',      # valid YAML scalar string
        "42",                   # valid YAML scalar int
    ],
    ids=["list-root", "string-root", "int-root"],
)
def test_read_yaml_raises_when_root_not_mapping(tmp_path: Path, content: str) -> None:
    """_read_yaml rejects YAML whose root is not a mapping (dict).

    Covers the `if not isinstance(data, dict)` guard — prevents downstream code
    from crashing with AttributeError when calling .get() on a list/scalar.
    """
    # Arrange: write raw YAML content (bypassing _write_yaml because we want specific shapes)
    config_path = tmp_path / "config.yaml"
    config_path.write_text(content, encoding="utf-8")

    # Act + Assert
    with pytest.raises(ValueError) as exc:
        _read_yaml(config_path)

    # Full-message equality — catches wording regressions in the error string
    assert exc.value.args[0] == f"Invalid config root in {config_path} (expected a mapping/object)"


######################################################################
# Tests for _load_config
######################################################################

# ----------------
# Positive tests for _load_config
# ----------------

def test_load_config_reads_config_yaml_when_present(patched_repo_root: Path) -> None:
    """_load_config reads config.yaml from repo root (primary config file)."""
    # Arrange: write only the primary .yaml file
    _write_yaml(patched_repo_root / "config.yaml", VALID_CONFIG)

    # Act
    result = _load_config()

    # Assert: full config returned, contents match what we wrote
    assert result == VALID_CONFIG


def test_load_config_reads_config_yml_when_yaml_absent(patched_repo_root: Path) -> None:
    """Both .yaml and .yml extensions are supported — .yml is an accepted alternative."""
    # Arrange: only the .yml file exists (no .yaml)
    _write_yaml(patched_repo_root / "config.yml", VALID_CONFIG)

    # Act
    result = _load_config()

    # Assert: _load_config iterates ("config.yaml", "config.yml") and picks whichever exists
    assert result == VALID_CONFIG


def test_load_config_prefers_yaml_over_yml_when_both_present(patched_repo_root: Path) -> None:
    """When both config files exist, config.yaml wins because it's first in the name tuple."""
    # Arrange: different contents in each file — lets us tell which one was read
    yaml_content = {"networks": {"mainnet": {"rpc": "from-yaml", "api": "from-yaml"}}}
    yml_content = {"networks": {"mainnet": {"rpc": "from-yml", "api": "from-yml"}}}
    _write_yaml(patched_repo_root / "config.yaml", yaml_content)
    _write_yaml(patched_repo_root / "config.yml", yml_content)

    # Act
    result = _load_config()

    # Assert: precedence is deterministic — .yaml always wins, documented behaviour
    assert result == yaml_content


# ----------------
# Negative tests for _load_config
# ----------------

def test_load_config_returns_none_when_neither_file_present(patched_repo_root: Path) -> None:
    """No config file means _load_config returns None — signals "use defaults"."""
    # Act: tmp_path is empty — neither config.yaml nor config.yml was written
    result = _load_config()

    # Assert: None triggers the fallback-to-DEFAULT_NETWORKS path in get_*_endpoint
    assert result is None


######################################################################
# Tests for _get_endpoints_from_config
######################################################################

# ----------------
# Positive tests for _get_endpoints_from_config
# ----------------

def test_get_endpoints_from_config_returns_endpoints_when_valid(patched_repo_root: Path) -> None:
    """Happy path: valid config.yaml produces a NetworkEndpoints dataclass."""
    # Arrange: write the canonical valid config
    _write_yaml(patched_repo_root / "config.yaml", VALID_CONFIG)

    # Act
    result = _get_endpoints_from_config("mainnet")

    # Assert: both fields extracted from the mainnet section
    assert result == NetworkEndpoints(
        rpc="https://custom-mainnet-rpc.example.com:443",
        api="https://custom-mainnet-api.example.com",
    )


def test_get_endpoints_from_config_strips_whitespace_from_values(patched_repo_root: Path) -> None:
    """Leading/trailing whitespace in rpc/api values is stripped before use.

    Common mistake: copy-paste leaves a trailing space or newline. Without stripping,
    the URL string would contain whitespace and break http requests.
    """
    # Arrange: spaces around rpc, tabs and newline around api
    padded = {
        "networks": {
            "mainnet": {
                "rpc": "  https://rpc.example.com  ",
                "api": "\thttps://api.example.com\n",
            }
        }
    }
    _write_yaml(patched_repo_root / "config.yaml", padded)

    # Act
    result = _get_endpoints_from_config("mainnet")

    # Assert: whitespace gone — final values are clean URLs
    assert result == NetworkEndpoints(rpc="https://rpc.example.com", api="https://api.example.com")


def test_get_endpoints_from_config_returns_none_when_no_config_file(patched_repo_root: Path) -> None:
    """No config file is not an error — returns None so callers can fall back to defaults."""
    # Act: tmp_path has no config file at all
    result = _get_endpoints_from_config("mainnet")

    # Assert: None (not a raise) — soft signal to use DEFAULT_NETWORKS
    assert result is None

def test_get_endpoints_from_config_returns_none_when_networks_key_missing(patched_repo_root: Path) -> None:
    """Config exists but lacks 'networks' key — None signals "use defaults"."""
    # Arrange: config file with unrelated content, no 'networks' key
    _write_yaml(patched_repo_root / "config.yaml", {"other": "content"})

    # Act
    result = _get_endpoints_from_config("mainnet")

    # Assert: graceful fallback, not an error
    assert result is None

def test_get_endpoints_from_config_returns_none_when_network_not_in_networks(patched_repo_root: Path) -> None:
    """Config defines some networks but not the one requested — fall back to defaults."""
    # Arrange: config defines testnet only
    config = {"networks": {"testnet": {"rpc": "r", "api": "a"}}}
    _write_yaml(patched_repo_root / "config.yaml", config)

    # Act: ask for mainnet (not in config)
    result = _get_endpoints_from_config("mainnet")

    # Assert: mainnet falls back, testnet config untouched
    assert result is None


# ----------------
# Negative tests for _get_endpoints_from_config
# ----------------


def test_get_endpoints_from_config_raises_when_networks_not_mapping(patched_repo_root: Path) -> None:
    """Common YAML mistake: writing `networks:` as a list instead of a mapping. """
    # Arrange: 'networks' is a list, not a dict
    _write_yaml(patched_repo_root / "config.yaml", {"networks": ["not", "a", "mapping"]})

    # Act + Assert: full-message equality catches any wording drift
    with pytest.raises(ValueError) as exc:
        _get_endpoints_from_config("mainnet")

    assert exc.value.args[0] == "Invalid config: 'networks' must be a mapping"


def test_get_endpoints_from_config_raises_when_network_not_mapping(patched_repo_root: Path) -> None:
    """networks.<name> must be a dict with rpc/api keys, not a scalar or list."""
    # Arrange: mainnet is a string instead of a mapping — e.g. user wrote `mainnet: foo`
    _write_yaml(patched_repo_root / "config.yaml", {"networks": {"mainnet": "not-a-mapping"}})

    # Act + Assert
    with pytest.raises(ValueError) as exc:
        _get_endpoints_from_config("mainnet")

    # Message includes the network name so the user knows which entry is broken
    assert exc.value.args[0] == "Invalid config: networks.mainnet must be a mapping"


def test_get_endpoints_from_config_raises_when_rpc_missing(patched_repo_root: Path) -> None:
    """Missing rpc key raises with a message naming both required fields."""
    # Arrange: only 'api' provided
    _write_yaml(patched_repo_root / "config.yaml", {"networks": {"mainnet": {"api": "a"}}})

    # Act + Assert
    with pytest.raises(ValueError) as exc:
        _get_endpoints_from_config("mainnet")

    # Error message mentions both fields so the user sees the full requirement
    assert exc.value.args[0] == "Invalid config: networks.mainnet must define both 'rpc' and 'api'"


def test_get_endpoints_from_config_raises_when_api_missing(patched_repo_root: Path) -> None:
    """Same as rpc-missing — both fields are required and the check uses a single branch."""
    # Arrange: only 'rpc' provided
    _write_yaml(patched_repo_root / "config.yaml", {"networks": {"mainnet": {"rpc": "r"}}})

    # Act + Assert
    with pytest.raises(ValueError) as exc:
        _get_endpoints_from_config("mainnet")

    # Same message as rpc-missing — the check is `if rpc is None or api is None`
    assert exc.value.args[0] == "Invalid config: networks.mainnet must define both 'rpc' and 'api'"


@pytest.mark.parametrize(
    "bad_rpc",
    ["", "   ", 42, []],
    ids=["empty", "whitespace-only", "int", "list"],
)
def test_get_endpoints_from_config_raises_when_rpc_invalid(
    patched_repo_root: Path,
    bad_rpc: Any,
) -> None:
    """rpc value must be a non-empty string — catches empty, whitespace, and wrong-type inputs."""
    # Arrange: rpc varies per parametrize case, api is always valid
    _write_yaml(patched_repo_root / "config.yaml", {"networks": {"mainnet": {"rpc": bad_rpc, "api": "a"}}})

    # Act + Assert: same error message regardless of which invalid shape triggered it
    with pytest.raises(ValueError) as exc:
        _get_endpoints_from_config("mainnet")

    assert exc.value.args[0] == "Invalid config: networks.mainnet.rpc must be a non-empty string"


@pytest.mark.parametrize(
    "bad_api",
    ["", "   ", 42, []],
    ids=["empty", "whitespace-only", "int", "list"],
)
def test_get_endpoints_from_config_raises_when_api_invalid(
    patched_repo_root: Path,
    bad_api: Any,
) -> None:
    """Mirror of the rpc test — api goes through the same isinstance + strip check."""
    # Arrange: api varies per parametrize case, rpc is always valid
    _write_yaml(patched_repo_root / "config.yaml", {"networks": {"mainnet": {"rpc": "r", "api": bad_api}}})

    # Act + Assert
    with pytest.raises(ValueError) as exc:
        _get_endpoints_from_config("mainnet")

    assert exc.value.args[0] == "Invalid config: networks.mainnet.api must be a non-empty string"


######################################################################
# Tests for _get_default_endpoints
######################################################################

# ----------------
# Positive tests for _get_default_endpoints
# ----------------

@pytest.mark.parametrize("network", ["mainnet", "testnet"])
def test_get_default_endpoints_returns_hardcoded_endpoints(network: str) -> None:
    """Known networks return the hardcoded DEFAULT_NETWORKS entries verbatim.

    Reading from the same DEFAULT_NETWORKS dict the function uses means the test
    tracks automatically if the hardcoded URLs are ever updated.
    """
    # Act
    result = _get_default_endpoints(network)

    # Assert: exact equality against the source of truth
    assert result == NetworkEndpoints(
        rpc=DEFAULT_NETWORKS[network]["rpc"],
        api=DEFAULT_NETWORKS[network]["api"],
    )


# ----------------
# Negative tests for _get_default_endpoints
# ----------------

@pytest.mark.parametrize(
    "network",
    ["", "unknown", "devnet", "Mainnet"],
    ids=["empty", "unknown", "devnet", "case-sensitive"],
)
def test_get_default_endpoints_raises_on_unknown_network(network: str) -> None:
    """Anything not exactly 'mainnet' or 'testnet' raises — lookup is case-sensitive."""
    # Act + Assert
    with pytest.raises(ValueError) as exc:
        _get_default_endpoints(network)

    # Full-message equality — the user-facing hint "Must be 'mainnet' or 'testnet'"
    assert exc.value.args[0] == f"Unknown network: {network}. Must be 'mainnet' or 'testnet'"


######################################################################
# Tests for get_rpc_endpoint / get_api_endpoint
######################################################################

# ----------------
# Positive tests for get_rpc_endpoint / get_api_endpoint
# ----------------

@pytest.mark.parametrize(
    "fn,field",
    [
        (get_rpc_endpoint, "rpc"),
        (get_api_endpoint, "api"),
    ],
    ids=["get_rpc", "get_api"],
)
def test_get_endpoint_uses_config_yaml_when_present(
    patched_repo_root: Path,
    fn: Any,
    field: str,
) -> None:
    """config.yaml values override the hardcoded DEFAULT_NETWORKS."""
    # Arrange: write a config with explicit custom URLs
    _write_yaml(patched_repo_root / "config.yaml", VALID_CONFIG)

    # Act
    result = fn("mainnet")

    # Assert: the custom URL wins — DEFAULT_NETWORKS is never consulted
    assert result == VALID_CONFIG["networks"]["mainnet"][field]


@pytest.mark.parametrize(
    "fn,field",
    [
        (get_rpc_endpoint, "rpc"),
        (get_api_endpoint, "api"),
    ],
    ids=["get_rpc", "get_api"],
)
def test_get_endpoint_falls_back_to_default_when_no_config(
    patched_repo_root: Path,
    fn: Any,
    field: str,
) -> None:
    """Zero-config case: without config.yaml, the hardcoded defaults are used."""
    # Act: patched_repo_root is empty, so _load_config() returns None
    result = fn("mainnet")

    # Assert: falls back to DEFAULT_NETWORKS[mainnet][field]
    assert result == DEFAULT_NETWORKS["mainnet"][field]


@pytest.mark.parametrize(
    "fn,field",
    [
        (get_rpc_endpoint, "rpc"),
        (get_api_endpoint, "api"),
    ],
    ids=["get_rpc", "get_api"],
)
def test_get_endpoint_falls_back_to_default_when_network_missing_from_config(
    patched_repo_root: Path,
    fn: Any,
    field: str,
) -> None:
    """Partial config: config.yaml has 'networks' but not the requested network."""
    # Arrange: config defines only testnet with a sentinel value we'd notice if wrongly used
    config = {"networks": {"testnet": {"rpc": "from-config", "api": "from-config"}}}
    _write_yaml(patched_repo_root / "config.yaml", config)

    # Act: ask for mainnet — which isn't in config
    result = fn("mainnet")

    # Assert: DEFAULT_NETWORKS['mainnet'] used, testnet's sentinel was never returned
    assert result == DEFAULT_NETWORKS["mainnet"][field]
    assert result != "from-config"


# ----------------
# Negative tests for get_rpc_endpoint / get_api_endpoint
# ----------------

@pytest.mark.parametrize(
    "fn",
    [get_rpc_endpoint, get_api_endpoint],
    ids=["get_rpc", "get_api"],
)
@pytest.mark.parametrize(
    "network",
    ["unknown", "devnet"],
)
def test_get_endpoint_raises_on_unknown_network_with_no_config(
    patched_repo_root: Path,
    fn: Any,
    network: str,
) -> None:
    """Unknown network + no config → the default-endpoint lookup raises."""
    # Act + Assert
    with pytest.raises(ValueError) as exc:
        fn(network)

    # Full-message assertion — error comes from _get_default_endpoints
    assert exc.value.args[0] == f"Unknown network: {network}. Must be 'mainnet' or 'testnet'"

