// SPDX-License-Identifier: MIT
pragma solidity ^0.8.30;
import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {ReentrancyGuard} from "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import {ICctpTransmitter,IPrincipalReceiver,IReturnReceiver} from "./ProtocolTypes.sol";
import {CctpMessage} from "./CctpMessage.sol";
/// @notice Receives only this project's authenticated CCTP routes. No keys or operator crediting.
contract CctpIngress is ReentrancyGuard {
    ICctpTransmitter public immutable transmitter;
    IERC20 public immutable localUsdc;
    uint32 public immutable sourceDomain;
    uint32 public immutable destinationDomain;
    bytes32 public immutable sourceToken;
    bytes32 public immutable sourceSender;
    address public immutable principalReceiver;
    address public immutable profitReceiver;
    address public immutable recoveryReceiver;
    mapping(bytes32=>bool) public consumed;
    struct Receipt {uint256 amount;uint8 kind;address recipient;bytes32 messageHash;}
    mapping(bytes32=>Receipt) public receipts;
    error WrongRoute();
    event Received(bytes32 indexed sourceId,uint8 kind,address indexed recipient,uint256 amount,uint256 basis);
    constructor(ICctpTransmitter txr,IERC20 token,uint32 from,uint32 to,address remoteToken,address sender,address principal,address profit,address recovery) {
        if(address(txr).code.length==0||address(token).code.length==0||remoteToken==address(0)||sender==address(0))revert WrongRoute();
        transmitter=txr;localUsdc=token;sourceDomain=from;destinationDomain=to;sourceToken=CctpMessage.addressWord(remoteToken);sourceSender=CctpMessage.addressWord(sender);
        principalReceiver=principal;profitReceiver=profit;recoveryReceiver=recovery;
    }
    function receiveTransfer(bytes calldata message,bytes calldata attestation) external nonReentrant {
        CctpMessage.Transfer memory t=CctpMessage.parse(message);
        address recipient=t.kind==0?principalReceiver:t.kind==1?profitReceiver:recoveryReceiver;
        bytes32 id=keccak256(abi.encode(t.sourceDomain,t.nonce));
        if(recipient==address(0)||t.sourceDomain!=sourceDomain||t.destinationDomain!=destinationDomain||t.sender!=sourceSender||
           t.token!=sourceToken||t.recipient!=CctpMessage.addressWord(recipient)||t.caller!=CctpMessage.addressWord(address(this))||consumed[id])revert WrongRoute();
        uint256 beforeBalance=localUsdc.balanceOf(recipient);
        consumed[id]=true;
        if(!transmitter.receiveMessage(message,attestation))revert WrongRoute();
        uint256 net=localUsdc.balanceOf(recipient)-beforeBalance;
        if(net!=t.gross-t.fee)revert WrongRoute();
        if(t.kind==0){if(t.basis==0)revert WrongRoute();IPrincipalReceiver(recipient).creditPrincipal(net,t.basis,id);}
        else IReturnReceiver(recipient).creditReturn(net,t.kind,id);
        receipts[id]=Receipt(net,t.kind,recipient,keccak256(message));emit Received(id,t.kind,recipient,net,t.basis);
    }
}
