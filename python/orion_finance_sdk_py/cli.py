"""Command line interface for the Orion Finance Python SDK."""

import json
import os
import sys

import questionary
import typer
from dotenv import load_dotenv

from .contracts import (
    OrionConfig,
    OrionEncryptedVault,
    OrionTransparentVault,
    VaultFactory,
)
from .encrypt import encrypt_order_intent
from .types import (
    ZERO_ADDRESS,
    FeeType,
    VaultType,
    fee_type_to_int,
)
from .utils import (
    BASIS_POINTS_FACTOR,
    MAX_MANAGEMENT_FEE,
    MAX_PERFORMANCE_FEE,
    ensure_env_file,
    format_transaction_logs,
    validate_order,
    validate_var,
)

ORION_BANNER = r"""
     ██████╗ ██████╗ ██╗ ██████╗ ███╗   ██╗    ███████╗██╗███╗   ██╗ █████╗ ███╗   ██╗ ██████╗███████╗
    ██╔═══██╗██╔══██╗██║██╔═══██╗████╗  ██║    ██╔════╝██║████╗  ██║██╔══██╗████╗  ██║██╔════╝██╔════╝
    ██║   ██║██████╔╝██║██║   ██║██╔██╗ ██║    █████╗  ██║██╔██╗ ██║███████║██╔██╗ ██║██║     █████╗
    ██║   ██║██╔══██╗██║██║   ██║██║╚██╗██║    ██╔══╝  ██║██║╚██╗██║██╔══██║██║╚██╗██║██║     ██╔══╝
    ╚██████╔╝██║  ██║██║╚██████╔╝██║ ╚████║    ██║     ██║██║ ╚████║██║  ██║██║ ╚████║╚██████╗███████╗
     ╚═════╝ ╚═╝  ╚═╝╚═╝ ╚═════╝ ╚═╝  ╚═══╝    ╚═╝     ╚═╝╚═╝  ╚═══╝╚═╝  ╚═╝╚═╝  ╚══╝ ╚═════╝╚══════╝
"""

app = typer.Typer(help="Orion Finance SDK CLI")


def _deploy_vault_logic(
    vault_type: str,
    name: str,
    symbol: str,
    fee_type_value: int,
    performance_fee_bp: int,
    management_fee_bp: int,
    deposit_access_control: str,
):
    """Logic for deploying a vault."""
    vault_factory = VaultFactory(vault_type=vault_type)

    tx_result = vault_factory.create_orion_vault(
        name=name,
        symbol=symbol,
        fee_type=fee_type_value,
        performance_fee=performance_fee_bp,
        management_fee=management_fee_bp,
        deposit_access_control=deposit_access_control,
    )

    format_transaction_logs(tx_result, "Vault deployment transaction completed!")

    vault_address = vault_factory.get_vault_address_from_result(tx_result)
    if vault_address:
        print(
            f"\n📍 ORION_VAULT_ADDRESS={vault_address} <------------------- COPY THIS TO YOUR .env FILE TO INTERACT WITH THE VAULT."
        )
    else:
        print("\n❌ Could not extract vault address from transaction")


def _submit_order_logic(order_intent_path: str, fuzz: bool):
    """Logic for submitting an order."""
    vault_address = os.getenv("ORION_VAULT_ADDRESS")
    validate_var(
        vault_address,
        error_message=(
            "ORION_VAULT_ADDRESS environment variable is missing or invalid. "
            "Please set ORION_VAULT_ADDRESS in your .env file or as an environment variable. "
        ),
    )

    with open(order_intent_path, "r") as f:
        order_intent = json.load(f)

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


def _update_strategist_logic(new_strategist_address: str):
    """Logic for updating strategist."""
    vault_address = os.getenv("ORION_VAULT_ADDRESS")
    validate_var(
        vault_address,
        error_message=(
            "ORION_VAULT_ADDRESS environment variable is missing or invalid. "
            "Please set ORION_VAULT_ADDRESS in your .env file or as an environment variable. "
        ),
    )

    config = OrionConfig()
    if vault_address in config.orion_transparent_vaults:
        vault = OrionTransparentVault()
    elif vault_address in config.orion_encrypted_vaults:
        vault = OrionEncryptedVault()
    else:
        raise ValueError(f"Vault address {vault_address} not in OrionConfig contract.")

    tx_result = vault.update_strategist(new_strategist_address)
    format_transaction_logs(tx_result, "Strategist address updated successfully!")


