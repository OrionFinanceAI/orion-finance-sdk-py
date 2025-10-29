# orion-finance-sdk [![Github Actions][gha-badge]][gha]

[gha]: https://github.com/OrionFinanceAI/orion-finance-sdk/actions
[gha-badge]: https://github.com/OrionFinanceAI/orion-finance-sdk/actions/workflows/build.yml/badge.svg

## About

A Python Software Development Kit (SDK) to ease interactions with the Orion Finance protocol and its Vaults. This repository provides tools and utilities for quants and developers to seamlessly integrate with Orion's [portfolio management on-chain infrastructure](https://github.com/OrionFinanceAI/protocol).

For additional information, please refer to the [Orion documentation](https://docs.orionfinance.ai), and the curator section in particular.

## Licence

This software is distributed under the BSD-3-Clause license. See the [`LICENSE`](./LICENSE) file for the full text.

## Installation

### From PyPI (Recommended)

Install the latest stable version from PyPI:

```bash
pip install orion-finance-sdk
```

### From Source

For development or to install the latest development version:

```bash
# Clone the repository
git clone https://github.com/OrionFinanceAI/orion-finance-sdk.git
cd orion-finance-sdk

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

The SDK requires the user to specify an `RPC_URL` environment variable in the `.env` file of the project. Follow the [SDK Installation](https://docs.orionfinance.ai/curator/orion_sdk/install) to get one.

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
orion deploy-vault --vault-type encrypted --name "Fully Homomorphic Encryption for Vault Management" --symbol "FHEVM" --fee-type high_water_mark --performance-fee 10 --management-fee 2
```

### Submit an order intent to a vault

```bash
# Use off-chain stack to generate an order intent
echo '{"0xD33AD8cf56a58eb99ce027F64D3b86D162944e66": 0.1, "0xe7A334d3C81EAf515e0330A30fF2663Bf06B999c": 0.2, "0xd6F1Bc1F1383dc0f709489475eD1A3eADD8eE43C": 0.15, "0xfB6Df75C3D299F2Fa3A1Ebe0e86A121cD30FC591": 0.02, "0x37c2CBDE804F4Be1736887f01E46A97d42133070": 0.03, "0x6862c557245648F6f5a24fD51Ce1BAfa91543c77": 0.1, "0xb146CD21C332b909Dc0cC45dE12db7e50581F7c4": 0.1, "0x9B98f24a74CA8a66689D041792730caC36B29e6C": 0.05, "0x23FE67d2687008D24092F3b782f621Dd1A5f9360": 0.05, "0x5E8082e34e226633bdb7D80279f5A815620f403c": 0.01, "0x0fa4013910C2E31A5039cC8788206Fea97001270": 0.01, "0xADbaDfE60511aF60FC35833C3A218eFC1c062A6C": 0.08, "0x3F446382bD132ae1a25f76B688395f1eA72A790b": 0.1}' > order_intent.json

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
