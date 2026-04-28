from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

import yaml


DEFAULT_NETWORKS: Dict[str, Dict[str, str]] = {
    "mainnet": {
        # "rpc": "https://rpc.zigchain.com:443",
        "rpc": "https://public-zigchain-rpc.numia.xyz",
        # "api": "https://api.zigchain.com",
        "api": "https://public-zigchain-lcd.numia.xyz",
    },
    "testnet": {
        # "rpc": "https://testnet-rpc.zigchain.com:443",
        "rpc": "https://public-zigchain-testnet-rpc.numia.xyz",
        # "api": "https://testnet-api.zigchain.com",
        "api": "https://public-zigchain-testnet-lcd.numia.xyz",
    },
}


@dataclass(frozen=True)
class NetworkEndpoints:
    rpc: str
    api: str


def _repo_root() -> Path:
    # scripts/config.py -> repo root is one level up from scripts/
    return Path(__file__).resolve().parents[1]


def _read_yaml(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Invalid config root in {path} (expected a mapping/object)")
    return data


def _load_config() -> Optional[Dict[str, Any]]:
    root = _repo_root()
    for name in ("config.yaml", "config.yml"):
        p = root / name
        if p.exists():
            return _read_yaml(p)
    return None


def _get_endpoints_from_config(network: str) -> Optional[NetworkEndpoints]:
    cfg = _load_config()
    if cfg is None:
        return None

    networks = cfg.get("networks")
    if networks is None:
        return None
    if not isinstance(networks, dict):
        raise ValueError("Invalid config: 'networks' must be a mapping")

    net = networks.get(network)
    if net is None:
        return None
    if not isinstance(net, dict):
        raise ValueError(f"Invalid config: networks.{network} must be a mapping")

    rpc = net.get("rpc")
    api = net.get("api")
    if rpc is None or api is None:
        raise ValueError(f"Invalid config: networks.{network} must define both 'rpc' and 'api'")
    if not isinstance(rpc, str) or not rpc.strip():
        raise ValueError(f"Invalid config: networks.{network}.rpc must be a non-empty string")
    if not isinstance(api, str) or not api.strip():
        raise ValueError(f"Invalid config: networks.{network}.api must be a non-empty string")

    return NetworkEndpoints(rpc=rpc.strip(), api=api.strip())


def _get_default_endpoints(network: str) -> NetworkEndpoints:
    if network not in DEFAULT_NETWORKS:
        raise ValueError(f"Unknown network: {network}. Must be 'mainnet' or 'testnet'")
    d = DEFAULT_NETWORKS[network]
    return NetworkEndpoints(rpc=d["rpc"], api=d["api"])


def get_rpc_endpoint(network: str) -> str:
    """
    Returns the RPC endpoint for the given network.

    Source order:
    1) config.yaml / config.yml (repo root)
    2) DEFAULT_NETWORKS (hard-coded fallback)
    """
    endpoints = _get_endpoints_from_config(network) or _get_default_endpoints(network)
    return endpoints.rpc


def get_api_endpoint(network: str) -> str:
    """
    Returns the REST API endpoint for the given network.

    Source order:
    1) config.yaml / config.yml (repo root)
    2) DEFAULT_NETWORKS (hard-coded fallback)
    """
    endpoints = _get_endpoints_from_config(network) or _get_default_endpoints(network)
    return endpoints.api

