// SPDX-License-Identifier: MIT
pragma solidity ^0.8.30;
/// @dev Offsets implement the public Circle MessageV2/BurnMessageV2 wire format.
/// https://github.com/circlefin/evm-cctp-contracts/tree/master/src/messages/v2
library CctpMessage {
    bytes4 internal constant MAGIC=0x46543033; // FT03
    struct Transfer {uint32 sourceDomain;uint32 destinationDomain;bytes32 nonce;bytes32 caller;bytes32 token;bytes32 recipient;bytes32 sender;uint256 gross;uint256 fee;uint8 kind;uint256 basis;uint64 sequence;bytes32 evidence;}
    error InvalidMessage();
    function word(bytes calldata data,uint256 offset) private pure returns(bytes32 out) {
        if(offset+32>data.length)revert InvalidMessage();
        assembly {out:=calldataload(add(data.offset,offset))}
    }
    function small(bytes calldata data,uint256 offset) private pure returns(uint32) {
        if(offset+4>data.length)revert InvalidMessage();return uint32(bytes4(data[offset:offset+4]));
    }
    function addressWord(address a) internal pure returns(bytes32){return bytes32(uint256(uint160(a)));}
    function hook(uint8 kind,uint256 basis,uint64 seq,bytes32 evidence) internal pure returns(bytes memory) {
        return abi.encode(MAGIC,kind,basis,seq,evidence);
    }
    function parse(bytes calldata data) internal pure returns(Transfer memory t) {
        if(data.length!=536||small(data,0)!=1||small(data,148)!=1||small(data,144)<2000)revert InvalidMessage();
        t.sourceDomain=small(data,4);t.destinationDomain=small(data,8);t.nonce=word(data,12);t.caller=word(data,108);
        t.token=word(data,152);t.recipient=word(data,184);t.gross=uint256(word(data,216));t.sender=word(data,248);t.fee=uint256(word(data,312));
        if(t.gross==0||t.fee>=t.gross||t.fee>uint256(word(data,280)))revert InvalidMessage();
        bytes4 magic;(magic,t.kind,t.basis,t.sequence,t.evidence)=abi.decode(data[376:],(bytes4,uint8,uint256,uint64,bytes32));
        if(magic!=MAGIC||t.kind>2||t.sequence==0)revert InvalidMessage();
    }
}
