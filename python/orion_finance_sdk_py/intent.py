"""Strategist intent helpers, including Orion HPKE encryption."""

from __future__ import annotations

from collections.abc import Mapping

from .hpke import seal_intent


class Intent:
    """Scaled strategist intent weights keyed by token address."""

    def __init__(self, weights: Mapping[str, int]):
        """Create an intent from ``address -> uint32 weight`` mappings.

        Args:
            weights: Already-scaled protocol weights (e.g. from ``validate_order``).
        """
        if not weights:
            raise ValueError("Intent weights must not be empty")
        self.weights = {str(k): int(v) for k, v in weights.items()}

    def encrypt(self, pk_r: bytes | None = None) -> bytes:
        """Seal this intent to an OrionCiphertext blob.

        When ``pk_r`` is omitted, fetches ``OrionConfig.hpkePublicKey()`` onchain.

        Args:
            pk_r: Optional 32-byte X25519 recipient public key.

        Returns:
            OrionCiphertext bytes (``enc || ct``).
        """
        if pk_r is None:
            from .contracts import OrionConfig

            pk_r = OrionConfig().hpke_public_key

        tokens = list(self.weights.keys())
        values = list(self.weights.values())
        return seal_intent(tokens, values, pk_r)
