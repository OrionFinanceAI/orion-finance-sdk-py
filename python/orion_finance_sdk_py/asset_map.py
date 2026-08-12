"""Admin helpers for mapping Sepolia twin assets to mainnet sources."""

from web3 import Web3

from .types import ZERO_ADDRESS

_MAINNET_SOURCE_ABI = [
    {
        "inputs": [],
        "name": "mainnetSource",
        "outputs": [{"internalType": "address", "name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function",
    }
]


def build_asset_address_map() -> dict[str, str]:
    """Build testnet → mainnet address map for twin assets on the whitelist.

    Walks ``OrionConfig.whitelisted_assets`` and calls ``mainnetSource()`` on each.
    Assets that do not implement the getter (or revert) are omitted.

    Returns:
        Dict mapping checksummed Sepolia (testnet) addresses to checksummed
        mainnet source addresses.
    """
    from .contracts import OrionConfig

    config = OrionConfig()
    address_map: dict[str, str] = {}

    for asset in config.whitelisted_assets:
        testnet = Web3.to_checksum_address(asset)
        try:
            twin = config.w3.eth.contract(address=testnet, abi=_MAINNET_SOURCE_ABI)
            mainnet = twin.functions.mainnetSource().call()
        except Exception:
            continue

        if not mainnet or Web3.to_checksum_address(mainnet) == ZERO_ADDRESS:
            continue

        address_map[testnet] = Web3.to_checksum_address(mainnet)

    return address_map
