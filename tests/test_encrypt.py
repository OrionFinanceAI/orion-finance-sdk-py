"""Tests for encryption."""

import json
from unittest.mock import patch

import pytest
from orion_finance_sdk_py.encrypt import check_npm_available, encrypt_order_intent


@patch("orion_finance_sdk_py.encrypt.subprocess.run")
def test_check_npm_available(mock_run):
    """Test npm check."""
    mock_run.return_value.returncode = 0
    assert check_npm_available()

    mock_run.return_value.returncode = 1
    assert not check_npm_available()

    mock_run.side_effect = FileNotFoundError
    assert not check_npm_available()


@patch("orion_finance_sdk_py.encrypt.subprocess.run")
@patch.dict(
    "os.environ",
    {"CURATOR_ADDRESS": "0xCurator", "ORION_VAULT_ADDRESS": "0xVault"},
)
def test_encrypt_order_intent(mock_run):
    """Test encryption logic."""
    # Mock npm check implicit via the first call in the function?
    # No, check_npm_available calls subprocess.run(["npm", ...])
    # The main logic calls subprocess.run(["node", ...])

    # We need to handle multiple calls to subprocess.run

    def side_effect(cmd, **kwargs):
        if cmd[0] == "npm":
            return type("Result", (), {"returncode": 0})()
        elif cmd[0] == "node":
            return type(
                "Result",
                (),
                {
                    "returncode": 0,
                    "stdout": json.dumps(
                        {
                            "encryptedValues": ["0xenc1", "0xenc2"],
                            "inputProof": "0xproof",
                        }
                    ),
                    "stderr": "",
                },
            )()
        return type("Result", (), {"returncode": 1})()

    mock_run.side_effect = side_effect

    order = {"0xA": 100, "0xB": 200}
    encrypted, proof = encrypt_order_intent(order)

    assert encrypted["0xA"] == "0xenc1"
    assert encrypted["0xB"] == "0xenc2"
    assert proof == "0xproof"


@patch("orion_finance_sdk_py.encrypt.check_npm_available", return_value=False)
def test_encrypt_no_npm(mock_check):
    """Test exit when npm missing."""
    with pytest.raises(SystemExit):
        encrypt_order_intent({})
