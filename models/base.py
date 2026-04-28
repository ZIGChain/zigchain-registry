"""Base Pydantic models for ZIGChain assets."""

import re
from typing import List, Literal, Optional, Union
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator


def _reject_non_list(value, field_name: str = "field"):
    """Reject tuple/set for list fields — only accept list or None."""
    if value is None:
        return value
    if isinstance(value, (tuple, set)):
        raise ValueError(f"{field_name} must be a list, not {type(value).__name__}")
    return value


# Hosts permitted for asset logo URLs. Restricting this set blocks SVG-XSS vectors
# via externally-hosted <script>-bearing SVG payloads. Extend here if a new CDN
# is approved for hosting registry logos.
_ALLOWED_LOGO_HOSTS: frozenset[str] = frozenset({"raw.githubusercontent.com"})


def _validate_logo_host(value: Optional[HttpUrl]) -> Optional[HttpUrl]:
    """Reject logo URLs whose host is not in the allowlist."""
    if value is None:
        return value
    host = (value.host or "").lower()
    if host not in _ALLOWED_LOGO_HOSTS:
        raise ValueError(
            f"logo URL host '{host}' is not in the allowlist: {sorted(_ALLOWED_LOGO_HOSTS)}"
        )
    return value


class LogoUris(BaseModel):
    """Logo URIs for an asset."""

    model_config = ConfigDict(extra="forbid")

    chain_name: Optional[str] = Field(
        None,
        min_length=1,
        description=(
            "Optional Cosmos chain-registry folder name to resolve this logo from during generation "
            "(e.g. 'cosmoshub', 'noble', 'stride', or 'ethereum' for _non-cosmos)."
        ),
        json_schema_extra={"title": "Chain Name"},
    )

    png: Optional[HttpUrl] = Field(
        None,
        description="URL to the PNG format logo image",
        json_schema_extra={
            "title": "PNG Logo URL",
            "example": "https://example.com/logo.png",
        },
    )

    svg: Optional[HttpUrl] = Field(
        None,
        description="URL to the SVG format logo image",
        json_schema_extra={
            "title": "SVG Logo URL",
            "example": "https://example.com/logo.svg",
        },
    )

    @field_validator("png", "svg", mode="after")
    @classmethod
    def _check_logo_host(cls, v: Optional[HttpUrl]) -> Optional[HttpUrl]:
        return _validate_logo_host(v)