def _update_fee_model_logic(
    fee_type_value: int, performance_fee_bp: int, management_fee_bp: int
):
    """Logic for updating fee model."""
    vault_address = os.getenv("ORION_VAULT_ADDRESS")
    validate_var(
        vault_address,
        error_message=(
            "ORION_VAULT_ADDRESS environment variable is missing or invalid. "
            "Please set ORION_VAULT_ADDRESS in your .env file or as an environment variable. "
        ),
    )

    config = OrionConfig()
    if vault_address in config.orion_transparent_vaults:
        vault = OrionTransparentVault()
    elif vault_address in config.orion_encrypted_vaults:
        vault = OrionEncryptedVault()
    else:
        raise ValueError(f"Vault address {vault_address} not in OrionConfig contract.")

    tx_result = vault.update_fee_model(
        fee_type=fee_type_value,
        performance_fee=performance_fee_bp,
        management_fee=management_fee_bp,
    )
    format_transaction_logs(tx_result, "Fee model updated successfully!")


def _update_deposit_access_control_logic(new_dac_address: str):
    """Logic for updating deposit access control."""
    vault_address = os.getenv("ORION_VAULT_ADDRESS")
    validate_var(
        vault_address,
        error_message="ORION_VAULT_ADDRESS environment variable is missing or invalid.",
    )

    config = OrionConfig()
    if vault_address in config.orion_transparent_vaults:
        vault = OrionTransparentVault()
    elif vault_address in config.orion_encrypted_vaults:
        vault = OrionEncryptedVault()
    else:
        raise ValueError(f"Vault address {vault_address} not in OrionConfig contract.")

    tx_result = vault.set_deposit_access_control(new_dac_address)
    format_transaction_logs(tx_result, "Deposit access control updated successfully!")


def _claim_fees_logic(amount: int):
    """Logic for claiming fees."""
    vault_address = os.getenv("ORION_VAULT_ADDRESS")
    validate_var(
        vault_address,
        error_message="ORION_VAULT_ADDRESS environment variable is missing or invalid.",
    )

    config = OrionConfig()

    if vault_address in config.orion_transparent_vaults:
        vault = OrionTransparentVault()
        tx_result = vault.transfer_manager_fees(amount)
        format_transaction_logs(tx_result, "Manager fees claimed successfully!")
    elif vault_address in config.orion_encrypted_vaults:
        vault = OrionEncryptedVault()
        tx_result = vault.transfer_strategist_fees(amount)
        format_transaction_logs(tx_result, "Strategist fees claimed successfully!")
    else:
        raise ValueError(f"Vault address {vault_address} not in OrionConfig contract.")


def _get_pending_fees_logic():
    """Logic for fetching pending vault fees."""
    vault_address = os.getenv("ORION_VAULT_ADDRESS")
    validate_var(
        vault_address,
        error_message="ORION_VAULT_ADDRESS environment variable is missing or invalid.",
    )

    config = OrionConfig()
    if vault_address in config.orion_transparent_vaults:
        vault = OrionTransparentVault()
    elif vault_address in config.orion_encrypted_vaults:
        vault = OrionEncryptedVault()
    else:
        raise ValueError(f"Vault address {vault_address} not in OrionConfig contract.")

    fees = vault.pending_vault_fees
    print(f"\n💰 Pending Vault Fees: {fees}")


def ask_or_exit(question):
    """Ask a questionary question and exit/return if cancelled."""
    result = question.ask()
    if result is None:
        raise KeyboardInterrupt
    return result


def validate_perf_fee_input(val: str) -> bool | str:
    """Validate performance fee input against on-chain limits if available."""
    try:
        val_float = float(val)
        if val_float < 0:
            return "Fee cannot be negative"

        limit = MAX_PERFORMANCE_FEE
        vault_address = os.getenv("ORION_VAULT_ADDRESS")
        if vault_address and vault_address != ZERO_ADDRESS:
            try:
                # Try to fetch from current vault
                config = OrionConfig()
                if vault_address in config.orion_transparent_vaults:
                    vault = OrionTransparentVault()
                elif vault_address in config.orion_encrypted_vaults:
                    vault = OrionEncryptedVault()
                else:
                    return True  # Fallback to constant if not found yet

                limit = vault.max_performance_fee
            except Exception:
                pass  # Fallback to constant

        if val_float * BASIS_POINTS_FACTOR > limit:
            return f"Fee cannot exceed {limit / BASIS_POINTS_FACTOR}%"
        return True
    except ValueError:
        return "Please enter a valid number"


