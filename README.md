<div align="center">

<img src="./assets/Orion_Logo_white_horizontal.png" alt="Orion" width="75%">

[![codecov][codecov-badge]][codecov] [![Sourcery][sourcery-badge]][sourcery] [![Github Actions][gha-badge]][gha] [![Ape][ape-badge]][ape]

[![LinkedIn][linkedin-badge]][linkedin] [![X][x-badge]][x] [![Telegram][telegram-badge]][telegram] [![Discord][discord-badge]][discord]

</div>

[gha]: https://github.com/OrionFinanceAI/orion-finance-sdk-py/actions
[gha-badge]: https://github.com/OrionFinanceAI/orion-finance-sdk-py/actions/workflows/build.yml/badge.svg

[codecov]: https://codecov.io/gh/OrionFinanceAI/orion-finance-sdk-py/graph/badge.svg?token=SJLL2VVQDS
[codecov-badge]: https://codecov.io/gh/OrionFinanceAI/orion-finance-sdk-py/branch/main/graph/badge.svg

[sourcery]: https://sourcery.ai
[sourcery-badge]: https://img.shields.io/badge/Sourcery-enabled-brightgreen

[ape]: https://docs.apeworx.io/
[ape-badge]: https://img.shields.io/badge/Built%20with-Ape-8C52FF.svg

[linkedin]: https://www.linkedin.com/company/orionfinance/
[linkedin-badge]: https://img.shields.io/badge/LinkedIn-0077B5?style=for-the-badge&logo=linkedin&logoColor=white

[x]: https://x.com/OrionFinanceAI
[x-badge]: https://img.shields.io/badge/X-000000?style=for-the-badge&logo=x&logoColor=white

[telegram]: https://t.me/orionfinance_ai
[telegram-badge]: https://img.shields.io/badge/Telegram-2CA5E0?style=for-the-badge&logo=telegram&logoColor=white

[discord]: https://discord.gg/8bAXxPSPdw
[discord-badge]: https://img.shields.io/badge/Discord-5865F2?style=for-the-badge&logo=discord&logoColor=white

[docs]: https://sdk.orionfinance.ai/
[docs-badge]: https://img.shields.io/badge/Documentation-Read%20the%20Docs-blue?style=for-the-badge&logo=readthedocs&logoColor=white

## About

A Python Software Development Kit (SDK) to facilitate interactions with the Orion Finance protocol. This repository provides tools and utilities for quants and developers to seamlessly integrate with Orion's [on-chain portfolio management infrastructure](https://github.com/OrionFinanceAI/protocol).

<div align="center">
  
[![Documentation][docs-badge]][docs]

</div>

For comprehensive documentation, including setup guides, API references, and developer resources, visit [sdk.orionfinance.ai](https://sdk.orionfinance.ai/).

## License

This software is distributed under the BSD-3-Clause license. See the [`LICENSE`](./LICENSE) file for the full text.

## Setup for Development

If you're working on the SDK itself:

```bash
# Clone the repository
git clone https://github.com/OrionFinanceAI/orion-finance-sdk-py.git
cd orion-finance-sdk-py

# Install dependencies
make uv-download
make venv
source .venv/bin/activate
make install

# Run tests (includes coverage)
make test

# Run code style checks
make codestyle

# Run docstring checks
make docs
```

### Installation from PyPI

For end users, install the latest stable version from PyPI:

```bash
pip install orion-finance-sdk-py
```

## Environment Variables Setup

The SDK uses `RPC_URL` from your `.env` if set; otherwise it probes default public Sepolia RPCs in order (1rpc.io → 0xrpc.io → publicnode), matching `install.sh`. For long historical queries, set your own `RPC_URL` (e.g. Alchemy/Infura). See [SDK Installation](https://sdk.orionfinance.ai/) for optional RPC setup.

Additional variables depend on what you do:
- **Deploy a vault:** `STRATEGIST_ADDRESS`, `MANAGER_PRIVATE_KEY`
- **Submit orders:** `ORION_VAULT_ADDRESS`, `STRATEGIST_PRIVATE_KEY`
- **Update strategist / fee model / deposit access:** `ORION_VAULT_ADDRESS`, `MANAGER_PRIVATE_KEY`
- **Read vault data:** pass `contract_address=` or set `ORION_VAULT_ADDRESS`

## Examples of Usage

The SDK supports **transparent** Orion vaults: deploy, read state, submit order intents, and manage fees/strategist via the CLI or Python API.

### List available commands

```bash
orion --help
orion deploy-vault --help
orion submit-order --help
```

### Deploy a new Orion vault

```bash
orion deploy-vault --strategist-address 0x... --name "Algorithmic Liquidity Provision & Hedging Agent" --symbol "ALPHA" --fee-type hard_hurdle --performance-fee 10 --management-fee 1
```

### Submit an order intent to a vault

`submit-order` accepts **`--order-intent`** (alias **`--order-intent-path`**):

- **File:** `.json` (object mapping addresses → weights that sum to 1), `.csv` / `.parquet` (tabular; see [docs](https://sdk.orionfinance.ai/))
- **Inline:** a JSON object or Python `dict` literal string (no file needed)

```bash
# From a JSON file
echo '{"0x...": 0.4, "0x...": 0.2, "0x...": 0.15, "0x...": 0.15, "0x...": 0.1}' > order_intent.json
orion submit-order --order-intent order_intent.json

# Inline
orion submit-order --order-intent '{"0x...": 0.4, "0x...": 0.6}'
```

Parquet support requires **pyarrow** (`pip install 'orion-finance-sdk-py[parquet]'` or it is included in the dev extra).

### Update the strategist address for a vault

```bash
orion update-strategist --new-strategist-address 0x...
```

### PIT prices and portfolio %TVL (Python)

```python
from orion_finance_sdk_py import OrionTransparentVault, PriceAdapterRegistry

prices = PriceAdapterRegistry().get_prices()  # full investment universe
vault = OrionTransparentVault()
weights = vault.get_portfolio_pct_tvl()  # portfolio as fractions of PIT TVL
```

### Discover vaults, metadata, and intent (Python)

```python
from orion_finance_sdk_py import OrionConfig, OrionTransparentVault

config = OrionConfig()
for addr in config.orion_transparent_vaults:
    vault = OrionTransparentVault(contract_address=addr)
    print(vault.name, vault.symbol, vault.share_price)
    intent = vault.get_intent()  # target weights (fractions, sum ≈ 1)
    current = vault.get_portfolio_pct_tvl()  # PIT allocation
    # Compare intent vs current for expected rebalancing (in your notebook)
```

### Vault share price history (notebook)

The SDK reads on-chain share prices (live or historical). Use pandas in your notebook for correlation analysis:

```python
from datetime import datetime, timezone, timedelta

from orion_finance_sdk_py import OrionConfig, OrionTransparentVault

config = OrionConfig()
vault_addr = config.orion_transparent_vaults[0]
vault = OrionTransparentVault(contract_address=vault_addr)

end = datetime.now(timezone.utc)
start = end - timedelta(days=30)
series = vault.share_price_history(start=start, end=end, interval="1d")
# series: [{"timestamp", "block", "share_price"}, ...]

# Optional — analytics stay in the notebook:
# import pandas as pd
# df = pd.DataFrame(series).set_index("timestamp")
# df["share_price"].pct_change().corr(...)
```

### Update the fee model for a vault

```bash
orion update-fee-model --fee-type high_water_mark --performance-fee 5.5 --management-fee 0.1
```
