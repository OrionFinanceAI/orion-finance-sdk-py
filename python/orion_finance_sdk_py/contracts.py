"""Interactions with the Orion Finance protocol contracts."""

import json
import os
import sys
from dataclasses import dataclass
from importlib import resources

from dotenv import load_dotenv
from web3 import Web3
from web3.types import TxReceipt

from .types import VaultType
from .utils import validate_management_fee, validate_performance_fee, validate_var

load_dotenv()


@dataclass
class TransactionResult:
    """Result of a transaction including receipt and extracted logs."""

    tx_hash: str
    receipt: TxReceipt
    decoded_logs: list[dict] | None = None


def load_contract_abi(contract_name: str) -> list[dict]:
    """Load the ABI for a given contract."""
    try:
        # Try to load from package data (when installed from PyPI)
        with (
            resources.files("orion_finance_sdk_py")
            .joinpath("abis", f"{contract_name}.json")
            .open() as f
        ):
            return json.load(f)["abi"]
    except (FileNotFoundError, AttributeError):
        # Fallback to local development path
        script_dir = os.path.dirname(os.path.abspath(__file__))
        abi_path = os.path.join(script_dir, "..", "abis", f"{contract_name}.json")
        with open(abi_path) as f:
            return json.load(f)["abi"]


class OrionSmartContract:
    """Base class for Orion smart contracts."""

    def __init__(self, contract_name: str, contract_address: str):
        """Initialize a smart contract."""
        rpc_url = os.getenv("RPC_URL")
        validate_var(
            rpc_url,
            error_message=(
                "RPC_URL environment variable is missing or invalid. "
                "Please set RPC_URL in your .env file or as an environment variable. "
                "Follow the SDK Installation instructions to get one: https://docs.orionfinance.ai/curator/orion_sdk/install"
            ),
        )

        self.w3 = Web3(Web3.HTTPProvider(rpc_url))
        self.contract_name = contract_name
        self.contract_address = contract_address
        self.contract = self.w3.eth.contract(
            address=self.contract_address, abi=load_contract_abi(self.contract_name)
        )

    def _wait_for_transaction_receipt(
        self, tx_hash: str, timeout: int = 120
    ) -> TxReceipt:
        """Wait for a transaction to be processed and return the receipt."""
        return self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=timeout)

    # TODO: verify contracts once deployed, potentially in the same cli command, as soon as deployed it,
    # verify with the same input parameters.
    # Skip verification if Etherscan API key is not provided without failing command.

    def _decode_logs(self, receipt: TxReceipt) -> list[dict]:
        """Decode logs from a transaction receipt."""
        decoded_logs = []
        for log in receipt.logs:
            # Only process logs from this contract
            if log.address.lower() != self.contract_address.lower():
                continue

            # Try to decode the log with each event in the contract
            for event in self.contract.events:
                try:
                    decoded_log = event.process_log(log)
                    decoded_logs.append(
                        {
                            "event": decoded_log.event,
                            "args": dict(decoded_log.args),
                            "address": decoded_log.address,
                            "blockHash": decoded_log.blockHash.hex(),
                            "blockNumber": decoded_log.blockNumber,
                            "logIndex": decoded_log.logIndex,
                            "transactionHash": decoded_log.transactionHash.hex(),
                            "transactionIndex": decoded_log.transactionIndex,
                        }
                    )
                    break  # Successfully decoded, move to next log
                except Exception:
                    # This event doesn't match this log, try the next event
                    continue
        return decoded_logs


