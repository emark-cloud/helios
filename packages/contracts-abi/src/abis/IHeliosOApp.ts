// Auto-generated. Do not edit.
// Source: contracts/out/IHeliosOApp.sol/IHeliosOApp.json

export const IHeliosOAppAbi = [
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
  }
] as const;
