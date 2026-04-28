"""Pydantic models for IBC tokens on ZIGChain."""

import re
from typing import List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from models.base import AssetBase, NativeTrace, _reject_non_list


class IBCTrace(BaseModel):
    """IBC trace information."""

    model_config = ConfigDict(extra="forbid")

    type: str = Field(
        ...,
        description="Type identifier for the IBC trace",
        json_schema_extra={
            "title": "Trace Type",
            "example": "ibc",
        },
    )

    @field_validator("type")
    @classmethod
    def validate_trace_type(cls, trace_type: str) -> str:
        """Trace type should be a string (allow legacy values)."""
        if isinstance(trace_type, bool):
            raise ValueError("type cannot be bool, must be a string")
        return trace_type

    chain_name: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="Name of the blockchain in this trace step",
        json_schema_extra={
            "title": "Chain Name",
            "example": "zigchain",
        },
    )

    base_denom: str = Field(
        ...,
        min_length=1,
        max_length=128,
        description="Denomination identifier used on this chain in the trace. Can be an IBC denom (ibc/{64-char-hash}) or a native denom on the origin chain (e.g. uatom, uusdc).",
        json_schema_extra={
            "title": "Base Denomination",
            "example": "uatom",
        },
    )

    @field_validator("base_denom")
    @classmethod
    def validate_trace_base_denom(cls, base_denom: str) -> str:
        """Allow any non-bool string for legacy traces."""
        if isinstance(base_denom, bool):
            raise ValueError("base_denom cannot be bool, must be a string")
        if not isinstance(base_denom, str) or base_denom.strip() == "":
            raise ValueError("base_denom must be a non-empty string")
        return base_denom

    path: str = Field(
        ...,
        min_length=1,
        max_length=256,
        description="IBC transfer path showing the routing through channels",
        json_schema_extra={
            "title": "IBC Transfer Path",
            "example": "transfer/channel-3/uusdc",
        },
    )

    provider: Optional[str] = Field(
        default=None,
        description="Optional hint for the bridge/transport provider used for this hop (e.g. 'eureka').",
        json_schema_extra={
            "title": "Provider",
            "example": "eureka",
        },
    )

    @field_validator("path")
    @classmethod
    def validate_trace_path(cls, path: str) -> str:
        """Ensure path starts with transfer/ and contains only safe characters."""
        if isinstance(path, bool):
            raise ValueError("path cannot be bool, must be a string")
        if not path.startswith("transfer/"):
            raise ValueError("path must start with 'transfer/'")
        # Validate suffix: no traversal, no control chars, safe character set only
        if ".." in path or any(ord(c) < 0x20 for c in path) or not re.match(r"^transfer/[a-zA-Z0-9/._-]+$", path):
            raise ValueError("path contains unsafe characters or sequences")
        return path

    @field_validator("provider")
    @classmethod
    def validate_trace_provider(cls, provider: Optional[str]) -> Optional[str]:
        """Normalize/validate provider (currently only 'eureka' and 'ibc' are supported)."""
        if provider is None:
            return None
        if isinstance(provider, bool):
            raise ValueError("provider cannot be bool, must be a string")
        if not isinstance(provider, str) or provider.strip() == "":
            raise ValueError("provider must be a non-empty string when provided")

        normalized = provider.strip().lower()
        if normalized not in {"eureka", "ibc"}:
            raise ValueError("provider must be 'eureka' or 'ibc' when provided")
        return normalized


