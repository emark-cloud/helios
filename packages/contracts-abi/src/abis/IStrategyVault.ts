// Auto-generated. Do not edit.
// Source: contracts/out/IStrategyVault.sol/IStrategyVault.json

export const IStrategyVaultAbi = [
  {
    "type": "function",
    "name": "allocateFrom",
    "inputs": [
      {
        "name": "amount",
        "type": "uint256",
        "internalType": "uint256"
      }
    ],
    "outputs": [],
    "stateMutability": "nonpayable"
  },
  {
    "type": "function",
    "name": "allocationOf",
    "inputs": [
      {
        "name": "allocator",
        "type": "address",
        "internalType": "address"
      }
    ],
    "outputs": [
      {
        "name": "",
        "type": "uint256",
        "internalType": "uint256"
      }
    ],
    "stateMutability": "view"
  },
  {
    "type": "function",
    "name": "distributeRealized",
    "inputs": [
      {
        "name": "allocator",
        "type": "address",
        "internalType": "address"
      }
    ],
    "outputs": [],
    "stateMutability": "nonpayable"
  },
  {
    "type": "function",
    "name": "executeWithProof",
    "inputs": [
      {
        "name": "proof",
        "type": "bytes",
        "internalType": "bytes"
      },
      {
        "name": "publicInputs",
        "type": "uint256[]",
        "internalType": "uint256[]"
      },
      {
        "name": "trades",
        "type": "tuple[]",
        "internalType": "struct IStrategyVault.Call[]",
        "components": [
          {
            "name": "target",
            "type": "address",
            "internalType": "address"
          },
          {
            "name": "value",
            "type": "uint256",
            "internalType": "uint256"
          },
          {
            "name": "data",
            "type": "bytes",
            "internalType": "bytes"
          }
        ]
      }
    ],
    "outputs": [],
    "stateMutability": "nonpayable"
  },
  {
    "type": "function",
    "name": "executeYieldRotationWithProof",
    "inputs": [
      {
        "name": "proof",
        "type": "bytes",
        "internalType": "bytes"
      },
      {
        "name": "publicInputs",
        "type": "uint256[]",
        "internalType": "uint256[]"
      },
      {
        "name": "trades",
        "type": "tuple[]",
        "internalType": "struct IStrategyVault.Call[]",
        "components": [
          {
            "name": "target",
            "type": "address",
            "internalType": "address"
          },
          {
            "name": "value",
            "type": "uint256",
            "internalType": "uint256"
          },
          {
            "name": "data",
            "type": "bytes",
            "internalType": "bytes"
          }
        ]
      }
    ],
    "outputs": [],
    "stateMutability": "nonpayable"
  },
  {
    "type": "function",
    "name": "manifest",
    "inputs": [],
    "outputs": [
      {
        "name": "",
        "type": "tuple",
        "internalType": "struct IStrategyVault.StrategyManifest",
        "components": [
          {
            "name": "declaredClass",
            "type": "bytes32",
            "internalType": "bytes32"
          },
          {
            "name": "assetUniverse",
            "type": "address[]",
            "internalType": "address[]"
          },
          {
            "name": "maxCapacity",
            "type": "uint256",
            "internalType": "uint256"
          },
          {
            "name": "feeRateBps",
            "type": "uint16",
            "internalType": "uint16"
          },
          {
            "name": "operator",
            "type": "address",
            "internalType": "address"
          },
          {
            "name": "stakeAmount",
            "type": "uint256",
            "internalType": "uint256"
          },
          {
            "name": "paramsHash",
            "type": "bytes32",
            "internalType": "bytes32"
          }
        ]
      }
    ],
    "stateMutability": "view"
  },
  {
    "type": "function",
    "name": "navDigest",
    "inputs": [
      {
        "name": "totalNAV_",
        "type": "uint256",
        "internalType": "uint256"
      },
      {
        "name": "timestamp",
        "type": "uint64",
        "internalType": "uint64"
      }
    ],
    "outputs": [
      {
        "name": "",
        "type": "bytes32",
        "internalType": "bytes32"
      }
    ],
    "stateMutability": "view"
  },
  {
    "type": "function",
    "name": "navOf",
    "inputs": [
      {
        "name": "allocator",
        "type": "address",
        "internalType": "address"
      }
    ],
    "outputs": [
      {
        "name": "",
        "type": "uint256",
        "internalType": "uint256"
      }
    ],
    "stateMutability": "view"
  },
  {
    "type": "function",
    "name": "priceAnchor",
    "inputs": [],
    "outputs": [
      {
        "name": "",
        "type": "address",
        "internalType": "address"
      }
    ],
    "stateMutability": "view"
  },
  {
    "type": "function",
    "name": "reportNAV",
    "inputs": [
      {
        "name": "signedNAV",
        "type": "bytes",
        "internalType": "bytes"
      }
    ],
    "outputs": [],
    "stateMutability": "nonpayable"
  },
  {
    "type": "function",
    "name": "slash",
    "inputs": [
      {
        "name": "reason",
        "type": "string",
        "internalType": "string"
      }
    ],
    "outputs": [],
    "stateMutability": "nonpayable"
  },
  {
    "type": "function",
    "name": "totalNAV",
    "inputs": [],
    "outputs": [
      {
        "name": "",
        "type": "uint256",
        "internalType": "uint256"
      }
    ],
    "stateMutability": "view"
  },
  {
    "type": "function",
    "name": "withdrawToAllocator",
    "inputs": [
      {
        "name": "allocator",
        "type": "address",
        "internalType": "address"
      },
      {
        "name": "amount",
        "type": "uint256",
        "internalType": "uint256"
      }
    ],
    "outputs": [],
    "stateMutability": "nonpayable"
  },
  {
    "type": "function",
    "name": "yieldAnchor",
    "inputs": [],
    "outputs": [
      {
        "name": "",
        "type": "address",
        "internalType": "address"
      }
    ],
    "stateMutability": "view"
  },
  {
    "type": "event",
    "name": "CrossChainAttestationQueued",
    "inputs": [
      {
        "name": "strategy",
        "type": "address",
        "indexed": true,
        "internalType": "address"
      },
      {
        "name": "oApp",
        "type": "address",
        "indexed": true,
        "internalType": "address"
      },
      {
        "name": "tradeHash",
        "type": "bytes32",
        "indexed": true,
        "internalType": "bytes32"
      }
    ],
    "anonymous": false
  },
  {
    "type": "event",
    "name": "HeliosOAppUpdated",
    "inputs": [
      {
        "name": "previous",
        "type": "address",
        "indexed": true,
        "internalType": "address"
      },
      {
        "name": "current",
        "type": "address",
        "indexed": true,
        "internalType": "address"
      }
    ],
    "anonymous": false
  },
  {
    "type": "event",
    "name": "NAVReported",
    "inputs": [
      {
        "name": "strategy",
        "type": "address",
        "indexed": true,
        "internalType": "address"
      },
      {
        "name": "totalNAV",
        "type": "uint256",
        "indexed": false,
        "internalType": "uint256"
      },
      {
        "name": "timestamp",
        "type": "uint64",
        "indexed": false,
        "internalType": "uint64"
      }
    ],
    "anonymous": false
  },
  {
    "type": "event",
    "name": "NavClampedOnWithdraw",
    "inputs": [
      {
        "name": "strategy",
        "type": "address",
        "indexed": true,
        "internalType": "address"
      },
      {
        "name": "allocator",
        "type": "address",
        "indexed": true,
        "internalType": "address"
      },
      {
        "name": "priorTotalNAV",
        "type": "uint256",
        "indexed": false,
        "internalType": "uint256"
      },
      {
        "name": "withdrawAmount",
        "type": "uint256",
        "indexed": false,
        "internalType": "uint256"
      }
    ],
    "anonymous": false
  },
  {
    "type": "event",
    "name": "NavDivergenceObserved",
    "inputs": [
      {
        "name": "strategy",
        "type": "address",
        "indexed": true,
        "internalType": "address"
      },
      {
        "name": "signedNAV",
        "type": "uint256",
        "indexed": false,
        "internalType": "uint256"
      },
      {
        "name": "markedFloor",
        "type": "uint256",
        "indexed": false,
        "internalType": "uint256"
      },
      {
        "name": "snapshotNonce",
        "type": "uint64",
        "indexed": false,
        "internalType": "uint64"
      }
    ],
    "anonymous": false
  },
  {
    "type": "event",
    "name": "NavDivergenceThresholdUpdated",
    "inputs": [
      {
        "name": "previous",
        "type": "uint16",
        "indexed": false,
        "internalType": "uint16"
      },
      {
        "name": "next",
        "type": "uint16",
        "indexed": false,
        "internalType": "uint16"
      }
    ],
    "anonymous": false
  },
  {
    "type": "event",
    "name": "OrphanedAllocationRecovered",
    "inputs": [
      {
        "name": "strategy",
        "type": "address",
        "indexed": true,
        "internalType": "address"
      },
      {
        "name": "to",
        "type": "address",
        "indexed": true,
        "internalType": "address"
      },
      {
        "name": "amount",
        "type": "uint256",
        "indexed": false,
        "internalType": "uint256"
      }
    ],
    "anonymous": false
  },
  {
    "type": "event",
    "name": "RealizedDistributed",
    "inputs": [
      {
        "name": "strategy",
        "type": "address",
        "indexed": true,
        "internalType": "address"
      },
      {
        "name": "allocator",
        "type": "address",
        "indexed": true,
        "internalType": "address"
      },
      {
        "name": "amount",
        "type": "uint256",
        "indexed": false,
        "internalType": "uint256"
      }
    ],
    "anonymous": false
  },
  {
    "type": "event",
    "name": "RegistryUpdated",
    "inputs": [
      {
        "name": "previous",
        "type": "address",
        "indexed": true,
        "internalType": "address"
      },
      {
        "name": "next",
        "type": "address",
        "indexed": true,
        "internalType": "address"
      }
    ],
    "anonymous": false
  },
  {
    "type": "event",
    "name": "Slashed",
    "inputs": [
      {
        "name": "strategy",
        "type": "address",
        "indexed": true,
        "internalType": "address"
      },
      {
        "name": "amount",
        "type": "uint256",
        "indexed": false,
        "internalType": "uint256"
      },
      {
        "name": "reason",
        "type": "string",
        "indexed": false,
        "internalType": "string"
      }
    ],
    "anonymous": false
  },
  {
    "type": "event",
    "name": "StrandedNAVRecovered",
    "inputs": [
      {
        "name": "strategy",
        "type": "address",
        "indexed": true,
        "internalType": "address"
      },
      {
        "name": "to",
        "type": "address",
        "indexed": true,
        "internalType": "address"
      },
      {
        "name": "amount",
        "type": "uint256",
        "indexed": false,
        "internalType": "uint256"
      }
    ],
    "anonymous": false
  },
  {
    "type": "event",
    "name": "TradeAttested",
    "inputs": [
      {
        "name": "strategy",
        "type": "address",
        "indexed": true,
        "internalType": "address"
      },
      {
        "name": "allocator",
        "type": "address",
        "indexed": true,
        "internalType": "address"
      },
      {
        "name": "tradeHash",
        "type": "bytes32",
        "indexed": true,
        "internalType": "bytes32"
      },
      {
        "name": "declaredClass",
        "type": "bytes32",
        "indexed": false,
        "internalType": "bytes32"
      },
      {
        "name": "assetIn",
        "type": "address",
        "indexed": false,
        "internalType": "address"
      },
      {
        "name": "assetOut",
        "type": "address",
        "indexed": false,
        "internalType": "address"
      },
      {
        "name": "amountIn",
        "type": "uint256",
        "indexed": false,
        "internalType": "uint256"
      },
      {
        "name": "minAmountOut",
        "type": "uint256",
        "indexed": false,
        "internalType": "uint256"
      },
      {
        "name": "direction",
        "type": "uint8",
        "indexed": false,
        "internalType": "uint8"
      },
      {
        "name": "blockWindowStart",
        "type": "uint64",
        "indexed": false,
        "internalType": "uint64"
      },
      {
        "name": "blockWindowEnd",
        "type": "uint64",
        "indexed": false,
        "internalType": "uint64"
      }
    ],
    "anonymous": false
  },
  {
    "type": "event",
    "name": "YieldRotationAttested",
    "inputs": [
      {
        "name": "strategy",
        "type": "address",
        "indexed": true,
        "internalType": "address"
      },
      {
        "name": "allocator",
        "type": "address",
        "indexed": true,
        "internalType": "address"
      },
      {
        "name": "tradeHash",
        "type": "bytes32",
        "indexed": true,
        "internalType": "bytes32"
      },
      {
        "name": "declaredClass",
        "type": "bytes32",
        "indexed": false,
        "internalType": "bytes32"
      },
      {
        "name": "mFrom",
        "type": "uint256",
        "indexed": false,
        "internalType": "uint256"
      },
      {
        "name": "mTo",
        "type": "uint256",
        "indexed": false,
        "internalType": "uint256"
      },
      {
        "name": "amountRotating",
        "type": "uint256",
        "indexed": false,
        "internalType": "uint256"
      },
      {
        "name": "yieldOracleRoot",
        "type": "bytes32",
        "indexed": false,
        "internalType": "bytes32"
      },
      {
        "name": "blockWindowStart",
        "type": "uint64",
        "indexed": false,
        "internalType": "uint64"
      },
      {
        "name": "blockWindowEnd",
        "type": "uint64",
        "indexed": false,
        "internalType": "uint64"
      }
    ],
    "anonymous": false
  },
  {
    "type": "error",
    "name": "AllocatorMismatch",
    "inputs": []
  },
  {
    "type": "error",
    "name": "ApproveAmountMismatch",
    "inputs": []
  },
  {
    "type": "error",
    "name": "ApproveSpenderMismatch",
    "inputs": []
  },
  {
    "type": "error",
    "name": "CapacityExceeded",
    "inputs": []
  },
  {
    "type": "error",
    "name": "ClassMismatch",
    "inputs": []
  },
  {
    "type": "error",
    "name": "InvalidProof",
    "inputs": []
  },
  {
    "type": "error",
    "name": "NotOperator",
    "inputs": []
  },
  {
    "type": "error",
    "name": "NotRegistry",
    "inputs": []
  },
  {
    "type": "error",
    "name": "ParamsHashMismatch",
    "inputs": []
  },
  {
    "type": "error",
    "name": "SwapAmountInMismatch",
    "inputs": []
  },
  {
    "type": "error",
    "name": "SwapMinOutMismatch",
    "inputs": []
  },
  {
    "type": "error",
    "name": "SwapRecipientMismatch",
    "inputs": []
  },
  {
    "type": "error",
    "name": "SwapTokenInMismatch",
    "inputs": []
  },
  {
    "type": "error",
    "name": "SwapTokenOutMismatch",
    "inputs": []
  },
  {
    "type": "error",
    "name": "TradeCallSelectorNotAllowed",
    "inputs": []
  },
  {
    "type": "error",
    "name": "VaultMismatch",
    "inputs": []
  },
  {
    "type": "error",
    "name": "YRTradesNotSupported",
    "inputs": []
  }
] as const;
