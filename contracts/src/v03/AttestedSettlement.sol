// SPDX-License-Identifier: MIT
pragma solidity ^0.8.30;
import {EIP712} from "@openzeppelin/contracts/utils/cryptography/EIP712.sol";
import {ECDSA} from "@openzeppelin/contracts/utils/cryptography/ECDSA.sol";
import {ISettlement03} from "./ProtocolTypes.sol";
/// @notice A publicly auditable venue attestation. Not a consensus or computation proof.
contract AttestedSettlement is EIP712,ISettlement03 {
    address public immutable signer;
    bytes32 public constant TYPEHASH=keccak256("Settlement(address account,bytes32 operation,bytes32 payload,uint64 coreBlock,uint64 deadline,bytes32 evidence)");
    error InvalidAttestation();
    constructor(address who) EIP712("FlyTerm Venue Settlement","1") {if(who==address(0))revert InvalidAttestation();signer=who;}
    function digest(address account,bytes32 op,bytes32 payload,uint64 coreBlock,uint64 deadline,bytes32 evidence) public view returns(bytes32) {
        return _hashTypedDataV4(keccak256(abi.encode(TYPEHASH,account,op,payload,coreBlock,deadline,evidence)));
    }
    function verify(address account,bytes32 op,bytes32 payload,uint64 coreBlock,uint64 deadline,bytes32 evidence,bytes calldata signature) external view {
        if(account==address(0)||op==0||payload==0||evidence==0||coreBlock==0||deadline<block.timestamp||deadline>block.timestamp+300||
           ECDSA.recover(digest(account,op,payload,coreBlock,deadline,evidence),signature)!=signer)revert InvalidAttestation();
    }
}