def validate_mgmt_fee_input(val: str) -> bool | str:
    """Validate management fee input against on-chain limits if available."""
    try:
        val_float = float(val)
        if val_float < 0:
            return "Fee cannot be negative"

        limit = MAX_MANAGEMENT_FEE
        vault_address = os.getenv("ORION_VAULT_ADDRESS")
        if vault_address and vault_address != ZERO_ADDRESS:
            try:
                # Try to fetch from current vault
                config = OrionConfig()
                if vault_address in config.orion_transparent_vaults:
                    vault = OrionTransparentVault()
                elif vault_address in config.orion_encrypted_vaults:
                    vault = OrionEncryptedVault()
                else:
                    return True  # Fallback to constant if not found yet

                limit = vault.max_management_fee
            except Exception:
                pass  # Fallback to constant

        if val_float * BASIS_POINTS_FACTOR > limit:
            return f"Fee cannot exceed {limit / BASIS_POINTS_FACTOR}%"
        return True
    except ValueError:
        return "Please enter a valid number"


def interactive_menu():
    """Launch the interactive TUI menu."""
    while True:
        # Force reload environment variables to pick up changes (e.g. newly deployed vault address)
        load_dotenv(override=True)
        try:
            choice = ask_or_exit(
                questionary.select(
                    "What would you like to do?",
                    choices=[
                        "Deploy Vault",
                        "Submit Order",
                        "Update Strategist",
                        "Update Fee Model",
                        "Update Deposit Access Control",
                        "Claim Fees",
                        "Get Pending Fees",
                        "Exit",
                    ],
                    instruction="[ ↑↓ to scroll | Enter to select ]",
                )
            )

            if choice == "Exit":
                break

            if choice == "Deploy Vault":
                # Always deploy transparent vaults from CLI
                vault_type = VaultType.TRANSPARENT.value
                name = ask_or_exit(questionary.text("Vault Name:"))
                symbol = ask_or_exit(questionary.text("Vault Symbol:"))
                fee_type_str = ask_or_exit(
                    questionary.select(
                        "Fee Type:",
                        choices=[t.value for t in FeeType],
                        instruction="[ ↑↓ to scroll | Enter to select ]",
                    )
                )
                perf_fee = float(
                    ask_or_exit(
                        questionary.text(
                            "Performance Fee (%):",
                            default="0",
                            validate=validate_perf_fee_input,
                        )
                    )
                )
                mgmt_fee = float(
                    ask_or_exit(
                        questionary.text(
                            "Management Fee (%):",
                            default="0",
                            validate=validate_mgmt_fee_input,
                        )
                    )
                )
                dac = ask_or_exit(
                    questionary.text(
                        "Deposit Access Control (Address):", default=ZERO_ADDRESS
                    )
                )

                _deploy_vault_logic(
                    vault_type,
                    name,
                    symbol,
                    fee_type_to_int[fee_type_str],
                    int(perf_fee * BASIS_POINTS_FACTOR),
                    int(mgmt_fee * BASIS_POINTS_FACTOR),
                    dac,
                )

            elif choice == "Submit Order":
                path = ask_or_exit(questionary.path("Path to Order Intent JSON:"))
                fuzz = ask_or_exit(
                    questionary.confirm("Fuzz order intent?", default=False)
                )
                _submit_order_logic(path, fuzz)

            elif choice == "Update Strategist":
                addr = ask_or_exit(questionary.text("New Strategist Address:"))
                _update_strategist_logic(addr)

            elif choice == "Update Fee Model":
                fee_type_str = ask_or_exit(
                    questionary.select(
                        "Fee Type:",
                        choices=[t.value for t in FeeType],
                        instruction="[ ↑↓ to scroll | Enter to select ]",
                    )
                )
                perf_fee = float(
                    ask_or_exit(
                        questionary.text(
                            "Performance Fee (%):",
                            default="0",
                            validate=validate_perf_fee_input,
                        )
                    )
                )
                mgmt_fee = float(
                    ask_or_exit(
                        questionary.text(
                            "Management Fee (%):",
                            default="0",
                            validate=validate_mgmt_fee_input,
                        )
                    )
                )

                _update_fee_model_logic(
                    fee_type_to_int[fee_type_str],
                    int(perf_fee * BASIS_POINTS_FACTOR),
                    int(mgmt_fee * BASIS_POINTS_FACTOR),
                )

            elif choice == "Update Deposit Access Control":
                addr = ask_or_exit(questionary.text("New Access Control Address:"))
                _update_deposit_access_control_logic(addr)

            elif choice == "Claim Fees":
                amount = int(ask_or_exit(questionary.text("Amount to Claim (units):")))
                _claim_fees_logic(amount)

            elif choice == "Get Pending Fees":
                _get_pending_fees_logic()

            input("\nPress Enter to continue...")

        except KeyboardInterrupt:
            print("\nOperation cancelled.")
            continue  # Go back to main menu loop
        except Exception as e:
            print(f"\n❌ Error: {e}")
            input("\nPress Enter to continue...")


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context):
    """Orion Finance CLI."""
    ensure_env_file()
    if ctx.invoked_subcommand is None:
        interactive_menu()