class IBCChannel(BaseModel):
    """IBC channel information."""

    model_config = ConfigDict(extra="forbid")

    zigchain_channel: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="IBC channel identifier on ZIGChain side of the connection",
        json_schema_extra={
            "title": "ZIGChain Channel",
            "example": "channel-3",
        },
    )

    counterparty_chain: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="Name of the blockchain on the other side of this channel",
        json_schema_extra={
            "title": "Counterparty Chain",
            "example": "noble",
        },
    )

    counterparty_channel: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="IBC channel identifier on the counterparty chain",
        json_schema_extra={
            "title": "Counterparty Channel",
            "example": "channel-175",
        },
    )

    @field_validator("counterparty_chain")
    @classmethod
    def validate_counterparty_chain(cls, value: str) -> str:
        """Ensure counterparty_chain uses safe chain name characters."""
        if isinstance(value, bool):
            raise ValueError("counterparty_chain cannot be bool, must be a string")
        if not re.match(r"^[a-z][a-z0-9-]*$", value):
            raise ValueError(
                "counterparty_chain must start with a lowercase letter "
                "and contain only lowercase letters, digits, or hyphens"
            )
        return value

    @field_validator("zigchain_channel", "counterparty_channel")
    @classmethod
    def validate_channel_format(cls, channel: str) -> str:
        """Validate channel identifiers match known IBC channel patterns."""
        if isinstance(channel, bool):
            raise ValueError("channel identifiers cannot be bool, must be strings")
        if not isinstance(channel, str) or channel.strip() == "":
            raise ValueError("channel identifiers must be non-empty strings")
        if not re.match(r"^(channel-\d+|08-wasm-\d+)$", channel):
            raise ValueError(
                "channel must match 'channel-<number>' or '08-wasm-<number>' format"
            )
        return channel


