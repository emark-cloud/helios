// Auto-generated. Do not edit.
// Source: contracts/out/IHeliosOApp.sol/IHeliosOApp.json

export const IHeliosOAppAbi = [
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
        "indexed": true,
        "internalType": "address"
      },
      {
        "name": "seq",
        "type": "uint64",
        "indexed": true,
        "internalType": "uint64"
      },
      {
        "name": "queueLength",
        "type": "uint256",
        "indexed": false,
        "internalType": "uint256"
      }
    ],
    "anonymous": false
  },
  {
    "type": "event",
    "name": "AttestationsFlushed",
    "inputs": [
      {
        "name": "dstEid",
        "type": "uint32",
        "indexed": true,
        "internalType": "uint32"
      },
      {
        "name": "batchSize",
        "type": "uint256",
        "indexed": false,
        "internalType": "uint256"
      },
      {
        "name": "firstSeq",
        "type": "uint64",
        "indexed": false,
        "internalType": "uint64"
      },
      {
        "name": "lastSeq",
        "type": "uint64",
        "indexed": false,
        "internalType": "uint64"
      },
      {
        "name": "guid",
        "type": "bytes32",
        "indexed": false,
        "internalType": "bytes32"
      }
    ],
    "anonymous": false
  },
  {
    "type": "event",
    "name": "BridgeAndDeployReceived",
    "inputs": [
      {
        "name": "srcEid",
        "type": "uint32",
        "indexed": true,
        "internalType": "uint32"
      },
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
        "name": "guid",
        "type": "bytes32",
        "indexed": false,
        "internalType": "bytes32"
      }
    ],
    "anonymous": false
  },
  {
    "type": "event",
    "name": "BridgeAndDeploySent",
    "inputs": [
      {
        "name": "dstEid",
        "type": "uint32",
        "indexed": true,
        "internalType": "uint32"
      },
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
        "name": "guid",
        "type": "bytes32",
        "indexed": false,
        "internalType": "bytes32"
      }
    ],
    "anonymous": false
  },
  {
    "type": "event",
    "name": "ReputationMessageReceived",
    "inputs": [
      {
        "name": "srcEid",
        "type": "uint32",
        "indexed": true,
        "internalType": "uint32"
      },
      {
        "name": "actor",
        "type": "address",
        "indexed": true,
        "internalType": "address"
      },
      {
        "name": "actorType",
        "type": "uint8",
        "indexed": false,
        "internalType": "enum IReputationAnchor.ActorType"
      },
      {
        "name": "guid",
        "type": "bytes32",
        "indexed": false,
        "internalType": "bytes32"
      }
    ],
    "anonymous": false
  },
  {
    "type": "event",
    "name": "ReputationMessageSent",
    "inputs": [
      {
        "name": "dstEid",
        "type": "uint32",
        "indexed": true,
        "internalType": "uint32"
      },
      {
        "name": "actor",
        "type": "address",
        "indexed": true,
        "internalType": "address"
      },
      {
        "name": "actorType",
        "type": "uint8",
        "indexed": false,
        "internalType": "enum IReputationAnchor.ActorType"
      },
      {
        "name": "guid",
        "type": "bytes32",
        "indexed": false,
        "internalType": "bytes32"
      }
    ],
    "anonymous": false
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
] as const;
