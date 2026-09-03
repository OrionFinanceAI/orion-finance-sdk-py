"""Orion HPKE (ORION_HPKE_V1) client seal/open helpers.

Implements RFC 9180 Base mode with DHKEM(X25519, HKDF-SHA256), HKDF-SHA256,
and AES-128-GCM. Ciphertext wire format is ``enc || ct`` (OrionCiphertext).
"""

from __future__ import annotations

import os
from typing import Sequence

from eth_abi import encode
from pyhpke import AEADId, CipherSuite, KDFId, KEMId, KEMKeyPair
from web3 import Web3

INFO_PORTFOLIO = b"ORION_PORTFOLIO_V1"
INFO_INTENT = b"ORION_INTENT_V1"
AAD = b""
_MIN_CIPHERTEXT_LEN = 48  # enc (32) + tag (16)
_PK_LEN = 32

_SUITE = CipherSuite.new(
    KEMId.DHKEM_X25519_HKDF_SHA256,
    KDFId.HKDF_SHA256,
    AEADId.AES128_GCM,
)


def _require_pk_r(pk_r: bytes) -> bytes:
    if not isinstance(pk_r, (bytes, bytearray)) or len(pk_r) != _PK_LEN:
        raise ValueError(f"pkR must be exactly {_PK_LEN} raw bytes")
    return bytes(pk_r)


def _checksum_addresses(tokens: Sequence[str]) -> list[str]:
    return [Web3.to_checksum_address(t) for t in tokens]


def encode_intent_plaintext(tokens: Sequence[str], weights: Sequence[int]) -> bytes:
    """ABI-encode intent plaintext as ``abi.encode(address[], uint32[])``."""
    if len(tokens) != len(weights):
        raise ValueError("tokens and weights must have the same length")
    return encode(
        ["address[]", "uint32[]"],
        [_checksum_addresses(tokens), [int(w) for w in weights]],
    )


def encode_portfolio_plaintext(tokens: Sequence[str], shares: Sequence[int]) -> bytes:
    """ABI-encode portfolio plaintext as ``abi.encode(address[], uint256[])``."""
    if len(tokens) != len(shares):
        raise ValueError("tokens and shares must have the same length")
    return encode(
        ["address[]", "uint256[]"],
        [_checksum_addresses(tokens), [int(s) for s in shares]],
    )


def _seal(pt: bytes, pk_r: bytes, info: bytes, eks: KEMKeyPair | None = None) -> bytes:
    pk = _SUITE.kem.deserialize_public_key(_require_pk_r(pk_r))
    if eks is None:
        eks = _SUITE.kem.derive_key_pair(os.urandom(32))
    enc, sender = _SUITE.create_sender_context(pk, info=info, eks=eks)
    ct = sender.seal(pt, aad=AAD)
    return enc + ct


def seal_intent(
    tokens: Sequence[str],
    weights: Sequence[int],
    pk_r: bytes,
    *,
    ikm_e: bytes | None = None,
) -> bytes:
    """Seal an intent to an OrionCiphertext blob (``ORION_INTENT_V1``).

    Args:
        tokens: Token addresses.
        weights: ``uint32`` scaled weights (same length as tokens).
        pk_r: Recipient X25519 public key (32 raw bytes).
        ikm_e: Optional test-only ephemeral IKM for ``DeriveKeyPair`` (fixed enc).
    """
    pt = encode_intent_plaintext(tokens, weights)
    eks = _SUITE.kem.derive_key_pair(ikm_e) if ikm_e is not None else None
    return _seal(pt, pk_r, INFO_INTENT, eks=eks)


def seal_portfolio(
    tokens: Sequence[str],
    shares: Sequence[int],
    pk_r: bytes,
    *,
    ikm_e: bytes | None = None,
) -> bytes:
    """Seal a portfolio to an OrionCiphertext blob (``ORION_PORTFOLIO_V1``).

    Args:
        tokens: Token addresses.
        shares: ``uint256`` share amounts (same length as tokens).
        pk_r: Recipient X25519 public key (32 raw bytes).
        ikm_e: Optional test-only ephemeral IKM for ``DeriveKeyPair`` (fixed enc).
    """
    pt = encode_portfolio_plaintext(tokens, shares)
    eks = _SUITE.kem.derive_key_pair(ikm_e) if ikm_e is not None else None
    return _seal(pt, pk_r, INFO_PORTFOLIO, eks=eks)


def open_orion_ciphertext(blob: bytes, sk_r: bytes, info: bytes) -> bytes:
    """Open an OrionCiphertext (``enc || ct``) with Base mode and empty AAD.

    Args:
        blob: Full OrionCiphertext bytes.
        sk_r: Recipient X25519 private key (32 raw bytes).
        info: HPKE info label (``ORION_INTENT_V1`` or ``ORION_PORTFOLIO_V1``).

    Returns:
        Decrypted plaintext bytes.
    """
    if len(blob) < _MIN_CIPHERTEXT_LEN:
        raise ValueError(
            f"OrionCiphertext must be at least {_MIN_CIPHERTEXT_LEN} bytes"
        )
    if len(sk_r) != _PK_LEN:
        raise ValueError(f"skR must be exactly {_PK_LEN} raw bytes")

    enc, ct = blob[:32], blob[32:]
    skr = _SUITE.kem.deserialize_private_key(sk_r)
    recipient = _SUITE.create_recipient_context(enc, skr, info=info)
    return recipient.open(ct, aad=AAD)
