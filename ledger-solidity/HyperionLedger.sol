// SPDX-License-Identifier: MIT
// Aodı-Hyperion — optional public anchor for the local sha256 lineage chain.
// Pin the current lineage head; anyone can later verify the head on-chain
// while all code/data stay on the owner's machines.
pragma solidity ^0.8.20;

contract HyperionLedger {
    struct Anchor {
        bytes32 head;
        uint64  size;
        uint64  timestamp;
    }

    mapping(address => Anchor) private anchors;

    event Anchored(address indexed owner, bytes32 head, uint64 size);

    function anchor(bytes32 head, uint64 size) external {
        anchors[msg.sender] = Anchor(head, size, uint64(block.timestamp));
        emit Anchored(msg.sender, head, size);
    }

    function get(address owner)
        external view
        returns (bytes32 head, uint64 size, uint64 timestamp)
    {
        Anchor memory a = anchors[owner];
        return (a.head, a.size, a.timestamp);
    }
}
