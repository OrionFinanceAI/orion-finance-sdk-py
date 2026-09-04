"""Utility functions for the Orion Finance Python SDK."""

import random
import uuid
from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from pathlib import Path

import numpy as np
from eth_typing import ChecksumAddress
from web3 import Web3

from .console_ui import print_env_created, print_tx_result, progress_step
from .types import ZERO_ADDRESS

random.seed(uuid.uuid4().int)  # uuid-based random seed for irreproducibility.

# Validation constants matching smart contract requirements
MAX_PERFORMANCE_FEE = 3000  # 30% in basis points
MAX_MANAGEMENT_FEE = 300  # 3% in basis points
BASIS_POINTS_FACTOR = 100  # 100 to convert percentage to basis points


def ensure_env_file(env_file_path: Path = Path.cwd() / ".env"):
    """Check if .env file exists in the directory, create it with template if not.

    Args:
        env_file_path: Path to the .env file
    """
    if not env_file_path.exists():
        # Create .env file with template
        env_template = """# Orion Finance SDK Environment Variables

# RPC URL for testnet connection
RPC_URL=

# Optional RPC for execution cost estimates (public mainnet RPCs if unset)
# MAINNET_RPC_URL=

# Private key for manager operations
MANAGER_PRIVATE_KEY=

# Private key for strategist operations
STRATEGIST_PRIVATE_KEY=

# Private key for LP deposit/redeem operations
LP_PRIVATE_KEY=

# Vault address
# ORION_VAULT_ADDRESS=
"""

        try:
            with open(env_file_path, "w") as f:
                f.write(env_template)
            print_env_created(env_file_path)
        except Exception:
            pass


def to_base_units(amount: str | int | float | Decimal, decimals: int) -> int:
    """Convert a human token amount to onchain integer units.

    Args:
        amount: Human-readable token amount (e.g. ``"100.5"``).
        decimals: Token decimals (e.g. 6 for USDC).

    Returns:
        Amount scaled by ``10**decimals``.

    Raises:
        ValueError: If ``amount`` is not a positive number, has more fractional
            digits than ``decimals``, or ``decimals`` is negative.
    """
    if decimals < 0:
        raise ValueError(f"decimals must be non-negative, got {decimals}")
    try:
        value = amount if isinstance(amount, Decimal) else Decimal(str(amount).strip())
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"Invalid amount: {amount}") from exc
    if not value.is_finite() or value <= 0:
        raise ValueError("Amount must be positive")
    exponent = value.as_tuple().exponent
    if isinstance(exponent, int) and -exponent > decimals:
        raise ValueError(f"Amount has more than {decimals} decimal places")
    scaled = value * (Decimal(10) ** decimals)
    if scaled != scaled.to_integral_value():
        raise ValueError(f"Amount has more than {decimals} decimal places")
    return int(scaled)


def validate_var(var: str | None, error_message: str) -> str:
    """Validate that the environment variable is not None or zero; return the value."""
    if not var or var == ZERO_ADDRESS:
        raise ValueError(error_message)
    return var


def checksum_address(address: str) -> ChecksumAddress:
    """Return the EIP-55 checksummed form of ``address``.

    Accepts lowercase or mixed-case hex. Raises ``ValueError`` only when the
    value is not a valid 20-byte Ethereum address.
    """
    try:
        return Web3.to_checksum_address(address.strip())
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid Ethereum address: {address!r}") from exc


def validate_performance_fee(performance_fee: int) -> None:
    """Validate that the performance fee is within acceptable bounds."""
    if performance_fee > MAX_PERFORMANCE_FEE:
        raise ValueError(
            f"Performance fee {performance_fee} basis points exceeds maximum allowed value of {MAX_PERFORMANCE_FEE}"
        )


def validate_management_fee(management_fee: int) -> None:
    """Validate that the management fee is within acceptable bounds."""
    if management_fee > MAX_MANAGEMENT_FEE:
        raise ValueError(
            f"Management fee {management_fee} basis points exceeds maximum allowed value of {MAX_MANAGEMENT_FEE}"
        )


def validate_order(
    order_intent: Mapping[str, int | float],
) -> dict[str, int]:
    """Validate an order intent (fractional weights per token, summing to ~1)."""
    from .contracts import OrionConfig

    orion_config = OrionConfig()

    progress_step("Validating tokens against whitelist")
    # Validate all tokens are whitelisted (normalize casing first)
    normalized_intent = {
        checksum_address(token_address): weight
        for token_address, weight in order_intent.items()
    }
    for token_address in normalized_intent:
        if not orion_config.is_whitelisted(token_address):
            raise ValueError(f"Token {token_address} is not whitelisted")

    # Validate all amounts are positive
    if any(weight <= 0 for weight in normalized_intent.values()):
        raise ValueError("All amounts must be positive")

    # Validate the sum of amounts is approximately 1 (within tolerance for floating point error)
    TOLERANCE = 1e-10
    if not np.isclose(sum(normalized_intent.values()), 1, atol=TOLERANCE):
        raise ValueError(
            "The sum of amounts is not 1 (within floating point tolerance)."
        )

    strategist_intent_decimals = orion_config.strategist_intent_decimals

    progress_step("Scaling weights to protocol decimals")
    order_intent = {
        token: weight * 10**strategist_intent_decimals
        for token, weight in normalized_intent.items()
    }
    rounded_values = round_with_fixed_sum(
        list(order_intent.values()), 10**strategist_intent_decimals
    )
    order_intent = dict(zip(order_intent.keys(), rounded_values))

    return order_intent


def round_with_fixed_sum(
    values: list[float], target_sum: int | None = None
) -> list[int]:
    """Round a list of values to a fixed sum."""
    arr = np.asarray(values, dtype=np.float64)

    if target_sum is None:
        target_sum = int(round(np.sum(arr)))

    floored = np.floor(arr).astype(int)
    remainder = int(round(target_sum - np.sum(floored)))

    # Get the fractional parts and their indices
    fractional_parts = arr - floored
    indices = np.argsort(-fractional_parts)  # Descending order

    # Allocate the remaining units
    result = floored.copy()
    result[indices[:remainder]] += 1

    return result.tolist()


def format_transaction_logs(
    tx_result, success_message: str = "Transaction completed successfully!"
):
    """Format transaction logs in a human-readable way.

    Args:
        tx_result: Transaction result object with tx_hash and decoded_logs attributes
        success_message: Custom success message to display at the end
    """
    print_tx_result(tx_result, title=success_message)
