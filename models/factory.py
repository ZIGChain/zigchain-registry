"""Pydantic models for factory tokens on ZIGChain."""

import re
from typing import List, Literal, Optional

from pydantic import ConfigDict, Field, HttpUrl, field_validator, model_validator

from models.base import AssetBase, DenomUnit, _reject_non_list


class FactoryAsset(AssetBase):
    """Model for factory tokens on ZIGChain."""

    model_config = ConfigDict(extra="forbid")

    # For factory assets we allow a longer display_denom so the registry can safely
    # use the full on-chain denom (base_denom) as the consumer-facing display value
    # to avoid collisions across creators.
    display_denom: str = Field(
        ...,
        min_length=1,
        max_length=128,
        description=(
            "Denomination symbol shown to users in wallets and interfaces. "
            "For factory assets this may be set to the full base_denom to guarantee uniqueness."
        ),
        json_schema_extra={
            "title": "Display Denomination",
            "example": "coin.zig1wze8mn5nsgl9qrgazq6a92fvh7m5e6psjcx2du.panda",
        },
    )

    # Override AssetBase.validate_display_denom for factory assets (length up to 128).
    # Using the same method name ensures we replace the base validator instead of stacking it.
    @field_validator("display_denom")
    @classmethod
    def validate_display_denom(cls, display_denom: str) -> str:
        if not re.match(r"^[A-Za-z0-9][A-Za-z0-9:._-]{0,127}$", display_denom):
            raise ValueError(
                "display_denom must start with a letter/number and contain only letters, numbers, ':', '.', '_' or '-'"
            )
        return display_denom

    type: Literal["factory"] = Field(
        "factory",
        description="Classification indicating this is a factory-created token",
        json_schema_extra={
            "title": "Asset Type",
            "example": "factory",
        },
    )

    base_denom: str = Field(
        ...,
        pattern=r"^coin\.zig1[0-9a-z]{38,}\.[a-z][a-z0-9-]{2,43}$",
        min_length=51,
        max_length=128,
        description="On-chain token base denomination constructed from creator address and subdenom. Maximum length is 128 bytes per ZIGChain factory constraints (https://docs.zigchain.com/build/factory).",
        json_schema_extra={
            "title": "Base Denomination",
            "example": "coin.zig1wze8mn5nsgl9qrgazq6a92fvh7m5e6psjcx2du.panda",
        },
    )

    creator: str = Field(
        ...,
        pattern=r"^zig1[0-9a-z]{38,}$",
        min_length=42,
        max_length=100,
        description="Bech32 address of the wallet or smart contract that created this token",
        json_schema_extra={
            "title": "Creator Address",
            "examples": [
                "zig1wze8mn5nsgl9qrgazq6a92fvh7m5e6psjcx2du",
                "zig1pt9u490q0km4lx8h9h48vzu3q20yl9nmq3ulkqjeelrfp5ec7nws68c2rn",
            ],
        },
    )

    @field_validator("base_denom", "creator", "subdenom", "uri_hash", mode="before")
    @classmethod
    def reject_bytes_factory_fields(cls, value, info):
        """Reject bytes input for factory-specific string fields — only str accepted."""
        if isinstance(value, bytes):
            raise ValueError(f"{info.field_name} must be a string, not bytes")
        return value

    @field_validator("creator")
    @classmethod
    def validate_creator(cls, creator: str) -> str:
        """Ensure creator looks like a bech32 address."""
        if isinstance(creator, bool):
            raise ValueError("creator cannot be bool, must be a string")
        return creator

    subdenom: str = Field(
        ...,
        pattern=r"^[a-z][a-z0-9-]{2,43}$",
        min_length=3,
        max_length=44,
        description="Unique identifier for this token within the creator's namespace",
        json_schema_extra={
            "title": "Subdenomination",
            "example": "panda",
        },
    )

    @field_validator("subdenom")
    @classmethod
    def validate_subdenom(cls, subdenom: str) -> str:
        """Ensure subdenom format and length are valid."""
        if isinstance(subdenom, bool):
            raise ValueError("subdenom cannot be bool, must be a string")
        return subdenom

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
                {"denom": "coin.zig1wze8mn5nsgl9qrgazq6a92fvh7m5e6psjcx2du.panda", "exponent": 0},
                {"denom": "PANDA", "exponent": 6},
            ],
        },
    )

    uri: Optional[HttpUrl] = Field(
        None,
        max_length=2048,
        description="A URI pointing to an on-chain or off-chain document containing additional information",
        json_schema_extra={
            "title": "URI",
            "example": "https://example.com/whitepaper.pdf",
        },
    )

    uri_hash: Optional[str] = Field(
        None,
        pattern=r"^[a-fA-F0-9]{64}$",
        description="SHA-256 hash of the document at URI for integrity verification",
        json_schema_extra={
            "title": "URI Hash",
            "example": "a3f4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2b3c4",
        },
    )

    @field_validator("uri_hash")
    @classmethod
    def validate_uri_hash(cls, uri_hash: Optional[str]) -> Optional[str]:
        """Ensure uri_hash is hex when provided."""
        if uri_hash is None:
            return uri_hash
        if isinstance(uri_hash, bool):
            raise ValueError("uri_hash cannot be bool, must be a string")
        if not re.match(r"^[A-Fa-f0-9]{64}$", uri_hash):
            raise ValueError("uri_hash must be 64 hexadecimal characters")
        return uri_hash

    @field_validator("asset_id")
    @classmethod
    def validate_asset_id(cls, asset_id: str) -> str:
        """Validate asset_id format for factory assets."""
        if isinstance(asset_id, bool):
            raise ValueError("asset_id cannot be bool, must be a string")
        if not re.match(r"^coin\.zig1[0-9a-z]{38,}\.[a-z][a-z0-9-]{2,43}$", asset_id):
            raise ValueError("asset_id must match format coin.<creator>.<subdenom>")
        return asset_id

    @model_validator(mode="after")
    def validate_denom_units(self):
        """Validate denom_units structure and consistency."""
        denom_units = self.denom_units
        base_denom = self.base_denom

        if not denom_units:
            raise ValueError("denom_units array is required")

        has_base_denom = False
        max_exponent = -1
        seen_exponents = set()

        for unit in denom_units:
            exponent = unit.exponent
            denom = unit.denom

            if exponent in seen_exponents:
                raise ValueError(f"denom_units must contain unique exponent values, found duplicate '{exponent}'")

            seen_exponents.add(exponent)

            if exponent == 0 and denom == base_denom:
                has_base_denom = True

            if exponent > max_exponent:
                max_exponent = exponent

        if not has_base_denom:
            raise ValueError(
                f"denom_units must contain an entry with exponent=0 and denom matching base_denom '{base_denom}'"
            )

        # Factory denom_units may be minimal (only exponent=0). If higher exponents are present,
        # enforce that decimals matches the highest exponent for consistency.
        if max_exponent > 0 and self.decimals != max_exponent:
            raise ValueError(
                f"decimals ({self.decimals}) must match highest exponent ({max_exponent}) in denom_units"
            )

        expected_base = f"coin.{self.creator}.{self.subdenom}"
        if self.base_denom != expected_base:
            raise ValueError(f"base_denom must be '{expected_base}' derived from creator and subdenom")

        if self.asset_id != expected_base:
            raise ValueError(f"asset_id must be '{expected_base}' derived from creator and subdenom")

        if self.uri and self.uri_hash is None:
            raise ValueError("uri_hash is required when uri is provided")

        return self

