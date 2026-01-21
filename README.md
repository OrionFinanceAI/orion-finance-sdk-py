# orion-finance-sdk-py

<div align="center">

[![codecov][codecov-badge]][codecov] [![Github Actions][gha-badge]][gha]


</div>

[gha]: https://github.com/OrionFinanceAI/orion-finance-sdk-py/actions
[gha-badge]: https://github.com/OrionFinanceAI/orion-finance-sdk-py/actions/workflows/build.yml/badge.svg

[codecov]: https://codecov.io/gh/OrionFinanceAI/orion-finance-sdk-py/graph/badge.svg?token=SJLL2VVQDS
[codecov-badge]: https://codecov.io/gh/OrionFinanceAI/orion-finance-sdk-py/branch/main/graph/badge.svg

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
echo '{"0x1c7D4B196Cb0C7B01d743Fbc6116a902379C7238": 0.4, "0x662DE589197f56aE9231Feb4CF591572339a47D9": 0.2, "0x473c1c81d480E8A0C53797ABcA282447319180d7": 0.15, "0x5C737d4EE9E8ab58a79adDF3764F94064ef7f8F9": 0.15, "0xF35E36Ba9ebA6c4Da1547ba2D8D5AC1dfC354B68": 0.1}' > order_intent.json

# Submit the order intent to the Orion vault
orion submit-order --order-intent-path order_intent.json
```

### Update the strategist address for a vault

```bash
orion update-strategist --new-strategist-address 0x92Cc2706b5775e2E783D76F20dC7ccC59bB92E48
```

### Update the fee model for a vault

```bash
orion update-fee-model --fee-type high_water_mark --performance-fee 5.5 --management-fee 0.1
```
