# orion-finance-sdk-py [![Github Actions][gha-badge]][gha]

[gha]: https://github.com/OrionFinanceAI/orion-finance-sdk-py/actions
[gha-badge]: https://github.com/OrionFinanceAI/orion-finance-sdk-py/actions/workflows/build.yml/badge.svg

## About

A Python Software Development Kit (SDK) to ease interactions with the Orion Finance protocol and its Vaults. This repository provides tools and utilities for quants and developers to seamlessly integrate with Orion's [portfolio management on-chain infrastructure](https://github.com/OrionFinanceAI/protocol).

For additional information, please refer to the [Orion documentation](https://docs.orionfinance.ai), and the manager section in particular.

## Licence

This software is distributed under the BSD-3-Clause license. See the [`LICENSE`](./LICENSE) file for the full text.

## Installation

### From PyPI (Recommended)

Install the latest stable version from PyPI:

```bash
pip install orion-finance-sdk-py
```

### From Source

For development or to install the latest development version:

```bash
# Clone the repository
git clone https://github.com/OrionFinanceAI/orion-finance-sdk-py.git
cd orion-finance-sdk-py

# Using uv (recommended)
curl -LsSf https://astral.sh/uv/install.sh | sh
uv venv
source .venv/bin/activate
uv pip install -e .
```

Or using make:

```bash
make uv-download
make venv
source .venv/bin/activate
make install
```

## Environment Variables Setup

The SDK requires the user to specify an `RPC_URL` environment variable in the `.env` file of the project. Follow the [SDK Installation](https://docs.orionfinance.ai/manager/orion_sdk/install) to get one.

Based on the usage, additional environment variables may be required, e.g.:
- `CURATOR_ADDRESS`: The address of the curator account.
- `VAULT_DEPLOYER_PRIVATE_KEY`: The private key of the vault deployer account.
- `CURATOR_PRIVATE_KEY`: The private key of the curator account.
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

### Deploy a new Encrypted Orion vault

```bash
orion deploy-vault --vault-type encrypted --name "Fully Homomorphic Encryption for Vault Management" --symbol "FHEVM" --fee-type high_water_mark --performance-fee 0 --management-fee 2
```

### Submit an order intent to a vault

```bash
# Use off-chain stack to generate an order intent
echo '{"0x3E15268AdE04Eb579EE490CA92736301C7D644Bb": 0.4, "0x4371227723a006e8ee3941AfF5018D084a06DB95": 0.2, "0x784C3AB4C7bdC2d219b902fA63e87b376F178d82": 0.15, "0xD06b768D498FFD3151e4Bc89e0dBdAA0d1413044": 0.15, "0x1904c298d44b6cd10003C843e29D51407fE1309f": 0.1}' > order_intent.json

# Submit the order intent to the Orion vault
orion submit-order --order-intent-path order_intent.json
```

### Update the curator address for a vault

```bash
orion update-curator --new-curator-address 0x92Cc2706b5775e2E783D76F20dC7ccC59bB92E48
```

### Update the fee model for a vault

```bash
orion update-fee-model --fee-type high_water_mark --performance-fee 5.5 --management-fee 0.1
```
