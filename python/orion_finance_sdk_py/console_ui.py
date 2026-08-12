"""Shared Rich console presentation for the Orion Finance CLI."""

from __future__ import annotations

import contextvars
import importlib.metadata
import os
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path

from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.rule import Rule
from rich.spinner import Spinner
from rich.table import Table
from rich.text import Text

from .types import CHAIN_CONFIG

# Status and chrome go to stderr so stdout stays pipe-friendly where needed.
console = Console(stderr=True)

_active_progress: contextvars.ContextVar["OperationProgress | None"] = (
    contextvars.ContextVar("orion_active_progress", default=None)
)

_CHAIN_LABELS = {
    11155111: "Sepolia",
    1: "Mainnet",
}


class OperationProgress:
    """Multi-step operation reporter for CLI flows."""

    def __init__(self, title: str) -> None:
        """Initialize progress reporting for an operation titled ``title``."""
        self.title = title
        self.completed: list[str] = []
        self.current: str | None = None
        self._live: Live | None = None
        self._token: contextvars.Token | None = None
        self._use_live = console.is_terminal

    def advance(self, message: str) -> None:
        """Mark the previous step complete and start a new active step."""
        if self.current:
            self.completed.append(self.current)
        self.current = message
        if self._use_live:
            self._refresh_live()
        else:
            console.print(f"[dim]  • {message}[/dim]")

    def _render(self) -> Group:
        parts: list[Text | Spinner] = [Text(self.title, style="bold")]
        for step in self.completed:
            parts.append(Text(f"  • {step}", style="dim"))
        if self.current:
            parts.append(Spinner("dots", text=f"  {self.current}"))
        return Group(*parts)

    def _refresh_live(self) -> None:
        if self._live is not None:
            self._live.update(self._render(), refresh=True)

    def __enter__(self) -> OperationProgress:
        """Start live progress rendering and register as the active reporter."""
        self._token = _active_progress.set(self)
        if self._use_live:
            self._live = Live(
                self._render(),
                console=console,
                refresh_per_second=10,
                transient=False,
            )
            self._live.__enter__()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        """Finalize the current step, stop live rendering, and clear context."""
        if self.current:
            self.completed.append(self.current)
            self.current = None
        if self._live is not None:
            self._live.update(self._render(), refresh=True)
            self._live.__exit__(exc_type, exc, tb)
            self._live = None
        if self._token is not None:
            _active_progress.reset(self._token)


def progress_step(message: str) -> None:
    """Report a step when inside ``operation_progress``; no-op otherwise."""
    op = _active_progress.get()
    if op is not None:
        op.advance(message)


@contextmanager
def operation_progress(title: str) -> Iterator[OperationProgress]:
    """Show a live step checklist while a multi-phase CLI operation runs."""
    with OperationProgress(title) as op:
        yield op


def _sdk_version() -> str:
    try:
        return importlib.metadata.version("orion-finance-sdk-py")
    except importlib.metadata.PackageNotFoundError:
        return "unknown"


def _chain_label() -> str:
    chain_id = int(os.getenv("CHAIN_ID", "11155111"))
    name = _CHAIN_LABELS.get(chain_id, f"chain {chain_id}")
    return f"{name} ({chain_id})"


def _explorer_url() -> str:
    chain_id = int(os.getenv("CHAIN_ID", "11155111"))
    if chain_id in CHAIN_CONFIG and "Explorer" in CHAIN_CONFIG[chain_id]:
        return CHAIN_CONFIG[chain_id]["Explorer"]
    return "https://sepolia.etherscan.io"


def _normalize_tx_hash(tx_hash: str) -> str:
    if not tx_hash.startswith("0x"):
        return f"0x{tx_hash}"
    return tx_hash


def _short_hash(tx_hash: str) -> str:
    if len(tx_hash) <= 14:
        return tx_hash
    return f"{tx_hash[:6]}…{tx_hash[-4:]}"


@contextmanager
def rpc_status(message: str) -> Iterator[None]:
    """Show a spinner while an RPC or on-chain operation is in progress."""
    with console.status(message, spinner="dots"):
        yield


def print_info(message: str) -> None:
    """Print an informational line."""
    console.print(f"[dim]{message}[/dim]")


def print_warn(message: str) -> None:
    """Print a warning line."""
    console.print(f"[yellow]{message}[/yellow]")


def print_error(message: str) -> None:
    """Print an error line."""
    console.print(f"[bold red]Error:[/bold red] {message}")


def print_key_value(rows: Sequence[tuple[str, str]], *, title: str | None = None) -> None:
    """Print labeled key/value rows inside a compact panel."""
    lines = Text()
    for index, (key, value) in enumerate(rows):
        if index:
            lines.append("\n")
        lines.append(f"{key:<22}", style="dim")
        lines.append(value)
    console.print(Panel(lines, title=title, border_style="dim", expand=False))


_ADDR_COL_WIDTH = 44


def print_table(
    columns: Sequence[str],
    rows: Sequence[Sequence[str]],
    *,
    title: str | None = None,
    caption: str | None = None,
) -> None:
    """Print a Rich table."""
    table = Table(title=title, show_header=True, header_style="bold", expand=False)
    for column in columns:
        lower = column.lower()
        if lower in {"address", "testnet", "mainnet"}:
            table.add_column(
                column, width=_ADDR_COL_WIDTH, no_wrap=True, overflow="ignore"
            )
        else:
            table.add_column(column)
    for row in rows:
        table.add_row(*row)
    if caption:
        table.caption = caption
        table.caption_style = "dim"
    address_cols = sum(
        1 for c in columns if c.lower() in {"address", "testnet", "mainnet"}
    )
    other_cols = len(columns) - address_cols
    table_width = address_cols * _ADDR_COL_WIDTH + other_cols * 16 + 3
    console.print(table, width=max(table_width, console.width))


def print_tx_result(tx_result, title: str = "Transaction completed") -> None:
    """Print a transaction result with hash and explorer link (no emojis)."""
    tx_hash = _normalize_tx_hash(tx_result.tx_hash)
    explorer = _explorer_url()
    short = _short_hash(tx_hash)
    explorer_tx = f"{explorer}/tx/{tx_hash}"

    body = Text()
    body.append(f"{title}\n\n", style="bold")
    body.append("Hash      ", style="dim")
    body.append(f"{short}\n")
    body.append("Explorer  ", style="dim")
    body.append(explorer_tx, style="cyan underline")

    console.print()
    console.print(Rule(style="dim"))
    console.print(body)
    console.print(Rule(style="dim"))
    console.print()


def print_welcome() -> None:
    """Print a full-width, centered Orion welcome header for the interactive CLI."""
    version = _sdk_version()
    chain = _chain_label()

    body = Text(justify="center")
    body.append("Orion Finance\n", style="bold")
    body.append("Infrastructure for institutional capital. Onchain.\n\n", style="dim")
    body.append("Python SDK  ", style="dim")
    body.append(f"v{version}", style="bold")
    body.append(f"  ·  {chain}\n\n", style="dim")
    body.append("Website  ", style="dim")
    body.append("https://orionfinance.ai\n", style="cyan")
    body.append("SDK docs ", style="dim")
    body.append("https://sdk.orionfinance.ai", style="cyan")

    panel = Panel(
        body,
        title="Orion Console",
        title_align="center",
        border_style="blue",
        expand=True,
        padding=(1, 2),
    )
    console.print(panel)
    console.print()


def print_env_created(env_file_path: Path) -> None:
    """Notify that a new .env template was written."""
    print_info(f"Created .env at {env_file_path}")
    print_info("Update the file with your RPC URL, keys, and vault address.")
