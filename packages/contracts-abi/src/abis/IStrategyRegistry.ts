// Auto-generated. Do not edit.
// Source: contracts/out/IStrategyRegistry.sol/IStrategyRegistry.json

export const IStrategyRegistryAbi = [
  {
    "type": "function",
    "name": "commitInitialParamsHash",
    "inputs": [
      {
        "name": "strategyId",
        "type": "address",
        "internalType": "address"
      },
      {
        "name": "paramsHash",
        "type": "bytes32",
        "internalType": "bytes32"
      }
    ],
    "outputs": [],
    "stateMutability": "nonpayable"
  },
  {
    "type": "function",
    "name": "completeParamsRotation",
    "inputs": [
      {
        "name": "strategyId",
        "type": "address",
        "internalType": "address"
      }
    ],
    "outputs": [],
    "stateMutability": "nonpayable"
  },
  {
    "type": "function",
    "name": "completeStakeWithdrawal",
    "inputs": [
      {
        "name": "strategyId",
        "type": "address",
        "internalType": "address"
      }
    ],
    "outputs": [],
    "stateMutability": "nonpayable"
  },
  {
    "type": "function",
    "name": "deactivate",
    "inputs": [
      {
        "name": "strategyId",
        "type": "address",
        "internalType": "address"
      }
    ],
    "outputs": [],
    "stateMutability": "nonpayable"
  },
  {
    "type": "function",
    "name": "initiateParamsRotation",
    "inputs": [
      {
        "name": "strategyId",
        "type": "address",
        "internalType": "address"
      },
      {
        "name": "newParamsHash",
        "type": "bytes32",
        "internalType": "bytes32"
      }
    ],
    "outputs": [],
    "stateMutability": "nonpayable"
  },
  {
    "type": "function",
    "name": "initiateStakeWithdrawal",
    "inputs": [
      {
        "name": "strategyId",
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
    "name": "marketAllowlistRoot",
    "inputs": [
      {
        "name": "declaredClass",
        "type": "bytes32",
        "internalType": "bytes32"
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
    "name": "paramsHashOf",
    "inputs": [
      {
        "name": "strategyId",
        "type": "address",
        "internalType": "address"
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
    "name": "pendingParamsHashOf",
    "inputs": [
      {
        "name": "strategyId",
        "type": "address",
        "internalType": "address"
      }
    ],
    "outputs": [
      {
        "name": "newHash",
        "type": "bytes32",
        "internalType": "bytes32"
      },
      {
        "name": "unlockAt",
        "type": "uint64",
        "internalType": "uint64"
      }
    ],
    "stateMutability": "view"
  },
  {
    "type": "function",
    "name": "registerStrategy",
    "inputs": [
      {
        "name": "vault",
        "type": "address",
        "internalType": "address"
      },
      {
        "name": "declaredClass",
        "type": "bytes32",
        "internalType": "bytes32"
      },
      {
        "name": "stakeAmount",
        "type": "uint256",
        "internalType": "uint256"
      }
    ],
    "outputs": [
      {
        "name": "strategyId",
        "type": "address",
        "internalType": "address"
      }
    ],
    "stateMutability": "nonpayable"
  },
  {
    "type": "function",
    "name": "setMarketAllowlistRoot",
    "inputs": [
      {
        "name": "declaredClass",
        "type": "bytes32",
        "internalType": "bytes32"
      },
      {
        "name": "root",
        "type": "bytes32",
        "internalType": "bytes32"
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
        "name": "strategyId",
        "type": "address",
        "internalType": "address"
      },
      {
        "name": "amount",
        "type": "uint256",
        "internalType": "uint256"
      },
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
    "name": "strategiesByClass",
    "inputs": [
      {
        "name": "declaredClass",
        "type": "bytes32",
        "internalType": "bytes32"
      }
    ],
    "outputs": [
      {
        "name": "",
        "type": "address[]",
        "internalType": "address[]"
      }
    ],
    "stateMutability": "view"
  },
  {
    "type": "function",
    "name": "strategyOf",
    "inputs": [
      {
        "name": "strategyId",
        "type": "address",
        "internalType": "address"
      }
    ],
    "outputs": [
      {
        "name": "",
        "type": "tuple",
        "internalType": "struct IStrategyRegistry.StrategyEntry",
        "components": [
          {
            "name": "vault",
            "type": "address",
            "internalType": "address"
          },
          {
            "name": "operator",
            "type": "address",
            "internalType": "address"
          },
          {
            "name": "declaredClass",
            "type": "bytes32",
            "internalType": "bytes32"
          },
          {
            "name": "stakeAmount",
            "type": "uint256",
            "internalType": "uint256"
          },
          {
            "name": "currentReputation",
            "type": "int256",
            "internalType": "int256"
          },
          {
            "name": "registeredAt",
            "type": "uint64",
            "internalType": "uint64"
          },
          {
            "name": "active",
            "type": "bool",
            "internalType": "bool"
          }
        ]
      }
    ],
    "stateMutability": "view"
  },
  {
    "type": "function",
    "name": "topUpStake",
    "inputs": [
      {
        "name": "strategyId",
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
    "name": "updateReputation",
    "inputs": [
      {
        "name": "strategyId",
        "type": "address",
        "internalType": "address"
      },
      {
        "name": "delta",
        "type": "int256",
        "internalType": "int256"
      }
    ],
    "outputs": [],
    "stateMutability": "nonpayable"
  },
  {
    "type": "event",
    "name": "MarketAllowlistRootSet",
    "inputs": [
      {
        "name": "declaredClass",
        "type": "bytes32",
        "indexed": true,
        "internalType": "bytes32"
      },
      {
        "name": "root",
        "type": "bytes32",
        "indexed": false,
        "internalType": "bytes32"
      }
    ],
    "anonymous": false
  },
  {
    "type": "event",
    "name": "ParamsHashCommitted",
    "inputs": [
      {
        "name": "strategyId",
        "type": "address",
        "indexed": true,
        "internalType": "address"
      },
      {
        "name": "paramsHash",
        "type": "bytes32",
        "indexed": false,
        "internalType": "bytes32"
      }
    ],
    "anonymous": false
  },
  {
    "type": "event",
    "name": "ParamsRotated",
    "inputs": [
      {
        "name": "strategyId",
        "type": "address",
        "indexed": true,
        "internalType": "address"
      },
      {
        "name": "oldHash",
        "type": "bytes32",
        "indexed": false,
        "internalType": "bytes32"
      },
      {
        "name": "newHash",
        "type": "bytes32",
        "indexed": false,
        "internalType": "bytes32"
      }
    ],
    "anonymous": false
  },
  {
    "type": "event",
    "name": "ParamsRotationCancelled",
    "inputs": [
      {
        "name": "strategyId",
        "type": "address",
        "indexed": true,
        "internalType": "address"
      },
      {
        "name": "cancelledNewHash",
        "type": "bytes32",
        "indexed": false,
        "internalType": "bytes32"
      }
    ],
    "anonymous": false
  },
  {
    "type": "event",
    "name": "ParamsRotationInitiated",
    "inputs": [
      {
        "name": "strategyId",
        "type": "address",
        "indexed": true,
        "internalType": "address"
      },
      {
        "name": "oldHash",
        "type": "bytes32",
        "indexed": false,
        "internalType": "bytes32"
      },
      {
        "name": "newHash",
        "type": "bytes32",
        "indexed": false,
        "internalType": "bytes32"
      },
      {
        "name": "unlockAt",
        "type": "uint64",
        "indexed": false,
        "internalType": "uint64"
      }
    ],
    "anonymous": false
  },
  {
    "type": "event",
    "name": "ReputationUpdated",
    "inputs": [
      {
        "name": "strategyId",
        "type": "address",
        "indexed": true,
        "internalType": "address"
      },
      {
        "name": "delta",
        "type": "int256",
        "indexed": false,
        "internalType": "int256"
      },
      {
        "name": "newScore",
        "type": "int256",
        "indexed": false,
        "internalType": "int256"
      }
    ],
    "anonymous": false
  },
  {
    "type": "event",
    "name": "StakeToppedUp",
    "inputs": [
      {
        "name": "strategyId",
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
    "name": "StakeWithdrawalInitiated",
    "inputs": [
      {
        "name": "strategyId",
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
        "name": "unlockAt",
        "type": "uint64",
        "indexed": false,
        "internalType": "uint64"
      }
    ],
    "anonymous": false
  },
  {
    "type": "event",
    "name": "StakeWithdrawn",
    "inputs": [
      {
        "name": "strategyId",
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
    "name": "StrategyDeactivated",
    "inputs": [
      {
        "name": "strategyId",
        "type": "address",
        "indexed": true,
        "internalType": "address"
      }
    ],
    "anonymous": false
  },
  {
    "type": "event",
    "name": "StrategyRegistered",
    "inputs": [
      {
        "name": "strategyId",
        "type": "address",
        "indexed": true,
        "internalType": "address"
      },
      {
        "name": "vault",
        "type": "address",
        "indexed": true,
        "internalType": "address"
      },
      {
        "name": "operator",
        "type": "address",
        "indexed": true,
        "internalType": "address"
      },
      {
        "name": "declaredClass",
        "type": "bytes32",
        "indexed": false,
        "internalType": "bytes32"
      },
      {
        "name": "stakeAmount",
        "type": "uint256",
        "indexed": false,
        "internalType": "uint256"
      }
    ],
    "anonymous": false
  },
  {
    "type": "event",
    "name": "StrategySlashed",
    "inputs": [
      {
        "name": "strategyId",
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
    "type": "error",
    "name": "NoPendingParamsRotation",
    "inputs": []
  },
  {
    "type": "error",
    "name": "NotOperator",
    "inputs": []
  },
  {
    "type": "error",
    "name": "NotReputationAnchor",
    "inputs": []
  },
  {
    "type": "error",
    "name": "ParamsHashAlreadyCommitted",
    "inputs": []
  },
  {
    "type": "error",
    "name": "ParamsHashNotCommitted",
    "inputs": []
  },
  {
    "type": "error",
    "name": "ParamsRotationAlreadyPending",
    "inputs": []
  },
  {
    "type": "error",
    "name": "ParamsRotationCooldownActive",
    "inputs": []
  },
  {
    "type": "error",
    "name": "StakeCooldownActive",
    "inputs": []
  },
  {
    "type": "error",
    "name": "ZeroParamsHash",
    "inputs": []
  }
] as const;
