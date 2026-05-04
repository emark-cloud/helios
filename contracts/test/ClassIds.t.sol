// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import { Test } from "forge-std/Test.sol";
import { ClassIds } from "../src/ClassIds.sol";

/// @notice Pin the canonical class-id values to the Python Poseidon helper
///         (`services/oracle/src/oracle/poseidon.py`) — the canonical Poseidon
///         shipped in circomlibjs. Run via `forge test --ffi`. If the values
///         in `ClassIds.sol` ever drift from the Poseidon convention
///         (`Poseidon([int.from_bytes(name, "big")])`), this test fails loudly
///         instead of breaking proofs at runtime.
contract ClassIdsTest is Test {
    function test_Momentum_MatchesPoseidon() public {
        bytes32 expected = _poseidonOfName("momentum_v1");
        assertEq(ClassIds.MOMENTUM_V1, expected, "ClassIds.MOMENTUM_V1 drift");
    }

    function test_MeanReversion_MatchesPoseidon() public {
        bytes32 expected = _poseidonOfName("mean_reversion_v1");
        assertEq(ClassIds.MEAN_REVERSION_V1, expected, "ClassIds.MEAN_REVERSION_V1 drift");
    }

    function test_YieldRotation_MatchesPoseidon() public {
        bytes32 expected = _poseidonOfName("yield_rotation_v1");
        assertEq(ClassIds.YIELD_ROTATION_V1, expected, "ClassIds.YIELD_ROTATION_V1 drift");
    }

    /// @dev Shells out to the Python Poseidon helper. The script prints a
    ///      bare 0x-prefixed 32-byte hex string on stdout; vm.ffi parses it
    ///      back to bytes for cheap equality.
    function _poseidonOfName(string memory name) internal returns (bytes32) {
        string[] memory cmd = new string[](3);
        cmd[0] = "bash";
        cmd[1] = "-c";
        cmd[2] = string.concat(
            "cd ../services/oracle && uv run --quiet python3 -c \"",
            "import sys; sys.path.insert(0, 'src');",
            "from oracle.poseidon import poseidon_hash;",
            "n = int.from_bytes(b'",
            name,
            "', 'big');",
            "print(f'0x{poseidon_hash([n]):064x}')\""
        );
        bytes memory out = vm.ffi(cmd);
        // vm.ffi returns the raw stdout bytes including any trailing newline;
        // forge auto-decodes 0x-hex output to bytes when it looks hex-shaped.
        return abi.decode(abi.encodePacked(out), (bytes32));
    }
}
