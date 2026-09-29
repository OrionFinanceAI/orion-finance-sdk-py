"""Bridge from a fitted portfolio estimator to onchain intent submit.

Quant composition stays with skfolio: build any estimator, then hand it to
``IntentSession`` for prepare → fit → encrypt → submit.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Self

import pandas as pd

from .contracts import TransactionResult
from .intent import Intent
from .stats.portfolio import FittedPortfolio, PortfolioEstimator, fit_estimator
from .stats.series import ReturnSeries
from .strategist import submit_intent
from .utils import checksum_address, validate_order


def weights_to_intent(
    weights: pd.Series,
    *,
    address_by_label: Mapping[str, str] | None = None,
    drop_abs_below: float = 1e-12,
) -> dict[str, float]:
    """Map labeled weights to fractional address weights summing to 1.

    Args:
        weights: Portfolio weights keyed by asset label (name or address).
        address_by_label: Optional label → token address map. Labels that are
            already addresses pass through ``checksum_address``.
        drop_abs_below: Drop legs whose absolute weight is at or below this.

    Returns:
        Checksummed address → positive fractional weight (sum 1).
    """
    if weights.empty:
        raise ValueError("weights must not be empty")

    mapped: dict[str, float] = {}
    for label, value in weights.items():
        amount = float(value)
        if abs(amount) <= drop_abs_below:
            continue
        key = str(label)
        if address_by_label is not None and key in address_by_label:
            address = checksum_address(address_by_label[key])
        else:
            address = checksum_address(key)
        mapped[address] = mapped.get(address, 0.0) + amount

    if not mapped:
        raise ValueError("No positive weights remain after filtering")
    if any(v < 0 for v in mapped.values()):
        raise ValueError("Intent weights must be non-negative")

    total = sum(mapped.values())
    if total <= 0:
        raise ValueError("Weight sum must be positive")
    return {addr: weight / total for addr, weight in mapped.items()}


class IntentSession:
    """Fit a user-built estimator, then encrypt and/or submit an intent."""

    def __init__(
        self,
        model: PortfolioEstimator,
        *,
        vault_address: str | None = None,
        address_by_label: Mapping[str, str] | None = None,
    ):
        """Bind an unfitted estimator and optional vault / label map.

        Args:
            model: Any estimator with ``fit`` / ``predict`` / ``weights_`` after fit.
            vault_address: Vault for submit; defaults to ``ORION_VAULT_ADDRESS``.
            address_by_label: Map return-column labels to token addresses.
        """
        self.model = model
        self.vault_address = vault_address
        self.address_by_label = (
            None if address_by_label is None else dict(address_by_label)
        )
        self._fitted: FittedPortfolio | None = None

    @property
    def fitted(self) -> FittedPortfolio:
        """Fitted portfolio from the last ``fit`` call."""
        if self._fitted is None:
            raise ValueError("IntentSession has not been fit yet")
        return self._fitted

    @property
    def weights(self) -> pd.Series:
        """Fractional weights from the last ``fit`` call."""
        return self.fitted.weights

    @property
    def intent(self) -> dict[str, int]:
        """Scaled protocol intent from the last ``fit`` call."""
        fractional = weights_to_intent(
            self.weights, address_by_label=self.address_by_label
        )
        return validate_order(fractional)

    def fit(self, returns: ReturnSeries | pd.DataFrame) -> Self:
        """Prepare returns and fit the bound estimator."""
        self._fitted = fit_estimator(returns, self.model)
        return self

    def predict(self, returns: ReturnSeries | pd.DataFrame) -> object:
        """Out-of-sample predict using the fitted estimator."""
        frame = returns.returns if isinstance(returns, ReturnSeries) else returns
        return self.fitted.predict(frame)

    def encrypt(self, pk_r: bytes | None = None) -> bytes:
        """Seal the fitted intent (does not broadcast)."""
        return Intent(self.intent).encrypt(pk_r)

    def submit(self) -> TransactionResult | None:
        """Submit the fitted intent via the strategist path.

        Returns ``None`` when a transparent vault already holds the same intent.
        """
        address = self.vault_address or os.getenv("ORION_VAULT_ADDRESS")
        return submit_intent(self.intent, vault_address=address)
