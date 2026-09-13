// SPDX-License-Identifier: MIT
pragma solidity ^0.8.30;
import {EIP712} from "@openzeppelin/contracts/utils/cryptography/EIP712.sol";
import {ECDSA} from "@openzeppelin/contracts/utils/cryptography/ECDSA.sol";

/// @notice Operator-attested records, NOT a proof of neural computation.
/// @dev No owner, upgrade, signer rotation, asset custody, or arbitrary call.
contract DecisionRegistry is EIP712 {
    struct Decision {
        uint64 sequence;
        uint64 observedAt;
        uint64 deadline;
        bytes32 previousState;
        bytes32 nextState;
        bytes32 inputHash;
        bytes32 recordHash;
        uint8 side; // 0 HOLD, 1 BUY, 2 SELL
    }
    bytes32 public constant TYPEHASH=keccak256("Decision(bytes32 runId,bytes32 modelHash,uint64 sequence,uint64 observedAt,uint64 deadline,bytes32 previousState,bytes32 nextState,bytes32 inputHash,bytes32 recordHash,uint8 side)");
    bytes32 public immutable runId;
    bytes32 public immutable modelHash;
    address public immutable attestor;
    uint64 public sequence;
    bytes32 public stateRoot;
    mapping(uint64=>bytes32) public recordHashes;
    mapping(uint64=>uint8) public sides;
    mapping(uint64=>uint64) public deadlines;
    error InvalidDecision();
    error InvalidAttestor();
    event DecisionRecorded(uint64 indexed sequence,bytes32 indexed recordHash,bytes32 inputHash,bytes32 previousState,bytes32 nextState,uint8 side,uint64 observedAt);

    constructor(bytes32 run,bytes32 model,bytes32 genesis,address signer) EIP712("FlyTerm Decision","1") {
        if(run==0||model==0||genesis==0||signer==address(0))revert InvalidDecision();
        runId=run;modelHash=model;stateRoot=genesis;attestor=signer;
    }
    function decisionDigest(Decision calldata d) public view returns(bytes32) {
        return _hashTypedDataV4(keccak256(abi.encode(TYPEHASH,runId,modelHash,d.sequence,d.observedAt,d.deadline,d.previousState,d.nextState,d.inputHash,d.recordHash,d.side)));
    }
    function submit(Decision calldata d,bytes calldata signature) external {
        if(d.sequence!=sequence+1||d.previousState!=stateRoot||d.nextState==0||d.inputHash==0||d.recordHash==0||d.side>2||
           d.observedAt>block.timestamp||d.deadline<block.timestamp||d.deadline<d.observedAt||d.deadline-d.observedAt>120)revert InvalidDecision();
        if(ECDSA.recover(decisionDigest(d),signature)!=attestor)revert InvalidAttestor();
        sequence=d.sequence;stateRoot=d.nextState;recordHashes[d.sequence]=d.recordHash;sides[d.sequence]=d.side;deadlines[d.sequence]=d.deadline;
        emit DecisionRecorded(d.sequence,d.recordHash,d.inputHash,d.previousState,d.nextState,d.side,d.observedAt);
    }
}
