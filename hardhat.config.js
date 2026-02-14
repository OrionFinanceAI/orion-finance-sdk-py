require("@nomicfoundation/hardhat-toolbox");
require("dotenv").config();

/** @type import('hardhat/config').HardhatUserConfig */
module.exports = {
  solidity: "0.8.28",
  networks: {
    hardhat: {
      hardfork: "shanghai",
      initialBaseFeePerGas: 0,
      blockGasLimit: 15000000,
      accounts: {
        mnemonic: "test test test test test test test test test test test junk",
        path: "m/44'/60'/0'/0",
        count: 10,
        accountsBalance: "10000000000000000000000",
      },
      forking: {
        url: process.env.ALCHEMY_API_KEY || "",
        enabled: true,
      },
    },
  },
};
