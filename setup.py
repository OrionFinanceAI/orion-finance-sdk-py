"""Setup script for the Orion Finance Python SDK."""

import os
import shutil
import urllib.request

from setuptools import find_packages, setup
from setuptools.command.build_py import build_py


class CustomBuild(build_py):
    """Download the Orion Finance contracts ABIs."""

    def run(self):
        """Run the build process."""
        self.download_abis()
        super().run()
        self.copy_abis_to_package()

    def download_abis(self):
        """Download the Orion Finance contracts ABIs."""
        abis = [
            "OrionConfig",
            "TransparentVaultFactory",
            "OrionTransparentVault",
            "LiquidityOrchestrator",
        ]
        os.makedirs("python/abis", exist_ok=True)

        base_url = (
            "https://github.com/OrionFinanceAI/protocol/releases/download/abis-v2.0.0"
        )

        for contract in abis:
            url = f"{base_url}/{contract}.json"
            dest = f"python/abis/{contract}.json"
            print(f"Downloading {contract} ABI...")
            urllib.request.urlretrieve(url, dest)

    def copy_abis_to_package(self):
        """Copy ABI files into the package directory for distribution."""
        package_dir = os.path.join(self.build_lib, "orion_finance_sdk_py")
        abis_dir = os.path.join(package_dir, "abis")
        os.makedirs(abis_dir, exist_ok=True)

        # Copy all ABI files to the package directory
        python_abis_dir = "python/abis"
        for abi_file in os.listdir(python_abis_dir):
            if abi_file.endswith(".json"):
                py_path = os.path.join(python_abis_dir, abi_file)
                dst_path = os.path.join(abis_dir, abi_file)
                shutil.copy2(py_path, dst_path)


setup(
    cmdclass={
        "build_py": CustomBuild,
    },
    packages=find_packages(where="python"),
    package_dir={"": "python"},
    include_package_data=True,
)
