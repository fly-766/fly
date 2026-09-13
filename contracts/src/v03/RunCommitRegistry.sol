// SPDX-License-Identifier: MIT
pragma solidity ^0.8.30;
import {EIP712} from "@openzeppelin/contracts/utils/cryptography/EIP712.sol";
import {ECDSA} from "@openzeppelin/contracts/utils/cryptography/ECDSA.sol";
/// @notice Batched public-record commitments. A signer attests; this is not a computation proof.
contract RunCommitRegistry is EIP712 {
    struct Commit {uint64 nonce;uint64 fromRound;uint64 toRound;uint64 observedAt;uint64 deadline;uint64 referencePriceE8;bytes32 previousRecord;bytes32 record;bytes32 previousState;bytes32 nextState;bytes32 inputHash;uint8 side;}
    bytes32 public constant TYPEHASH=keccak256("Commit(bytes32 runId,bytes32 modelHash,uint64 nonce,uint64 fromRound,uint64 toRound,uint64 observedAt,uint64 deadline,uint64 referencePriceE8,bytes32 previousRecord,bytes32 record,bytes32 previousState,bytes32 nextState,bytes32 inputHash,uint8 side)");
    bytes32 public immutable runId;bytes32 public immutable modelHash;address public immutable signer;
    uint64 public nonce;uint64 public lastRound;bytes32 public recordRoot;bytes32 public stateRoot;
    uint8 public side;uint64 public deadline;uint64 public referencePriceE8;
    error InvalidCommit();
    event Committed(uint64 indexed nonce,uint64 fromRound,uint64 toRound,bytes32 indexed record,bytes32 nextState,uint8 side);
    constructor(bytes32 run,bytes32 model,bytes32 genesisRecord,bytes32 genesisState,address who) EIP712("FlyTerm Run Commit","1") {
        if(run==0||model==0||genesisRecord==0||genesisState==0||who==address(0))revert InvalidCommit();
        runId=run;modelHash=model;recordRoot=genesisRecord;stateRoot=genesisState;signer=who;
    }
    function digest(Commit calldata c) public view returns(bytes32) {
        return _hashTypedDataV4(keccak256(abi.encode(TYPEHASH,runId,modelHash,c.nonce,c.fromRound,c.toRound,c.observedAt,c.deadline,c.referencePriceE8,c.previousRecord,c.record,c.previousState,c.nextState,c.inputHash,c.side)));
    }
    function submit(Commit calldata c,bytes calldata sig) external {
        if(c.nonce!=nonce+1||c.fromRound!=lastRound+1||c.toRound<c.fromRound||c.toRound-c.fromRound>1023||
           c.previousRecord!=recordRoot||c.previousState!=stateRoot||c.record==0||c.nextState==0||c.inputHash==0||
           c.side>2||c.referencePriceE8==0||c.observedAt>block.timestamp||c.deadline<block.timestamp||c.deadline<c.observedAt||c.deadline-c.observedAt>120||
           ECDSA.recover(digest(c),sig)!=signer)revert InvalidCommit();
        nonce=c.nonce;lastRound=c.toRound;recordRoot=c.record;stateRoot=c.nextState;side=c.side;deadline=c.deadline;referencePriceE8=c.referencePriceE8;
        emit Committed(c.nonce,c.fromRound,c.toRound,c.record,c.nextState,c.side);
    }
}
