// Auto-generated. Do not edit.
// Source: contracts/out/IOracleAnchor.sol/IOracleAnchor.json

export const IOracleAnchorAbi = [
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
    "type": "event",
    "name": "Committed",
    "inputs": [
      {
        "name": "index",
        "type": "uint256",
        "indexed": true,
        "internalType": "uint256"
      },
      {
        "name": "root",
        "type": "bytes32",
        "indexed": true,
        "internalType": "bytes32"
      },
      {
        "name": "windowStart",
        "type": "uint64",
        "indexed": false,
        "internalType": "uint64"
      },
      {
        "name": "windowEnd",
        "type": "uint64",
        "indexed": false,
        "internalType": "uint64"
      },
      {
        "name": "signer",
        "type": "address",
        "indexed": true,
        "internalType": "address"
      }
    ],
    "anonymous": false
  },
  {
    "type": "event",
    "name": "SignerUpdated",
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
    "name": "UnknownIndex",
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
] as const;
