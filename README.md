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

# Run tests
make test

# Run tests with coverage
make test  # Coverage is included automatically

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

The SDK requires the user to specify an `RPC_URL` environment variable in the `.env` file of the project. Follow the [SDK Installation](https://sdk.orionfinance.ai/) to get one.

Based on the usage, additional environment variables may be required, e.g.:
- `STRATEGIST_ADDRESS`: The address of the strategist account.
- `MANAGER_PRIVATE_KEY`: The private key of the vault manager account.
- `STRATEGIST_PRIVATE_KEY`: The private key of the strategist account.
- `ORION_VAULT_ADDRESS`: The address of the Orion vault.

## Examples of Usage

### List available commands

```bash
orion --help
orion deploy-vault --help
orion submit-order --help
```

### Deploy a new Transparent Orion vault

```bash
orion deploy-vault --vault-type transparent --name "Algorithmic Liquidity Provision & Hedging Agent" --symbol "ALPHA" --fee-type hard_hurdle --performance-fee 10 --management-fee 1
```

### Submit an order intent to a vault

```bash
# Use off-chain stack to generate an order intent
echo '{"0x...": 0.4, "0x...": 0.2, "0x...": 0.15, "0x...": 0.15, "0x...": 0.1}' > order_intent.json

# Submit the order intent to the Orion vault
orion submit-order --order-intent-path order_intent.json
```

### Update the strategist address for a vault

```bash
orion update-strategist --new-strategist-address 0x...
```

### Update the fee model for a vault

```bash
orion update-fee-model --fee-type high_water_mark --performance-fee 5.5 --management-fee 0.1
```
