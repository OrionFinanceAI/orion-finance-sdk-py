"""Tests for the twin asset address map helper."""

from unittest.mock import MagicMock, patch

from orion_finance_sdk_py.asset_map import build_asset_address_map
from orion_finance_sdk_py.types import ZERO_ADDRESS
from web3 import Web3

TWIN = "0x1111111111111111111111111111111111111111"
MAINNET_SOURCE = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"
NON_TWIN = "0x1c7D4B196Cb0C7B01d743Fbc6116a902379C7238"
ZERO_SOURCE_TWIN = "0x2222222222222222222222222222222222222222"


@patch("orion_finance_sdk_py.contracts.OrionConfig")
def test_build_asset_address_map_includes_twins_only(MockConfig):
    """Twins with mainnetSource are mapped; non-twins and zero sources are skipped."""
    config = MockConfig.return_value
    config.whitelisted_assets = [TWIN, NON_TWIN, ZERO_SOURCE_TWIN]

    twin_contract = MagicMock()
    twin_contract.functions.mainnetSource.return_value.call.return_value = (
        MAINNET_SOURCE
    )

    non_twin_contract = MagicMock()
    non_twin_contract.functions.mainnetSource.return_value.call.side_effect = Exception(
        "execution reverted"
    )

    zero_contract = MagicMock()
    zero_contract.functions.mainnetSource.return_value.call.return_value = ZERO_ADDRESS

    contracts = {
        Web3.to_checksum_address(TWIN): twin_contract,
        Web3.to_checksum_address(NON_TWIN): non_twin_contract,
        Web3.to_checksum_address(ZERO_SOURCE_TWIN): zero_contract,
    }

    def contract_factory(address, abi):
        return contracts[address]

    config.w3.eth.contract.side_effect = contract_factory

    result = build_asset_address_map()

    assert result == {
        Web3.to_checksum_address(TWIN): Web3.to_checksum_address(MAINNET_SOURCE),
    }


@patch("orion_finance_sdk_py.contracts.OrionConfig")
def test_build_asset_address_map_empty_when_no_twins(MockConfig):
    """Empty map when no whitelist asset implements mainnetSource."""
    config = MockConfig.return_value
    config.whitelisted_assets = [NON_TWIN]

    non_twin_contract = MagicMock()
    non_twin_contract.functions.mainnetSource.return_value.call.side_effect = Exception(
        "no code"
    )
    config.w3.eth.contract.return_value = non_twin_contract

    assert build_asset_address_map() == {}
