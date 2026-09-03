"""Tests for Orion HPKE (ORION_HPKE_V1) conformance vectors and Intent.encrypt."""

from unittest.mock import MagicMock, patch

import pytest
from orion_finance_sdk_py.hpke import (
    INFO_INTENT,
    INFO_PORTFOLIO,
    encode_intent_plaintext,
    encode_portfolio_plaintext,
    open_orion_ciphertext,
    seal_intent,
    seal_portfolio,
)
from orion_finance_sdk_py.intent import Intent
from pyhpke import OpenError

# §17.1 / §17.2
SK_R = bytes.fromhex("91f7a467df4ef97053ec2a47b6e619f632df9547bb009fd0bcc747909f1b7bd4")
PK_R = bytes.fromhex("b1f1b840de7a3241b02748cf9b05b74dc8c5e8451298738817bd76aa8ebe8c2b")
IKM_E = bytes.fromhex(
    "202122232425262728292a2b2c2d2e2f303132333435363738393a3b3c3d3e3f"
)

TOKENS = [
    "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
    "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
]
SHARES = [1_000_000, 500_000_000_000_000_000]
WEIGHTS = [6000, 4000]

PORTFOLIO_PT = bytes.fromhex(
    "0000000000000000000000000000000000000000000000000000000000000040"
    "00000000000000000000000000000000000000000000000000000000000000a0"
    "0000000000000000000000000000000000000000000000000000000000000002"
    "000000000000000000000000a0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"
    "000000000000000000000000c02aaa39b223fe8d0a0e5c4f27ead9083c756cc2"
    "0000000000000000000000000000000000000000000000000000000000000002"
    "00000000000000000000000000000000000000000000000000000000000f4240"
    "00000000000000000000000000000000000000000000000006f05b59d3b20000"
)

INTENT_PT = bytes.fromhex(
    "0000000000000000000000000000000000000000000000000000000000000040"
    "00000000000000000000000000000000000000000000000000000000000000a0"
    "0000000000000000000000000000000000000000000000000000000000000002"
    "000000000000000000000000a0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"
    "000000000000000000000000c02aaa39b223fe8d0a0e5c4f27ead9083c756cc2"
    "0000000000000000000000000000000000000000000000000000000000000002"
    "0000000000000000000000000000000000000000000000000000000000001770"
    "0000000000000000000000000000000000000000000000000000000000000fa0"
)

PORTFOLIO_BLOB = bytes.fromhex(
    "693658254630f73ad8da78fb331bf976cd42f90e0e9c9e83f40c51072a6f7417"
    "5129dc2b2cfec1d37c1860aa2b0834adc013f120e6ad01e87d272f6dc7038067"
    "c905f4356ea0ae528aae945d50b91385ebcc42a5b164d2c06297ee9220713f5e"
    "2141919eab26d25b6b31ae6325e54c3ec67a1ec0a7cc524907b8a5a4f437d538"
    "a9433353d6c796d027e0843dd12b1d0ac919fb2504d4adcd41fe7f68882e29ff"
    "b5e9180839a4ed7ad99c9cc76e538fb0524dce4bbd0593eb77182c91714269e5"
    "db3b27f1177b31ce3fca0218c64bab75c0fc53bcd75a32b94e2984f6ac544719"
    "897be8cdb0829d5122ca298360e1014e830501eaffd3513c656d991a4de4ee61"
    "1c00590e5631f8c9d626d2130063e7adb3cba4ee226ba44b20acb9f0a0167aa1"
    "87d8c998e01e7b89de51921f7d87543d"
)

INTENT_BLOB = bytes.fromhex(
    "693658254630f73ad8da78fb331bf976cd42f90e0e9c9e83f40c51072a6f7417"
    "bdb98ee21c5fbd63b638e332a609dad2c433b7dddcadec1f43586b8df178c488"
    "01bc357ad2b6b530cfd9d63a8da1e0506ad748b7445373c5028131d0133fd563"
    "172331decd5b2c69027a78699d713bb7426278f5cfa7754cb9e608f8cac946bf"
    "f38dd79d43391007eb7e87cca2a60b9e8ba869ae6dcdeb9289a09fa9748fc6a7"
    "57160df5b25eb1fab133b18d11865a12f04a6ba70fa9a7f6c1dcf32fdffcabda"
    "cd028fb3317650842264ba14ba30388f115b39266ce51c51f0d17c40776da974"
    "a9981d8f622a44fe2c905be117a8d6a9c2cb51e787d6b27a7676bf6ccb89fa31"
    "e3b8d9b4c24e887030a7caf503ba52d1d44510f73f5e7d30a396b4662a408d50"
    "0fb451c883075e39b4c6d64ccdbd89be"
)


