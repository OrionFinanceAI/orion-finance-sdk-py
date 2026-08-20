# Orion Finance SDK

::::{container} orion-hero

Python SDK and CLI for Orion's [onchain portfolio management infrastructure](https://github.com/OrionFinanceAI/protocol): deploy vaults, submit strategist intents, and read protocol state, including the whitelisted investment universe, without leaving Python or the shell.

::::{container} orion-hero-links

- **PyPI:** [orion-finance-sdk-py](https://pypi.org/project/orion-finance-sdk-py/)
- **Source:** [GitHub](https://github.com/OrionFinanceAI/orion-finance-sdk-py)

::::

::::

## What you can do

::::{grid} 1 2 2 2
:gutter: 2

:::{grid-item-card} Install and configure
:link: quick-start
:link-type: ref

Install the CLI or package, set environment variables, and connect to an RPC.
:::

:::{grid-item-card} Use the console
:link: orion-console
:link-type: ref

Interactive `orion` menu and scriptable commands for every role.
:::

:::{grid-item-card} Investment universe
:link: investment-universe
:link-type: ref

List the onchain whitelist: names, addresses, and how to query it.
:::

:::{grid-item-card} Testnet sandbox
:link: testnet-sandbox
:link-type: ref

Sepolia twins, `mainnetSource()`, and which address to use where.
:::

:::{grid-item-card} Deploy and manage vaults
:link: vault-operations
:link-type: ref

Create transparent vaults, update strategist and fees, verify deployment.
:::

:::{grid-item-card} Submit strategist intents
:link: submit-intents
:link-type: ref

Push rebalancing allocations from JSON, CSV, Parquet, or an inline dict.
:::

:::{grid-item-card} Analyze universe and vaults
:link: analytics-and-reads
:link-type: ref

PIT prices, asset price history, share-price series, and intent vs holdings.
:::

:::{grid-item-card} Estimate execution cost
:link: execution-cost
:link-type: ref

Uniswap v3 fee and slippage for a signed asset trade, as of a calendar date.
:::

::::

---

(quick-start)=

## Quick start

::::{tab-set}

:::{tab-item} CLI
:sync: cli

```bash
curl -sSfL https://sdk.orionfinance.ai/cli/install.sh | sh
orion --help
```

Or install from PyPI:

```bash
pip install "orion-finance-sdk-py>=2.1.1"
```

Running `orion` with no arguments opens the {ref}`interactive console <orion-console>`.
:::

:::{tab-item} Python
:sync: python

```python
from orion_finance_sdk_py import OrionConfig

config = OrionConfig()
print(f"Risk-free Rate: {config.risk_free_rate}")
```
:::

::::

### Manager workflow

1. **Install** the SDK (above).
2. **Deploy** a vault with `orion deploy-vault` (managers).
3. **Set strategist** if you want to submit intents as the manager (`orion update-strategist`).
4. **Submit intents** with `orion submit-intent`.

---

## Configure environment

Create a `.env` in your project directory. Keep it private and never commit it.

| Task | Variables |
| ---- | --------- |
| Deploy / manage a vault | `MANAGER_PRIVATE_KEY`, `ORION_VAULT_ADDRESS` (after deploy) |
| Submit intents | `ORION_VAULT_ADDRESS`, `STRATEGIST_PRIVATE_KEY` |
| LP deposit / redeem | `ORION_VAULT_ADDRESS`, `LP_PRIVATE_KEY` |
| Read vault data | Pass `contract_address=` in Python, or set `ORION_VAULT_ADDRESS` |
| Estimate execution cost | Optional `MAINNET_RPC_URL` (public mainnet RPCs if unset) |

---

(orion-console)=

## Orion Console

The SDK ships a CLI named `orion`. With **no subcommand** it opens an interactive menu. With a subcommand it runs that action non-interactively.

```bash
orion          # interactive console
orion --help   # list scriptable commands
```

### Scriptable commands

```bash
orion deploy-vault --help
orion submit-intent --help
orion list-whitelisted-assets
orion list-asset-address-map
```

---

(investment-universe)=

## Investment universe

The investment universe is the onchain whitelist in `OrionConfig`: the only tokens a vault may hold and the only keys allowed in a strategist intent. The list is maintained on the protocol, not in this SDK, so query it rather than copying a static table.

Names come from `whitelisted_asset_names` (same order as the addresses).

### List from the console

```bash
orion list-whitelisted-assets
```

Or from the interactive menu: **Access and assets** → **List Whitelisted Assets**. The table prints name, address, and a total count.

On Sepolia, those addresses are **twins**. Map them to mainnet with `orion list-asset-address-map` ({ref}`testnet-sandbox`).

### List from Python

```python
from orion_finance_sdk_py import OrionConfig

config = OrionConfig()
for name, address in zip(
    config.whitelisted_asset_names,
    config.whitelisted_assets,
    strict=True,
):
    print(name.strip(), address)

config.is_whitelisted("0x...")
```

---

(testnet-sandbox)=

## Testnet sandbox

The operational sandbox is **Ethereum Sepolia**. Vaults, intents, and the {ref}`investment universe <investment-universe>` live there. Twin ERC-20s on Sepolia expose `mainnetSource()` so you can recover the Ethereum mainnet token they stand in for.

The SDK mapping is **testnet → mainnet**. Tokens that do not implement the getter, revert, or return `address(0)` are omitted.

```
Sepolia twin  --mainnetSource()-->  Ethereum mainnet token
     ^                                      ^
     |                                      |
  intents, whitelist, vaults           get_cost
```

### List the map

```bash
orion list-asset-address-map
```

Or from the interactive menu: **Access and assets** → **List Asset Address Map**. Each twin is printed as a Testnet / Mainnet pair.

```python
from orion_finance_sdk_py import build_asset_address_map

address_map = build_asset_address_map()
# {checksummed Sepolia address: checksummed mainnet address}
```

---

(vault-operations)=

## Vault operations

Managers create transparent or encrypted vaults with the CLI. Use the {ref}`interactive console <orion-console>` or the commands below.

### Deploy a vault

```bash
orion deploy-vault \
  --name "Algorithmic Liquidity Provision & Hedging Agent" \
  --symbol "ALPHA" \
  --fee-type hard_hurdle \
  --performance-fee 100 \
  --management-fee 10 \
  --strategist-address 0x... \
  --vault-type transparent
```

Use `--vault-type encrypted` for confidential vaults. Default is `transparent`.

This deploys an ERC-7540 vault, registers the manager from your `.env`, and sets fees.

### Update strategist or fees

```bash
orion update-strategist --new-strategist-address 0x...

orion update-fee-model \
  --fee-type high_water_mark \
  --performance-fee 5.5 \
  --management-fee 0.1
```

### LP deposit / redeem

Needs `ORION_VAULT_ADDRESS` and `LP_PRIVATE_KEY`. Amounts for deposit/cancel-deposit are human units of the vault underlying.

```bash
orion request-deposit --assets 1.5
orion cancel-deposit-request --amount 1.5
orion request-redeem --shares 500000
orion cancel-redeem-request --shares 500000
# After full decommission only:
orion redeem --shares 500000 --receiver 0x... --owner 0x...
```

### Remove / decommission vault (manager)

```bash
orion remove-vault
```

---

(submit-intents)=

## Submit rebalancing order intents

Strategists (or managers who set themselves as strategist) submit portfolio allocation intents executed on the next rebalancing cycle.

**`--order-intent`** (alias **`--order-intent-path`**) accepts a file or an inline string:

- **JSON file:** object mapping token addresses → weights (fractions summing to **1**).
- **CSV / Parquet:** tabular; Parquet needs **pyarrow** (`pip install 'orion-finance-sdk-py[parquet]'`).
- **Inline:** JSON object or Python `dict` literal.

```bash
orion submit-intent --order-intent order_intent.json

orion submit-intent --order-intent '{"0x...": 0.5, "0x...": 0.5}'
```

Intents are collected and executed at the **next rebalance** (bundling, batching, netting).

### Portfolio file schema

| Column Name         | Type    | Description                                          |
| ------------------- | ------- | ---------------------------------------------------- |
| `address`           | string  | Token contract address (checksummed).                |
| `percentage_of_tvl` | decimal | Percentage of total vault value to allocate (0-100). |

Aliases: **`token`** / **`addr`** for address; **`weight`**, **`value`**, or **`percentage`** for weights. Columns named `percentage_of_tvl` / `percentage` are treated as **0–100** and normalized to fractions.

Example intent (addresses must be on the current {ref}`investment universe <investment-universe>` for the chain you are connected to):

```json
{
  "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48": 0.5,
  "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2": 0.3,
  "0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599": 0.2
}
```

> **Note:** On **transparent** vaults, intents are visible onchain after submission. Confidential vault intents are sealed with Orion HPKE before submission, the chain stores an opaque `OrionCiphertext`:

```text
0x693658254630f73ad8da78fb331bf976cd42f90e0e9c9e83f40c51072a6f7417
bdb98ee21c5fbd63b638e332a609dad2c433b7dddcadec1f43586b8df178c488
01bc357ad2b6b530cfd9d63a8da1e0506ad748b7445373c5028131d0133fd503
172331decd5b2c69027a78699d713bb7426278f5cfa7754cb9e608f8cac946be
f38dd79d43391007eb7e87cca2a60b9e8ba869ae6dcdeb9289a09fa9748fc6a7
57160df5b25eb1fab133b18d11865a12f04a6ba70fa9a7f6c1dcf32fdffcabda
cd028fb3317650842264ba149850c24af40f1351564153ed0e0e00594caf6cef
a9981d8f622a44fe2c905be117a8d6a9c2cb51e787d6b27a7676bf6ccb89ed42
e3b8d9b4c24e887030a7caf503ba52d1d44510f73f5e7d30a396b4662a409178
234f21d6d9a3a1256b7ae0aac3a31c5f5242a66db00495f1a46f8d171dd7be9d
60d6dbaf04562614a8176738d66cf746101efeb2721f44ff2ed3ed3c3a1882ac
cbee5712dff0103eca8470ee5774e02e
```

---

(analytics-and-reads)=

## Analytics and reads

### Point-in-time prices and portfolio weights

Point-in-time oracle prices for the {ref}`investment universe <investment-universe>`, combined with vault holdings for portfolio weights:

```python
from orion_finance_sdk_py import (
    OrionTransparentVault,
    PriceAdapterRegistry,
)

registry = PriceAdapterRegistry()
prices = registry.get_prices()  # address -> price for every whitelisted asset

vault = OrionTransparentVault()  # or OrionTransparentVault(contract_address="0x...")
portfolio = vault.get_portfolio()  # address -> shares
pct_tvl = vault.get_portfolio_pct_tvl()  # address -> weight (sums to ~1)
pit_tvl = vault.point_in_time_total_assets()
share_price = vault.share_price  # value of 1 full share in underlying units
```

`PriceAdapterRegistry` is resolved from `OrionConfig.price_adapter_registry`. Pass `assets=` to `get_prices` to price a subset.

### Investment universe price history

Screen whitelisted assets before deploying a vault - daily PIT prices from the adapter registry:

```python
from datetime import datetime, timezone, timedelta

from orion_finance_sdk_py import OrionConfig, PriceAdapterRegistry

config = OrionConfig()
registry = PriceAdapterRegistry()
end = datetime.now(timezone.utc)
start = end - timedelta(days=30)
series = registry.price_history(start=start, end=end)
# [{"timestamp": int, "block": int, "prices": {addr: int, ...}}, ...]

# Optional subset:
# series = registry.price_history(
#     start=start, end=end, assets=config.whitelisted_assets[:3]
# )
```

For long series, set a dedicated `RPC_URL` - public endpoints are rate-limited.

A longer research walkthrough (excess returns, covariance, a sample portfolio) is in [`notebooks/investment_universe_research.ipynb`](https://github.com/OrionFinanceAI/orion-finance-sdk-py/blob/main/notebooks/investment_universe_research.ipynb).

### Vault metadata and strategist intent

```python
from orion_finance_sdk_py import OrionConfig, OrionTransparentVault

config = OrionConfig()
for addr in config.orion_transparent_vaults:
    vault = OrionTransparentVault(contract_address=addr)
    print(vault.name, vault.symbol, vault.decimals)
    print(vault.manager_address, vault.strategist_address)
    intent = vault.get_intent()  # address -> fraction (sum ≈ 1); {} if unset
    current = vault.get_portfolio_pct_tvl()
    # Diff intent vs current to reason about expected rebalancing
```

`get_intent()` scales onchain weights by `OrionConfig.strategist_intent_decimals` so they match the fractional weights used when submitting intents.

### Vault share price history

```python
from datetime import datetime, timezone, timedelta

from orion_finance_sdk_py import OrionConfig, OrionTransparentVault

config = OrionConfig()
for addr in config.orion_transparent_vaults:
    vault = OrionTransparentVault(contract_address=addr)
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=30)
    series = vault.share_price_history(start=start, end=end, interval="1d")
    # [{"timestamp": int, "block": int, "share_price": int}, ...]
```

You can also query a single past block with `vault.share_price_at(block)` or `registry.get_price(asset, block=...)`.

(execution-cost)=

## Estimate execution cost

Estimate Uniswap v3 execution cost (pool fee plus price impact) for a signed trade in an Orion universe asset versus USDC.

`signed_size` is human units of the risk asset: positive buys that many tokens (exact-output, matching adapter `buy`), negative sells them (exact-input, matching adapter `sell`).

When constructing `ExecutionCostEstimator` without an explicit `rpc_url` or `MAINNET_RPC_URL`, the SDK probes public Ethereum mainnet RPCs (`publicnode` → Alchemy public → `1rpc` → `drpc`). Set `MAINNET_RPC_URL` to an archival endpoint for historical `timestamp` queries and higher rate limits — public RPCs often cannot serve old `eth_call` snapshots.

```python
from orion_finance_sdk_py import ExecutionCostEstimator

est = ExecutionCostEstimator()
now = est.get_cost("WETH", 1.5)
btc = est.get_cost("WBTC", 0.5)
past = est.get_cost("WETH", 1.5, timestamp="2026-08-01")
netted = est.get_cost("WETH", 1.5, timestamp="2026-08-01", netting_eta=0.3)
# now.fee_pct, now.slippage_pct, now.cost_pct
```

- **symbol:** ticker (`WETH`, `WBTC`) or **mainnet** token address. Not a Sepolia twin — see {ref}`testnet-sandbox`.
- **timestamp:** UTC `YYYY-MM-DD`. Omitted means now. Unix seconds and block numbers are internal.
- **netting_eta:** shrinks the swap to `(1 - η) * signed_size`, then runs the full non-linear cost model on that size.

Cost coverage is a **subset** of the onchain {ref}`investment universe <investment-universe>`: WETH, WBTC, XAUt, USDT, and DAI versus USDC.

---

## API reference

```{toctree}
:maxdepth: 2

api
```