class Socials(BaseModel):
    """Social links for an asset (project/community URLs)."""

    model_config = ConfigDict(
        extra="forbid",
        # Match Cosmos chain-registry socials schema constraint: minProperties: 1
        json_schema_extra={"minProperties": 1},
    )

    website: Optional[HttpUrl] = Field(None, max_length=2048, json_schema_extra={"format": "uri"})
    x: Optional[str] = Field(
        None,
        min_length=1,
        max_length=2048,
        description="X (formerly Twitter)",
        json_schema_extra={
            "format": "uri",
            "pattern": r"^https://(x\.com|twitter\.com)/.+$",
        },
    )
    telegram: Optional[HttpUrl] = Field(None, max_length=2048, json_schema_extra={"format": "uri"})
    discord: Optional[HttpUrl] = Field(None, max_length=2048, json_schema_extra={"format": "uri"})
    github: Optional[HttpUrl] = Field(None, max_length=2048, json_schema_extra={"format": "uri"})
    medium: Optional[HttpUrl] = Field(None, max_length=2048, json_schema_extra={"format": "uri"})
    reddit: Optional[HttpUrl] = Field(None, max_length=2048, json_schema_extra={"format": "uri"})

    @field_validator("x")
    @classmethod
    def validate_x_url(cls, value: Optional[str]) -> Optional[str]:
        """Validate X/Twitter URL format."""
        if value is None:
            return value
        if not re.match(r"^https://(x\.com|twitter\.com)/.+$", value):
            raise ValueError("socials.x must match ^https://(x\\.com|twitter\\.com)/.+$")
        return value

    @field_validator("telegram")
    @classmethod
    def validate_telegram_url(cls, value: Optional[HttpUrl]) -> Optional[HttpUrl]:
        """Validate Telegram URL points to t.me domain."""
        if value is None:
            return value
        host = str(value).split("//")[-1].split("/")[0].lower()
        if host not in ("t.me", "telegram.me"):
            raise ValueError("socials.telegram must be a t.me or telegram.me URL")
        return value

    @field_validator("discord")
    @classmethod
    def validate_discord_url(cls, value: Optional[HttpUrl]) -> Optional[HttpUrl]:
        """Validate Discord URL points to discord.gg or discord.com domain."""
        if value is None:
            return value
        host = str(value).split("//")[-1].split("/")[0].lower()
        if not (host in ("discord.gg", "discord.com", "discordapp.com") or "discord" in host):
            raise ValueError("socials.discord must be a Discord URL (discord.gg, discord.com, discordapp.com, or custom discord domain)")
        return value

    @field_validator("github")
    @classmethod
    def validate_github_url(cls, value: Optional[HttpUrl]) -> Optional[HttpUrl]:
        """Validate GitHub URL points to github.com domain."""
        if value is None:
            return value
        host = str(value).split("//")[-1].split("/")[0].lower()
        if host not in ("github.com", "www.github.com"):
            raise ValueError("socials.github must be a github.com URL")
        return value

    @field_validator("medium")
    @classmethod
    def validate_medium_url(cls, value: Optional[HttpUrl]) -> Optional[HttpUrl]:
        """Validate Medium URL points to medium.com domain."""
        if value is None:
            return value
        host = str(value).split("//")[-1].split("/")[0].lower()
        # medium.com or *.medium.com (for custom domains, users access via medium.com/@user)
        if not (host == "medium.com" or host.endswith(".medium.com")):
            raise ValueError("socials.medium must be a medium.com URL")
        return value

    @field_validator("reddit")
    @classmethod
    def validate_reddit_url(cls, value: Optional[HttpUrl]) -> Optional[HttpUrl]:
        """Validate Reddit URL points to reddit.com domain."""
        if value is None:
            return value
        host = str(value).split("//")[-1].split("/")[0].lower()
        if host not in ("reddit.com", "www.reddit.com", "old.reddit.com"):
            raise ValueError("socials.reddit must be a reddit.com URL")
        return value

    @model_validator(mode="after")
    def validate_min_properties(self) -> "Socials":
        if not any(
            getattr(self, k) is not None
            for k in ("website", "x", "telegram", "discord", "github", "medium", "reddit")
        ):
            raise ValueError("socials must contain at least one property")
        return self


class TraceCounterparty(BaseModel):
    """Counterparty reference for a non-IBC trace entry (e.g. Ethereum contract address)."""

    model_config = ConfigDict(extra="forbid")

    chain_name: str = Field(..., min_length=1, max_length=64, description="Counterparty chain name")
    base_denom: str = Field(
        ...,
        min_length=1,
        max_length=256,
        description="Counterparty base denom (e.g. uatom, uusdc, or an EVM contract address).",
    )

    @field_validator("chain_name", "base_denom")
    @classmethod
    def _must_be_non_empty_string(cls, v: str) -> str:
        if isinstance(v, bool):
            raise ValueError("value cannot be bool, must be a string")
        if not isinstance(v, str) or v.strip() == "":
            raise ValueError("value must be a non-empty string")
        return v