class OrionConfig(OrionSmartContract):
    """OrionConfig contract."""

    def __init__(self):
        """Initialize the OrionConfig contract."""
        contract_address = "0x8eD5Fb264A049b18B98e8403e01146Ee78C1e984"
        super().__init__(
            contract_name="OrionConfig",
            contract_address=contract_address,
        )

    @property
    def curator_intent_decimals(self) -> int:
        """Fetch the curator intent decimals from the OrionConfig contract."""
        return self.contract.functions.curatorIntentDecimals().call()

    @property
    def whitelisted_assets(self) -> list[str]:
        """Fetch all whitelisted assets from the OrionConfig contract."""
        return self.contract.functions.getAllWhitelistedAssets().call()

    def is_whitelisted(self, token_address: str) -> bool:
        """Check if a token address is whitelisted."""
        return self.contract.functions.isWhitelisted(
            Web3.to_checksum_address(token_address)
        ).call()

    @property
    def orion_transparent_vaults(self) -> list[str]:
        """Fetch all Orion transparent vault addresses from the OrionConfig contract."""
        return self.contract.functions.getAllOrionVaults(0).call()

    @property
    def orion_encrypted_vaults(self) -> list[str]:
        """Fetch all Orion encrypted vault addresses from the OrionConfig contract."""
        return self.contract.functions.getAllOrionVaults(1).call()

    def is_system_idle(self) -> bool:
        """Check if the system is in idle state, required for vault deployment."""
        return self.contract.functions.isSystemIdle().call()


class VaultFactory(OrionSmartContract):
    """VaultFactory contract."""

    def __init__(
        self,
        vault_type: str,
        contract_address: str | None = None,
    ):
        """Initialize the VaultFactory contract."""
        if vault_type == VaultType.TRANSPARENT:
            contract_address = "0x5689219Aa5dC2766928d316E719AaE25047314e4"
        elif vault_type == VaultType.ENCRYPTED:
            contract_address = "0xdD7900c4B6abfEB4D2Cb9F233d875071f6e1093F"

        super().__init__(
            contract_name=f"{vault_type.capitalize()}VaultFactory",
            contract_address=contract_address,
        )

    def create_orion_vault(
        self,
        name: str,
        symbol: str,
        fee_type: int,
        performance_fee: int,
        management_fee: int,
    ) -> TransactionResult:
        """Create an Orion vault for a given curator address."""
        config = OrionConfig()

        curator_address = os.getenv("CURATOR_ADDRESS")
        validate_var(
            curator_address,
            error_message=(
                "CURATOR_ADDRESS environment variable is missing or invalid. "
                "Please set CURATOR_ADDRESS in your .env file or as an environment variable. "
                "Follow the SDK Installation instructions to get one: https://docs.orionfinance.ai/curator/orion_sdk/install"
            ),
        )

        deployer_private_key = os.getenv("VAULT_DEPLOYER_PRIVATE_KEY")
        validate_var(
            deployer_private_key,
            error_message=(
                "VAULT_DEPLOYER_PRIVATE_KEY environment variable is missing or invalid. "
                "Please set VAULT_DEPLOYER_PRIVATE_KEY in your .env file or as an environment variable. "
                "Follow the SDK Installation instructions to get one: https://docs.orionfinance.ai/curator/orion_sdk/install"
            ),
        )
        account = self.w3.eth.account.from_key(deployer_private_key)
        validate_var(
            account.address,
            error_message="Invalid VAULT_DEPLOYER_PRIVATE_KEY.",
        )

        validate_performance_fee(performance_fee)
        validate_management_fee(management_fee)

        if not config.is_system_idle():
            print("System is not idle. Cannot deploy vault at this time.")
            sys.exit(1)

        account = self.w3.eth.account.from_key(deployer_private_key)
        nonce = self.w3.eth.get_transaction_count(account.address)

        # Estimate gas needed for the transaction
        gas_estimate = self.contract.functions.createVault(
            curator_address, name, symbol, fee_type, performance_fee, management_fee
        ).estimate_gas({"from": account.address, "nonce": nonce})

        # Add 20% buffer to gas estimate
        gas_limit = int(gas_estimate * 1.2)

        # TODO: add check to measure deployer ETH balance and raise error if not enough before building tx.

        tx = self.contract.functions.createVault(
            curator_address, name, symbol, fee_type, performance_fee, management_fee
        ).build_transaction(
            {
                "from": account.address,
                "nonce": nonce,
                "gas": gas_limit,
                "gasPrice": self.w3.eth.gas_price,
            }
        )

        signed = account.sign_transaction(tx)
        tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
        tx_hash_hex = tx_hash.hex()

        receipt = self._wait_for_transaction_receipt(tx_hash_hex)

        # Check if transaction was successful
        if receipt["status"] != 1:
            raise Exception(f"Transaction failed with status: {receipt['status']}")

        # Decode logs from the transaction receipt
        decoded_logs = self._decode_logs(receipt)

        return TransactionResult(
            tx_hash=tx_hash_hex, receipt=receipt, decoded_logs=decoded_logs
        )

    def get_vault_address_from_result(self, result: TransactionResult) -> str | None:
        """Extract the vault address from OrionVaultCreated event in the transaction result."""
        if not result.decoded_logs:
            return None

        for log in result.decoded_logs:
            if log.get("event") == "OrionVaultCreated":
                return log["args"].get("vault")

        return None