def test_encode_portfolio_plaintext_matches_spec():
    """§17.3 ABI encoding."""
    assert encode_portfolio_plaintext(TOKENS, SHARES) == PORTFOLIO_PT


def test_encode_intent_plaintext_matches_spec():
    """§17.4 ABI encoding."""
    assert encode_intent_plaintext(TOKENS, WEIGHTS) == INTENT_PT


def test_open_portfolio_blob_recovers_plaintext():
    """§17.3 OpenBase recovers portfolio plaintext."""
    pt = open_orion_ciphertext(PORTFOLIO_BLOB, SK_R, INFO_PORTFOLIO)
    assert pt == PORTFOLIO_PT


def test_open_intent_blob_recovers_plaintext():
    """§17.4 OpenBase recovers intent plaintext."""
    pt = open_orion_ciphertext(INTENT_BLOB, SK_R, INFO_INTENT)
    assert pt == INTENT_PT


def test_fixed_ikm_seal_matches_portfolio_blob():
    """§17.3 fixed-ephemeral seal matches published portfolio_blob."""
    blob = seal_portfolio(TOKENS, SHARES, PK_R, ikm_e=IKM_E)
    assert blob == PORTFOLIO_BLOB


def test_fixed_ikm_seal_matches_intent_blob():
    """§17.4 fixed-ephemeral seal matches published intent_blob."""
    blob = seal_intent(TOKENS, WEIGHTS, PK_R, ikm_e=IKM_E)
    assert blob == INTENT_BLOB


def test_random_seal_intent_roundtrip():
    """Production seal (CSPRNG IKM) round-trips via OpenBase."""
    blob = seal_intent(TOKENS, WEIGHTS, PK_R)
    assert len(blob) >= 48
    assert open_orion_ciphertext(blob, SK_R, INFO_INTENT) == INTENT_PT


def test_reject_truncated_blob():
    """§17.6 truncated blob rejected before open."""
    with pytest.raises(ValueError, match="at least 48"):
        open_orion_ciphertext(INTENT_BLOB[:47], SK_R, INFO_INTENT)


def test_reject_wrong_info():
    """§17.6 wrong info fails closed."""
    with pytest.raises(OpenError):
        open_orion_ciphertext(INTENT_BLOB, SK_R, b"ORION_INTENT_V2")


def test_reject_cross_type_open():
    """§17.6 cross-type open fails closed."""
    with pytest.raises(OpenError):
        open_orion_ciphertext(PORTFOLIO_BLOB, SK_R, INFO_INTENT)
    with pytest.raises(OpenError):
        open_orion_ciphertext(INTENT_BLOB, SK_R, INFO_PORTFOLIO)


def test_reject_flipped_bit():
    """§17.6 flipped ciphertext bit fails closed."""
    tampered = bytearray(PORTFOLIO_BLOB)
    tampered[40] ^= 0x01
    with pytest.raises(OpenError):
        open_orion_ciphertext(bytes(tampered), SK_R, INFO_PORTFOLIO)


def test_reject_bad_pk_r():
    """pkR length must be 32."""
    with pytest.raises(ValueError, match="32"):
        seal_intent(TOKENS, WEIGHTS, b"\x00" * 31)


def test_intent_encrypt_with_explicit_pk():
    """Intent.encrypt seals and opens with provided pkR."""
    intent = Intent(dict(zip(TOKENS, WEIGHTS, strict=True)))
    blob = intent.encrypt(pk_r=PK_R)
    assert open_orion_ciphertext(blob, SK_R, INFO_INTENT) == INTENT_PT


@patch("orion_finance_sdk_py.contracts.OrionConfig")
def test_intent_encrypt_fetches_onchain_pk(MockConfig):
    """Intent.encrypt fetches OrionConfig.hpke_public_key when pk_r omitted."""
    mock_config = MagicMock()
    mock_config.hpke_public_key = PK_R
    MockConfig.return_value = mock_config

    intent = Intent(dict(zip(TOKENS, WEIGHTS, strict=True)))
    blob = intent.encrypt()
    MockConfig.assert_called_once()
    assert open_orion_ciphertext(blob, SK_R, INFO_INTENT) == INTENT_PT


def test_intent_rejects_empty_weights():
    """Empty intent is rejected."""
    with pytest.raises(ValueError, match="empty"):
        Intent({})


def test_encode_intent_length_mismatch():
    with pytest.raises(ValueError, match="same length"):
        encode_intent_plaintext(TOKENS, [1])


def test_encode_portfolio_length_mismatch():
    with pytest.raises(ValueError, match="same length"):
        encode_portfolio_plaintext(TOKENS, [1])


def test_open_rejects_sk_r_wrong_length():
    with pytest.raises(ValueError, match="skR must be exactly"):
        open_orion_ciphertext(INTENT_BLOB, SK_R[:31], INFO_INTENT)
