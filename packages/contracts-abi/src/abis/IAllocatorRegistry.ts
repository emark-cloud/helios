// Auto-generated. Do not edit.
// Source: contracts/out/IAllocatorRegistry.sol/IAllocatorRegistry.json

export const IAllocatorRegistryAbi = [
  {
    "type": "function",
    "name": "allocatorByName",
    "inputs": [
      {
        "name": "name",
        "type": "string",
        "internalType": "string"
      }
    ],
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
    "name": "allocatorOf",
    "inputs": [
      {
        "name": "allocatorId",
        "type": "address",
        "internalType": "address"
      }
    ],
    "outputs": [
      {
        "name": "",
        "type": "tuple",
        "internalType": "struct IAllocatorRegistry.AllocatorEntry",
        "components": [
          {
            "name": "name",
            "type": "string",
            "internalType": "string"
          },
          {
            "name": "operatorVault",
            "type": "address",
            "internalType": "address"
          },
          {
            "name": "operator",
            "type": "address",
            "internalType": "address"
          },
          {
            "name": "rankingFunctionHash",
            "type": "bytes32",
            "internalType": "bytes32"
          },
          {
            "name": "supportedClasses",
            "type": "bytes32[]",
            "internalType": "bytes32[]"
          },
          {
            "name": "feeRateBps",
            "type": "uint16",
            "internalType": "uint16"
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
            "name": "totalUsers",
            "type": "uint256",
            "internalType": "uint256"
          },
          {
            "name": "totalCapitalManaged",
            "type": "uint256",
            "internalType": "uint256"
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
          },
          {
            "name": "isReferenceBrand",
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
    "name": "assignReferenceBrand",
    "inputs": [
      {
        "name": "allocatorId",
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
        "name": "allocatorId",
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
        "name": "allocatorId",
        "type": "address",
        "internalType": "address"
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
        "name": "allocatorId",
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
    "name": "isNameReserved",
    "inputs": [
      {
        "name": "name",
        "type": "string",
        "internalType": "string"
      }
    ],
    "outputs": [
      {
        "name": "",
        "type": "bool",
        "internalType": "bool"
      }
    ],
    "stateMutability": "view"
  },
  {
    "type": "function",
    "name": "registerAllocator",
    "inputs": [
      {
        "name": "name",
        "type": "string",
        "internalType": "string"
      },
      {
        "name": "operatorVault",
        "type": "address",
        "internalType": "address"
      },
      {
        "name": "rankingFunctionHash",
        "type": "bytes32",
        "internalType": "bytes32"
      },
      {
        "name": "supportedClasses",
        "type": "bytes32[]",
        "internalType": "bytes32[]"
      },
      {
        "name": "feeRateBps",
        "type": "uint16",
        "internalType": "uint16"
      },
      {
        "name": "stakeAmount",
        "type": "uint256",
        "internalType": "uint256"
      }
    ],
    "outputs": [
      {
        "name": "allocatorId",
        "type": "address",
        "internalType": "address"
      }
    ],
    "stateMutability": "nonpayable"
  },
  {
    "type": "function",
    "name": "reserveName",
    "inputs": [
      {
        "name": "name",
        "type": "string",
        "internalType": "string"
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
        "name": "allocatorId",
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
    "name": "topUpStake",
    "inputs": [
      {
        "name": "allocatorId",
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
        "name": "allocatorId",
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
    "name": "AllocatorDeactivated",
    "inputs": [
      {
        "name": "allocatorId",
        "type": "address",
        "indexed": true,
        "internalType": "address"
      }
    ],
    "anonymous": false
  },
  {
    "type": "event",
    "name": "AllocatorRegistered",
    "inputs": [
      {
        "name": "allocatorId",
        "type": "address",
        "indexed": true,
        "internalType": "address"
      },
      {
        "name": "name",
        "type": "string",
        "indexed": false,
        "internalType": "string"
      },
      {
        "name": "operatorVault",
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
        "name": "rankingFunctionHash",
        "type": "bytes32",
        "indexed": false,
        "internalType": "bytes32"
      },
      {
        "name": "feeRateBps",
        "type": "uint16",
        "indexed": false,
        "internalType": "uint16"
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
    "name": "AllocatorReputationUpdated",
    "inputs": [
      {
        "name": "allocatorId",
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
    "name": "AllocatorSlashed",
    "inputs": [
      {
        "name": "allocatorId",
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
    "name": "AllocatorStakeToppedUp",
    "inputs": [
      {
        "name": "allocatorId",
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
    "name": "AllocatorStakeWithdrawalInitiated",
    "inputs": [
      {
        "name": "allocatorId",
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
    "name": "AllocatorStakeWithdrawn",
    "inputs": [
      {
        "name": "allocatorId",
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
    "name": "NameReserved",
    "inputs": [
      {
        "name": "name",
        "type": "string",
        "indexed": false,
        "internalType": "string"
      }
    ],
    "anonymous": false
  },
  {
    "type": "event",
    "name": "ReferenceBrandAssigned",
    "inputs": [
      {
        "name": "allocatorId",
        "type": "address",
        "indexed": true,
        "internalType": "address"
      }
    ],
    "anonymous": false
  },
  {
    "type": "error",
    "name": "NotAllocatorOperator",
    "inputs": []
  },
  {
    "type": "error",
    "name": "NotReputationAnchor",
    "inputs": []
  },
  {
    "type": "error",
    "name": "ReservedName",
    "inputs": []
  }
] as const;
