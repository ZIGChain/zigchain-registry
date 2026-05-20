"""Pydantic models for ZIGChain EVM chain metadata.

EVM chains are chain-level metadata (chainId, RPCs, explorers, faucets) and
deliberately do NOT inherit from AssetBase — they describe a chain, not an
asset on a chain. The canonical record lives in chains/evm/*.json and is
transformed to ethereum-lists/chains' EIP-155 format at sync time.

The model mirrors the field set required by
https://github.com/ethereum-lists/chains/blob/master/tools/schema/chainSchema.json
plus three repo-local extensions that are stripped before upstream emit:

- cosmos_chain_id: links an EVM chain (e.g. 944) to the corresponding Cosmos
  chain ID (e.g. zigchain-1). Internal consumers join the two registries through
  this field; ethereum-lists never sees it.
- icon_path:      local path to a logo asset for use by ZIGChain UIs that
                  consume this repo directly. The ethereum-lists 'icon' field
                  (an IPFS-pinned slug) is a separate, out-of-scope concern
                  tracked for a future PR.
- is_verified:    matches the existing repo convention used by other models
                  (see AssetBase.is_verified). Stripped from upstream payload.
"""

import re
import warnings
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator

from models.base import _reject_non_list


# Allowed values for ethereum-lists/chains 'explorers[].standard'. ligi (upstream
# maintainer) rejects PRs that claim EIP3091 compliance without it. Use "none" if
# the explorer is not EIP-3091 compliant.
_EXPLORER_STANDARDS = ("EIP3091", "none")

# Convention enforced by upstream: lifecycle status of the chain.
_CHAIN_STATUSES = ("active", "incubating", "deprecated")


class NativeCurrency(BaseModel):
    """Native currency of an EVM chain (e.g. ZIG with 18 decimals)."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="Human-readable name of the native currency (e.g. 'ZIG').",
        json_schema_extra={"title": "Currency Name", "example": "ZIG"},
    )
    symbol: str = Field(
        ...,
        min_length=1,
        max_length=16,
        description="Ticker symbol of the native currency.",
        json_schema_extra={"title": "Currency Symbol", "example": "ZIG"},
    )
    decimals: int = Field(
        ...,
        ge=0,
        le=36,
        description="Decimal places of the native currency's smallest unit. EVM convention is 18.",
        json_schema_extra={"title": "Decimals", "example": 18},
    )

    @field_validator("name", "symbol", mode="before")
    @classmethod
    def _reject_bytes_strings(cls, value, info):
        if isinstance(value, bytes):
            raise ValueError(f"{info.field_name} must be a string, not bytes")
        return value

    @field_validator("decimals", mode="before")
    @classmethod
    def _decimals_not_bool(cls, value):
        if isinstance(value, bool):
            raise ValueError("decimals cannot be bool, must be an integer")
        return value


class Explorer(BaseModel):
    """Block explorer entry for an EVM chain."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(
        ...,
        min_length=1,
        max_length=128,
        description="Human-readable explorer name (e.g. 'ZIGChain Explorer').",
        json_schema_extra={"title": "Explorer Name", "example": "ZIGChain Explorer"},
    )
    url: HttpUrl = Field(
        ...,
        description="Base URL of the explorer (no trailing slash).",
        json_schema_extra={"title": "Explorer URL", "example": "https://explorer.zigchain.com"},
    )
    standard: Literal["EIP3091", "none"] = Field(
        ...,
        description=(
            "Explorer URL standard. Use 'EIP3091' only if the explorer actually implements EIP-3091 "
            "(https://eips.ethereum.org/EIPS/eip-3091); otherwise use 'none'. ligi rejects false claims."
        ),
        json_schema_extra={"title": "Standard", "example": "EIP3091"},
    )
    icon: Optional[str] = Field(
        None,
        min_length=1,
        max_length=64,
        description="Optional icon slug referenced from ethereum-lists/_data/icons/<slug>.json.",
    )

    @field_validator("name", "icon", mode="before")
    @classmethod
    def _reject_bytes_strings(cls, value, info):
        if isinstance(value, bytes):
            raise ValueError(f"{info.field_name} must be a string, not bytes")
        return value


