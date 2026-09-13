// SPDX-License-Identifier: MIT
pragma solidity ^0.8.30;
import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {SafeERC20} from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import {ReentrancyGuard} from "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import {ICctpMessenger,ICostTreasury} from "./ProtocolTypes.sol";
import {CctpMessage} from "./CctpMessage.sol";
/// @notice Authenticated conversion basis follows the USDC across CCTP.
contract TaxTreasury is ReentrancyGuard,ICostTreasury {
    using SafeERC20 for IERC20;
    IERC20 public immutable usdc;
    ICctpMessenger public immutable messenger;
    address public immutable converter;
    address public immutable receiver;
    address public immutable ingress;
    address public immutable guardian;
    uint32 public immutable domain;
    uint16 public immutable maxFeeBps;
    uint256 public immutable minBatch;
    uint256 public immutable maxBatch;
    uint256 public immutable dailyCap;
    uint256 public liquidPrincipal;
    uint256 public basis;
    uint64 public sequence;
    uint256 public day;
    uint256 public sentToday;
    bool public paused;
    error Restricted();
    event ConversionCredited(uint256 usdcAmount,uint256 basis);
    event PrincipalBurned(uint64 indexed sequence,uint256 amount,uint256 basis,uint256 maxFee);
    constructor(IERC20 token,ICctpMessenger router,address source,address dest,address caller,address g,uint32 domain_,uint256 minimum,uint256 maximum,uint256 cap,uint16 fee) {
        if(address(token).code.length==0||address(router).code.length==0||source==address(0)||dest==address(0)||caller==address(0)||g==address(0)||minimum==0||maximum<minimum||cap<maximum||fee>100)revert Restricted();
        usdc=token;messenger=router;converter=source;receiver=dest;ingress=caller;guardian=g;domain=domain_;minBatch=minimum;maxBatch=maximum;dailyCap=cap;maxFeeBps=fee;
    }
    function creditConversion(uint256 amount,uint256 cost) external {
        if(msg.sender!=converter||amount==0||cost==0||usdc.balanceOf(address(this))<liquidPrincipal+amount)revert Restricted();
        liquidPrincipal+=amount;basis+=cost;emit ConversionCredited(amount,cost);
    }
    function pause() external {if(msg.sender!=guardian)revert Restricted();paused=true;}
    function resume() external {if(msg.sender!=guardian)revert Restricted();paused=false;}
    function forward(uint256 amount,uint256 maxFee) external nonReentrant {
        if(paused||amount<minBatch||amount>maxBatch||amount>liquidPrincipal||maxFee>=amount||maxFee>amount*maxFeeBps/10000)revert Restricted();
        uint256 today=block.timestamp/1 days;if(day!=today){day=today;sentToday=0;}
        if(sentToday+amount>dailyCap)revert Restricted();sentToday+=amount;
        uint256 cost=amount==liquidPrincipal?basis:(basis*amount+liquidPrincipal-1)/liquidPrincipal;
        liquidPrincipal-=amount;basis-=cost;sequence++;
        uint256 beforeBalance=usdc.balanceOf(address(this));
        usdc.forceApprove(address(messenger),amount);
        messenger.depositForBurnWithHook(amount,domain,CctpMessage.addressWord(receiver),address(usdc),CctpMessage.addressWord(ingress),maxFee,2000,CctpMessage.hook(0,cost,sequence,bytes32(0)));
        usdc.forceApprove(address(messenger),0);
        if(beforeBalance-usdc.balanceOf(address(this))!=amount)revert Restricted();
        emit PrincipalBurned(sequence,amount,cost,maxFee);
    }
}
