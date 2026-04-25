// Shared primitive types used by the ABI module.
// Mirrors viem's naming without depending on viem, so services can consume
// this package whether they use viem, ethers, web3, or a raw RPC client.

export type Address = `0x${string}`;
export type Hex = `0x${string}`;
export type Bytes32 = `0x${string}`;

export const HELIOS_CHAIN_NAMES = [
  "kite-testnet",
  "base-sepolia",
  "arbitrum-sepolia",
  "anvil",
] as const;
