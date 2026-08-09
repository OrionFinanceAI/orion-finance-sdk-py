# Orion Finance SDK

::::{container} orion-hero

Python SDK and CLI for Orion's [on-chain portfolio management infrastructure](https://github.com/OrionFinanceAI/protocol): deploy transparent vaults, submit strategist intents, and read protocol state, including the whitelisted investment universe, without leaving Python or the shell.

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
pip install "orion-finance-sdk-py>=1.5.0"
```
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
4. **Submit intents** with `orion submit-order`.

---

## Configure environment

Create a `.env` in your project directory. Keep it private and never commit it.

| Task | Variables |
| ---- | --------- |
| Deploy a vault | `MANAGER_PRIVATE_KEY`, `MANAGER_ADDRESS` (must match the key), optional `STRATEGIST_ADDRESS` / CLI flag |
| Submit intents | `ORION_VAULT_ADDRESS`, `STRATEGIST_PRIVATE_KEY` |
| Update strategist / fees / deposit access | `ORION_VAULT_ADDRESS`, `MANAGER_PRIVATE_KEY` |
| Read vault data | Pass `contract_address=` in Python, or set `ORION_VAULT_ADDRESS` |

**`RPC_URL` (optional).** If unset, the SDK probes default public Sepolia RPCs (`1rpc.io` → `0xrpc.io` → `publicnode`), matching `install.sh`. Set your own endpoint for higher rate limits, other networks, or long historical series.

### Getting an RPC URL (optional)

An RPC URL is the HTTP endpoint the SDK uses to talk to the chain. Popular options:

- **[Alchemy](https://alchemy.com/):** create an app → Ethereum / Sepolia → copy the HTTP URL → `RPC_URL=https://eth-sepolia.g.alchemy.com/v2/YOUR_API_KEY`
- **[Infura](https://infura.io/):** create a project → Sepolia → copy the HTTPS endpoint → `RPC_URL=https://sepolia.infura.io/v3/YOUR_API_KEY`

---

(vault-operations)=

## Vault operations

Managers create transparent vaults with the CLI.

### Deploy a transparent vault

```bash
orion deploy-vault \
  --name "Algorithmic Liquidity Provision & Hedging Agent" \
  --symbol "ALPHA" \
  --fee-type hard_hurdle \
  --performance-fee 100 \
  --management-fee 10 \
  --strategist-address 0x...
```

This deploys an ERC-7540 vault, registers the manager from your `.env`, sets fees, and makes allocations visible onchain.

**Verify:** the CLI prints the vault contract address - store it and share it with LPs. Set `ORION_VAULT_ADDRESS` for later commands.

### Update strategist or fees

```bash
orion update-strategist --new-strategist-address 0x...

orion update-fee-model \
  --fee-type high_water_mark \
  --performance-fee 5.5 \
  --management-fee 0.1
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
orion submit-order --order-intent order_intent.json

orion submit-order --order-intent '{"0x...": 0.5, "0x...": 0.5}'
```

Intents are collected and executed at the **next rebalance** (bundling, batching, netting).

### Portfolio file schema

| Column Name         | Type    | Description                                          |
| ------------------- | ------- | ---------------------------------------------------- |
| `address`           | string  | Token contract address (checksummed).                |
| `percentage_of_tvl` | decimal | Percentage of total vault value to allocate (0-100). |

Aliases: **`token`** / **`addr`** for address; **`weight`**, **`value`**, or **`percentage`** for weights. Columns named `percentage_of_tvl` / `percentage` are treated as **0–100** and normalized to fractions.

Example intent:

```json
{
  "0x...": 0.25,
  "0x...": 0.02,
  "0x...": 0.015,
  "0x...": 0.0255,
  "0x...": 0.06,
  "0x...": 0.4,
  "0x...": 0.22,
  "0x...": 0.0095
}
```

> **Note:** On **transparent** vaults, intents are visible onchain after submission. On **private** vaults, values are encrypted and only known to managers.

---

(analytics-and-reads)=

## Analytics and reads

### Point-in-time prices and portfolio weights

Point-in-time oracle prices for the investment universe, combined with vault holdings for portfolio weights:

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

`get_intent()` scales on-chain weights by `OrionConfig.strategist_intent_decimals` so they match the fractional weights used when submitting intents.

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

---

## API reference

```{toctree}
:maxdepth: 2

api
```