class EvmChain(BaseModel):
    """Canonical EVM chain metadata for a ZIGChain network.

    Source of truth for the chain entry that ends up in
    https://github.com/ethereum-lists/chains as _data/chains/eip155-<chain_id>.json,
    plus a few repo-local fields (cosmos_chain_id, icon_path, is_verified) that
    internal consumers can use but that are stripped before upstream emit.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_ref: Optional[str] = Field(
        None,
        alias="$schema",
        description="Optional JSON Schema reference for tooling. Not emitted upstream.",
        json_schema_extra={
            "title": "JSON Schema Reference",
            "example": "../../schemas/chain.evm.schema.json",
        },
    )

    # --- ethereum-lists/chains REQUIRED fields ---

    chain_id: int = Field(
        ...,
        gt=0,
        description="EIP-155 chain ID. Must be globally unique across ethereum-lists/chains.",
        json_schema_extra={"title": "Chain ID", "example": 944},
    )
    network_id: int = Field(
        ...,
        gt=0,
        description=(
            "EIP-155 network ID. Conventionally equal to chain_id; divergence "
            "breaks wallet compatibility with the original EIP-155 intent."
        ),
        json_schema_extra={"title": "Network ID", "example": 944},
    )
    name: str = Field(
        ...,
        min_length=1,
        max_length=128,
        description="Human-readable chain name. Must be globally unique in ethereum-lists/chains.",
        json_schema_extra={"title": "Chain Name", "example": "ZIGChain"},
    )
    short_name: str = Field(
        ...,
        pattern=r"^[A-Za-z0-9_-]{1,64}$",
        min_length=1,
        max_length=64,
        description=(
            "Short identifier (EIP-3770). Must match ^[A-Za-z0-9_-]{1,64}$ and be globally "
            "unique across ethereum-lists/chains. Verify availability at "
            "https://chainid.network/shortNameMapping.json before sync."
        ),
        json_schema_extra={"title": "Short Name", "example": "zigchain"},
    )
    chain: str = Field(
        ...,
        min_length=1,
        max_length=16,
        description=(
            "Free-text grouping bucket used by ethereum-lists/chains (e.g. 'ETH', 'BSC', "
            "'ZIG'). This is NOT a CAIP-2 identifier — CAIP-2 would be 'eip155:944'."
        ),
        json_schema_extra={"title": "Chain Group", "example": "ZIG"},
    )
    native_currency: NativeCurrency = Field(
        ...,
        description="Native currency of the chain.",
        json_schema_extra={"title": "Native Currency"},
    )
    rpc: List[HttpUrl] = Field(
        default_factory=list,
        max_length=20,
        description=(
            "Public EVM JSON-RPC endpoints. ethereum-lists' Kotlin validator calls eth_chainId on "
            "each URL at PR-time; any unreachable URL (or one returning the wrong chainId) fails CI. "
            "Empty list is permitted for status='incubating' chains that are reserving the chainId "
            "before EVM infra is deployed (see eip155-152 Redbelly Devnet for precedent); a warning "
            "fires if rpc is empty and status='active'."
        ),
        json_schema_extra={
            "title": "RPC Endpoints",
            "example": ["https://evm-rpc.zigchain.com"],
        },
    )
    faucets: List[HttpUrl] = Field(
        default_factory=list,
        max_length=10,
        description="Faucet URLs (typically populated for testnets, empty for mainnet).",
        json_schema_extra={
            "title": "Faucets",
            "example": ["https://faucet-testnet.zigchain.com"],
        },
    )
    info_url: HttpUrl = Field(
        ...,
        description="Public landing page describing the chain.",
        json_schema_extra={"title": "Info URL", "example": "https://zigchain.com"},
    )

    # --- ethereum-lists/chains OPTIONAL fields ---

    title: Optional[str] = Field(
        None,
        min_length=1,
        max_length=128,
        description="Optional alternate display title (e.g. 'ZIGChain Testnet Alpha').",
    )
    explorers: Optional[List[Explorer]] = Field(
        None,
        max_length=10,
        description="Optional block explorers. EIP-3091 standard preferred for wallet UX.",
    )
    status: Literal["active", "incubating", "deprecated"] = Field(
        "active",
        description="Lifecycle status of the chain.",
        json_schema_extra={"title": "Status", "example": "active"},
    )
    slip44: Optional[int] = Field(
        None,
        ge=0,
        description=(
            "Optional SLIP-44 coin type. If set, must be unique across ethereum-lists/chains. "
            "Most chains omit this; only request a slip44 once mainnet stability is proven."
        ),
        json_schema_extra={"title": "SLIP-44", "example": 60},
    )
    icon: Optional[str] = Field(
        None,
        pattern=r"^[a-z0-9_-]{1,64}$",
        description=(
            "Optional ethereum-lists icon slug. References _data/icons/<slug>.json in their repo "
            "(IPFS-pinned image — Pinata explicitly disallowed). v1 leaves this unset; icon "
            "submission is tracked as a follow-up."
        ),
    )

    # --- Repo-local extensions (stripped before upstream emit) ---

    cosmos_chain_id: Optional[str] = Field(
        None,
        min_length=1,
        max_length=64,
        description=(
            "Cosmos chain ID this EVM chain corresponds to (e.g. 'zigchain-1', 'zig-test-2'). "
            "Lets internal consumers join the two registries from one source. Never emitted upstream."
        ),
        json_schema_extra={"title": "Cosmos Chain ID", "example": "zigchain-1"},
    )
    icon_path: Optional[str] = Field(
        None,
        min_length=1,
        max_length=256,
        description=(
            "Repo-relative path to a logo asset for use by ZIGChain UIs that read this repo. "
            "Separate from the upstream 'icon' field (which is an IPFS slug). Not emitted upstream."
        ),
    )
    is_verified: bool = Field(
        True,
        description="Whether this EVM chain entry has been verified/audited by the platform.",
        json_schema_extra={"title": "Is Verified", "example": True},
    )

    # --- Validators ---

    @field_validator("name", "short_name", "chain", "title", "icon",
                     "cosmos_chain_id", "icon_path", "schema_ref", mode="before")
    @classmethod
    def _reject_bytes_strings(cls, value, info):
        """Reject bytes input for string fields — only str or None accepted."""
        if isinstance(value, bytes):
            raise ValueError(f"{info.field_name} must be a string, not bytes")
        return value

    @field_validator("chain_id", "network_id", "slip44", mode="before")
    @classmethod
    def _ints_not_bool(cls, value, info):
        """Prevent bool from being treated as an int."""
        if isinstance(value, bool):
            raise ValueError(f"{info.field_name} cannot be bool, must be an integer")
        return value

    @field_validator("is_verified", mode="before")
    @classmethod
    def _is_verified_strict_bool(cls, value):
        """Reject non-bool truthy/falsy values for is_verified."""
        if value is not None and not isinstance(value, bool):
            raise ValueError("is_verified must be a boolean, not a bool-like value")
        return value

    @field_validator("rpc", "faucets", "explorers", mode="before")
    @classmethod
    def _reject_non_list_fields(cls, value, info):
        return _reject_non_list(value, info.field_name)

    @field_validator("name")
    @classmethod
    def _name_not_blank(cls, name: str) -> str:
        if name.strip() == "":
            raise ValueError("name cannot be empty or whitespace")
        return name

    @field_validator("chain")
    @classmethod
    def _chain_charset(cls, value: str) -> str:
        # 'chain' is the free-text bucket. Keep it alphanumeric/dash to avoid surprises in upstream tooling.
        if not re.match(r"^[A-Za-z0-9_-]+$", value):
            raise ValueError("chain must contain only letters, digits, '_' or '-'")
        return value

    @model_validator(mode="after")
    def _warn_network_id_diverges(self) -> "EvmChain":
        """Warn (not error) if network_id != chain_id.

        EIP-155 conflated the two; ~all production chains keep them equal.
        Divergence is a load-bearing decision so it should be explicit, not silent.
        """
        if self.network_id != self.chain_id:
            warnings.warn(
                f"network_id ({self.network_id}) != chain_id ({self.chain_id}); "
                "wallet compatibility may suffer. Set them equal unless you have a documented reason.",
                stacklevel=2,
            )
        return self

    @model_validator(mode="after")
    def _warn_testnet_naming(self) -> "EvmChain":
        """Warn if the chain has faucets but its name lacks 'Testnet'.

        ethereum-lists convention is to include 'Testnet' in the name when faucets
        are listed. The presence of a faucet (which dispenses tokens for free) is a
        strong testnet signal. ``status='incubating'`` alone is NOT a testnet signal
        — mainnet chains can legitimately use ``incubating`` to reserve a chainId
        before EVM infra is deployed (see eip155-152 Redbelly Devnet for similar
        usage; deprecated mainnets like Kotti / Morden also have status set without
        being testnets in the operational sense).
        """
        if self.faucets and "testnet" not in self.name.lower():
            warnings.warn(
                f"Chain has faucets configured but name '{self.name}' does not contain "
                "'Testnet'. ethereum-lists convention is to include 'Testnet' in the name "
                "of any chain that lists a faucet. ligi may push back.",
                stacklevel=2,
            )
        return self

    @model_validator(mode="after")
    def _warn_testnet_missing_faucet(self) -> "EvmChain":
        """Warn if the name says 'testnet' and status is 'incubating' but no faucet is set.

        Scoped to chains whose name actually claims to be a testnet — avoids firing on
        mainnet chains that use ``incubating`` to reserve a chainId before EVM infra is
        deployed.
        """
        if (
            self.status == "incubating"
            and "testnet" in self.name.lower()
            and not self.faucets
        ):
            warnings.warn(
                f"Testnet '{self.name}' (chainId {self.chain_id}) is status='incubating' but "
                "no faucets are configured. Most testnets list at least one faucet URL — "
                "add one once the faucet is deployed.",
                stacklevel=2,
            )
        return self

    @model_validator(mode="after")
    def _warn_active_chain_without_rpc(self) -> "EvmChain":
        """Empty rpc[] is intentional for status='incubating' (reserving chainId before
        EVM infra is deployed — see eip155-152 Redbelly Devnet). For status='active' it's
        almost certainly a mistake, so warn loudly.
        """
        if self.status == "active" and not self.rpc:
            warnings.warn(
                f"Chain '{self.name}' (chainId {self.chain_id}) has status='active' but rpc[] is "
                "empty. ethereum-lists' validator allows this, but most consumers (wallets, dApps) "
                "expect at least one RPC for an active chain. Set status='incubating' if the chain "
                "isn't fully operational yet.",
                stacklevel=2,
            )
        return self
