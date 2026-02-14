from ape import networks


def test_fork_connection():
    with networks.ethereum.sepolia_fork.use_provider("foundry"):
        block_number = networks.active_provider.get_block("latest").number
        assert block_number > 0
        print(f"Connected to sepolia fork at block {block_number}")
