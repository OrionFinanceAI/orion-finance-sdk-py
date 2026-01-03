"""Utility functions for the Orion Finance Python SDK."""

import random
import sys
import uuid
from pathlib import Path

import numpy as np

random.seed(uuid.uuid4().int)  # uuid-based random seed for irreproducibility.

# Validation constants matching smart contract requirements
MAX_PERFORMANCE_FEE = 5000  # 50% in basis points
MAX_MANAGEMENT_FEE = 500  # 5% in basis points
BASIS_POINTS_FACTOR = 100  # 100 to convert percentage to basis points


def ensure_env_file(env_file_path: Path = Path.cwd() / ".env"):
    """Check if .env file exists in the directory, create it with template if not.

    Args:
        env_file_path: Path to the .env file
    """
    if not env_file_path.exists():
        # Create .env file with template
        env_template = """# Orion Finance SDK Environment Variables

# RPC URL for blockchain connection
RPC_URL=

# Curator contract address
CURATOR_ADDRESS=

# Private key for vault deployment
VAULT_DEPLOYER_PRIVATE_KEY=

# Private key for curator operations
CURATOR_PRIVATE_KEY=

# Vault address
# ORION_VAULT_ADDRESS=
"""

        try:
            with open(env_file_path, "w") as f:
                f.write(env_template)
            print(f"✅ Created .env file at {env_file_path}")
            print(
                "📝 Please update the .env file with your actual configuration values"
            )
        except:
            pass


def validate_var(var: str, error_message: str) -> None:
    """Validate that the environment variable is not zero."""
    if not var or var == "0x0000000000000000000000000000000000000000":
        print(error_message)
        sys.exit(1)


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


def validate_order(order_intent: dict[str, int], fuzz: bool = False) -> dict[str, int]:
    """Validate an order intent."""
    from .contracts import OrionConfig

    orion_config = OrionConfig()

    # Validate all tokens are whitelisted
    for token_address in order_intent.keys():
        if not orion_config.is_whitelisted(token_address):
            raise ValueError(f"Token {token_address} is not whitelisted")

    # Validate all amounts are positive
    if any(weight <= 0 for weight in order_intent.values()):
        raise ValueError("All amounts must be positive")

    # Validate the sum of amounts is approximately 1 (within tolerance for floating point error)
    TOLERANCE = 1e-10
    if not np.isclose(sum(order_intent.values()), 1, atol=TOLERANCE):
        raise ValueError(
            "The sum of amounts is not 1 (within floating point tolerance)."
        )

    curator_intent_decimals = orion_config.curator_intent_decimals

    if fuzz:
        # Add remaining whitelisted assets with small random amounts
        whitelisted_assets = orion_config.whitelisted_assets
        for asset in whitelisted_assets:
            if asset not in order_intent.keys():
                order_intent[asset] = (
                    random.randint(1, 10) / 10**curator_intent_decimals
                )

        # Normalize again to sum to 1
        order_intent = {
            token: weight / sum(order_intent.values())
            for token, weight in order_intent.items()
        }

        # Shuffle the order_intent to avoid dust amounts always being last
        items = list(order_intent.items())
        random.shuffle(items)
        order_intent = dict(items)

    order_intent = {
        token: weight * 10**curator_intent_decimals
        for token, weight in order_intent.items()
    }
    rounded_values = round_with_fixed_sum(
        list(order_intent.values()), 10**curator_intent_decimals
    )
    order_intent = dict(zip(order_intent.keys(), rounded_values))

    return order_intent


def round_with_fixed_sum(
    values: list[float], target_sum: int | None = None
) -> list[int]:
    """Round a list of values to a fixed sum."""
    values = np.asarray(values, dtype=np.float64)

    if target_sum is None:
        target_sum = int(round(np.sum(values)))

    floored = np.floor(values).astype(int)
    remainder = int(round(target_sum - np.sum(floored)))

    # Get the fractional parts and their indices
    fractional_parts = values - floored
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
    print(f"✅ https://sepolia.etherscan.io/tx/0x{tx_result.tx_hash}")
    print("=" * 60)

    if tx_result.decoded_logs:
        print("📋 Transaction Events:")
        for i, log in enumerate(tx_result.decoded_logs, 1):
            print(f"\n{i}. Event: {log.get('event', 'Unknown')}")

            if log.get("args"):
                args = log["args"]
                print("   Arguments:")
                for key, value in args.items():
                    if key == "vaultType":
                        vault_type_name = "Transparent" if value == 0 else "Encrypted"
                        print(f"     {key}: {value} ({vault_type_name})")
                    else:
                        print(f"     {key}: {value}")

            print(f"   Contract: {log.get('address', 'Unknown')}")
            print(f"   Block: {log.get('blockNumber', 'Unknown')}")
    else:
        print("⚠️  No events found in transaction logs")

    print("=" * 60)
    print(f"🎉 {success_message}")
