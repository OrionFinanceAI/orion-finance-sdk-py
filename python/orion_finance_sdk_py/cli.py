"""Command line interface for the Orion Finance Python SDK."""

import os
import sys

import questionary
import typer
from dotenv import load_dotenv

from .asset_map import build_asset_address_map
from .console_ui import (
    operation_progress,
    print_error,
    print_info,
    print_key_value,
    print_table,
    print_welcome,
    progress_step,
    rpc_status,
)
from .contracts import (
    OrionConfig,
    OrionEncryptedVault,
    OrionTransparentVault,
    VaultFactory,
)
from .order_intent_io import load_order_intent
from .types import (
    ZERO_ADDRESS,
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

app = typer.Typer(help="Orion Finance SDK CLI")


def _resolve_vault(
    config: OrionConfig, vault_address: str
) -> OrionTransparentVault | OrionEncryptedVault:
    """Return the SDK vault wrapper for a registered Orion vault address."""
    if config.is_encrypted_vault(vault_address):
        return OrionEncryptedVault()
    if vault_address in config.orion_transparent_vaults:
        return OrionTransparentVault()
    raise ValueError(f"Vault address {vault_address} not in OrionConfig contract.")


def _deploy_vault_logic(
    vault_type: str,
    strategist_address: str,
    name: str,
    symbol: str,
    fee_type_value: int,
    performance_fee_bp: int,
    management_fee_bp: int,
    deposit_access_control: str,
):
    """Logic for deploying a vault."""
    vault_factory = VaultFactory(vault_type=vault_type)

    with operation_progress("Deploy vault"):
        tx_result = vault_factory.create_orion_vault(
            strategist_address=strategist_address,
            name=name,
            symbol=symbol,
            fee_type=fee_type_value,
            performance_fee=performance_fee_bp,
            management_fee=management_fee_bp,
            deposit_access_control=deposit_access_control,
        )

    format_transaction_logs(tx_result, "Vault deployment transaction completed")

    vault_address = vault_factory.get_vault_address_from_result(tx_result)
    if vault_address:
        print_key_value(
            [("ORION_VAULT_ADDRESS", vault_address)],
            title="Vault address",
        )
        print_info("Add this address to your .env file to interact with the vault.")
    else:
        print_error("Could not extract vault address from transaction")


def _submit_intent_logic(intent_source: str):
    """Logic for submitting a strategist intent.

    ``intent_source`` may be a path to ``.json`` / ``.csv`` / ``.parquet``, or an
    inline JSON / Python dict literal string mapping addresses to weights.
    """
    vault_address = validate_var(
        os.getenv("ORION_VAULT_ADDRESS"),
        error_message=(
            "ORION_VAULT_ADDRESS environment variable is missing or invalid. "
            "Please set ORION_VAULT_ADDRESS in your .env file or as an environment variable. "
        ),
    )

    with operation_progress("Submit intent"):
        progress_step("Loading intent from source")
        order_intent = load_order_intent(intent_source)
        config = OrionConfig()
        vault = _resolve_vault(config, vault_address)
        output_order_intent = validate_order(order_intent=order_intent)
        tx_result = vault.submit_order_intent(order_intent=output_order_intent)

    format_transaction_logs(tx_result, "Intent submitted successfully")


def _update_strategist_logic(new_strategist_address: str):
    """Logic for updating strategist."""
    vault_address = validate_var(
        os.getenv("ORION_VAULT_ADDRESS"),
        error_message=(
            "ORION_VAULT_ADDRESS environment variable is missing or invalid. "
            "Please set ORION_VAULT_ADDRESS in your .env file or as an environment variable. "
        ),
    )

    config = OrionConfig()
    vault = _resolve_vault(config, vault_address)

    with operation_progress("Update vault strategist"):
        tx_result = vault.update_strategist(new_strategist_address)
    format_transaction_logs(tx_result, "Strategist address updated successfully")


def _update_fee_model_logic(
    fee_type_value: int, performance_fee_bp: int, management_fee_bp: int
):
    """Logic for updating fee model."""
    vault_address = validate_var(
        os.getenv("ORION_VAULT_ADDRESS"),
        error_message=(
            "ORION_VAULT_ADDRESS environment variable is missing or invalid. "
            "Please set ORION_VAULT_ADDRESS in your .env file or as an environment variable. "
        ),
    )

    config = OrionConfig()
    vault = _resolve_vault(config, vault_address)

    with operation_progress("Update vault fee model"):
        tx_result = vault.update_fee_model(
            fee_type=fee_type_value,
            performance_fee=performance_fee_bp,
            management_fee=management_fee_bp,
        )
    format_transaction_logs(tx_result, "Fee model updated successfully")


def _update_deposit_access_control_logic(new_dac_address: str):
    """Logic for updating deposit access control."""
    vault_address = validate_var(
        os.getenv("ORION_VAULT_ADDRESS"),
        error_message="ORION_VAULT_ADDRESS environment variable is missing or invalid.",
    )

    config = OrionConfig()
    vault = _resolve_vault(config, vault_address)

    with operation_progress("Update deposit access control"):
        tx_result = vault.set_deposit_access_control(new_dac_address)
    format_transaction_logs(tx_result, "Deposit access control updated successfully")


def _claim_fees_logic(amount: int):
    """Logic for claiming fees."""
    vault_address = validate_var(
        os.getenv("ORION_VAULT_ADDRESS"),
        error_message="ORION_VAULT_ADDRESS environment variable is missing or invalid.",
    )

    config = OrionConfig()
    vault = _resolve_vault(config, vault_address)

    with operation_progress("Claim manager fees"):
        tx_result = vault.transfer_manager_fees(amount)
    format_transaction_logs(tx_result, "Manager fees claimed successfully")


def _get_pending_fees_logic():
    """Logic for fetching pending vault fees."""
    vault_address = validate_var(
        os.getenv("ORION_VAULT_ADDRESS"),
        error_message="ORION_VAULT_ADDRESS environment variable is missing or invalid.",
    )

    config = OrionConfig()
    vault = _resolve_vault(config, vault_address)

    with rpc_status("Fetching pending vault fees…"):
        fees = vault.pending_vault_fees

    print_key_value([("Pending vault fees", str(fees))], title="Vault fees")


def _request_deposit_logic(assets: int):
    """LP request deposit (approve + requestDeposit)."""
    from . import lp as lp_api

    with operation_progress("Submit deposit request"):
        tx_result = lp_api.request_deposit(assets)
    format_transaction_logs(tx_result, "Deposit request submitted successfully")


def _cancel_deposit_logic(amount: int):
    """LP cancel deposit request."""
    from . import lp as lp_api

    with operation_progress("Cancel deposit request"):
        tx_result = lp_api.cancel_deposit_request(amount)
    format_transaction_logs(tx_result, "Deposit request cancelled successfully")


def _request_redeem_logic(shares: int):
    """LP request redeem (approve shares + requestRedeem)."""
    from . import lp as lp_api

    with operation_progress("Submit redeem request"):
        tx_result = lp_api.request_redeem(shares)
    format_transaction_logs(tx_result, "Redeem request submitted successfully")


def _cancel_redeem_logic(shares: int):
    """LP cancel redeem request."""
    from . import lp as lp_api

    with operation_progress("Cancel redeem request"):
        tx_result = lp_api.cancel_redeem_request(shares)
    format_transaction_logs(tx_result, "Redeem request cancelled successfully")


def _redeem_logic(shares: int, receiver: str, owner: str):
    """LP sync redeem (decommissioned vaults only)."""
    from . import lp as lp_api

    with operation_progress("Submit sync redeem"):
        tx_result = lp_api.redeem(shares, receiver, owner)
    format_transaction_logs(tx_result, "Redeem completed successfully")


def _remove_vault_logic():
    """Manager-initiated vault decommissioning."""
    from . import manager as manager_api

    with operation_progress("Start vault decommissioning"):
        tx_result = manager_api.remove_orion_vault()
    format_transaction_logs(tx_result, "Vault removal / decommissioning started")


def _list_whitelisted_assets_logic():
    """Logic for listing whitelisted assets from OrionConfig."""
    config = OrionConfig()

    with rpc_status("Fetching whitelisted assets from chain…"):
        assets = config.whitelisted_assets
        try:
            names = [n.strip() for n in config.whitelisted_asset_names]
        except Exception:
            names = ["Unknown"] * len(assets)

    print_table(
        ["Name", "Address"],
        list(zip(names, assets, strict=True)),
        title="Whitelisted assets",
        caption=f"Total: {len(assets)} whitelisted assets",
    )


def _list_asset_address_map_logic():
    """Logic for listing testnet → mainnet twin address map."""
    with rpc_status("Resolving mainnetSource() for whitelisted twins…"):
        address_map = build_asset_address_map()

    if not address_map:
        print_info("No twin assets with mainnetSource() found.")
        return

    for index, (testnet, mainnet) in enumerate(address_map.items(), start=1):
        title = "Asset twin" if len(address_map) == 1 else f"Twin {index}"
        print_key_value(
            [("Testnet", testnet), ("Mainnet", mainnet)],
            title=title,
        )
    print_info(f"Total: {len(address_map)} twin assets with mainnetSource()")


def ask_or_exit(question):
    """Ask a questionary question and exit/return if cancelled."""
    result = question.ask()
    if result is None:
        raise KeyboardInterrupt
    return result


def validate_int_input(val: str) -> bool | str:
    """Validate integer input."""
    try:
        if int(val) > 0:
            return True
        return "Amount must be positive"
    except ValueError:
        return "Please enter a valid integer"


def validate_name(val: str) -> bool | str:
    """Validate vault name length (max 26 bytes)."""
    if len(val.encode("utf-8")) > 26:
        return "Name too long (max 26 bytes)"
    if not val:
        return "Name cannot be empty"
    return True


def validate_symbol(val: str) -> bool | str:
    """Validate vault symbol length (max 4 bytes)."""
    if len(val.encode("utf-8")) > 4:
        return "Symbol too long (max 4 bytes)"
    if not val:
        return "Symbol cannot be empty"
    return True


def interactive_menu():
    """Launch the interactive TUI menu."""
    print_welcome()
    while True:
        # Force reload environment variables to pick up changes (e.g. newly deployed vault address)
        load_dotenv(override=True)
        try:
            choice = ask_or_exit(
                questionary.select(
                    "What would you like to do?",
                    choices=[
                        "Deploy Vault",
                        "Submit Intent",
                        "Request Deposit",
                        "Cancel Deposit Request",
                        "Request Redeem",
                        "Cancel Redeem Request",
                        "Redeem (Decommissioned)",
                        "Update Strategist",
                        "Update Fee Model",
                        "Update Deposit Access Control",
                        "Claim Fees",
                        "Get Pending Fees",
                        "Remove Vault",
                        "List Whitelisted Assets",
                        "List Asset Address Map",
                        "Exit",
                    ],
                    instruction="[ ↑↓ to scroll | Enter to select ]",
                )
            )

            if choice == "Exit":
                break

            if choice == "Deploy Vault":
                vault_type = ask_or_exit(
                    questionary.select(
                        "Vault Type:",
                        choices=[t.value for t in VaultType],
                        instruction="[ ↑↓ to scroll | Enter to select ]",
                    )
                )
                strategist_address = ask_or_exit(
                    questionary.text("Strategist Address:")
                )
                name = ask_or_exit(
                    questionary.text("Vault Name:", validate=validate_name)
                )
                symbol = ask_or_exit(
                    questionary.text("Vault Symbol:", validate=validate_symbol)
                )
                fee_type_str = ask_or_exit(
                    questionary.select(
                        "Fee Type:",
                        choices=[t.value for t in FeeType],
                        instruction="[ ↑↓ to scroll | Enter to select ]",
                    )
                )
                perf_fee_str = ask_or_exit(
                    questionary.text(
                        "Performance Fee (%):",
                        default="",
                    )
                )
                perf_fee = float(perf_fee_str) if perf_fee_str else 0.0

                mgmt_fee_str = ask_or_exit(
                    questionary.text(
                        "Management Fee (%):",
                        default="",
                    )
                )
                mgmt_fee = float(mgmt_fee_str) if mgmt_fee_str else 0.0
                dac = ask_or_exit(
                    questionary.text("Deposit Access Control (Address):", default="")
                )
                if not dac:
                    dac = ZERO_ADDRESS

                _deploy_vault_logic(
                    vault_type,
                    strategist_address,
                    name,
                    symbol,
                    fee_type_to_int[fee_type_str],
                    int(perf_fee * BASIS_POINTS_FACTOR),
                    int(mgmt_fee * BASIS_POINTS_FACTOR),
                    dac,
                )

            elif choice == "Submit Intent":
                path = ask_or_exit(
                    questionary.text(
                        "Intent: path to .json/.csv/.parquet or inline JSON object:",
                    )
                )
                _submit_intent_logic(path)

            elif choice == "Request Deposit":
                assets = int(
                    ask_or_exit(
                        questionary.text(
                            "Deposit assets (wei/units):", validate=validate_int_input
                        )
                    )
                )
                _request_deposit_logic(assets)

            elif choice == "Cancel Deposit Request":
                amount = int(
                    ask_or_exit(
                        questionary.text(
                            "Cancel deposit amount (wei/units):",
                            validate=validate_int_input,
                        )
                    )
                )
                _cancel_deposit_logic(amount)

            elif choice == "Request Redeem":
                shares = int(
                    ask_or_exit(
                        questionary.text(
                            "Redeem shares (units):", validate=validate_int_input
                        )
                    )
                )
                _request_redeem_logic(shares)

            elif choice == "Cancel Redeem Request":
                shares = int(
                    ask_or_exit(
                        questionary.text(
                            "Cancel redeem shares (units):",
                            validate=validate_int_input,
                        )
                    )
                )
                _cancel_redeem_logic(shares)

            elif choice == "Redeem (Decommissioned)":
                shares = int(
                    ask_or_exit(
                        questionary.text(
                            "Shares to redeem:", validate=validate_int_input
                        )
                    )
                )
                receiver = ask_or_exit(questionary.text("Receiver address:"))
                owner = ask_or_exit(questionary.text("Owner address:"))
                _redeem_logic(shares, receiver, owner)

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
                perf_fee_str = ask_or_exit(
                    questionary.text(
                        "Performance Fee (%):",
                        default="",
                    )
                )
                perf_fee = float(perf_fee_str) if perf_fee_str else 0.0

                mgmt_fee_str = ask_or_exit(
                    questionary.text(
                        "Management Fee (%):",
                        default="",
                    )
                )
                mgmt_fee = float(mgmt_fee_str) if mgmt_fee_str else 0.0

                _update_fee_model_logic(
                    fee_type_to_int[fee_type_str],
                    int(perf_fee * BASIS_POINTS_FACTOR),
                    int(mgmt_fee * BASIS_POINTS_FACTOR),
                )

            elif choice == "Update Deposit Access Control":
                addr = ask_or_exit(questionary.text("New Access Control Address:"))
                _update_deposit_access_control_logic(addr)

            elif choice == "Claim Fees":
                amount = int(
                    ask_or_exit(
                        questionary.text(
                            "Amount to Claim (units):", validate=validate_int_input
                        )
                    )
                )
                _claim_fees_logic(amount)

            elif choice == "Get Pending Fees":
                _get_pending_fees_logic()

            elif choice == "Remove Vault":
                confirmed = ask_or_exit(
                    questionary.confirm(
                        "Decommission this vault? This action is irreversible.",
                        default=False,
                    )
                )
                if confirmed:
                    _remove_vault_logic()
                else:
                    print("Vault removal cancelled.")

            elif choice == "List Whitelisted Assets":
                _list_whitelisted_assets_logic()

            elif choice == "List Asset Address Map":
                _list_asset_address_map_logic()

            input("\nPress Enter to continue...")

        except KeyboardInterrupt:
            print_info("Operation cancelled.")
            continue  # Go back to main menu loop
        except Exception as e:
            print_error(str(e))
            input("\nPress Enter to continue...")


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context):
    """Orion Finance CLI."""
    ensure_env_file()
    if ctx.invoked_subcommand is None:
        interactive_menu()


