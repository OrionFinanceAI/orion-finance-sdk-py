import orion_finance_sdk_py as sdk


def test_entry_points():
    assert sdk.__version__ is not None
    assert sdk.deploy_vault is not None
    assert sdk.submit_order is not None
