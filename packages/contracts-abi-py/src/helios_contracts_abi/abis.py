"""Helios contract ABIs. Auto-generated from Foundry artifacts. Do not edit."""

IUserVault_ABI = [
  {
    "type": "function",
    "name": "allocatorOf",
    "inputs": [
      {
        "name": "user",
        "type": "address",
        "internalType": "address"
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
    "name": "delegateToAllocator",
    "inputs": [
      {
        "name": "allocator",
        "type": "address",
        "internalType": "address"
      },
      {
        "name": "sessionTTL",
        "type": "uint64",
        "internalType": "uint64"
      }
    ],
    "outputs": [],
    "stateMutability": "nonpayable"
  },
  {
    "type": "function",
    "name": "deposit",
    "inputs": [
      {
        "name": "asset",
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
    "name": "highWaterMarkOf",
    "inputs": [
      {
        "name": "user",
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
    "name": "metaStrategyOf",
    "inputs": [
      {
        "name": "user",
        "type": "address",
        "internalType": "address"
      }
    ],
    "outputs": [
      {
        "name": "",
        "type": "tuple",
        "internalType": "struct MetaStrategyLib.MetaStrategy",
        "components": [
          {
            "name": "metaStrategyHash",
            "type": "bytes32",
            "internalType": "bytes32"
          },
          {
            "name": "allowedStrategyClasses",
            "type": "bytes32[]",
            "internalType": "bytes32[]"
          },
          {
            "name": "allowedAssets",
            "type": "address[]",
            "internalType": "address[]"
          },
          {
            "name": "allowedChains",
            "type": "uint32[]",
            "internalType": "uint32[]"
          },
          {
            "name": "maxCapital",
            "type": "uint256",
            "internalType": "uint256"
          },
          {
            "name": "maxPerStrategyBps",
            "type": "uint16",
            "internalType": "uint16"
          },
          {
            "name": "maxStrategiesCount",
            "type": "uint8",
            "internalType": "uint8"
          },
          {
            "name": "drawdownThresholdBps",
            "type": "uint16",
            "internalType": "uint16"
          },
          {
            "name": "maxFeeRateBps",
            "type": "uint16",
            "internalType": "uint16"
          },
          {
            "name": "rebalanceCadenceSec",
            "type": "uint256",
            "internalType": "uint256"
          },
          {
            "name": "validUntil",
            "type": "uint64",
            "internalType": "uint64"
          },
          {
            "name": "defundTwapBars",
            "type": "uint16",
            "internalType": "uint16"
          },
          {
            "name": "defundBondBps",
            "type": "uint16",
            "internalType": "uint16"
          },
          {
            "name": "defundConfirmBlocks",
            "type": "uint32",
            "internalType": "uint32"
          }
        ]
      }
    ],
    "stateMutability": "view"
  },
  {
    "type": "function",
    "name": "setMetaStrategy",
    "inputs": [
      {
        "name": "meta",
        "type": "tuple",
        "internalType": "struct MetaStrategyLib.MetaStrategy",
        "components": [
          {
            "name": "metaStrategyHash",
            "type": "bytes32",
            "internalType": "bytes32"
          },
          {
            "name": "allowedStrategyClasses",
            "type": "bytes32[]",
            "internalType": "bytes32[]"
          },
          {
            "name": "allowedAssets",
            "type": "address[]",
            "internalType": "address[]"
          },
          {
            "name": "allowedChains",
            "type": "uint32[]",
            "internalType": "uint32[]"
          },
          {
            "name": "maxCapital",
            "type": "uint256",
            "internalType": "uint256"
          },
          {
            "name": "maxPerStrategyBps",
            "type": "uint16",
            "internalType": "uint16"
          },
          {
            "name": "maxStrategiesCount",
            "type": "uint8",
            "internalType": "uint8"
          },
          {
            "name": "drawdownThresholdBps",
            "type": "uint16",
            "internalType": "uint16"
          },
          {
            "name": "maxFeeRateBps",
            "type": "uint16",
            "internalType": "uint16"
          },
          {
            "name": "rebalanceCadenceSec",
            "type": "uint256",
            "internalType": "uint256"
          },
          {
            "name": "validUntil",
            "type": "uint64",
            "internalType": "uint64"
          },
          {
            "name": "defundTwapBars",
            "type": "uint16",
            "internalType": "uint16"
          },
          {
            "name": "defundBondBps",
            "type": "uint16",
            "internalType": "uint16"
          },
          {
            "name": "defundConfirmBlocks",
            "type": "uint32",
            "internalType": "uint32"
          }
        ]
      },
      {
        "name": "signature",
        "type": "bytes",
        "internalType": "bytes"
      }
    ],
    "outputs": [],
    "stateMutability": "nonpayable"
  },
  {
    "type": "function",
    "name": "withdraw",
    "inputs": [
      {
        "name": "asset",
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
    "type": "event",
    "name": "AllocatorCredit",
    "inputs": [
      {
        "name": "user",
        "type": "address",
        "indexed": True,
        "internalType": "address"
      },
      {
        "name": "allocator",
        "type": "address",
        "indexed": True,
        "internalType": "address"
      },
      {
        "name": "amount",
        "type": "uint256",
        "indexed": False,
        "internalType": "uint256"
      },
      {
        "name": "newBalance",
        "type": "uint256",
        "indexed": False,
        "internalType": "uint256"
      },
      {
        "name": "newHighWaterMark",
        "type": "uint256",
        "indexed": False,
        "internalType": "uint256"
      }
    ],
    "anonymous": False
  },
  {
    "type": "event",
    "name": "AllocatorDelegated",
    "inputs": [
      {
        "name": "user",
        "type": "address",
        "indexed": True,
        "internalType": "address"
      },
      {
        "name": "allocator",
        "type": "address",
        "indexed": True,
        "internalType": "address"
      },
      {
        "name": "sessionTTL",
        "type": "uint64",
        "indexed": False,
        "internalType": "uint64"
      },
      {
        "name": "sessionKey",
        "type": "bytes32",
        "indexed": False,
        "internalType": "bytes32"
      }
    ],
    "anonymous": False
  },
  {
    "type": "event",
    "name": "AllocatorTransfer",
    "inputs": [
      {
        "name": "user",
        "type": "address",
        "indexed": True,
        "internalType": "address"
      },
      {
        "name": "allocator",
        "type": "address",
        "indexed": True,
        "internalType": "address"
      },
      {
        "name": "amount",
        "type": "uint256",
        "indexed": False,
        "internalType": "uint256"
      },
      {
        "name": "newBalance",
        "type": "uint256",
        "indexed": False,
        "internalType": "uint256"
      }
    ],
    "anonymous": False
  },
  {
    "type": "event",
    "name": "Deposited",
    "inputs": [
      {
        "name": "user",
        "type": "address",
        "indexed": True,
        "internalType": "address"
      },
      {
        "name": "asset",
        "type": "address",
        "indexed": True,
        "internalType": "address"
      },
      {
        "name": "amount",
        "type": "uint256",
        "indexed": False,
        "internalType": "uint256"
      }
    ],
    "anonymous": False
  },
  {
    "type": "event",
    "name": "MetaStrategySet",
    "inputs": [
      {
        "name": "user",
        "type": "address",
        "indexed": True,
        "internalType": "address"
      },
      {
        "name": "metaStrategyHash",
        "type": "bytes32",
        "indexed": True,
        "internalType": "bytes32"
      }
    ],
    "anonymous": False
  },
  {
    "type": "event",
    "name": "Withdrawn",
    "inputs": [
      {
        "name": "user",
        "type": "address",
        "indexed": True,
        "internalType": "address"
      },
      {
        "name": "asset",
        "type": "address",
        "indexed": True,
        "internalType": "address"
      },
      {
        "name": "amount",
        "type": "uint256",
        "indexed": False,
        "internalType": "uint256"
      }
    ],
    "anonymous": False
  },
  {
    "type": "error",
    "name": "InvalidSignature",
    "inputs": []
  },
  {
    "type": "error",
    "name": "MetaStrategyExpired",
    "inputs": []
  },
  {
    "type": "error",
    "name": "OutOfBoundsDelegation",
    "inputs": []
  }
]

IAllocatorVault_ABI = [
  {
    "type": "function",
    "name": "accruedFees",
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
    "name": "allocateToStrategy",
    "inputs": [
      {
        "name": "user",
        "type": "address",
        "internalType": "address"
      },
      {
        "name": "strategy",
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
    "name": "allocationOf",
    "inputs": [
      {
        "name": "user",
        "type": "address",
        "internalType": "address"
      },
      {
        "name": "strategy",
        "type": "address",
        "internalType": "address"
      }
    ],
    "outputs": [
      {
        "name": "",
        "type": "tuple",
        "internalType": "struct IAllocatorVault.AllocationRecord",
        "components": [
          {
            "name": "strategy",
            "type": "address",
            "internalType": "address"
          },
          {
            "name": "capitalDeployed",
            "type": "uint256",
            "internalType": "uint256"
          },
          {
            "name": "strategyHighWaterMark",
            "type": "uint256",
            "internalType": "uint256"
          },
          {
            "name": "lastRebalanceTimestamp",
            "type": "uint64",
            "internalType": "uint64"
          },
          {
            "name": "defundedAt",
            "type": "uint64",
            "internalType": "uint64"
          }
        ]
      }
    ],
    "stateMutability": "view"
  },
  {
    "type": "function",
    "name": "cancelDefund",
    "inputs": [
      {
        "name": "user",
        "type": "address",
        "internalType": "address"
      },
      {
        "name": "strategy",
        "type": "address",
        "internalType": "address"
      }
    ],
    "outputs": [],
    "stateMutability": "nonpayable"
  },
  {
    "type": "function",
    "name": "defundStrategy",
    "inputs": [
      {
        "name": "user",
        "type": "address",
        "internalType": "address"
      },
      {
        "name": "strategy",
        "type": "address",
        "internalType": "address"
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
    "name": "finalizeDefund",
    "inputs": [
      {
        "name": "user",
        "type": "address",
        "internalType": "address"
      },
      {
        "name": "strategy",
        "type": "address",
        "internalType": "address"
      }
    ],
    "outputs": [],
    "stateMutability": "nonpayable"
  },
  {
    "type": "function",
    "name": "pendingDefundOf",
    "inputs": [
      {
        "name": "user",
        "type": "address",
        "internalType": "address"
      },
      {
        "name": "strategy",
        "type": "address",
        "internalType": "address"
      }
    ],
    "outputs": [
      {
        "name": "",
        "type": "tuple",
        "internalType": "struct IAllocatorVault.PendingDefund",
        "components": [
          {
            "name": "firstObservedAt",
            "type": "uint64",
            "internalType": "uint64"
          },
          {
            "name": "firstObservedBlock",
            "type": "uint64",
            "internalType": "uint64"
          },
          {
            "name": "lastObservedBlock",
            "type": "uint64",
            "internalType": "uint64"
          },
          {
            "name": "breachCount",
            "type": "uint8",
            "internalType": "uint8"
          },
          {
            "name": "triggerer",
            "type": "address",
            "internalType": "address"
          },
          {
            "name": "bondAmount",
            "type": "uint128",
            "internalType": "uint128"
          }
        ]
      }
    ],
    "stateMutability": "view"
  },
  {
    "type": "function",
    "name": "rebalance",
    "inputs": [
      {
        "name": "user",
        "type": "address",
        "internalType": "address"
      },
      {
        "name": "strategies",
        "type": "address[]",
        "internalType": "address[]"
      },
      {
        "name": "weightsBps",
        "type": "uint256[]",
        "internalType": "uint256[]"
      }
    ],
    "outputs": [],
    "stateMutability": "nonpayable"
  },
  {
    "type": "function",
    "name": "settleStrategyFee",
    "inputs": [
      {
        "name": "user",
        "type": "address",
        "internalType": "address"
      },
      {
        "name": "strategy",
        "type": "address",
        "internalType": "address"
      }
    ],
    "outputs": [],
    "stateMutability": "nonpayable"
  },
  {
    "type": "function",
    "name": "triggerDefund",
    "inputs": [
      {
        "name": "user",
        "type": "address",
        "internalType": "address"
      },
      {
        "name": "strategy",
        "type": "address",
        "internalType": "address"
      }
    ],
    "outputs": [],
    "stateMutability": "nonpayable"
  },
  {
    "type": "function",
    "name": "withdrawAllocatorFees",
    "inputs": [],
    "outputs": [],
    "stateMutability": "nonpayable"
  },
  {
    "type": "event",
    "name": "AllocationCreated",
    "inputs": [
      {
        "name": "user",
        "type": "address",
        "indexed": True,
        "internalType": "address"
      },
      {
        "name": "strategy",
        "type": "address",
        "indexed": True,
        "internalType": "address"
      },
      {
        "name": "amount",
        "type": "uint256",
        "indexed": False,
        "internalType": "uint256"
      },
      {
        "name": "chainId",
        "type": "uint32",
        "indexed": False,
        "internalType": "uint32"
      }
    ],
    "anonymous": False
  },
  {
    "type": "event",
    "name": "AllocationDecreased",
    "inputs": [
      {
        "name": "user",
        "type": "address",
        "indexed": True,
        "internalType": "address"
      },
      {
        "name": "strategy",
        "type": "address",
        "indexed": True,
        "internalType": "address"
      },
      {
        "name": "delta",
        "type": "uint256",
        "indexed": False,
        "internalType": "uint256"
      }
    ],
    "anonymous": False
  },
  {
    "type": "event",
    "name": "AllocationIncreased",
    "inputs": [
      {
        "name": "user",
        "type": "address",
        "indexed": True,
        "internalType": "address"
      },
      {
        "name": "strategy",
        "type": "address",
        "indexed": True,
        "internalType": "address"
      },
      {
        "name": "delta",
        "type": "uint256",
        "indexed": False,
        "internalType": "uint256"
      }
    ],
    "anonymous": False
  },
  {
    "type": "event",
    "name": "AllocatorFeesWithdrawn",
    "inputs": [
      {
        "name": "allocator",
        "type": "address",
        "indexed": True,
        "internalType": "address"
      },
      {
        "name": "amount",
        "type": "uint256",
        "indexed": False,
        "internalType": "uint256"
      }
    ],
    "anonymous": False
  },
  {
    "type": "event",
    "name": "BridgeReceiverUpdated",
    "inputs": [
      {
        "name": "previous",
        "type": "address",
        "indexed": True,
        "internalType": "address"
      },
      {
        "name": "next",
        "type": "address",
        "indexed": True,
        "internalType": "address"
      }
    ],
    "anonymous": False
  },
  {
    "type": "event",
    "name": "DefundArmed",
    "inputs": [
      {
        "name": "user",
        "type": "address",
        "indexed": True,
        "internalType": "address"
      },
      {
        "name": "strategy",
        "type": "address",
        "indexed": True,
        "internalType": "address"
      },
      {
        "name": "armedAtBlock",
        "type": "uint64",
        "indexed": False,
        "internalType": "uint64"
      }
    ],
    "anonymous": False
  },
  {
    "type": "event",
    "name": "DefundCancelled",
    "inputs": [
      {
        "name": "user",
        "type": "address",
        "indexed": True,
        "internalType": "address"
      },
      {
        "name": "strategy",
        "type": "address",
        "indexed": True,
        "internalType": "address"
      },
      {
        "name": "reason",
        "type": "bytes32",
        "indexed": False,
        "internalType": "bytes32"
      }
    ],
    "anonymous": False
  },
  {
    "type": "event",
    "name": "DefundFinalized",
    "inputs": [
      {
        "name": "user",
        "type": "address",
        "indexed": True,
        "internalType": "address"
      },
      {
        "name": "strategy",
        "type": "address",
        "indexed": True,
        "internalType": "address"
      },
      {
        "name": "triggerer",
        "type": "address",
        "indexed": False,
        "internalType": "address"
      },
      {
        "name": "refunded",
        "type": "uint256",
        "indexed": False,
        "internalType": "uint256"
      },
      {
        "name": "reward",
        "type": "uint256",
        "indexed": False,
        "internalType": "uint256"
      },
      {
        "name": "slashedToUser",
        "type": "uint256",
        "indexed": False,
        "internalType": "uint256"
      }
    ],
    "anonymous": False
  },
  {
    "type": "event",
    "name": "DefundObserved",
    "inputs": [
      {
        "name": "user",
        "type": "address",
        "indexed": True,
        "internalType": "address"
      },
      {
        "name": "strategy",
        "type": "address",
        "indexed": True,
        "internalType": "address"
      },
      {
        "name": "triggerer",
        "type": "address",
        "indexed": True,
        "internalType": "address"
      },
      {
        "name": "breachCount",
        "type": "uint8",
        "indexed": False,
        "internalType": "uint8"
      },
      {
        "name": "observedDrawdownBps",
        "type": "uint256",
        "indexed": False,
        "internalType": "uint256"
      },
      {
        "name": "bondAmount",
        "type": "uint256",
        "indexed": False,
        "internalType": "uint256"
      }
    ],
    "anonymous": False
  },
  {
    "type": "event",
    "name": "DefundRewardCapUpdated",
    "inputs": [
      {
        "name": "previous",
        "type": "uint256",
        "indexed": False,
        "internalType": "uint256"
      },
      {
        "name": "next",
        "type": "uint256",
        "indexed": False,
        "internalType": "uint256"
      }
    ],
    "anonymous": False
  },
  {
    "type": "event",
    "name": "DestinationReceiverUpdated",
    "inputs": [
      {
        "name": "dstEid",
        "type": "uint32",
        "indexed": True,
        "internalType": "uint32"
      },
      {
        "name": "previous",
        "type": "address",
        "indexed": True,
        "internalType": "address"
      },
      {
        "name": "next",
        "type": "address",
        "indexed": True,
        "internalType": "address"
      }
    ],
    "anonymous": False
  },
  {
    "type": "event",
    "name": "OftAdapterUpdated",
    "inputs": [
      {
        "name": "previous",
        "type": "address",
        "indexed": True,
        "internalType": "address"
      },
      {
        "name": "next",
        "type": "address",
        "indexed": True,
        "internalType": "address"
      }
    ],
    "anonymous": False
  },
  {
    "type": "event",
    "name": "OperatorUpdated",
    "inputs": [
      {
        "name": "previous",
        "type": "address",
        "indexed": True,
        "internalType": "address"
      },
      {
        "name": "next",
        "type": "address",
        "indexed": True,
        "internalType": "address"
      }
    ],
    "anonymous": False
  },
  {
    "type": "event",
    "name": "OracleAnchorUpdated",
    "inputs": [
      {
        "name": "previous",
        "type": "address",
        "indexed": True,
        "internalType": "address"
      },
      {
        "name": "next",
        "type": "address",
        "indexed": True,
        "internalType": "address"
      }
    ],
    "anonymous": False
  },
  {
    "type": "event",
    "name": "RemoteAllocationSent",
    "inputs": [
      {
        "name": "user",
        "type": "address",
        "indexed": True,
        "internalType": "address"
      },
      {
        "name": "strategyId",
        "type": "bytes32",
        "indexed": True,
        "internalType": "bytes32"
      },
      {
        "name": "dstEid",
        "type": "uint32",
        "indexed": True,
        "internalType": "uint32"
      },
      {
        "name": "remoteVault",
        "type": "address",
        "indexed": False,
        "internalType": "address"
      },
      {
        "name": "amount",
        "type": "uint256",
        "indexed": False,
        "internalType": "uint256"
      }
    ],
    "anonymous": False
  },
  {
    "type": "event",
    "name": "RemoteDefundSettled",
    "inputs": [
      {
        "name": "user",
        "type": "address",
        "indexed": True,
        "internalType": "address"
      },
      {
        "name": "strategyId",
        "type": "bytes32",
        "indexed": True,
        "internalType": "bytes32"
      },
      {
        "name": "srcEid",
        "type": "uint32",
        "indexed": True,
        "internalType": "uint32"
      },
      {
        "name": "amount",
        "type": "uint256",
        "indexed": False,
        "internalType": "uint256"
      }
    ],
    "anonymous": False
  },
  {
    "type": "event",
    "name": "StrategyDefunded",
    "inputs": [
      {
        "name": "user",
        "type": "address",
        "indexed": True,
        "internalType": "address"
      },
      {
        "name": "strategy",
        "type": "address",
        "indexed": True,
        "internalType": "address"
      },
      {
        "name": "reason",
        "type": "string",
        "indexed": False,
        "internalType": "string"
      },
      {
        "name": "triggeredBy",
        "type": "address",
        "indexed": True,
        "internalType": "address"
      }
    ],
    "anonymous": False
  },
  {
    "type": "event",
    "name": "StrategyFeeSettled",
    "inputs": [
      {
        "name": "user",
        "type": "address",
        "indexed": True,
        "internalType": "address"
      },
      {
        "name": "strategy",
        "type": "address",
        "indexed": True,
        "internalType": "address"
      },
      {
        "name": "feeAmount",
        "type": "uint256",
        "indexed": False,
        "internalType": "uint256"
      },
      {
        "name": "newHighWaterMark",
        "type": "uint256",
        "indexed": False,
        "internalType": "uint256"
      }
    ],
    "anonymous": False
  },
  {
    "type": "event",
    "name": "StrategyRegistryUpdated",
    "inputs": [
      {
        "name": "previous",
        "type": "address",
        "indexed": True,
        "internalType": "address"
      },
      {
        "name": "next",
        "type": "address",
        "indexed": True,
        "internalType": "address"
      }
    ],
    "anonymous": False
  },
  {
    "type": "error",
    "name": "AllocationOutOfBounds",
    "inputs": []
  },
  {
    "type": "error",
    "name": "BarTooSoon",
    "inputs": []
  },
  {
    "type": "error",
    "name": "ConfirmWindowNotElapsed",
    "inputs": []
  },
  {
    "type": "error",
    "name": "DefundNotArmed",
    "inputs": []
  },
  {
    "type": "error",
    "name": "DefundNotPending",
    "inputs": []
  },
  {
    "type": "error",
    "name": "DrawdownNotBreached",
    "inputs": []
  },
  {
    "type": "error",
    "name": "NotAllocator",
    "inputs": []
  },
  {
    "type": "error",
    "name": "OracleAnchorNotSet",
    "inputs": []
  },
  {
    "type": "error",
    "name": "OracleStale",
    "inputs": []
  }
]

IStrategyVault_ABI = [
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
        "indexed": True,
        "internalType": "address"
      },
      {
        "name": "oApp",
        "type": "address",
        "indexed": True,
        "internalType": "address"
      },
      {
        "name": "tradeHash",
        "type": "bytes32",
        "indexed": True,
        "internalType": "bytes32"
      }
    ],
    "anonymous": False
  },
  {
    "type": "event",
    "name": "HeliosOAppUpdated",
    "inputs": [
      {
        "name": "previous",
        "type": "address",
        "indexed": True,
        "internalType": "address"
      },
      {
        "name": "current",
        "type": "address",
        "indexed": True,
        "internalType": "address"
      }
    ],
    "anonymous": False
  },
  {
    "type": "event",
    "name": "NAVReported",
    "inputs": [
      {
        "name": "strategy",
        "type": "address",
        "indexed": True,
        "internalType": "address"
      },
      {
        "name": "totalNAV",
        "type": "uint256",
        "indexed": False,
        "internalType": "uint256"
      },
      {
        "name": "timestamp",
        "type": "uint64",
        "indexed": False,
        "internalType": "uint64"
      }
    ],
    "anonymous": False
  },
  {
    "type": "event",
    "name": "NavClampedOnWithdraw",
    "inputs": [
      {
        "name": "strategy",
        "type": "address",
        "indexed": True,
        "internalType": "address"
      },
      {
        "name": "allocator",
        "type": "address",
        "indexed": True,
        "internalType": "address"
      },
      {
        "name": "priorTotalNAV",
        "type": "uint256",
        "indexed": False,
        "internalType": "uint256"
      },
      {
        "name": "withdrawAmount",
        "type": "uint256",
        "indexed": False,
        "internalType": "uint256"
      }
    ],
    "anonymous": False
  },
  {
    "type": "event",
    "name": "NavDivergenceObserved",
    "inputs": [
      {
        "name": "strategy",
        "type": "address",
        "indexed": True,
        "internalType": "address"
      },
      {
        "name": "signedNAV",
        "type": "uint256",
        "indexed": False,
        "internalType": "uint256"
      },
      {
        "name": "markedFloor",
        "type": "uint256",
        "indexed": False,
        "internalType": "uint256"
      },
      {
        "name": "snapshotNonce",
        "type": "uint64",
        "indexed": False,
        "internalType": "uint64"
      }
    ],
    "anonymous": False
  },
  {
    "type": "event",
    "name": "NavDivergenceThresholdUpdated",
    "inputs": [
      {
        "name": "previous",
        "type": "uint16",
        "indexed": False,
        "internalType": "uint16"
      },
      {
        "name": "next",
        "type": "uint16",
        "indexed": False,
        "internalType": "uint16"
      }
    ],
    "anonymous": False
  },
  {
    "type": "event",
    "name": "OrphanedAllocationRecovered",
    "inputs": [
      {
        "name": "strategy",
        "type": "address",
        "indexed": True,
        "internalType": "address"
      },
      {
        "name": "to",
        "type": "address",
        "indexed": True,
        "internalType": "address"
      },
      {
        "name": "amount",
        "type": "uint256",
        "indexed": False,
        "internalType": "uint256"
      }
    ],
    "anonymous": False
  },
  {
    "type": "event",
    "name": "RealizedDistributed",
    "inputs": [
      {
        "name": "strategy",
        "type": "address",
        "indexed": True,
        "internalType": "address"
      },
      {
        "name": "allocator",
        "type": "address",
        "indexed": True,
        "internalType": "address"
      },
      {
        "name": "amount",
        "type": "uint256",
        "indexed": False,
        "internalType": "uint256"
      }
    ],
    "anonymous": False
  },
  {
    "type": "event",
    "name": "RegistryUpdated",
    "inputs": [
      {
        "name": "previous",
        "type": "address",
        "indexed": True,
        "internalType": "address"
      },
      {
        "name": "next",
        "type": "address",
        "indexed": True,
        "internalType": "address"
      }
    ],
    "anonymous": False
  },
  {
    "type": "event",
    "name": "Slashed",
    "inputs": [
      {
        "name": "strategy",
        "type": "address",
        "indexed": True,
        "internalType": "address"
      },
      {
        "name": "amount",
        "type": "uint256",
        "indexed": False,
        "internalType": "uint256"
      },
      {
        "name": "reason",
        "type": "string",
        "indexed": False,
        "internalType": "string"
      }
    ],
    "anonymous": False
  },
  {
    "type": "event",
    "name": "StrandedNAVRecovered",
    "inputs": [
      {
        "name": "strategy",
        "type": "address",
        "indexed": True,
        "internalType": "address"
      },
      {
        "name": "to",
        "type": "address",
        "indexed": True,
        "internalType": "address"
      },
      {
        "name": "amount",
        "type": "uint256",
        "indexed": False,
        "internalType": "uint256"
      }
    ],
    "anonymous": False
  },
  {
    "type": "event",
    "name": "TradeAttested",
    "inputs": [
      {
        "name": "strategy",
        "type": "address",
        "indexed": True,
        "internalType": "address"
      },
      {
        "name": "allocator",
        "type": "address",
        "indexed": True,
        "internalType": "address"
      },
      {
        "name": "tradeHash",
        "type": "bytes32",
        "indexed": True,
        "internalType": "bytes32"
      },
      {
        "name": "declaredClass",
        "type": "bytes32",
        "indexed": False,
        "internalType": "bytes32"
      },
      {
        "name": "assetIn",
        "type": "address",
        "indexed": False,
        "internalType": "address"
      },
      {
        "name": "assetOut",
        "type": "address",
        "indexed": False,
        "internalType": "address"
      },
      {
        "name": "amountIn",
        "type": "uint256",
        "indexed": False,
        "internalType": "uint256"
      },
      {
        "name": "minAmountOut",
        "type": "uint256",
        "indexed": False,
        "internalType": "uint256"
      },
      {
        "name": "direction",
        "type": "uint8",
        "indexed": False,
        "internalType": "uint8"
      },
      {
        "name": "blockWindowStart",
        "type": "uint64",
        "indexed": False,
        "internalType": "uint64"
      },
      {
        "name": "blockWindowEnd",
        "type": "uint64",
        "indexed": False,
        "internalType": "uint64"
      }
    ],
    "anonymous": False
  },
  {
    "type": "event",
    "name": "YieldRotationAttested",
    "inputs": [
      {
        "name": "strategy",
        "type": "address",
        "indexed": True,
        "internalType": "address"
      },
      {
        "name": "allocator",
        "type": "address",
        "indexed": True,
        "internalType": "address"
      },
      {
        "name": "tradeHash",
        "type": "bytes32",
        "indexed": True,
        "internalType": "bytes32"
      },
      {
        "name": "declaredClass",
        "type": "bytes32",
        "indexed": False,
        "internalType": "bytes32"
      },
      {
        "name": "mFrom",
        "type": "uint256",
        "indexed": False,
        "internalType": "uint256"
      },
      {
        "name": "mTo",
        "type": "uint256",
        "indexed": False,
        "internalType": "uint256"
      },
      {
        "name": "amountRotating",
        "type": "uint256",
        "indexed": False,
        "internalType": "uint256"
      },
      {
        "name": "yieldOracleRoot",
        "type": "bytes32",
        "indexed": False,
        "internalType": "bytes32"
      },
      {
        "name": "blockWindowStart",
        "type": "uint64",
        "indexed": False,
        "internalType": "uint64"
      },
      {
        "name": "blockWindowEnd",
        "type": "uint64",
        "indexed": False,
        "internalType": "uint64"
      }
    ],
    "anonymous": False
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
]

IStrategyRegistry_ABI = [
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
        "indexed": True,
        "internalType": "bytes32"
      },
      {
        "name": "root",
        "type": "bytes32",
        "indexed": False,
        "internalType": "bytes32"
      }
    ],
    "anonymous": False
  },
  {
    "type": "event",
    "name": "ParamsHashCommitted",
    "inputs": [
      {
        "name": "strategyId",
        "type": "address",
        "indexed": True,
        "internalType": "address"
      },
      {
        "name": "paramsHash",
        "type": "bytes32",
        "indexed": False,
        "internalType": "bytes32"
      }
    ],
    "anonymous": False
  },
  {
    "type": "event",
    "name": "ParamsRotated",
    "inputs": [
      {
        "name": "strategyId",
        "type": "address",
        "indexed": True,
        "internalType": "address"
      },
      {
        "name": "oldHash",
        "type": "bytes32",
        "indexed": False,
        "internalType": "bytes32"
      },
      {
        "name": "newHash",
        "type": "bytes32",
        "indexed": False,
        "internalType": "bytes32"
      }
    ],
    "anonymous": False
  },
  {
    "type": "event",
    "name": "ParamsRotationCancelled",
    "inputs": [
      {
        "name": "strategyId",
        "type": "address",
        "indexed": True,
        "internalType": "address"
      },
      {
        "name": "cancelledNewHash",
        "type": "bytes32",
        "indexed": False,
        "internalType": "bytes32"
      }
    ],
    "anonymous": False
  },
  {
    "type": "event",
    "name": "ParamsRotationInitiated",
    "inputs": [
      {
        "name": "strategyId",
        "type": "address",
        "indexed": True,
        "internalType": "address"
      },
      {
        "name": "oldHash",
        "type": "bytes32",
        "indexed": False,
        "internalType": "bytes32"
      },
      {
        "name": "newHash",
        "type": "bytes32",
        "indexed": False,
        "internalType": "bytes32"
      },
      {
        "name": "unlockAt",
        "type": "uint64",
        "indexed": False,
        "internalType": "uint64"
      }
    ],
    "anonymous": False
  },
  {
    "type": "event",
    "name": "ReputationUpdated",
    "inputs": [
      {
        "name": "strategyId",
        "type": "address",
        "indexed": True,
        "internalType": "address"
      },
      {
        "name": "delta",
        "type": "int256",
        "indexed": False,
        "internalType": "int256"
      },
      {
        "name": "newScore",
        "type": "int256",
        "indexed": False,
        "internalType": "int256"
      }
    ],
    "anonymous": False
  },
  {
    "type": "event",
    "name": "StakeToppedUp",
    "inputs": [
      {
        "name": "strategyId",
        "type": "address",
        "indexed": True,
        "internalType": "address"
      },
      {
        "name": "amount",
        "type": "uint256",
        "indexed": False,
        "internalType": "uint256"
      }
    ],
    "anonymous": False
  },
  {
    "type": "event",
    "name": "StakeWithdrawalInitiated",
    "inputs": [
      {
        "name": "strategyId",
        "type": "address",
        "indexed": True,
        "internalType": "address"
      },
      {
        "name": "amount",
        "type": "uint256",
        "indexed": False,
        "internalType": "uint256"
      },
      {
        "name": "unlockAt",
        "type": "uint64",
        "indexed": False,
        "internalType": "uint64"
      }
    ],
    "anonymous": False
  },
  {
    "type": "event",
    "name": "StakeWithdrawn",
    "inputs": [
      {
        "name": "strategyId",
        "type": "address",
        "indexed": True,
        "internalType": "address"
      },
      {
        "name": "amount",
        "type": "uint256",
        "indexed": False,
        "internalType": "uint256"
      }
    ],
    "anonymous": False
  },
  {
    "type": "event",
    "name": "StrategyDeactivated",
    "inputs": [
      {
        "name": "strategyId",
        "type": "address",
        "indexed": True,
        "internalType": "address"
      }
    ],
    "anonymous": False
  },
  {
    "type": "event",
    "name": "StrategyRegistered",
    "inputs": [
      {
        "name": "strategyId",
        "type": "address",
        "indexed": True,
        "internalType": "address"
      },
      {
        "name": "vault",
        "type": "address",
        "indexed": True,
        "internalType": "address"
      },
      {
        "name": "operator",
        "type": "address",
        "indexed": True,
        "internalType": "address"
      },
      {
        "name": "declaredClass",
        "type": "bytes32",
        "indexed": False,
        "internalType": "bytes32"
      },
      {
        "name": "stakeAmount",
        "type": "uint256",
        "indexed": False,
        "internalType": "uint256"
      }
    ],
    "anonymous": False
  },
  {
    "type": "event",
    "name": "StrategySlashed",
    "inputs": [
      {
        "name": "strategyId",
        "type": "address",
        "indexed": True,
        "internalType": "address"
      },
      {
        "name": "amount",
        "type": "uint256",
        "indexed": False,
        "internalType": "uint256"
      },
      {
        "name": "reason",
        "type": "string",
        "indexed": False,
        "internalType": "string"
      }
    ],
    "anonymous": False
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
]

IAllocatorRegistry_ABI = [
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
        "indexed": True,
        "internalType": "address"
      }
    ],
    "anonymous": False
  },
  {
    "type": "event",
    "name": "AllocatorRegistered",
    "inputs": [
      {
        "name": "allocatorId",
        "type": "address",
        "indexed": True,
        "internalType": "address"
      },
      {
        "name": "name",
        "type": "string",
        "indexed": False,
        "internalType": "string"
      },
      {
        "name": "operatorVault",
        "type": "address",
        "indexed": True,
        "internalType": "address"
      },
      {
        "name": "operator",
        "type": "address",
        "indexed": True,
        "internalType": "address"
      },
      {
        "name": "rankingFunctionHash",
        "type": "bytes32",
        "indexed": False,
        "internalType": "bytes32"
      },
      {
        "name": "feeRateBps",
        "type": "uint16",
        "indexed": False,
        "internalType": "uint16"
      },
      {
        "name": "stakeAmount",
        "type": "uint256",
        "indexed": False,
        "internalType": "uint256"
      }
    ],
    "anonymous": False
  },
  {
    "type": "event",
    "name": "AllocatorReputationUpdated",
    "inputs": [
      {
        "name": "allocatorId",
        "type": "address",
        "indexed": True,
        "internalType": "address"
      },
      {
        "name": "delta",
        "type": "int256",
        "indexed": False,
        "internalType": "int256"
      },
      {
        "name": "newScore",
        "type": "int256",
        "indexed": False,
        "internalType": "int256"
      }
    ],
    "anonymous": False
  },
  {
    "type": "event",
    "name": "AllocatorSlashed",
    "inputs": [
      {
        "name": "allocatorId",
        "type": "address",
        "indexed": True,
        "internalType": "address"
      },
      {
        "name": "amount",
        "type": "uint256",
        "indexed": False,
        "internalType": "uint256"
      },
      {
        "name": "reason",
        "type": "string",
        "indexed": False,
        "internalType": "string"
      }
    ],
    "anonymous": False
  },
  {
    "type": "event",
    "name": "AllocatorStakeToppedUp",
    "inputs": [
      {
        "name": "allocatorId",
        "type": "address",
        "indexed": True,
        "internalType": "address"
      },
      {
        "name": "amount",
        "type": "uint256",
        "indexed": False,
        "internalType": "uint256"
      }
    ],
    "anonymous": False
  },
  {
    "type": "event",
    "name": "AllocatorStakeWithdrawalInitiated",
    "inputs": [
      {
        "name": "allocatorId",
        "type": "address",
        "indexed": True,
        "internalType": "address"
      },
      {
        "name": "amount",
        "type": "uint256",
        "indexed": False,
        "internalType": "uint256"
      },
      {
        "name": "unlockAt",
        "type": "uint64",
        "indexed": False,
        "internalType": "uint64"
      }
    ],
    "anonymous": False
  },
  {
    "type": "event",
    "name": "AllocatorStakeWithdrawn",
    "inputs": [
      {
        "name": "allocatorId",
        "type": "address",
        "indexed": True,
        "internalType": "address"
      },
      {
        "name": "amount",
        "type": "uint256",
        "indexed": False,
        "internalType": "uint256"
      }
    ],
    "anonymous": False
  },
  {
    "type": "event",
    "name": "NameReserved",
    "inputs": [
      {
        "name": "name",
        "type": "string",
        "indexed": False,
        "internalType": "string"
      }
    ],
    "anonymous": False
  },
  {
    "type": "event",
    "name": "ReferenceBrandAssigned",
    "inputs": [
      {
        "name": "allocatorId",
        "type": "address",
        "indexed": True,
        "internalType": "address"
      }
    ],
    "anonymous": False
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
]

IReputationAnchor_ABI = [
  {
    "type": "function",
    "name": "postCrossChainTradeTick",
    "inputs": [
      {
        "name": "actor",
        "type": "address",
        "internalType": "address"
      }
    ],
    "outputs": [],
    "stateMutability": "nonpayable"
  },
  {
    "type": "function",
    "name": "postCrossChainUpdate",
    "inputs": [
      {
        "name": "actor",
        "type": "address",
        "internalType": "address"
      },
      {
        "name": "actorType",
        "type": "uint8",
        "internalType": "enum IReputationAnchor.ActorType"
      },
      {
        "name": "data",
        "type": "tuple",
        "internalType": "struct IReputationAnchor.ReputationData",
        "components": [
          {
            "name": "currentScore",
            "type": "int256",
            "internalType": "int256"
          },
          {
            "name": "lastUpdateBlock",
            "type": "uint256",
            "internalType": "uint256"
          },
          {
            "name": "totalAttestedTrades",
            "type": "uint256",
            "internalType": "uint256"
          },
          {
            "name": "totalRealizedPnL",
            "type": "uint256",
            "internalType": "uint256"
          },
          {
            "name": "maxDrawdownBps",
            "type": "uint256",
            "internalType": "uint256"
          },
          {
            "name": "proofValidityRateBps",
            "type": "uint256",
            "internalType": "uint256"
          },
          {
            "name": "actorType",
            "type": "uint8",
            "internalType": "enum IReputationAnchor.ActorType"
          },
          {
            "name": "componentsHash",
            "type": "bytes32",
            "internalType": "bytes32"
          }
        ]
      }
    ],
    "outputs": [],
    "stateMutability": "nonpayable"
  },
  {
    "type": "function",
    "name": "postReputationUpdate",
    "inputs": [
      {
        "name": "actor",
        "type": "address",
        "internalType": "address"
      },
      {
        "name": "actorType",
        "type": "uint8",
        "internalType": "enum IReputationAnchor.ActorType"
      },
      {
        "name": "data",
        "type": "tuple",
        "internalType": "struct IReputationAnchor.ReputationData",
        "components": [
          {
            "name": "currentScore",
            "type": "int256",
            "internalType": "int256"
          },
          {
            "name": "lastUpdateBlock",
            "type": "uint256",
            "internalType": "uint256"
          },
          {
            "name": "totalAttestedTrades",
            "type": "uint256",
            "internalType": "uint256"
          },
          {
            "name": "totalRealizedPnL",
            "type": "uint256",
            "internalType": "uint256"
          },
          {
            "name": "maxDrawdownBps",
            "type": "uint256",
            "internalType": "uint256"
          },
          {
            "name": "proofValidityRateBps",
            "type": "uint256",
            "internalType": "uint256"
          },
          {
            "name": "actorType",
            "type": "uint8",
            "internalType": "enum IReputationAnchor.ActorType"
          },
          {
            "name": "componentsHash",
            "type": "bytes32",
            "internalType": "bytes32"
          }
        ]
      },
      {
        "name": "signerSignature",
        "type": "bytes",
        "internalType": "bytes"
      }
    ],
    "outputs": [],
    "stateMutability": "nonpayable"
  },
  {
    "type": "function",
    "name": "reputationOf",
    "inputs": [
      {
        "name": "actor",
        "type": "address",
        "internalType": "address"
      }
    ],
    "outputs": [
      {
        "name": "",
        "type": "tuple",
        "internalType": "struct IReputationAnchor.ReputationData",
        "components": [
          {
            "name": "currentScore",
            "type": "int256",
            "internalType": "int256"
          },
          {
            "name": "lastUpdateBlock",
            "type": "uint256",
            "internalType": "uint256"
          },
          {
            "name": "totalAttestedTrades",
            "type": "uint256",
            "internalType": "uint256"
          },
          {
            "name": "totalRealizedPnL",
            "type": "uint256",
            "internalType": "uint256"
          },
          {
            "name": "maxDrawdownBps",
            "type": "uint256",
            "internalType": "uint256"
          },
          {
            "name": "proofValidityRateBps",
            "type": "uint256",
            "internalType": "uint256"
          },
          {
            "name": "actorType",
            "type": "uint8",
            "internalType": "enum IReputationAnchor.ActorType"
          },
          {
            "name": "componentsHash",
            "type": "bytes32",
            "internalType": "bytes32"
          }
        ]
      }
    ],
    "stateMutability": "view"
  },
  {
    "type": "event",
    "name": "CrossChainReputationPosted",
    "inputs": [
      {
        "name": "actor",
        "type": "address",
        "indexed": True,
        "internalType": "address"
      },
      {
        "name": "actorType",
        "type": "uint8",
        "indexed": True,
        "internalType": "enum IReputationAnchor.ActorType"
      },
      {
        "name": "srcEid",
        "type": "uint32",
        "indexed": False,
        "internalType": "uint32"
      },
      {
        "name": "newScore",
        "type": "int256",
        "indexed": False,
        "internalType": "int256"
      }
    ],
    "anonymous": False
  },
  {
    "type": "event",
    "name": "CrossChainTradeTick",
    "inputs": [
      {
        "name": "actor",
        "type": "address",
        "indexed": True,
        "internalType": "address"
      },
      {
        "name": "newTotalAttestedTrades",
        "type": "uint256",
        "indexed": False,
        "internalType": "uint256"
      }
    ],
    "anonymous": False
  },
  {
    "type": "event",
    "name": "ReputationPosted",
    "inputs": [
      {
        "name": "actor",
        "type": "address",
        "indexed": True,
        "internalType": "address"
      },
      {
        "name": "actorType",
        "type": "uint8",
        "indexed": True,
        "internalType": "enum IReputationAnchor.ActorType"
      },
      {
        "name": "newScore",
        "type": "int256",
        "indexed": False,
        "internalType": "int256"
      },
      {
        "name": "blockNumber",
        "type": "uint256",
        "indexed": False,
        "internalType": "uint256"
      }
    ],
    "anonymous": False
  },
  {
    "type": "error",
    "name": "InvalidSigner",
    "inputs": []
  },
  {
    "type": "error",
    "name": "NotOApp",
    "inputs": []
  }
]

ITradeAttestationVerifier_ABI = [
  {
    "type": "function",
    "name": "registerVerifier",
    "inputs": [
      {
        "name": "declaredClass",
        "type": "bytes32",
        "internalType": "bytes32"
      },
      {
        "name": "verifier",
        "type": "address",
        "internalType": "address"
      }
    ],
    "outputs": [],
    "stateMutability": "nonpayable"
  },
  {
    "type": "function",
    "name": "verifierOf",
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
        "type": "address",
        "internalType": "address"
      }
    ],
    "stateMutability": "view"
  },
  {
    "type": "function",
    "name": "verify",
    "inputs": [
      {
        "name": "declaredClass",
        "type": "bytes32",
        "internalType": "bytes32"
      },
      {
        "name": "proof",
        "type": "bytes",
        "internalType": "bytes"
      },
      {
        "name": "publicInputs",
        "type": "uint256[]",
        "internalType": "uint256[]"
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
    "type": "event",
    "name": "VerifierRegistered",
    "inputs": [
      {
        "name": "declaredClass",
        "type": "bytes32",
        "indexed": True,
        "internalType": "bytes32"
      },
      {
        "name": "verifier",
        "type": "address",
        "indexed": False,
        "internalType": "address"
      }
    ],
    "anonymous": False
  },
  {
    "type": "error",
    "name": "UnknownClass",
    "inputs": []
  }
]

IHeliosOApp_ABI = [
  {
    "type": "function",
    "name": "bridgeAndDeploy",
    "inputs": [
      {
        "name": "dstEid",
        "type": "uint32",
        "internalType": "uint32"
      },
      {
        "name": "strategyOnDst",
        "type": "address",
        "internalType": "address"
      },
      {
        "name": "amount",
        "type": "uint256",
        "internalType": "uint256"
      },
      {
        "name": "options",
        "type": "bytes",
        "internalType": "bytes"
      }
    ],
    "outputs": [],
    "stateMutability": "payable"
  },
  {
    "type": "function",
    "name": "flushAttestationsFor",
    "inputs": [
      {
        "name": "strategy",
        "type": "address",
        "internalType": "address"
      },
      {
        "name": "dstEid",
        "type": "uint32",
        "internalType": "uint32"
      },
      {
        "name": "options",
        "type": "bytes",
        "internalType": "bytes"
      }
    ],
    "outputs": [
      {
        "name": "guid",
        "type": "bytes32",
        "internalType": "bytes32"
      }
    ],
    "stateMutability": "payable"
  },
  {
    "type": "function",
    "name": "lastSeqIn",
    "inputs": [
      {
        "name": "srcEid",
        "type": "uint32",
        "internalType": "uint32"
      },
      {
        "name": "actor",
        "type": "address",
        "internalType": "address"
      }
    ],
    "outputs": [
      {
        "name": "",
        "type": "uint64",
        "internalType": "uint64"
      }
    ],
    "stateMutability": "view"
  },
  {
    "type": "function",
    "name": "lastSeqOut",
    "inputs": [
      {
        "name": "strategy",
        "type": "address",
        "internalType": "address"
      }
    ],
    "outputs": [
      {
        "name": "",
        "type": "uint64",
        "internalType": "uint64"
      }
    ],
    "stateMutability": "view"
  },
  {
    "type": "function",
    "name": "maxPendingPerStrategy",
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
    "name": "pendingCount",
    "inputs": [
      {
        "name": "strategy",
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
    "name": "queueAttestation",
    "inputs": [
      {
        "name": "strategy",
        "type": "address",
        "internalType": "address"
      },
      {
        "name": "data",
        "type": "tuple",
        "internalType": "struct IReputationAnchor.ReputationData",
        "components": [
          {
            "name": "currentScore",
            "type": "int256",
            "internalType": "int256"
          },
          {
            "name": "lastUpdateBlock",
            "type": "uint256",
            "internalType": "uint256"
          },
          {
            "name": "totalAttestedTrades",
            "type": "uint256",
            "internalType": "uint256"
          },
          {
            "name": "totalRealizedPnL",
            "type": "uint256",
            "internalType": "uint256"
          },
          {
            "name": "maxDrawdownBps",
            "type": "uint256",
            "internalType": "uint256"
          },
          {
            "name": "proofValidityRateBps",
            "type": "uint256",
            "internalType": "uint256"
          },
          {
            "name": "actorType",
            "type": "uint8",
            "internalType": "enum IReputationAnchor.ActorType"
          },
          {
            "name": "componentsHash",
            "type": "bytes32",
            "internalType": "bytes32"
          }
        ]
      }
    ],
    "outputs": [],
    "stateMutability": "nonpayable"
  },
  {
    "type": "function",
    "name": "quote",
    "inputs": [
      {
        "name": "dstEid",
        "type": "uint32",
        "internalType": "uint32"
      },
      {
        "name": "payload",
        "type": "bytes",
        "internalType": "bytes"
      },
      {
        "name": "options",
        "type": "bytes",
        "internalType": "bytes"
      }
    ],
    "outputs": [
      {
        "name": "",
        "type": "tuple",
        "internalType": "struct IHeliosOApp.MessagingFee",
        "components": [
          {
            "name": "nativeFee",
            "type": "uint256",
            "internalType": "uint256"
          },
          {
            "name": "lzTokenFee",
            "type": "uint256",
            "internalType": "uint256"
          }
        ]
      }
    ],
    "stateMutability": "view"
  },
  {
    "type": "function",
    "name": "sendReputationUpdate",
    "inputs": [
      {
        "name": "dstEid",
        "type": "uint32",
        "internalType": "uint32"
      },
      {
        "name": "actor",
        "type": "address",
        "internalType": "address"
      },
      {
        "name": "actorType",
        "type": "uint8",
        "internalType": "enum IReputationAnchor.ActorType"
      },
      {
        "name": "data",
        "type": "tuple",
        "internalType": "struct IReputationAnchor.ReputationData",
        "components": [
          {
            "name": "currentScore",
            "type": "int256",
            "internalType": "int256"
          },
          {
            "name": "lastUpdateBlock",
            "type": "uint256",
            "internalType": "uint256"
          },
          {
            "name": "totalAttestedTrades",
            "type": "uint256",
            "internalType": "uint256"
          },
          {
            "name": "totalRealizedPnL",
            "type": "uint256",
            "internalType": "uint256"
          },
          {
            "name": "maxDrawdownBps",
            "type": "uint256",
            "internalType": "uint256"
          },
          {
            "name": "proofValidityRateBps",
            "type": "uint256",
            "internalType": "uint256"
          },
          {
            "name": "actorType",
            "type": "uint8",
            "internalType": "enum IReputationAnchor.ActorType"
          },
          {
            "name": "componentsHash",
            "type": "bytes32",
            "internalType": "bytes32"
          }
        ]
      },
      {
        "name": "options",
        "type": "bytes",
        "internalType": "bytes"
      }
    ],
    "outputs": [],
    "stateMutability": "payable"
  },
  {
    "type": "event",
    "name": "AttestationQueued",
    "inputs": [
      {
        "name": "strategy",
        "type": "address",
        "indexed": True,
        "internalType": "address"
      },
      {
        "name": "seq",
        "type": "uint64",
        "indexed": True,
        "internalType": "uint64"
      },
      {
        "name": "queueLength",
        "type": "uint256",
        "indexed": False,
        "internalType": "uint256"
      }
    ],
    "anonymous": False
  },
  {
    "type": "event",
    "name": "AttestationsFlushed",
    "inputs": [
      {
        "name": "dstEid",
        "type": "uint32",
        "indexed": True,
        "internalType": "uint32"
      },
      {
        "name": "batchSize",
        "type": "uint256",
        "indexed": False,
        "internalType": "uint256"
      },
      {
        "name": "firstSeq",
        "type": "uint64",
        "indexed": False,
        "internalType": "uint64"
      },
      {
        "name": "lastSeq",
        "type": "uint64",
        "indexed": False,
        "internalType": "uint64"
      },
      {
        "name": "guid",
        "type": "bytes32",
        "indexed": False,
        "internalType": "bytes32"
      }
    ],
    "anonymous": False
  },
  {
    "type": "event",
    "name": "BridgeAndDeployReceived",
    "inputs": [
      {
        "name": "srcEid",
        "type": "uint32",
        "indexed": True,
        "internalType": "uint32"
      },
      {
        "name": "strategy",
        "type": "address",
        "indexed": True,
        "internalType": "address"
      },
      {
        "name": "amount",
        "type": "uint256",
        "indexed": False,
        "internalType": "uint256"
      },
      {
        "name": "guid",
        "type": "bytes32",
        "indexed": False,
        "internalType": "bytes32"
      }
    ],
    "anonymous": False
  },
  {
    "type": "event",
    "name": "BridgeAndDeploySent",
    "inputs": [
      {
        "name": "dstEid",
        "type": "uint32",
        "indexed": True,
        "internalType": "uint32"
      },
      {
        "name": "strategy",
        "type": "address",
        "indexed": True,
        "internalType": "address"
      },
      {
        "name": "amount",
        "type": "uint256",
        "indexed": False,
        "internalType": "uint256"
      },
      {
        "name": "guid",
        "type": "bytes32",
        "indexed": False,
        "internalType": "bytes32"
      }
    ],
    "anonymous": False
  },
  {
    "type": "event",
    "name": "ReputationMessageReceived",
    "inputs": [
      {
        "name": "srcEid",
        "type": "uint32",
        "indexed": True,
        "internalType": "uint32"
      },
      {
        "name": "actor",
        "type": "address",
        "indexed": True,
        "internalType": "address"
      },
      {
        "name": "actorType",
        "type": "uint8",
        "indexed": False,
        "internalType": "enum IReputationAnchor.ActorType"
      },
      {
        "name": "guid",
        "type": "bytes32",
        "indexed": False,
        "internalType": "bytes32"
      }
    ],
    "anonymous": False
  },
  {
    "type": "event",
    "name": "ReputationMessageSent",
    "inputs": [
      {
        "name": "dstEid",
        "type": "uint32",
        "indexed": True,
        "internalType": "uint32"
      },
      {
        "name": "actor",
        "type": "address",
        "indexed": True,
        "internalType": "address"
      },
      {
        "name": "actorType",
        "type": "uint8",
        "indexed": False,
        "internalType": "enum IReputationAnchor.ActorType"
      },
      {
        "name": "guid",
        "type": "bytes32",
        "indexed": False,
        "internalType": "bytes32"
      }
    ],
    "anonymous": False
  },
  {
    "type": "error",
    "name": "CallerActorMismatch",
    "inputs": [
      {
        "name": "caller",
        "type": "address",
        "internalType": "address"
      },
      {
        "name": "actor",
        "type": "address",
        "internalType": "address"
      }
    ]
  },
  {
    "type": "error",
    "name": "CrossChainOnly",
    "inputs": [
      {
        "name": "chainId",
        "type": "uint64",
        "internalType": "uint64"
      }
    ]
  },
  {
    "type": "error",
    "name": "EmptyQueue",
    "inputs": [
      {
        "name": "strategy",
        "type": "address",
        "internalType": "address"
      }
    ]
  },
  {
    "type": "error",
    "name": "NotStrategyVault",
    "inputs": [
      {
        "name": "caller",
        "type": "address",
        "internalType": "address"
      }
    ]
  },
  {
    "type": "error",
    "name": "PeerNotSet",
    "inputs": [
      {
        "name": "dstEid",
        "type": "uint32",
        "internalType": "uint32"
      }
    ]
  },
  {
    "type": "error",
    "name": "PendingCapTooHigh",
    "inputs": [
      {
        "name": "cap",
        "type": "uint256",
        "internalType": "uint256"
      },
      {
        "name": "hardCap",
        "type": "uint256",
        "internalType": "uint256"
      }
    ]
  },
  {
    "type": "error",
    "name": "QueueFull",
    "inputs": [
      {
        "name": "strategy",
        "type": "address",
        "internalType": "address"
      },
      {
        "name": "cap",
        "type": "uint256",
        "internalType": "uint256"
      }
    ]
  },
  {
    "type": "error",
    "name": "ReplaySeq",
    "inputs": [
      {
        "name": "srcEid",
        "type": "uint32",
        "internalType": "uint32"
      },
      {
        "name": "actor",
        "type": "address",
        "internalType": "address"
      },
      {
        "name": "seq",
        "type": "uint64",
        "internalType": "uint64"
      },
      {
        "name": "lastSeq",
        "type": "uint64",
        "internalType": "uint64"
      }
    ]
  },
  {
    "type": "error",
    "name": "UnknownPayloadKind",
    "inputs": [
      {
        "name": "kind",
        "type": "uint8",
        "internalType": "uint8"
      }
    ]
  }
]

IOracleAnchor_ABI = [
  {
    "type": "function",
    "name": "commit",
    "inputs": [
      {
        "name": "root",
        "type": "bytes32",
        "internalType": "bytes32"
      },
      {
        "name": "windowStart",
        "type": "uint64",
        "internalType": "uint64"
      },
      {
        "name": "windowEnd",
        "type": "uint64",
        "internalType": "uint64"
      },
      {
        "name": "sig",
        "type": "bytes",
        "internalType": "bytes"
      }
    ],
    "outputs": [],
    "stateMutability": "nonpayable"
  },
  {
    "type": "function",
    "name": "commitAt",
    "inputs": [
      {
        "name": "index",
        "type": "uint256",
        "internalType": "uint256"
      }
    ],
    "outputs": [
      {
        "name": "",
        "type": "tuple",
        "internalType": "struct IOracleAnchor.Commit",
        "components": [
          {
            "name": "root",
            "type": "bytes32",
            "internalType": "bytes32"
          },
          {
            "name": "windowStart",
            "type": "uint64",
            "internalType": "uint64"
          },
          {
            "name": "windowEnd",
            "type": "uint64",
            "internalType": "uint64"
          },
          {
            "name": "committedAt",
            "type": "uint64",
            "internalType": "uint64"
          },
          {
            "name": "signer",
            "type": "address",
            "internalType": "address"
          }
        ]
      }
    ],
    "stateMutability": "view"
  },
  {
    "type": "function",
    "name": "commitCount",
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
    "name": "freshness",
    "inputs": [
      {
        "name": "root",
        "type": "bytes32",
        "internalType": "bytes32"
      }
    ],
    "outputs": [
      {
        "name": "",
        "type": "uint64",
        "internalType": "uint64"
      }
    ],
    "stateMutability": "view"
  },
  {
    "type": "function",
    "name": "hashCommit",
    "inputs": [
      {
        "name": "root",
        "type": "bytes32",
        "internalType": "bytes32"
      },
      {
        "name": "windowStart",
        "type": "uint64",
        "internalType": "uint64"
      },
      {
        "name": "windowEnd",
        "type": "uint64",
        "internalType": "uint64"
      },
      {
        "name": "nonce_",
        "type": "uint256",
        "internalType": "uint256"
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
    "name": "isKnownRoot",
    "inputs": [
      {
        "name": "root",
        "type": "bytes32",
        "internalType": "bytes32"
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
    "name": "latest",
    "inputs": [],
    "outputs": [
      {
        "name": "",
        "type": "tuple",
        "internalType": "struct IOracleAnchor.Commit",
        "components": [
          {
            "name": "root",
            "type": "bytes32",
            "internalType": "bytes32"
          },
          {
            "name": "windowStart",
            "type": "uint64",
            "internalType": "uint64"
          },
          {
            "name": "windowEnd",
            "type": "uint64",
            "internalType": "uint64"
          },
          {
            "name": "committedAt",
            "type": "uint64",
            "internalType": "uint64"
          },
          {
            "name": "signer",
            "type": "address",
            "internalType": "address"
          }
        ]
      }
    ],
    "stateMutability": "view"
  },
  {
    "type": "function",
    "name": "nonce",
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
    "name": "oracleSigner",
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
    "name": "revokeRoot",
    "inputs": [
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
    "name": "setSigner",
    "inputs": [
      {
        "name": "signer_",
        "type": "address",
        "internalType": "address"
      }
    ],
    "outputs": [],
    "stateMutability": "nonpayable"
  },
  {
    "type": "function",
    "name": "unrevokeRoot",
    "inputs": [
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
    "type": "event",
    "name": "Committed",
    "inputs": [
      {
        "name": "index",
        "type": "uint256",
        "indexed": True,
        "internalType": "uint256"
      },
      {
        "name": "root",
        "type": "bytes32",
        "indexed": True,
        "internalType": "bytes32"
      },
      {
        "name": "windowStart",
        "type": "uint64",
        "indexed": False,
        "internalType": "uint64"
      },
      {
        "name": "windowEnd",
        "type": "uint64",
        "indexed": False,
        "internalType": "uint64"
      },
      {
        "name": "signer",
        "type": "address",
        "indexed": True,
        "internalType": "address"
      }
    ],
    "anonymous": False
  },
  {
    "type": "event",
    "name": "RootRevoked",
    "inputs": [
      {
        "name": "root",
        "type": "bytes32",
        "indexed": True,
        "internalType": "bytes32"
      }
    ],
    "anonymous": False
  },
  {
    "type": "event",
    "name": "RootUnrevoked",
    "inputs": [
      {
        "name": "root",
        "type": "bytes32",
        "indexed": True,
        "internalType": "bytes32"
      }
    ],
    "anonymous": False
  },
  {
    "type": "event",
    "name": "SignerUpdated",
    "inputs": [
      {
        "name": "previous",
        "type": "address",
        "indexed": True,
        "internalType": "address"
      },
      {
        "name": "next",
        "type": "address",
        "indexed": True,
        "internalType": "address"
      }
    ],
    "anonymous": False
  },
  {
    "type": "error",
    "name": "EmptyWindow",
    "inputs": []
  },
  {
    "type": "error",
    "name": "InvalidSigner",
    "inputs": []
  },
  {
    "type": "error",
    "name": "NonMonotonicWindow",
    "inputs": []
  },
  {
    "type": "error",
    "name": "RootNotRevoked",
    "inputs": []
  },
  {
    "type": "error",
    "name": "UnknownIndex",
    "inputs": []
  },
  {
    "type": "error",
    "name": "UnknownRoot",
    "inputs": []
  },
  {
    "type": "error",
    "name": "ZeroAddress",
    "inputs": []
  },
  {
    "type": "error",
    "name": "ZeroRoot",
    "inputs": []
  }
]
