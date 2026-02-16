require("@nomicfoundation/hardhat-toolbox");

// No forking here: Ape's HardhatForkProvider passes --fork and --fork-block-number
// on the CLI. Defining forking in this file as well caused Hardhat to exit with code 1.
/** @type import('hardhat/config').HardhatUserConfig */
module.exports = {
  solidity: "0.8.24",
  networks: {
    hardhat: {
      hardfork: "shanghai",
      initialBaseFeePerGas: 0,
      // Web3 default call gas is 60M; node cap must be >= that.
      blockGasLimit: 80000000,
      gasLimit: 80000000,
      accounts: {
        mnemonic: "test test test test test test test test test test test junk",
        path: "m/44'/60'/0'/0",
        count: 10,
        accountsBalance: "10000000000000000000000",
      },
    },
  },
};
