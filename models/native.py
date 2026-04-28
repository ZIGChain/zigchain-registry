"""Pydantic models for native ZIGChain assets."""

import re
from typing import List, Literal, Optional

from pydantic import ConfigDict, Field, field_validator, model_validator

from models.base import AssetBase, DenomUnit, NativeTrace, _reject_non_list


class NativeAsset(AssetBase):
    """Model for native ZIGChain assets."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["native"] = Field(
        "native",
        description="Classification indicating this is a chain-native token",
        json_schema_extra={
            "title": "Asset Type",
            "example": "native",
        },
    )

    base_denom: str = Field(
        ...,
        min_length=3,
        max_length=128,
        description="On-chain base denomination identifier, subject to Cosmos SDK's 128-character limit",
        json_schema_extra={
            "title": "Base Denomination",
            "example": "uzig",
        },
    )

    @field_validator("base_denom", mode="before")
    @classmethod
    def reject_bytes_base_denom(cls, value, info):
        """Reject bytes input for base_denom — only str accepted."""
        if isinstance(value, bytes):
            raise ValueError(f"{info.field_name} must be a string, not bytes")
        return value

    @field_validator("base_denom")
    @classmethod
    def validate_base_denom(cls, value: str) -> str:
        """Ensure base_denom follows denom conventions."""
        if isinstance(value, bool):
            raise ValueError("base_denom cannot be bool, must be a string")
        if not re.match(r"^[A-Za-z][A-Za-z0-9:/._-]*$", value):
            raise ValueError("base_denom must start with a letter and use letters, numbers or '/:._-'")
        return value

    @field_validator("denom_units", mode="before")
    @classmethod
    def reject_non_list_denom_units(cls, value):
        """Reject tuple/set for denom_units — only list accepted."""
        return _reject_non_list(value, "denom_units")

    denom_units: List[DenomUnit] = Field(
        ...,
        min_length=1,
        description="List of denomination units for conversion between different scales",
        json_schema_extra={
            "title": "Denomination Units",
            "example": [
                {"denom": "uzig", "exponent": 0},
                {"denom": "ZIG", "exponent": 6},
            ],
        },
    )

    @field_validator("traces", mode="before")
    @classmethod
    def reject_non_list_traces(cls, value):
        """Reject tuple/set for traces — only list accepted."""
        return _reject_non_list(value, "traces")

    traces: Optional[List[NativeTrace]] = Field(
        default=None,
        max_length=10,
        description=(
            "Optional traces for native assets. These are passed through into chain-registry generation "
            "and may describe external minting/bridging relationships."
        ),
        json_schema_extra={
            "title": "Traces",
            "example": [
                {
                    "type": "additional-mintage",
                    "counterparty": {
                        "chain_name": "ethereum",
                        "base_denom": "0xb2617246d0c6c0087f18703d576831899ca94f01",
                    },
                    "provider": "ZIGChain",
                }
            ],
        },
    )

    @field_validator("asset_id")
    @classmethod
    def validate_asset_id(cls, v: str) -> str:
        """Validate asset_id format for native assets."""
        if not re.match(r"^[a-z0-9]+$", v):
            raise ValueError("asset_id for native assets must use lowercase letters and digits only")
        return v

    @model_validator(mode="after")
    def validate_denom_units(self):
        """Validate denom_units structure and consistency."""
        denom_units = self.denom_units
        base_denom = self.base_denom

        if not denom_units:
            raise ValueError("denom_units array is required")

        has_base_denom = False
        max_exponent = -1
        seen_denoms = set()
        seen_exponents = set()

        for unit in denom_units:
            exponent = unit.exponent
            denom = unit.denom

            if denom in seen_denoms:
                raise ValueError(f"denom_units must contain unique denom values, found duplicate '{denom}'")
            if exponent in seen_exponents:
                raise ValueError(f"denom_units must contain unique exponent values, found duplicate '{exponent}'")

            seen_denoms.add(denom)
            seen_exponents.add(exponent)

            if exponent == 0 and denom == base_denom:
                has_base_denom = True

            if exponent > max_exponent:
                max_exponent = exponent

        if not has_base_denom:
            raise ValueError(
                f"denom_units must contain an entry with exponent=0 and denom matching base_denom '{base_denom}'"
            )

        if self.decimals != max_exponent:
            raise ValueError(
                f"decimals ({self.decimals}) must match highest exponent ({max_exponent}) in denom_units"
            )

        # Reject duplicate trace entries (full object equality)
        if self.traces:
            seen_traces: list[str] = []
            for trace in self.traces:
                trace_key = trace.model_dump_json()
                if trace_key in seen_traces:
                    raise ValueError("traces must not contain duplicate entries")
                seen_traces.append(trace_key)

        return self