class OrionVault(OrionSmartContract):
    """OrionVault contract."""

    def __init__(self, contract_name: str):
        """Initialize the OrionVault contract."""
        contract_address = os.getenv("ORION_VAULT_ADDRESS")
        validate_var(
            contract_address,
            error_message=(
                "ORION_VAULT_ADDRESS environment variable is missing or invalid. "
                "Please set ORION_VAULT_ADDRESS in your .env file or as an environment variable. "
            ),
        )
        super().__init__(contract_name, contract_address)

    def update_curator(self, new_curator_address: str) -> TransactionResult:
        """Update the curator address for the vault."""
        deployer_private_key = os.getenv("VAULT_DEPLOYER_PRIVATE_KEY")
        validate_var(
            deployer_private_key,
            error_message=(
                "VAULT_DEPLOYER_PRIVATE_KEY environment variable is missing or invalid. "
                "Please set VAULT_DEPLOYER_PRIVATE_KEY in your .env file or as an environment variable. "
                "Follow the SDK Installation instructions to get one: https://docs.orionfinance.ai/curator/orion_sdk/install"
            ),
        )

        account = self.w3.eth.account.from_key(deployer_private_key)
        nonce = self.w3.eth.get_transaction_count(account.address)

        tx = self.contract.functions.updateCurator(
            new_curator_address
        ).build_transaction({"from": account.address, "nonce": nonce})

        signed = account.sign_transaction(tx)
        tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
        tx_hash_hex = tx_hash.hex()

        receipt = self._wait_for_transaction_receipt(tx_hash_hex)

        if receipt["status"] != 1:
            raise Exception(f"Transaction failed with status: {receipt['status']}")

        decoded_logs = self._decode_logs(receipt)

        return TransactionResult(
            tx_hash=tx_hash_hex, receipt=receipt, decoded_logs=decoded_logs
        )

    def update_fee_model(
        self, fee_type: int, performance_fee: int, management_fee: int
    ) -> TransactionResult:
        """Update the fee model for the vault."""
        deployer_private_key = os.getenv("VAULT_DEPLOYER_PRIVATE_KEY")
        validate_var(
            deployer_private_key,
            error_message=(
                "VAULT_DEPLOYER_PRIVATE_KEY environment variable is missing or invalid. "
                "Please set VAULT_DEPLOYER_PRIVATE_KEY in your .env file or as an environment variable. "
                "Follow the SDK Installation instructions to get one: https://docs.orionfinance.ai/curator/orion_sdk/install"
            ),
        )

        account = self.w3.eth.account.from_key(deployer_private_key)
        nonce = self.w3.eth.get_transaction_count(account.address)

        tx = self.contract.functions.updateFeeModel(
            fee_type, performance_fee, management_fee
        ).build_transaction({"from": account.address, "nonce": nonce})

        signed = account.sign_transaction(tx)
        tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
        tx_hash_hex = tx_hash.hex()

        receipt = self._wait_for_transaction_receipt(tx_hash_hex)

        if receipt["status"] != 1:
            raise Exception(f"Transaction failed with status: {receipt['status']}")

        decoded_logs = self._decode_logs(receipt)

        return TransactionResult(
            tx_hash=tx_hash_hex, receipt=receipt, decoded_logs=decoded_logs
        )