def entry_point():
    """Entry point for the CLI."""
    try:
        app()
    except ValueError as e:
        print_error(str(e))
        sys.exit(1)


@app.command()
def deploy_vault(
    strategist_address: str = typer.Option(
        ..., help="Strategist address to set for the vault"
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
    deposit_access_control: str = typer.Option(
        ZERO_ADDRESS, help="Address of the deposit access control contract"
    ),
    vault_type: VaultType = typer.Option(
        VaultType.TRANSPARENT,
        help="Vault type: transparent or encrypted",
    ),
):
    """Deploy an Orion vault with customizable fee structure, name, and symbol."""
    fee_type_int = fee_type_to_int[fee_type.value]
    _deploy_vault_logic(
        vault_type.value,
        strategist_address,
        name,
        symbol,
        fee_type_int,
        int(performance_fee * BASIS_POINTS_FACTOR),
        int(management_fee * BASIS_POINTS_FACTOR),
        deposit_access_control,
    )


@app.command()
def submit_intent(
    intent: str = typer.Option(
        ...,
        "--intent",
        "--intent-path",
        "--order-intent",
        "--order-intent-path",
        help=(
            "Path to .json (object), .csv, or .parquet intent; or inline JSON / "
            "Python dict literal, e.g. '{\"0xabc...\": 0.5, ...}'"
        ),
    ),
) -> None:
    """Submit an intent to an Orion vault.

    Transparent vaults submit plaintext weights. Encrypted vaults HPKE-seal the
    intent automatically before calling ``submitIntent(bytes)``.
    """
    _submit_intent_logic(intent)


# Backwards-compatible alias for older scripts/docs.
submit_order = submit_intent


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


@app.command()
def list_whitelisted_assets() -> None:
    """List all whitelisted assets from OrionConfig."""
    _list_whitelisted_assets_logic()


@app.command()
def list_asset_address_map() -> None:
    """List testnet → mainnet address map for twin assets (mainnetSource)."""
    _list_asset_address_map_logic()


@app.command()
def request_deposit(
    assets: int = typer.Option(..., help="Underlying amount in token units"),
) -> None:
    """Request an async vault deposit (approves underlying, then requestDeposit)."""
    _request_deposit_logic(assets)


@app.command()
def cancel_deposit_request(
    amount: int = typer.Option(..., help="Pending deposit amount to cancel"),
) -> None:
    """Cancel a pending vault deposit request."""
    _cancel_deposit_logic(amount)


@app.command()
def request_redeem(
    shares: int = typer.Option(..., help="Vault share amount to redeem"),
) -> None:
    """Request an async vault redeem (approves shares to vault, then requestRedeem)."""
    _request_redeem_logic(shares)


@app.command()
def cancel_redeem_request(
    shares: int = typer.Option(..., help="Pending redeem shares to cancel"),
) -> None:
    """Cancel a pending vault redeem request."""
    _cancel_redeem_logic(shares)


@app.command()
def redeem(
    shares: int = typer.Option(..., help="Shares to redeem"),
    receiver: str = typer.Option(..., help="Receiver of underlying"),
    owner: str = typer.Option(..., help="Share owner"),
) -> None:
    """Sync redeem — only for decommissioned vaults."""
    _redeem_logic(shares, receiver, owner)


@app.command()
def remove_vault() -> None:
    """Start vault decommissioning via OrionConfig.removeOrionVault (manager)."""
    _remove_vault_logic()
