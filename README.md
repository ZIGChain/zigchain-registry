# ZIGChain Registry

Canonical registry for ZIGChain. Includes metadata for native, factory, and IBC tokens, auto-generating wallet-ready asset lists and dApps — with the tooling to validate them, verify them on-chain, and publish them to the upstream [Cosmos Chain Registry](https://github.com/cosmos/chain-registry) so wallets and frontends render them correctly.

- **Native base denoms** (e.g., `uzig`) — manually added, maintainer-curated.
- **Factory tokens** (`coin.{creator}.{subdenom}`) — automatically discovered from the ZIGChain network.
- **IBC tokens** (`ibc/{hash}`) — manual whitelist; only verified, accepted assets are listed.

Assets live in `assets/{native,factory,ibc}/*.json` with a `network` suffix (`zig.mainnet.json`, `zig.testnet.json`). Validation is driven by Pydantic models in `models/` that serve as the single source of truth; JSON schemas in `schemas/` are auto-generated from them. The `scripts/generate_chain_registry.py` generator produces Cosmos-compatible `assetlist.json` outputs under `generated/chain-registry/` which can be synced to the upstream Cosmos Chain Registry.

---

## Quick Start (for contributors)

> Assumes prerequisites are installed (see [Prerequisites](#prerequisites-once-off)).

**Factory token** (automatically discovered — most common contributor path):

```bash
python3 scripts/import_factory_assets.py --network mainnet        # 1. Auto-import
# Edit the generated file under assets/factory/ to add logo_uris + description
python3 scripts/validate_assets.py --network mainnet              # 2. Validate
python3 scripts/verify_chain_denominations.py --network mainnet   # 3. Verify on-chain
git checkout -b feat/add-<symbol> && git add -A && git commit && git push && gh pr create
```

**IBC token** (hand-authored whitelist):

```bash
# Hand-author assets/ibc/<symbol>.<network>.json following the schema
python3 scripts/validate_assets.py --network mainnet
python3 scripts/verify_chain_denominations.py --network mainnet
git checkout -b feat/add-ibc-<symbol> && git add -A && git commit && git push && gh pr create
```

Native asset additions are maintainer-only — open an issue first if you think a new native denom belongs here.

The full walkthrough below explains what each step does, what to expect, and what to do if something fails.

---

## Contributor Walkthrough

### Prerequisites (once-off)

1. **Python 3.9+** with a virtual environment:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. **Optional `config.yaml`** for custom RPC/API endpoints:

   ```bash
   cp config.example.yaml config.yaml
   # Edit networks.mainnet.{rpc,api} / networks.testnet.{rpc,api} if needed
   ```

   If omitted, the scripts fall back to public Numia endpoints. See [Endpoint configuration](#endpoint-configuration) for details.

3. **`zigchaind` binary** — only required for factory token contributors (the importer shells out to `zigchaind q factory list-denom`). Install from the [ZIGChain node docs](https://docs.zigchain.com). Verify with `which zigchaind`.

4. **Git fork and remote wiring** — fork this repo on GitHub, clone your fork, and add this repo as `upstream`:

   ```bash
   git clone git@github.com:<your-user>/zigchain-registry.git
   cd zigchain-registry
   git remote add upstream git@github.com:ZIGChain/zigchain-registry.git
   ```

### Step 1 — Create a feature branch

```bash
git fetch upstream && git checkout -b feat/add-<symbol> upstream/main
```

Never work directly on `main`. A branch per asset addition keeps PRs focused and reviewable.

**If it fails:** check `git remote -v` — `upstream` must point at `ZIGChain/zigchain-registry`.

### Step 2 — Choose your asset type

```
Is your token minted via the ZIGChain x/factory module (denom looks like coin.{creator}.{subdenom})?
├── Yes → Step 4a (Factory)
└── No
    ├── Is it bridged via IBC from another chain (denom looks like ibc/{HASH})?
    │   └── Yes → Step 4b (IBC)
    └── Otherwise (a new native base denom)
        └── Stop — native additions are maintainer-only. Open an issue first.
```

### Step 3 — Prepare the logo

- **Format:** PNG required; SVG optional but recommended.
- **Dimensions:** square (1:1 aspect ratio).
- **Size:** maximum 250 KB per file.
- **Location:** drop the files directly in the `logos/` directory (flat — no subdirectories).
- **Naming:** use the asset's `asset_id` or `symbol` as the filename (e.g., `zigchain.png`, `stzig.svg`).

The filename you choose **must match** the path in your asset file's `logo_uris` URL. For example, `logos/mytoken.png` → `https://raw.githubusercontent.com/ZIGChain/zigchain-registry/main/logos/mytoken.png`. A mismatch here is caught at CI time, not locally.

**If the logo is too large or non-square:** compress/crop to spec before committing. CI checks URL reachability (post-merge), not file dimensions (pre-commit).

### Step 4 — Author the asset file

#### Step 4a — Factory token (auto-import)

```bash
python3 scripts/import_factory_assets.py --network mainnet
```

**What it does:** queries `zigchaind q factory list-denom` (paginated), derives `symbol` / `name` / `display_denom` from the subdenom, and writes `assets/factory/coin.{creator}.{subdenom}.{network}.json`. Existing files are skipped unless you pass `--overwrite`. When re-importing with `--overwrite`, maintainer-edited fields like `is_verified`, `description`, `logo_uris`, and socials are preserved.

**Expected output:** one `✅ Created` line per new asset, `⏭️ Skipped` for existing files, and an `✅ Import complete` summary with counts.

**What you must edit afterward:** open the generated file under `assets/factory/` and add:

- `logo_uris.png` (required) and `logo_uris.svg` (optional) — pointing at your logos from Step 3.
- `description` — a short human description of the token.
- Optional: `website`, `twitter`, or other social links.

**Leave `is_verified` alone.** It stays `false` for new contributions. A maintainer flips it to `true` after review — see [What Happens After You Open the PR](#what-happens-after-you-open-the-pr).

**If the script fails:**
- `zigchaind: command not found` — install the binary and re-run (`--zigchaind-path /custom/path` overrides PATH lookup).
- `Network error` — override endpoints via `config.yaml`, or retry (the public Numia RPC is occasionally rate-limited).

#### Step 4b — IBC token (hand-authored whitelist)

IBC tokens are curated manually. Create `assets/ibc/<symbol>.<network>.json` following the IBC schema (`schemas/asset.ibc.schema.json`). Required fields:

- `network`, `asset_id`, `type: "ibc"`, `symbol`, `name`, `decimals`, `display_denom`
- `base_denom`: must match `ibc/{HASH}` (uppercase 64-char hex)
- `hash`: the IBC hash (without the `ibc/` prefix)
- `origin_chain`: canonical chain name (e.g., `cosmoshub`, `osmosis`, `noble`)
- `origin_denom`: the base denom on the origin chain
- `traces` and `channels`: IBC trace / channel metadata

Use an existing IBC asset (e.g., `assets/ibc/atom.mainnet.json`) as a template. The IBC hash is deterministic from the channel and origin denom — derive it with `zigchaind q ibc-transfer denom-hash {trace}` or the [Cosmos IBC denom tool](https://tfm.com/ibc).

**If protected-asset rules flag your PR** (e.g., a USDC-symbol asset must originate from Noble): confirm the `origin_chain` matches the expected canonical source. See [Protected external asset verification](#protected-external-asset-verification) for the list.

#### Step 4c — Native asset (maintainer-only)

Only `ZIG` exists today. Adding a new native base denom is a maintainer decision with chain-level implications. Open an issue instead of sending a PR.

### Step 5 — Validate locally

```bash
python3 scripts/validate_assets.py --network mainnet
```

**What it does:** loads every asset file, validates against the Pydantic models, checks cross-file integrity (no duplicate `asset_id` or `base_denom` within a network), and enforces protected-asset rules (factory tokens can't impersonate well-known symbols like USDC/USDT).

**Expected output:**

```
✅ All assets validated successfully for network 'mainnet'!
Protection validation: N assets checked, 0 violations, 0 warnings
```

**Violations vs warnings:**
- **Violations block merge.** Fix your asset file and re-run.
- **Warnings are advisory** (e.g., a factory token with a symbol similar to a protected asset like `USDCX`). Mention the warning in your PR description; a maintainer will decide.

**If it fails:**
- Pydantic error listing a field → fix that field per the schema.
- `Duplicate asset_id` / `Duplicate base_denom` → another file already claims this identifier; pick a different one or confirm this isn't a duplicate submission.

### Step 6 — Verify on-chain

```bash
python3 scripts/verify_chain_denominations.py --network mainnet
```

For testnet contributions, pass `--network testnet`.

**What it does:** queries the ZIGChain REST API (`/cosmos/bank/v1beta1/supply` and `/zigchain/factory/denom`) and reconciles your registry entry against what actually exists on-chain. Factory tokens with zero supply are handled via the factory module query; native and IBC tokens are checked against bank supply.

**Expected output:**

```
✅ All assets verified successfully for this network.
```

**If it fails:**
- `Network error` / `HTTP error` — transient RPC issue. Retry, or override endpoints in `config.yaml` (see [Endpoint configuration](#endpoint-configuration)).
- Your asset appears as *missing on-chain* — confirm you used the correct `base_denom`, and that the token actually exists on the network you're targeting. IBC tokens must exist in bank supply; a not-yet-bridged token will fail here.

### Step 7 — Preview the generated output (optional)

```bash
python3 scripts/generate_chain_registry.py --skip-sync
```

**What it does:** walks `assets/` + `logos/`, builds a Cosmos-compatible `assetlist.json` under `generated/chain-registry/` for each network that has assets, and copies logos into the corresponding `images/` folders.

**Verified-only is the default.** Since your new contribution has `is_verified: false`, it will **not** appear in the generated output until a maintainer flips the flag during review. Empty diffs here are expected — this is a preview of what would ship upstream today, not of what your PR proposes.

To preview your contribution locally anyway:

```bash
python3 scripts/generate_chain_registry.py --include-unverified --skip-sync
```

The `--include-unverified` flag must be paired with `--skip-sync` — unverified assets must never be synced upstream.

### Step 8 — Commit, push, open a PR

```bash
git add assets/ logos/
git commit -m "feat: add <symbol> factory asset"
git push -u origin feat/add-<symbol>
gh pr create --title "feat: add <symbol>" --body "..."
```

Reference any protected-asset warnings from Step 5 in your PR description so the maintainer knows to review them explicitly.

---

## What Happens After You Open the PR

### CI checks to expect

Five workflows run on every PR:

| Workflow | What it checks |
|---|---|
| `Validate Assets` (`validate.yml`) | Pydantic validation + cross-file integrity + protected-asset rules. Same as `scripts/validate_assets.py`. |
| `Check Schema Generation` (`check-schema.yml`) | Ensures the JSON schemas in `schemas/` are up-to-date with the Pydantic models. |
| `Verify Chain Denominations (Mainnet + Testnet)` (`verify-chain-denoms.yml`) | Registry ↔ on-chain reconciliation. Same as `scripts/verify_chain_denominations.py`. |
| `Check is_verified changes` (`check-is-verified.yml`) | Blocks PRs that flip `is_verified: false → true` without maintainer acknowledgment. For contributors this check should simply pass (you're not flipping anything). |
| `Tests` (`test.yml`) | Runs the full pytest suite. |

If a check fails after you push, read the failure log, fix locally, and push again — CI re-runs automatically.

### Maintainer review and `is_verified` flip

A maintainer reviews your PR. If accepted, they set `is_verified: true` on your asset(s) in a follow-up commit. This flip requires explicit maintainer action — it cannot be done by a contributor without the `check-is-verified.yml` workflow blocking the PR.

### Upstream Cosmos Chain Registry sync

Once merged and verified, your asset is eligible for inclusion in the upstream [Cosmos Chain Registry](https://github.com/cosmos/chain-registry). Maintainers batch verified additions and open sync PRs upstream periodically.

If you'd like to open the upstream PR yourself after your asset is verified, it's welcome — fork `cosmos/chain-registry`, apply the relevant files from this repo's `generated/chain-registry/` output, and open a PR. Otherwise, it's handled for you.

---

## EVM Chain Registry

Alongside Cosmos chain/asset data, this repo is the canonical source-of-truth for ZIGChain's **EVM** chain metadata (chainId, RPC, explorer, faucet, native currency). The same operator-driven sync pattern that mirrors Cosmos data into `cosmos/chain-registry` mirrors EVM data into [`ethereum-lists/chains`](https://github.com/ethereum-lists/chains) — which then propagates automatically to `chainid.network/chains.json` and `chainlist.org`.

ZIGChain currently registers:
- Mainnet (`zigchain-1`) → EVM chain ID **944**, shortName `zigchain`
- Testnet (`zig-test-2`) → EVM chain ID **2061**, shortName `zigchain-testnet`

### Directory layout

```
chains/evm/
├── zigchain-mainnet.json    # chainId 944
└── zigchain-testnet.json    # chainId 2061
```

Each file is validated against `schemas/chain.evm.schema.json` (auto-generated from `models/evm_chain.py`). The schema mirrors the field set required by [ethereum-lists/chains/tools/schema/chainSchema.json](https://github.com/ethereum-lists/chains/blob/master/tools/schema/chainSchema.json) and adds three repo-local extensions that are stripped before upstream emit:

- `cosmos_chain_id` — link back to the Cosmos chain (e.g. `zigchain-1`), so internal consumers (UIs, SDKs) can join the two registries from a single source.
- `icon_path` — repo-relative path to a local logo asset for our own UI consumption (the upstream `icon` field is a separate IPFS-pinned slug — out of scope for v1).
- `is_verified` — matches the existing `is_verified` convention used elsewhere in the repo.

### Editing an EVM chain entry

To update RPC URLs, add an explorer, or tweak metadata: edit the JSON file directly. CI's `validate.yml` will fail the PR if the file no longer matches `chain.evm.schema.json`. Run validation locally with:

```bash
python scripts/validate_assets.py --repo-root .
```

### Syncing to ethereum-lists/chains

The sync helper clones `ethereum-lists/chains`, writes our EIP-155 payloads under `_data/chains/eip155-<id>.json`, runs `prettier --write` on them (required by their CI), pushes a timestamped branch to a fork at `ZIGChain/chains`, and prints a GitHub compare URL plus a ready-to-paste PR body.

```bash
# Dry-run: validate + render to generated/evm/, no git operations
python scripts/generate_chain_registry.py --sync-evm --sync-evm-dry-run

# Full sync (operator-driven; you click the printed compare URL to open the PR)
python scripts/generate_chain_registry.py --sync-evm

# Re-sync an already-registered chain (e.g. to update RPC URLs after merge)
python scripts/generate_chain_registry.py --sync-evm --sync-evm-update
```

**Pre-flight checks** run automatically before any git push (skip with `--sync-evm-skip-preflight` for offline dev):

1. **RPC liveness** — POST `eth_chainId` to every URL in `rpc[]`, refuse if any URL is unreachable or returns the wrong `chainId`. This replicates ethereum-lists' Kotlin validator (the #1 cause of failed upstream PRs).
2. **Uniqueness** — GET `chainid.network/chains.json` and `shortNameMapping.json`, refuse if our chainIds or shortNames collide. Use `--sync-evm-update` to bypass (for re-sync flow).
3. **Fork existence + open-branch detection** — `git ls-remote` against the fork; refuse if `zigchain-evm-sync-*` branches already exist on the fork (pass `--sync-evm-force-new-branch` to override).
4. **Tooling** — `prettier` or `npx` must be on PATH (ethereum-lists CI rejects formatting diffs).

**Two registration flows are supported:**

1. **ChainId-locking (no EVM infra needed)** — register with empty `rpc: []`, no `explorers`, `status: "incubating"`. Reserves the chainId at ethereum-lists/chains before the EVM JSON-RPC + Blockscout are deployed. ligi's Kotlin validator has no URLs to probe, so it can't fail. Upstream precedent: [eip155-152 Redbelly Devnet](https://github.com/ethereum-lists/chains/blob/master/_data/chains/eip155-152.json). This is the current state of `chains/evm/zigchain-{mainnet,testnet}.json`.
2. **Full registration (EVM JSON-RPC live)** — once the validator-side prerequisite below is met, populate `rpc[]` and `explorers[]`, then re-run `python scripts/generate_chain_registry.py --sync-evm --sync-evm-update` to push an updated entry to the same upstream files.

**Validator-infra prerequisite (required only for flow 2):**

The Cosmos EVM JSON-RPC service is a **separate listener** from Tendermint RPC and is **disabled by default**. It must be explicitly enabled in `app.toml` on at least one publicly-reachable validator per network (mainnet + testnet) so ligi's Kotlin validator at `ethereum-lists/chains` can probe it via `eth_chainId`:

```toml
# app.toml
[json-rpc]
enable = true
address = "0.0.0.0:8545"
```

See the [Cosmos EVM JSON-RPC reference](https://docs.cosmos.network/evm/latest/api-reference/ethereum-json-rpc) for the full configuration. You also need an EVM-aware block explorer (e.g. Blockscout) pointed at the EVM JSON-RPC — none of the Cosmos-side explorers (Range, zigscan.org, NodeStake) handle `/tx/<0x…>` or `/address/<0x…>` routes that ethereum-lists expects.

**Requirements before first sync (operator-side, both flows):**
- A `ZIGChain/chains` fork of `ethereum-lists/chains` must exist with SSH push access for the operator.
- Public ZIGChain EVM RPC must be reachable and return the correct `chainId` (flow 2 only — flow 1 has no RPCs to check).
- `npm` / `npx` installed (or `prettier` globally) — `npm i -g prettier`.

**CLI flag reference:**

| Flag | Behavior |
| --- | --- |
| `--sync-evm` | Dispatch to the EVM sync (mutually exclusive with the Cosmos generate flow). |
| `--sync-evm-dry-run` | Render + validate to `generated/evm/`; no git operations. |
| `--sync-evm-update` | Allow re-sync of an already-registered chain (swaps the uniqueness check for a positive existence check — refuses if the chainId isn't already on `chainid.network`). |
| `--sync-evm-skip-preflight` | Skip RPC, uniqueness, and prettier checks (dev/test only). |
| `--sync-evm-force-new-branch` | Push a new branch even if existing `zigchain-evm-sync-*` branches exist on the fork. |
| `--sync-evm-upstream-repo URL` | Override upstream (default: `https://github.com/ethereum-lists/chains`). |
| `--sync-evm-fork-repo URL` | Override fork (default: `https://github.com/ZIGChain/chains`). |

### What ends up in `ethereum-lists/chains`

A single PR adds two files: `_data/chains/eip155-944.json` (mainnet) and `_data/chains/eip155-2061.json` (testnet). Once merged, `chainid.network/chains.json` and `chainlist.org` reflect the entries within ~hours (CDN refresh).

[`DefiLlama/chainlist`](https://github.com/DefiLlama/chainlist) is a **separate repo** for overrides (extra RPCs, custom display names, priority); it does **not** auto-import from `ethereum-lists/chains`. The basic metadata on chainlist.org does come from chainid.network, so a DefiLlama PR is only needed if we want custom overrides — deferred until a concrete need.

### Out of scope for v1

- **Icon submission** — ethereum-lists icons require IPFS pinning (Pinata explicitly disallowed). Tracked for a follow-up. v1 leaves `icon` unset; our internal UIs use `icon_path` instead.
- **DefiLlama/chainlist PR** — see above; opt-in only.
- **Devnet registration** — schema supports it; we don't have a stable devnet to register yet.
- **GitHub Action automation** — sync is operator-driven by design (preserves the human-review checkpoint that ligi expects).

---

## Reference

### Asset file structure and naming

Every asset file must include:

- `network` — `"mainnet"` or `"testnet"`.
- `asset_id` — deterministic identifier, lowercase.
- `type` — `"native"`, `"factory"`, or `"ibc"`.
- `symbol`, `name`, `decimals`, `display_denom`.
- `denom_units` — array with exponent `0` matching `base_denom` exactly, and an exponent matching `decimals` for the display unit.

Asset filenames must include the network suffix, e.g., `zig.mainnet.json`. Factory files must use the full denom to avoid creator-collisions: `coin.{creator}.{subdenom}.{network}.json`.

**Example — native asset:**

```json
{
  "network": "mainnet",
  "asset_id": "zig",
  "type": "native",
  "symbol": "ZIG",
  "name": "ZIGChain Native Token",
  "description": "The native staking token of ZIGChain",
  "decimals": 6,
  "display_denom": "ZIG",
  "base_denom": "uzig",
  "denom_units": [
    { "denom": "uzig", "exponent": 0 },
    { "denom": "ZIG", "exponent": 6 }
  ],
  "logo_uris": {
    "png": "https://raw.githubusercontent.com/ZIGChain/zigchain-registry/main/logos/zigchain.png",
    "svg": "https://raw.githubusercontent.com/ZIGChain/zigchain-registry/main/logos/zigchain.svg"
  }
}
```

### Schemas — Pydantic as source of truth

The JSON schemas in `schemas/` are **auto-generated** from the Pydantic models in `models/`. Never edit `schemas/*.json` by hand — changes will be overwritten on the next schema generation. To modify validation rules, update the Pydantic models and regenerate schemas (see the [Maintainer Guide](#maintainer-guide)).

### Logo specifications

See [Step 3](#step-3--prepare-the-logo). Key points:

- PNG required, SVG optional.
- Square (1:1), ≤ 250 KB.
- Flat directory: `logos/<filename>.{png,svg}`.
- **Filename must match** the path in `logo_uris` URLs.

### Protected external asset verification

Factory tokens cannot impersonate well-known external assets. Configuration lives in `config/protected_assets.json`. Each entry defines:

- `symbol` — the protected symbol (e.g., `USDC`).
- `name` — the protected name (e.g., `USD Coin`).
- `allowed_types` — which asset types may use this symbol (e.g., `["ibc"]` for USDC).
- `expected_origin_chains` — for IBC assets using a protected symbol, the origin chain must be in this list (e.g., USDC from `noble`).
- `similar_patterns` — optional regex that flags close variants (e.g., `USDCX`) as warnings.

Factory tokens with a protected symbol fail validation outright. IBC tokens with a protected symbol must originate from an expected chain, or they fail. Similar-symbol warnings surface in the `validate_assets.py` output for manual review.

### Endpoint configuration

Scripts that query ZIGChain nodes or REST APIs read endpoints from `config.yaml`. Endpoints are **not hard-coded**; they're resolved via the `get_rpc_endpoint(network)` and `get_api_endpoint(network)` functions in `scripts/config.py`.

**Setup:**

```bash
cp config.example.yaml config.yaml
# Edit the endpoints if you want to use custom RPCs
```

- `networks.<network>.rpc` — used by `scripts/import_factory_assets.py` via `zigchaind --node <rpc>`.
- `networks.<network>.api` — used by `scripts/verify_chain_denominations.py` for REST queries.

`config.yaml` is git-ignored. If it's missing, scripts fall back to public Numia endpoints.

### Multi-network support

Assets from different networks live in the same directory tree, distinguished by their `network` field and filename suffix (`*.mainnet.json`, `*.testnet.json`). Generated outputs are written per-network:

- **Mainnet:** `generated/chain-registry/zigchain/` and `_non-cosmos/ethereum/`.
- **Testnet:** `generated/chain-registry/testnets/zigchaintestnet/` and `testnets/_non-cosmos/ethereumtestnet/` — only written when testnet assets exist.

---

## Maintainer Guide

> Not for community contributors. The scripts in this section modify generated artifacts, change validation rules, or flip verification flags.

### Modifying validation rules (`generate_schemas.py`)

When you change a Pydantic model in `models/`, regenerate the JSON schemas:

```bash
python3 scripts/generate_schemas.py
```

**Expected output:** one `✅ Generated <filename>` line per schema, then `✅ All schemas generated successfully!`.

The `check-schema.yml` CI workflow fails if this was forgotten.

### Pre-strictness-change audit (`audit_strictness.py`)

A dry-run lint that reports how many existing assets would break under a proposed stricter ruleset (channel-pattern regex, `transfer/` prefix, length caps, etc.):

```bash
python3 scripts/audit_strictness.py
```

**Expected output (clean):** `✅ No issues found — all assets are compatible with proposed strict rules.`

Exit code 1 means at least one asset would break — inspect the report before tightening the model.

### The `is_verified` flip policy

`is_verified: true` indicates a human maintainer has vetted the asset. Flipping `false → true` is the **only** contributor-disallowed action in this repo. The `check-is-verified.yml` CI workflow enforces this.

**Bypass token:** include the literal string `[allow-verified]` anywhere in a commit message in the PR range to authorize the flip. Use this deliberately — it's a conscious acknowledgment that the flip is maintainer-approved.

### CI guard (`scripts/ci/check_is_verified.py`)

The workflow's underlying logic. Diffs `BASE_SHA..HEAD_SHA` for `assets/**/*.json` and fails if any file flips `is_verified` from false/missing to true without the bypass token.

Exit codes: `0` pass, `1` violation, `2` script error.

### Upstream Cosmos Chain Registry sync

After verified assets are merged here, sync to the upstream fork with:

```bash
python3 scripts/generate_chain_registry.py \
  --upstream-repo cosmos/chain-registry \
  --fork-repo ZIGChain/chain-registry
```

This clones the fork, copies the generated `assetlist.json` + `images/` into place, pushes a branch, and prints a PR URL. Pair with `--git-no-prompt` / `--git-env-file` for CI usage. Use `--skip-sync` for local dry-runs (no git operations).

---

## Repository Structure

```
zigchain-registry/
├── README.md
├── requirements.txt              # Python dependencies
├── config.example.yaml           # Copy to config.yaml for custom endpoints
├── models/                       # Pydantic models (single source of truth)
│   ├── base.py
│   ├── native.py
│   ├── factory.py
│   └── ibc.py
├── schemas/                      # Auto-generated JSON schemas — do not edit
├── assets/
│   ├── native/                   # Native asset JSONs (ZIG only)
│   ├── factory/                  # Factory token JSONs (auto-discovered)
│   └── ibc/                      # IBC token JSONs (manual whitelist)
├── config/
│   └── protected_assets.json     # Symbols that can't be impersonated
├── logos/                        # Flat directory of PNG/SVG logos
├── generated/
│   └── chain-registry/           # Generated Cosmos assetlists (per-network)
├── scripts/
│   ├── validate_assets.py                 # Pydantic + integrity + protection
│   ├── import_factory_assets.py           # Auto-import factory tokens
│   ├── verify_chain_denominations.py      # Registry ↔ on-chain reconciliation
│   ├── generate_chain_registry.py         # Build Cosmos chain-registry output
│   ├── generate_schemas.py                # Regenerate schemas from models
│   ├── audit_strictness.py                # Dry-run strictness audit
│   ├── config.py                          # Endpoint resolution module
│   └── ci/
│       └── check_is_verified.py           # CI guard for the is_verified flip
└── .github/workflows/            # validate, check-schema, verify-chain-denoms,
                                  # check-is-verified, test
```

## License

Apache License 2.0 — see [LICENSE](LICENSE).