class IBCAsset(AssetBase):
    """Model for IBC tokens on ZIGChain."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["ibc"] = Field(
        "ibc",
        description="Classification indicating this is an IBC-transferred token",
        json_schema_extra={
            "title": "Asset Type",
            "example": "ibc",
        },
    )

    base_denom: str = Field(
        ...,
        pattern=r"^ibc/[A-Fa-f0-9]{64}$",
        min_length=68,
        max_length=68,
        description="On-chain IBC denomination identifier constructed from the IBC hash. Uses SHA256 hash to ensure the denomination fits within Cosmos SDK's 64-character limit for token denominations.",
        json_schema_extra={
            "title": "Base Denomination",
            "example": "ibc/6490A7EAB61059BFC1CDDEB05917DD70BDF3A611654162A1A47DB930D40D8AF4",
        },
    )

    @field_validator("base_denom", "hash", "origin_chain", "origin_denom", mode="before")
    @classmethod
    def reject_bytes_ibc_fields(cls, value, info):
        """Reject bytes input for IBC-specific string fields — only str accepted."""
        if isinstance(value, bytes):
            raise ValueError(f"{info.field_name} must be a string, not bytes")
        return value

    @field_validator("base_denom")
    @classmethod
    def validate_base_denom(cls, value: str) -> str:
        """Ensure base_denom matches ibc/<hash> format."""
        if isinstance(value, bool):
            raise ValueError("base_denom cannot be bool, must be a string")
        if not re.match(r"^ibc/[A-Fa-f0-9]{64}$", value):
            raise ValueError("base_denom must match pattern ibc/<64 hex chars>")
        return value

    hash: str = Field(
        ...,
        pattern=r"^[A-Fa-f0-9]{64}$",
        min_length=64,
        max_length=64,
        description="SHA256 hash (64 hexadecimal characters) of the IBC transfer path, used to create a fixed-length denomination that fits within Cosmos SDK's 64-character limit",
        json_schema_extra={
            "title": "IBC Hash",
            "example": "6490A7EAB61059BFC1CDDEB05917DD70BDF3A611654162A1A47DB930D40D8AF4",
        },
    )

    @field_validator("hash")
    @classmethod
    def validate_hash(cls, value: str) -> str:
        """Ensure hash is hex."""
        if isinstance(value, bool):
            raise ValueError("hash cannot be bool, must be a string")
        if not re.match(r"^[A-Fa-f0-9]{64}$", value):
            raise ValueError("hash must be 64 hexadecimal characters")
        return value

    origin_chain: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="Name of the blockchain where this token originated",
        json_schema_extra={
            "title": "Origin Chain",
            "example": "noble",
        },
    )

    origin_denom: str = Field(
        ...,
        min_length=1,
        max_length=128,
        description="Original denomination identifier on the source blockchain",
        json_schema_extra={
            "title": "Origin Denomination",
            "example": "uusdc",
        },
    )

    @field_validator("origin_chain")
    @classmethod
    def validate_origin_chain(cls, value: str) -> str:
        """Ensure origin_chain uses safe chain name characters."""
        if isinstance(value, bool):
            raise ValueError("origin_chain cannot be bool, must be a string")
        if not re.match(r"^[a-z][a-z0-9-]*$", value):
            raise ValueError(
                "origin_chain must start with a lowercase letter "
                "and contain only lowercase letters, digits, or hyphens"
            )
        return value

    @field_validator("origin_denom")
    @classmethod
    def validate_origin_denom(cls, value: str) -> str:
        """Ensure origin_denom uses safe denom characters."""
        if isinstance(value, bool):
            raise ValueError("origin_denom cannot be bool, must be a string")
        if not re.match(r"^[a-zA-Z0-9][a-zA-Z0-9:/._-]*$", value):
            raise ValueError(
                "origin_denom must start with a letter or digit "
                "and contain only letters, digits, or '/:._-'"
            )
        return value

    @field_validator("traces", mode="before")
    @classmethod
    def reject_non_list_traces(cls, value):
        """Reject tuple/set for traces — only list accepted."""
        return _reject_non_list(value, "traces")

    traces: List[Union[IBCTrace, NativeTrace]] = Field(
        ...,
        min_length=1,
        max_length=10,
        description=(
            "Traces for IBC assets.\n"
            "- IBC hop traces (required): chain_name/base_denom/path describing routing.\n"
            "- Supplemental traces (optional): {type, counterparty{chain_name,base_denom}, provider?} for extra metadata."
        ),
        json_schema_extra={
            "title": "IBC Traces",
            "example": [
                {
                    "type": "ibc",
                    "chain_name": "zigchain",
                    "base_denom": "ibc/6490A7EAB61059BFC1CDDEB05917DD70BDF3A611654162A1A47DB930D40D8AF4",
                    "path": "transfer/channel-3/uusdc",
                },
                {
                    "type": "synthetic",
                    "counterparty": {"chain_name": "forex", "base_denom": "USD"},
                    "provider": "Circle",
                },
            ],
        },
    )


    @field_validator("channels", mode="before")
    @classmethod
    def reject_non_list_channels(cls, value):
        """Reject tuple/set for channels — only list accepted."""
        return _reject_non_list(value, "channels")

    channels: List[IBCChannel] = Field(
        ...,
        min_length=1,
        max_length=5,
        description="IBC channel connections between ZIGChain and counterparty chains (max 5)",
        json_schema_extra={
            "title": "IBC Channels",
            "example": [
                {
                    "zigchain_channel": "channel-3",
                    "counterparty_chain": "noble",
                    "counterparty_channel": "channel-175",
                },
            ],
        },
    )

    @field_validator("asset_id")
    @classmethod
    def validate_asset_id(cls, v: str) -> str:
        """Validate asset_id format for IBC assets."""
        if not re.match(r"^ibc/[A-Fa-f0-9]{64}$", v):
            raise ValueError("asset_id must match format ibc/<64 hex chars>")
        return v

    @model_validator(mode="after")
    def validate_hash_alignment(self):
        """Ensure asset_id, base_denom, and hash agree."""
        expected = f"ibc/{self.hash}"

        if self.asset_id != expected:
            raise ValueError(f"asset_id must be '{expected}' derived from hash")

        if self.base_denom != expected:
            raise ValueError(f"base_denom must be '{expected}' derived from hash")

        return self


    @model_validator(mode="after")
    def validate_traces_must_include_ibc_hops(self) -> "IBCAsset":
        """Ensure traces includes at least one IBC hop entry.

        Supplemental trace entries are allowed, but they are not a substitute for IBC routing traces.
        """
        if not any(isinstance(t, IBCTrace) for t in self.traces):
            raise ValueError("traces must include at least one IBC hop trace entry")
        return self

    @model_validator(mode="after")
    def validate_no_duplicate_entries(self) -> "IBCAsset":
        """Reject duplicate trace and channel entries."""
        # Reject duplicate trace entries (full object equality)
        if self.traces:
            seen_traces: list[str] = []
            for trace in self.traces:
                trace_key = trace.model_dump_json()
                if trace_key in seen_traces:
                    raise ValueError("traces must not contain duplicate entries")
                seen_traces.append(trace_key)

        # Reject duplicate channel entries (full object equality)
        if self.channels:
            seen_channels: list[str] = []
            for channel in self.channels:
                channel_key = channel.model_dump_json()
                if channel_key in seen_channels:
                    raise ValueError("channels must not contain duplicate entries")
                seen_channels.append(channel_key)

        return self

