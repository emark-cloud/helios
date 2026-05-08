// Auto-generated. Do not edit.
// Source: contracts/out/IReputationAnchor.sol/IReputationAnchor.json

export const IReputationAnchorAbi = [
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
        "indexed": true,
        "internalType": "address"
      },
      {
        "name": "actorType",
        "type": "uint8",
        "indexed": true,
        "internalType": "enum IReputationAnchor.ActorType"
      },
      {
        "name": "srcEid",
        "type": "uint32",
        "indexed": false,
        "internalType": "uint32"
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
    "name": "CrossChainTradeTick",
    "inputs": [
      {
        "name": "actor",
        "type": "address",
        "indexed": true,
        "internalType": "address"
      },
      {
        "name": "newTotalAttestedTrades",
        "type": "uint256",
        "indexed": false,
        "internalType": "uint256"
      }
    ],
    "anonymous": false
  },
  {
    "type": "event",
    "name": "ReputationPosted",
    "inputs": [
      {
        "name": "actor",
        "type": "address",
        "indexed": true,
        "internalType": "address"
      },
      {
        "name": "actorType",
        "type": "uint8",
        "indexed": true,
        "internalType": "enum IReputationAnchor.ActorType"
      },
      {
        "name": "newScore",
        "type": "int256",
        "indexed": false,
        "internalType": "int256"
      },
      {
        "name": "blockNumber",
        "type": "uint256",
        "indexed": false,
        "internalType": "uint256"
      }
    ],
    "anonymous": false
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
] as const;
