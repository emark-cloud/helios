// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import { Test } from "forge-std/Test.sol";
import { Helios } from "../src/Helios.sol";

contract HeliosTest is Test {
    Helios internal helios;

    event HeliosDeployed(address indexed deployer, uint256 timestamp);

    function setUp() public {
        helios = new Helios();
    }

    function test_Version() public view {
        assertEq(helios.VERSION(), "0.1.0-phase0");
    }

    function test_Heartbeat() public view {
        assertEq(helios.heartbeat(), "helios: phase 0 alive");
    }

    function test_DeployEmitsEvent() public {
        vm.expectEmit(true, false, false, false);
        emit HeliosDeployed(address(this), block.timestamp);
        new Helios();
    }
}
