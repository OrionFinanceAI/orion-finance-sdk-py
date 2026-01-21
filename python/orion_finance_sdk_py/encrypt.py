"""Encryption operations for the Orion Finance Python SDK."""

import json
import os
import subprocess
import sys
from importlib.resources import files

from .utils import validate_var


def encrypt_order_intent(order_intent: dict[str, int]) -> tuple[dict[str, bytes], str]:
    """Encrypt an order intent."""
    if not check_npm_available():
        print_installation_guide()
        sys.exit(1)

    strategist_address = os.getenv("STRATEGIST_ADDRESS")
    validate_var(
        strategist_address,
        error_message=(
            "STRATEGIST_ADDRESS environment variable is missing or invalid. "
            "Please set STRATEGIST_ADDRESS in your .env file or as an environment variable. "
            "Follow the SDK Installation instructions to get one: https://docs.orionfinance.ai/strategist/orion_sdk/install"
        ),
    )
    vault_address = os.getenv("ORION_VAULT_ADDRESS")
    validate_var(
        vault_address,
        error_message=(
            "ORION_VAULT_ADDRESS environment variable is missing or invalid. "
            "Please set ORION_VAULT_ADDRESS in your .env file or as an environment variable. "
            "Follow the SDK Installation instructions to get one: https://docs.orionfinance.ai/strategist/orion_sdk/install"
        ),
    )

    tokens = [token for token in order_intent.keys()]
    values = [value for value in order_intent.values()]

    payload = {
        "vaultAddress": vault_address,
        "curatorAddress": strategist_address,
        "values": values,
    }

    js_entry = files("orion_finance_sdk_py.js_sdk").joinpath("bundle.js")

    result = subprocess.run(
        ["node", str(js_entry)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise RuntimeError(f"Encryption failed: {result.stderr}")

    data = json.loads(result.stdout)

    encrypted_values = data["encryptedValues"]

    encrypted_intent = dict(zip(tokens, encrypted_values))

    input_proof = data["inputProof"]

    return encrypted_intent, input_proof


def print_installation_guide():
    """Print installation guide for npm."""
    print("=" * 80)
    print("ERROR: Management of Encrypted Vaults requires npm to be installed.")
    print("=" * 80)
    print()
    print("npm is not available on your system.")
    print("Please install Node.js and npm first:")
    print()
    print("  Visit: https://nodejs.org/")
    print("  OR use a package manager:")
    print("    macOS: brew install node")
    print("    Ubuntu/Debian: sudo apt install nodejs npm")
    print("    Windows: Download from https://nodejs.org/")
    print()
    print("=" * 80)


def check_npm_available() -> bool:
    """Check if npm is available on the system."""
    try:
        result = subprocess.run(
            ["npm", "--version"],
            capture_output=True,
            text=True,
            check=False,
        )
        return result.returncode == 0
    except (subprocess.SubprocessError, FileNotFoundError):
        return False
