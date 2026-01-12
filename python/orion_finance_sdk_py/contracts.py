"""Interactions with the Orion Finance protocol contracts."""

import json
import os
import sys
from dataclasses import dataclass
from importlib import resources

from dotenv import load_dotenv
from web3 import Web3
from web3.types import TxReceipt

from .types import CHAIN_CONFIG, ZERO_ADDRESS, VaultType
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
                "Follow the SDK Installation instructions to get one: https://docs.orionfinance.ai/manager/orion_sdk/install"
            ),
        )

        self.w3 = Web3(Web3.HTTPProvider(rpc_url))
        self.chain_id = self.w3.eth.chain_id

        env_chain_id = os.getenv("CHAIN_ID")
        if env_chain_id and int(env_chain_id) != self.chain_id:
            print(
                f"⚠️ Warning: CHAIN_ID in env ({env_chain_id}) does not match RPC chain ID ({self.chain_id})"
            )

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
        # Default to Sepolia if not specified, but prefer env var
        chain_id = int(os.getenv("CHAIN_ID", "11155111"))

        if chain_id in CHAIN_CONFIG:
            contract_address = CHAIN_CONFIG[chain_id]["OrionConfig"]
        else:
            raise ValueError(
                f"Unsupported CHAIN_ID: {chain_id}. Please check CHAIN_CONFIG in types.py or set CHAIN_ID env var correctly."
            )

        super().__init__(
            contract_name="OrionConfig",
            contract_address=contract_address,
        )

    @property
    def strategist_intent_decimals(self) -> int:
        """Fetch the strategist intent decimals from the OrionConfig contract."""
        return self.contract.functions.strategistIntentDecimals().call()

    @property
    def manager_intent_decimals(self) -> int:
        """Alias for strategist_intent_decimals."""
        return self.strategist_intent_decimals

    @property
    def risk_free_rate(self) -> int:
        """Fetch the risk free rate from the OrionConfig contract."""
        return self.contract.functions.riskFreeRate().call()

    @property
    def whitelisted_assets(self) -> list[str]:
        """Fetch all whitelisted assets from the OrionConfig contract."""
        return self.contract.functions.getAllWhitelistedAssets().call()

    @property
    def get_investment_universe(self) -> list[str]:
        """Alias for whitelisted_assets (Investment Universe)."""
        return self.whitelisted_assets

    def is_whitelisted(self, token_address: str) -> bool:
        """Check if a token address is whitelisted."""
        return self.contract.functions.isWhitelisted(
            Web3.to_checksum_address(token_address)
        ).call()

    def is_whitelisted_manager(self, manager_address: str) -> bool:
        """Check if a manager address is whitelisted."""
        return self.contract.functions.isWhitelistedManager(
            Web3.to_checksum_address(manager_address)
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


class LiquidityOrchestrator(OrionSmartContract):
    """LiquidityOrchestrator contract."""

    def __init__(self):
        """Initialize the LiquidityOrchestrator contract."""
        config = OrionConfig()
        contract_address = config.contract.functions.liquidityOrchestrator().call()
        super().__init__(
            contract_name="LiquidityOrchestrator",
            contract_address=contract_address,
        )

    @property
    def target_buffer_ratio(self) -> int:
        """Fetch the target buffer ratio."""
        return self.contract.functions.targetBufferRatio().call()

    @property
    def slippage_tolerance(self) -> int:
        """Fetch the slippage tolerance."""
        return self.contract.functions.slippageTolerance().call()


class VaultFactory(OrionSmartContract):
    """VaultFactory contract."""

    def __init__(
        self,
        vault_type: str,
        contract_address: str | None = None,
    ):
        """Initialize the VaultFactory contract."""
        if contract_address is None:
            config = OrionConfig()
            if vault_type == VaultType.TRANSPARENT:
                contract_address = (
                    config.contract.functions.transparentVaultFactory().call()
                )
            elif vault_type == VaultType.ENCRYPTED:
                # Retrieve from config if possible (added to CHAIN_CONFIG)
                chain_id = int(os.getenv("CHAIN_ID", "11155111"))
                if (
                    chain_id in CHAIN_CONFIG
                    and "EncryptedVaultFactory" in CHAIN_CONFIG[chain_id]
                ):
                    contract_address = CHAIN_CONFIG[chain_id]["EncryptedVaultFactory"]
                else:
                    # Fallback or error
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
        deposit_access_control: str = ZERO_ADDRESS,
    ) -> TransactionResult:
        """Create an Orion vault for a given strategist address."""
        config = OrionConfig()

        strategist_address = os.getenv("STRATEGIST_ADDRESS")
        validate_var(
            strategist_address,
            error_message=(
                "STRATEGIST_ADDRESS environment variable is missing or invalid. "
                "Please set STRATEGIST_ADDRESS in your .env file or as an environment variable. "
                "Follow the SDK Installation instructions to get one: https://docs.orionfinance.ai/manager/orion_sdk/install"
            ),
        )

        manager_private_key = os.getenv("MANAGER_PRIVATE_KEY")
        validate_var(
            manager_private_key,
            error_message=(
                "MANAGER_PRIVATE_KEY environment variable is missing or invalid. "
                "Please set MANAGER_PRIVATE_KEY in your .env file or as an environment variable. "
                "Follow the SDK Installation instructions to get one: https://docs.orionfinance.ai/manager/orion_sdk/install"
            ),
        )
        account = self.w3.eth.account.from_key(manager_private_key)
        validate_var(
            account.address,
            error_message="Invalid MANAGER_PRIVATE_KEY.",
        )

        validate_performance_fee(performance_fee)
        validate_management_fee(management_fee)

        if not config.is_system_idle():
            print("System is not idle. Cannot deploy vault at this time.")
            sys.exit(1)

        account = self.w3.eth.account.from_key(manager_private_key)
        nonce = self.w3.eth.get_transaction_count(account.address)

        # Estimate gas needed for the transaction
        gas_estimate = self.contract.functions.createVault(
            strategist_address,
            name,
            symbol,
            fee_type,
            performance_fee,
            management_fee,
            Web3.to_checksum_address(deposit_access_control),
        ).estimate_gas({"from": account.address, "nonce": nonce})

        # Add 20% buffer to gas estimate
        gas_limit = int(gas_estimate * 1.2)

        gas_price = self.w3.eth.gas_price
        estimated_cost = gas_limit * gas_price
        balance = self.w3.eth.get_balance(account.address)

        if balance < estimated_cost:
            raise ValueError(
                f"Insufficient ETH balance. Required: {estimated_cost}, Available: {balance}"
            )

        tx = self.contract.functions.createVault(
            strategist_address,
            name,
            symbol,
            fee_type,
            performance_fee,
            management_fee,
            Web3.to_checksum_address(deposit_access_control),
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

    def update_strategist(self, new_strategist_address: str) -> TransactionResult:
        """Update the strategist address for the vault."""
        manager_private_key = os.getenv("MANAGER_PRIVATE_KEY")
        validate_var(
            manager_private_key,
            error_message=(
                "MANAGER_PRIVATE_KEY environment variable is missing or invalid. "
                "Please set MANAGER_PRIVATE_KEY in your .env file or as an environment variable. "
                "Follow the SDK Installation instructions to get one: https://docs.orionfinance.ai/manager/orion_sdk/install"
            ),
        )

        account = self.w3.eth.account.from_key(manager_private_key)
        nonce = self.w3.eth.get_transaction_count(account.address)

        tx = self.contract.functions.updateStrategist(
            new_strategist_address
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
        manager_private_key = os.getenv("MANAGER_PRIVATE_KEY")
        validate_var(
            manager_private_key,
            error_message=(
                "MANAGER_PRIVATE_KEY environment variable is missing or invalid. "
                "Please set MANAGER_PRIVATE_KEY in your .env file or as an environment variable. "
                "Follow the SDK Installation instructions to get one: https://docs.orionfinance.ai/manager/orion_sdk/install"
            ),
        )

        account = self.w3.eth.account.from_key(manager_private_key)
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

    @property
    def total_assets(self) -> int:
        """Fetch the total assets of the vault."""
        return self.contract.functions.totalAssets().call()

    @property
    def share_price(self) -> int:
        """Fetch the current share price (value of 1 share unit)."""
        decimals = self.contract.functions.decimals().call()
        return self.contract.functions.convertToAssets(10**decimals).call()

    def convert_to_assets(self, shares: int) -> int:
        """Convert shares to assets."""
        return self.contract.functions.convertToAssets(shares).call()

    def get_portfolio(self) -> dict:
        """Get the vault portfolio."""
        # This returns a tuple (tokens, values)
        tokens, values = self.contract.functions.getPortfolio().call()
        return dict(zip(tokens, values))

    def set_deposit_access_control(
        self, access_control_address: str
    ) -> TransactionResult:
        """Set the deposit access control contract address."""
        manager_private_key = os.getenv("MANAGER_PRIVATE_KEY")
        validate_var(
            manager_private_key,
            error_message="MANAGER_PRIVATE_KEY environment variable is missing or invalid.",
        )
        account = self.w3.eth.account.from_key(manager_private_key)
        nonce = self.w3.eth.get_transaction_count(account.address)

        tx = self.contract.functions.setDepositAccessControl(
            Web3.to_checksum_address(access_control_address)
        ).build_transaction({"from": account.address, "nonce": nonce})

        signed = account.sign_transaction(tx)
        tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
        tx_hash_hex = tx_hash.hex()
        receipt = self._wait_for_transaction_receipt(tx_hash_hex)
        return TransactionResult(
            tx_hash=tx_hash_hex,
            receipt=receipt,
            decoded_logs=self._decode_logs(receipt),
        )

    def max_deposit(self, receiver: str) -> int:
        """Fetch the maximum deposit amount for a receiver."""
        return self.contract.functions.maxDeposit(
            Web3.to_checksum_address(receiver)
        ).call()

    def can_request_deposit(self, user: str) -> bool:
        """Check if a user is allowed to request a deposit.

        This method queries the vault's depositAccessControl contract.
        If no access control is set (zero address), it returns True.
        """
        try:
            access_control_address = (
                self.contract.functions.depositAccessControl().call()
            )
        except Exception:
            # If the contract doesn't expose depositAccessControl, assume permissionless
            return True

        if access_control_address == ZERO_ADDRESS:
            return True

        # Minimal ABI for IOrionAccessControl to check permissions
        access_control_abi = [
            {
                "inputs": [
                    {"internalType": "address", "name": "sender", "type": "address"}
                ],
                "name": "canRequestDeposit",
                "outputs": [{"internalType": "bool", "name": "", "type": "bool"}],
                "stateMutability": "view",
                "type": "function",
            }
        ]
        access_control = self.w3.eth.contract(
            address=access_control_address, abi=access_control_abi
        )
        return access_control.functions.canRequestDeposit(
            Web3.to_checksum_address(user)
        ).call()


class OrionTransparentVault(OrionVault):
    """OrionTransparentVault contract."""

    def __init__(self):
        """Initialize the OrionTransparentVault contract."""
        super().__init__("OrionTransparentVault")

    def transfer_manager_fees(self, amount: int) -> TransactionResult:
        """Transfer manager fees (claimVaultFees)."""
        manager_private_key = os.getenv("MANAGER_PRIVATE_KEY")
        account = self.w3.eth.account.from_key(manager_private_key)
        nonce = self.w3.eth.get_transaction_count(account.address)

        tx = self.contract.functions.claimVaultFees(amount).build_transaction(
            {"from": account.address, "nonce": nonce}
        )
        signed = account.sign_transaction(tx)
        tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = self._wait_for_transaction_receipt(tx_hash.hex())
        return TransactionResult(
            tx_hash=tx_hash.hex(),
            receipt=receipt,
            decoded_logs=self._decode_logs(receipt),
        )

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
        strategist_private_key = os.getenv("STRATEGIST_PRIVATE_KEY")
        validate_var(
            strategist_private_key,
            error_message=(
                "STRATEGIST_PRIVATE_KEY environment variable is missing or invalid. "
                "Please set STRATEGIST_PRIVATE_KEY in your .env file or as an environment variable. "
                "Follow the SDK Installation instructions to get one: https://docs.orionfinance.ai/manager/orion_sdk/install"
            ),
        )

        account = self.w3.eth.account.from_key(strategist_private_key)
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

    def transfer_strategist_fees(self, amount: int) -> TransactionResult:
        """Transfer strategist fees (claimCuratorFees)."""
        strategist_private_key = os.getenv("STRATEGIST_PRIVATE_KEY") or os.getenv(
            "CURATOR_PRIVATE_KEY"
        )

        validate_var(strategist_private_key, "STRATEGIST_PRIVATE_KEY missing")

        account = self.w3.eth.account.from_key(strategist_private_key)
        nonce = self.w3.eth.get_transaction_count(account.address)

        tx = self.contract.functions.claimCuratorFees(amount).build_transaction(
            {"from": account.address, "nonce": nonce}
        )
        signed = account.sign_transaction(tx)
        tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
        tx_hash_hex = tx_hash.hex()
        receipt = self._wait_for_transaction_receipt(tx_hash_hex)
        return TransactionResult(
            tx_hash=tx_hash_hex,
            receipt=receipt,
            decoded_logs=self._decode_logs(receipt),
        )

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
        # Use STRATEGIST_PRIVATE_KEY preferrably, fallback to CURATOR
        strategist_private_key = os.getenv("STRATEGIST_PRIVATE_KEY") or os.getenv(
            "CURATOR_PRIVATE_KEY"
        )
        validate_var(
            strategist_private_key,
            error_message=(
                "STRATEGIST_PRIVATE_KEY environment variable is missing or invalid. "
                "Please set STRATEGIST_PRIVATE_KEY in your .env file or as an environment variable. "
                "Follow the SDK Installation instructions to get one: https://docs.orionfinance.ai/manager/orion_sdk/install"
            ),
        )

        account = self.w3.eth.account.from_key(strategist_private_key)
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

    def update_strategist(self, new_strategist_address: str) -> TransactionResult:
        """Update the strategist (curator) address for the vault."""
        manager_private_key = os.getenv("MANAGER_PRIVATE_KEY")
        validate_var(
            manager_private_key,
            error_message=(
                "MANAGER_PRIVATE_KEY environment variable is missing or invalid. "
                "Please set MANAGER_PRIVATE_KEY in your .env file or as an environment variable. "
                "Follow the SDK Installation instructions to get one: https://docs.orionfinance.ai/manager/orion_sdk/install"
            ),
        )

        account = self.w3.eth.account.from_key(manager_private_key)
        nonce = self.w3.eth.get_transaction_count(account.address)

        tx = self.contract.functions.updateCurator(
            new_strategist_address
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