def entry_point():
    """Entry point for the CLI that prints the banner."""
    print(ORION_BANNER, file=sys.stderr)
    app()


@app.command()
def deploy_vault(
    name: str = typer.Option(..., help="Name of the vault"),
    symbol: str = typer.Option(..., help="Symbol of the vault"),
    fee_type: FeeType = typer.Option(..., help="Type of the fee"),
    performance_fee: float = typer.Option(
        ..., help="Performance fee in percentage i.e. 10.2 (maximum 30%)"
    ),
    management_fee: float = typer.Option(
        ..., help="Management fee in percentage i.e. 2.1 (maximum 3%)"
    ),
    deposit_access_control: str = typer.Option(
        ZERO_ADDRESS, help="Address of the deposit access control contract"
    ),
):
    """Deploy an Orion vault with customizable fee structure, name, and symbol. The vault defaults to transparent."""
    fee_type_int = fee_type_to_int[fee_type.value]
    _deploy_vault_logic(
        VaultType.TRANSPARENT.value,
        name,
        symbol,
        fee_type_int,
        int(performance_fee * BASIS_POINTS_FACTOR),
        int(management_fee * BASIS_POINTS_FACTOR),
        deposit_access_control,
    )


@app.command()
def submit_order(
    order_intent_path: str = typer.Option(
        ..., help="Path to JSON file containing order intent"
    ),
    fuzz: bool = typer.Option(False, help="Fuzz the order intent"),
) -> None:
    """Submit an order intent to an Orion vault. The order intent can be either transparent or encrypted."""
    _submit_order_logic(order_intent_path, fuzz)


@app.command()
def update_strategist(
    new_strategist_address: str = typer.Option(
        ..., help="New strategist address to set for the vault"
    ),
) -> None:
    """Update the strategist address for an Orion vault."""
    _update_strategist_logic(new_strategist_address)


@app.command()
def update_fee_model(
    fee_type: FeeType = typer.Option(
        ...,
        help="Type of the fee. Options: absolute, soft_hurdle, hard_hurdle, high_water_mark, hurdle_hwm",
    ),
    performance_fee: float = typer.Option(
        ..., help="Performance fee in percentage i.e. 10.2 (maximum 30%)"
    ),
    management_fee: float = typer.Option(
        ..., help="Management fee in percentage i.e. 2.1 (maximum 3%)"
    ),
) -> None:
    """Update the fee model for an Orion vault."""
    fee_type_int = fee_type_to_int[fee_type.value]
    _update_fee_model_logic(
        fee_type_int,
        int(performance_fee * BASIS_POINTS_FACTOR),
        int(management_fee * BASIS_POINTS_FACTOR),
    )


@app.command()
def get_pending_fees() -> None:
    """Get pending fees for the current vault."""
    _get_pending_fees_logic()
