"""Command line interface for the Orion Finance Python SDK."""

import json
import os

import typer

from .contracts import (
    OrionEncryptedVault,
    OrionTransparentVault,
    VaultFactory,
)
from .encrypt import encrypt_order_intent
from .types import (
    FeeType,
    VaultType,
    fee_type_to_int,
)
from .utils import (
    BASIS_POINTS_FACTOR,
    ensure_env_file,
    format_transaction_logs,
    validate_order,
    validate_var,
)

app = typer.Typer()


@app.command()
def deploy_vault(
    vault_type: VaultType = typer.Option(
        ..., help="Type of the vault (encrypted or transparent)"
    ),
    name: str = typer.Option(..., help="Name of the vault"),
    symbol: str = typer.Option(..., help="Symbol of the vault"),
    fee_type: FeeType = typer.Option(..., help="Type of the fee"),
    performance_fee: float = typer.Option(
        ..., help="Performance fee in percentage i.e. 10.2 (maximum 30%)"
    ),
    management_fee: float = typer.Option(
        ..., help="Management fee in percentage i.e. 2.1 (maximum 3%)"
    ),
):
    """Deploy an Orion vault with customizable fee structure, name, and symbol. The vault can be either transparent or encrypted."""
    ensure_env_file()

    fee_type = fee_type_to_int[fee_type.value]

    vault_factory = VaultFactory(vault_type=vault_type.value)

    tx_result = vault_factory.create_orion_vault(
        name=name,
        symbol=symbol,
        fee_type=fee_type,
        performance_fee=int(performance_fee * BASIS_POINTS_FACTOR),
        management_fee=int(management_fee * BASIS_POINTS_FACTOR),
    )

    # Format transaction logs
    format_transaction_logs(tx_result, "Vault deployment transaction completed!")

    # Extract vault address if available
    vault_address = vault_factory.get_vault_address_from_result(tx_result)
    if vault_address:
        print(
            f"\n📍 ORION_VAULT_ADDRESS={vault_address} <------------------- COPY THIS TO YOUR .env FILE TO INTERACT WITH THE VAULT."
        )
    else:
        print("\n❌ Could not extract vault address from transaction")


@app.command()
def submit_order(
    order_intent_path: str = typer.Option(
        ..., help="Path to JSON file containing order intent"
    ),
    fuzz: bool = typer.Option(False, help="Fuzz the order intent"),
) -> None:
    """Submit an order intent to an Orion vault. The order intent can be either transparent or encrypted."""
    ensure_env_file()

    vault_address = os.getenv("ORION_VAULT_ADDRESS")
    validate_var(
        vault_address,
        error_message=(
            "ORION_VAULT_ADDRESS environment variable is missing or invalid. "
            "Please set ORION_VAULT_ADDRESS in your .env file or as an environment variable. "
        ),
    )

    # JSON file input
    with open(order_intent_path, "r") as f:
        order_intent = json.load(f)

    from .contracts import OrionConfig

    config = OrionConfig()

    if vault_address in config.orion_transparent_vaults:
        output_order_intent = validate_order(order_intent=order_intent)
        vault = OrionTransparentVault()
        tx_result = vault.submit_order_intent(order_intent=output_order_intent)
    elif vault_address in config.orion_encrypted_vaults:
        validated_order_intent = validate_order(order_intent=order_intent, fuzz=fuzz)
        output_order_intent, input_proof = encrypt_order_intent(
            order_intent=validated_order_intent
        )

        vault = OrionEncryptedVault()
        tx_result = vault.submit_order_intent(
            order_intent=output_order_intent, input_proof=input_proof
        )
    else:
        raise ValueError(f"Vault address {vault_address} not in OrionConfig contract.")

    format_transaction_logs(tx_result, "Order intent submitted successfully!")


@app.command()
def update_curator(
    new_curator_address: str = typer.Option(
        ..., help="New curator address to set for the vault"
    ),
) -> None:
    """Update the curator address for an Orion vault."""
    ensure_env_file()

    vault_address = os.getenv("ORION_VAULT_ADDRESS")
    validate_var(
        vault_address,
        error_message=(
            "ORION_VAULT_ADDRESS environment variable is missing or invalid. "
            "Please set ORION_VAULT_ADDRESS in your .env file or as an environment variable. "
        ),
    )

    # Working for both vaults types
    vault = OrionTransparentVault()

    tx_result = vault.update_curator(new_curator_address)
    format_transaction_logs(tx_result, "Curator address updated successfully!")


@app.command()
def update_fee_model(
    fee_type: FeeType = typer.Option(..., help="Type of the fee"),
    performance_fee: float = typer.Option(
        ..., help="Performance fee in percentage i.e. 10.2 (maximum 30%)"
    ),
    management_fee: float = typer.Option(
        ..., help="Management fee in percentage i.e. 2.1 (maximum 3%)"
    ),
) -> None:
    """Update the fee model for an Orion vault."""
    ensure_env_file()

    fee_type = fee_type_to_int[fee_type.value]

    vault_address = os.getenv("ORION_VAULT_ADDRESS")
    validate_var(
        vault_address,
        error_message=(
            "ORION_VAULT_ADDRESS environment variable is missing or invalid. "
            "Please set ORION_VAULT_ADDRESS in your .env file or as an environment variable. "
        ),
    )

    # Working for both vaults types
    vault = OrionTransparentVault()

    tx_result = vault.update_fee_model(
        fee_type=fee_type,
        performance_fee=int(performance_fee * BASIS_POINTS_FACTOR),
        management_fee=int(management_fee * BASIS_POINTS_FACTOR),
    )
    format_transaction_logs(tx_result, "Fee model updated successfully!")