class OrionTransparentVault(OrionVault):
    """OrionTransparentVault contract."""

    def __init__(self):
        """Initialize the OrionTransparentVault contract."""
        super().__init__("OrionTransparentVault")

    def submit_order_intent(
        self,
        order_intent: dict[str, int],
    ) -> TransactionResult:
        """Submit a portfolio order intent.

        Args:
            order_intent: Dictionary mapping token addresses to values

        Returns:
            TransactionResult
        """
        curator_private_key = os.getenv("CURATOR_PRIVATE_KEY")
        validate_var(
            curator_private_key,
            error_message=(
                "CURATOR_PRIVATE_KEY environment variable is missing or invalid. "
                "Please set CURATOR_PRIVATE_KEY in your .env file or as an environment variable. "
                "Follow the SDK Installation instructions to get one: https://docs.orionfinance.ai/curator/orion_sdk/install"
            ),
        )

        account = self.w3.eth.account.from_key(curator_private_key)
        nonce = self.w3.eth.get_transaction_count(account.address)

        items = [
            {"token": Web3.to_checksum_address(token), "value": value}
            for token, value in order_intent.items()
        ]

        # Estimate gas needed for the transaction
        gas_estimate = self.contract.functions.submitIntent(items).estimate_gas(
            {"from": account.address, "nonce": nonce}
        )

        # Add 20% buffer to gas estimate
        gas_limit = int(gas_estimate * 1.2)

        tx = self.contract.functions.submitIntent(items).build_transaction(
            {
                "from": account.address,
                "nonce": nonce,
                "gas": gas_limit,
                "gasPrice": self.w3.eth.gas_price,
            }
        )

        signed = account.sign_transaction(tx)
        tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
        tx_hash_hex = tx_hash.hex()

        receipt = self._wait_for_transaction_receipt(tx_hash_hex)

        if receipt["status"] != 1:
            raise Exception(f"Transaction failed with status: {receipt['status']}")

        decoded_logs = self._decode_logs(receipt)

        return TransactionResult(
            tx_hash=tx_hash_hex, receipt=receipt, decoded_logs=decoded_logs
        )


# TODO: Consider having a single class for both transparent and encrypted vaults.
class OrionEncryptedVault(OrionVault):
    """OrionEncryptedVault contract."""

    def __init__(self):
        """Initialize the OrionEncryptedVault contract."""
        super().__init__("OrionEncryptedVault")

    def submit_order_intent(
        self,
        order_intent: dict[str, bytes],
        input_proof: str,
    ) -> TransactionResult:
        """Submit a portfolio order intent.

        Args:
            order_intent: Dictionary mapping token addresses to values
            input_proof: A Zero-Knowledge Proof ensuring the validity of the encrypted data.

        Returns:
            TransactionResult
        """
        curator_private_key = os.getenv("CURATOR_PRIVATE_KEY")
        validate_var(
            curator_private_key,
            error_message=(
                "CURATOR_PRIVATE_KEY environment variable is missing or invalid. "
                "Please set CURATOR_PRIVATE_KEY in your .env file or as an environment variable. "
                "Follow the SDK Installation instructions to get one: https://docs.orionfinance.ai/curator/orion_sdk/install"
            ),
        )

        account = self.w3.eth.account.from_key(curator_private_key)
        nonce = self.w3.eth.get_transaction_count(account.address)

        items = [
            {"token": Web3.to_checksum_address(token), "weight": weight}
            for token, weight in order_intent.items()
        ]

        # Estimate gas needed for the transaction
        gas_estimate = self.contract.functions.submitIntent(
            items, input_proof
        ).estimate_gas({"from": account.address, "nonce": nonce})

        # Add 20% buffer to gas estimate
        gas_limit = int(gas_estimate * 1.2)

        tx = self.contract.functions.submitIntent(items, input_proof).build_transaction(
            {
                "from": account.address,
                "nonce": nonce,
                "gas": gas_limit,
                "gasPrice": self.w3.eth.gas_price,
            }
        )

        signed = account.sign_transaction(tx)
        tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
        tx_hash_hex = tx_hash.hex()

        receipt = self._wait_for_transaction_receipt(tx_hash_hex)

        if receipt["status"] != 1:
            raise Exception(f"Transaction failed with status: {receipt['status']}")

        decoded_logs = self._decode_logs(receipt)

        return TransactionResult(
            tx_hash=tx_hash_hex, receipt=receipt, decoded_logs=decoded_logs
        )