class NativeTrace(BaseModel):
    """
    Trace entry for native (and potentially factory) assets.

    Example (as used in this repo's asset JSONs):
      {
        "type": "additional-mintage",
        "counterparty": { "chain_name": "ethereum", "base_denom": "0x..." },
        "provider": "ZIGChain"
      }
    """

    model_config = ConfigDict(extra="forbid")

    type: str = Field(..., min_length=1, max_length=64, description="Trace type identifier (free-form)")
    counterparty: TraceCounterparty = Field(..., description="Counterparty reference for this trace")
    provider: Optional[str] = Field(
        default=None,
        max_length=64,
        description="Optional provider hint. When omitted, generation must not emit a provider field.",
    )

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        if isinstance(v, bool):
            raise ValueError("type cannot be bool, must be a string")
        if not isinstance(v, str) or v.strip() == "":
            raise ValueError("type must be a non-empty string")
        return v

    @field_validator("provider")
    @classmethod
    def validate_provider(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        if isinstance(v, bool):
            raise ValueError("provider cannot be bool, must be a string")
        if not isinstance(v, str) or v.strip() == "":
            raise ValueError("provider must be a non-empty string when provided")
        return v.strip()


class ImageSyncPointer(BaseModel):
    """Pointer to an upstream image definition in the Cosmos chain-registry."""

    model_config = ConfigDict(extra="forbid")

    chain_name: str = Field(..., min_length=1, max_length=64, description="Chain name in the Cosmos chain registry")
    base_denom: str = Field(..., min_length=1, max_length=256, description="Base denom (or contract address) on the source chain")


class ImageTheme(BaseModel):
    """Optional theming hints for images."""

    model_config = ConfigDict(extra="forbid", json_schema_extra={"minProperties": 1})

    circle: Optional[bool] = None
    dark_mode: Optional[bool] = None

    @field_validator("circle", "dark_mode", mode="before")
    @classmethod
    def reject_non_bool_theme(cls, value):
        """Reject non-bool truthy/falsy values — only bool or None accepted."""
        if value is not None and not isinstance(value, bool):
            raise ValueError("must be a boolean, not a bool-like value")
        return value

    @model_validator(mode="after")
    def validate_min_properties(self) -> "ImageTheme":
        if self.circle is None and self.dark_mode is None:
            raise ValueError("images[].theme must contain at least one property")
        return self


class ImageEntry(BaseModel):
    """
    Cosmos chain-registry compatible images entry.

    Note: for convenience, this repo also allows the shortcut form:
      { "chain_name": "...", "base_denom": "..." }
    which is represented by ImageSyncPointer and transformed during generation.
    """

    model_config = ConfigDict(extra="forbid")

    image_sync: Optional[ImageSyncPointer] = Field(
        None,
        description="Pointer to upstream image metadata (Cosmos chain-registry 'pointer' definition)",
    )
    png: Optional[HttpUrl] = Field(None, min_length=1, description="PNG image URL (uri-reference)")
    svg: Optional[HttpUrl] = Field(None, min_length=1, description="SVG image URL (uri-reference)")
    theme: Optional[ImageTheme] = Field(None, description="Optional theming hints")

    @field_validator("png", "svg", mode="after")
    @classmethod
    def _check_logo_host(cls, v: Optional[HttpUrl]) -> Optional[HttpUrl]:
        return _validate_logo_host(v)


class DenomUnit(BaseModel):
    """Denom unit with exponent for conversion (chain-registry compatible)."""

    model_config = ConfigDict(extra="forbid")

    denom: str = Field(
        ...,
        min_length=1,
        max_length=128,
        description="Denomination identifier for this unit, subject to Cosmos SDK's 128-character limit",
        json_schema_extra={
            "title": "Denomination",
            "example": "uzig",
        },
    )

    @field_validator("denom")
    @classmethod
    def validate_denom(cls, value: str) -> str:
        """Ensure denom uses alphanumerics (case-insensitive) with optional slashes/colons."""
        if not re.match(r"^[A-Za-z][A-Za-z0-9:/._-]*$", value):
            raise ValueError("denom must start with a letter and use letters, numbers or '/:._-'")
        return value

    exponent: int = Field(
        ...,
        ge=0,
        le=18,
        description="Exponent for conversion (0-18, matching Cosmos SDK convention)",
        json_schema_extra={"example": 6},
    )

    @field_validator("exponent", mode="before")
    @classmethod
    def exponent_must_not_be_bool(cls, value):
        """Prevent bool from being treated as an int."""
        if isinstance(value, bool):
            raise ValueError("exponent cannot be bool, must be an integer")
        return value

    aliases: Optional[List[str]] = Field(
        None,
        max_length=10,
        description="Optional alternative names or symbols that can be used to refer to this denomination (max 10)",
        json_schema_extra={
            "title": "Aliases",
            "example": ["ZIG"],
        },
    )

    @field_validator("aliases", mode="before")
    @classmethod
    def reject_non_list_aliases(cls, value):
        """Reject tuple/set for aliases — only list accepted."""
        return _reject_non_list(value, "aliases")

    @field_validator("aliases")
    @classmethod
    def validate_aliases(cls, value: Optional[List[str]]) -> Optional[List[str]]:
        """Ensure aliases are unique, non-empty strings."""
        if value is None:
            return value
        cleaned = []
        seen = set()
        for alias in value:
            if not isinstance(alias, str) or alias.strip() == "":
                raise ValueError("aliases must be non-empty strings")
            if alias in seen:
                raise ValueError("aliases must be unique")
            seen.add(alias)
            cleaned.append(alias)
        return cleaned


class AssetBase(BaseModel):
    """Base model for all ZIGChain assets with common fields."""

    model_config = ConfigDict(extra="forbid")

    schema_ref: Optional[str] = Field(
        None,
        alias="$schema",
        description="Optional JSON Schema reference for tooling (editors/validators). Not part of on-chain asset data.",
        json_schema_extra={
            "title": "JSON Schema Reference",
            "example": "../../schemas/asset.native.schema.json",
        },
    )

    network: Literal["mainnet", "testnet"] = Field(
        ...,
        description="Blockchain network where this asset is available",
        json_schema_extra={
            "title": "Network Environment",
            "example": "mainnet",
        },
    )

    asset_id: str = Field(
        ...,
        min_length=1,
        max_length=128,
        description="Deterministic ID, e.g. zig, factory.creator.subdenom, ibc/HASH...",
        json_schema_extra={
            "title": "Asset ID",
            "examples": [
                "zig",
                "factory.zig1pvm4lt2xct387nhxynedz0zll9uw0gyh4mftlw.panda",
                "ibc/EF48E6B1A1A19F47ECAEA62F5670C37C0580E86A9E88498B7E393EB6F49F33C0",
            ],
        },
    )

    @field_validator("asset_id", "symbol", "name", "display_denom", "description", "extended_description", "coingecko_id", mode="before")
    @classmethod
    def reject_bytes_string_fields(cls, value, info):
        """Reject bytes input for all string fields — only str accepted."""
        if isinstance(value, bytes):
            raise ValueError(f"{info.field_name} must be a string, not bytes")
        return value

    order: Optional[int] = Field(
        None,
        ge=0,
        description=(
            "Optional numerical order for controlling asset display order in generated chain-registry outputs. "
            "Lower values appear first. Assets without order are sorted after ordered assets."
        ),
        json_schema_extra={"title": "Order", "example": 10},
    )

    @field_validator("order", mode="before")
    @classmethod
    def order_must_not_be_bool(cls, value):
        """Prevent bool from being treated as an int."""
        if value is None:
            return None
        if isinstance(value, bool):
            raise ValueError("order cannot be bool, must be an integer")
        return value

    type: Literal["native", "factory", "ibc"] = Field(
        ...,
        description="Classification of the asset: native (chain-native), factory (created via factory module), or ibc (IBC-transferred)",
        json_schema_extra={
            "title": "Asset Type",
            "example": "native",
        },
    )

    symbol: str = Field(
        ...,
        min_length=2,
        max_length=42,
        description="Ticker symbol used to represent the asset (typically uppercase, 2-42 characters)",
        json_schema_extra={
            "title": "Asset Symbol",
            "example": "ZIG",
        },
    )

    @field_validator("symbol")
    @classmethod
    def validate_symbol(cls, symbol: str) -> str:
        """Ensure symbol has only allowed characters and limited length."""
        if not re.match(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,41}$", symbol):
            raise ValueError(
                "symbol must start with a letter/number and contain only letters, numbers, '.', '_' or '-'"
            )
        return symbol

    name: str = Field(
        ...,
        min_length=2,
        max_length=100,
        description="Full human-readable name of the asset",
        json_schema_extra={
            "title": "Asset Name",
            "example": "ZIGChain Native Token",
        },
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, name: str) -> str:
        """Ensure name is non-empty and trimmed."""
        if name.strip() == "":
            raise ValueError("name cannot be empty or whitespace")
        return name

    @field_validator("decimals", mode="before")
    @classmethod
    def coerce_decimals_from_string(cls, value):
        # If provided as a string, attempt to cast to int (but not bool)
        if isinstance(value, str):
            try:
                # Forbid "True"/"False" as numbers
                if value.strip().lower() in ("true", "false"):
                    raise ValueError
                value = int(value)
            except Exception:
                raise ValueError("decimals must be an integer or string that can be parsed as integer")
        return value

    decimals: int = Field(
        ...,
        ge=0,
        le=18,
        description="Precision for the asset's smallest unit (typically 6-18 for most tokens)",
        json_schema_extra={
            "title": "Decimal Places",
            "example": 6,
        },
    )

    @field_validator("denom_units", mode="before")
    @classmethod
    def reject_non_list_denom_units(cls, value):
        """Reject tuple/set for denom_units — only list accepted."""
        return _reject_non_list(value, "denom_units")

    denom_units: Optional[List[DenomUnit]] = Field(
        None,
        description=(
            "Optional list of denomination units for conversion between different scales "
            "(Cosmos chain-registry compatible). Native and factory assets require this; "
            "IBC assets may omit it and rely on generation defaults."
        ),
        json_schema_extra={
            "title": "Denomination Units",
            "example": [
                {"denom": "ibc/ABCDEF0123456789ABCDEF0123456789ABCDEF0123456789ABCDEF0123456789", "exponent": 0},
                {"denom": "token", "exponent": 6},
            ],
        },
    )

    @field_validator("decimals", mode="before")
    @classmethod
    def decimals_must_not_be_bool(cls, decimals: int) -> int:
        """Prevent bool from being treated as an int."""
        if isinstance(decimals, bool):
            raise ValueError("decimals cannot be bool, must be an integer")
        return decimals

    display_denom: str = Field(
        ...,
        min_length=1,
        max_length=32,
        description="Denomination symbol shown to users in wallets and interfaces",
        json_schema_extra={
            "title": "Display Denomination",
            "example": "ZIG",
        },
    )

    @field_validator("display_denom")
    @classmethod
    def validate_display_denom(cls, display_denom: str) -> str:
        """Restrict display_denom characters (allow '.' for bridged symbols)."""
        if not re.match(r"^[A-Za-z0-9][A-Za-z0-9:._-]{0,31}$", display_denom):
            raise ValueError(
                "display_denom must start with a letter/number and contain only letters, numbers, ':', '.', '_' or '-'"
            )
        return display_denom

    description: Optional[str] = Field(
        None,
        min_length=1,
        max_length=2048,
        description="Optional text providing additional context about the asset",
        json_schema_extra={
            "title": "Asset Description",
            "example": "The native staking token of ZIGChain",
        },
    )

    extended_description: Optional[str] = Field(
        None,
        min_length=1,
        max_length=8192,
        description="Optional long description of the asset",
        json_schema_extra={
            "title": "Extended Description",
            "example": "ZIGChain (ZIG) is a Layer 1 blockchain focused on unlocking financial opportunities for everyone.",
        },
    )

    keywords: Optional[List[str]] = Field(
        None,
        description="Optional list of keywords (1-20 items) to help categorize/search this asset",
        json_schema_extra={"minContains": 1, "maxContains": 20},
    )

    @field_validator("keywords", mode="before")
    @classmethod
    def reject_non_list_keywords(cls, value):
        """Reject tuple/set for keywords — only list accepted."""
        return _reject_non_list(value, "keywords")

    @field_validator("keywords")
    @classmethod
    def validate_keywords(cls, value: Optional[List[str]]) -> Optional[List[str]]:
        if value is None:
            return None
        if not isinstance(value, list):
            raise ValueError("keywords must be a list of strings")
        if not (1 <= len(value) <= 20):
            raise ValueError("keywords must contain between 1 and 20 items")
        cleaned: List[str] = []
        for item in value:
            if not isinstance(item, str) or item.strip() == "":
                raise ValueError("keywords items must be non-empty strings")
            cleaned.append(item)
        return cleaned

    images: Optional[List[Union[ImageEntry, ImageSyncPointer]]] = Field(
        None,
        description=(
            "Optional images entries. Supports Cosmos chain-registry format, and also a shortcut form "
            "of {chain_name, base_denom} which will be transformed into image_sync during generation."
        ),
    )

    @field_validator("images", mode="before")
    @classmethod
    def reject_non_list_images(cls, value):
        """Reject tuple/set for images — only list accepted."""
        return _reject_non_list(value, "images")

    logo_uris: Optional[LogoUris] = Field(
        None,
        description="Image URLs for displaying the asset logo in different formats",
        json_schema_extra={
            "title": "Logo URIs",
            "example": {"png": "https://example.com/logo.png", "svg": "https://example.com/logo.svg"},
        },
    )

    @field_validator("logo_uris", mode="before")
    @classmethod
    def validate_logo_uris(cls, logo_uris):
        """Validate logo URIs are valid HTTPS URLs if provided."""
        if logo_uris is None:
            return logo_uris
        if isinstance(logo_uris, LogoUris):
            return logo_uris
        if isinstance(logo_uris, dict):
            for logo_type, url in logo_uris.items():
                if logo_type == "chain_name":
                    continue
                if url and not cls._is_valid_url(url):
                    raise ValueError(f"logo_uris.{logo_type} is not a valid URL: {url}")
            return logo_uris
        raise ValueError("logo_uris must be a LogoUris object or mapping of logo types to URLs")

    socials: Optional[Socials] = Field(
        None,
        description="Optional social links for the asset/project/community",
        json_schema_extra={
            "title": "Socials",
            "example": {
                "website": "https://example.com",
                "x": "https://x.com/example",
                "telegram": "https://t.me/example",
                "discord": "https://discord.gg/example",
                "github": "https://github.com/example",
                "medium": "https://medium.com/@example",
                "reddit": "https://reddit.com/r/example",
            },
        },
    )

    @field_validator("socials", mode="before")
    @classmethod
    def validate_socials(cls, socials):
        if socials is None:
            return socials
        if isinstance(socials, Socials):
            return socials
        if isinstance(socials, dict):
            return socials
        raise ValueError("socials must be a Socials object or mapping of platform names to URLs")

    coingecko_id: Optional[str] = Field(
        None,
        min_length=2,
        max_length=100,
        description="CoinGecko API slug for fetching price and market data (lowercase alphanumerics and hyphens only, e.g. 'usd-coin')",
        json_schema_extra={
            "title": "CoinGecko ID",
            "example": "usd-coin",
        },
    )

    is_verified: Optional[bool] = Field(
        None,
        description="Indicates if this asset has been verified or audited by the platform",
        json_schema_extra={
            "title": "Is Verified",
            "example": False,
        },
    )

    @field_validator("is_verified", mode="before")
    @classmethod
    def reject_non_bool_is_verified(cls, value):
        """Reject non-bool truthy/falsy values — only bool or None accepted."""
        if value is not None and not isinstance(value, bool):
            raise ValueError("is_verified must be a boolean, not a bool-like value")
        return value

    @field_validator("coingecko_id")
    @classmethod
    def validate_coingecko_id(cls, coingecko_id: Optional[str]) -> Optional[str]:
        """Validate CoinGecko slug format when provided."""
        if coingecko_id is None:
            return coingecko_id
        if not re.match(r"^[a-z0-9]+(-[a-z0-9]+)*$", coingecko_id):
            raise ValueError("coingecko_id must be lowercase alphanumerics separated by hyphens")
        return coingecko_id

    @staticmethod
    def _is_valid_url(url: str) -> bool:
        """Check if a string is a valid URL."""
        try:
            result = urlparse(url)
            return all([result.scheme, result.netloc])
        except Exception:
            return False

