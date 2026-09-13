// SPDX-License-Identifier: MIT
pragma solidity ^0.8.30;
import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {SafeERC20} from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import {ReentrancyGuard} from "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
interface ITokenMessengerV2 {
    function depositForBurn(uint256 amount,uint32 destinationDomain,bytes32 mintRecipient,address burnToken,bytes32 destinationCaller,uint256 maxFee,uint32 minFinalityThreshold) external;
}
/// @notice Native-USDC-only route. It does not assume IGNIX accepts native USDC as quote.
/// @dev No withdrawals, arbitrary target, unlimited approval, upgrade or recipient changes.
contract FixedRouteTreasury is ReentrancyGuard {
    using SafeERC20 for IERC20;
    IERC20 public immutable usdc;
    ITokenMessengerV2 public immutable messenger;
    uint32 public immutable destinationDomain;
    bytes32 public immutable mintRecipient;
    address public immutable guardian;
    uint16 public immutable maxFeeBps;
    uint256 public immutable minimumBatch;
    uint256 public immutable maximumBatch;
    uint256 public immutable dailyLimit;
    bool public paused;
    uint256 public day;
    uint256 public sentToday;
    uint256 public totalRouted;
    error Restricted();
    event Routed(uint256 amount,uint256 maxFee,uint32 indexed destinationDomain,bytes32 indexed recipient);
    event Paused(address caller);
    constructor(IERC20 token,ITokenMessengerV2 route,uint32 domain,address recipient,address pauseGuardian,uint16 feeBps,uint256 minBatch,uint256 maxBatch,uint256 perDay) {
        require(block.chainid==31337, "Local research only: exit route not accepted");
        if(address(token).code.length==0||address(route).code.length==0||recipient==address(0)||pauseGuardian==address(0)||feeBps>100||
           minBatch==0||maxBatch<minBatch||perDay<maxBatch)revert Restricted();
        usdc=token;messenger=route;destinationDomain=domain;mintRecipient=bytes32(uint256(uint160(recipient)));
        guardian=pauseGuardian;maxFeeBps=feeBps;minimumBatch=minBatch;maximumBatch=maxBatch;dailyLimit=perDay;
    }
    function pause() external {
        if(msg.sender!=guardian)revert Restricted();paused=true;emit Paused(msg.sender);
    }
    function forward(uint256 amount,uint256 maxFee) external nonReentrant {
        if(paused||amount<minimumBatch||amount>maximumBatch||maxFee>amount*maxFeeBps/10000||maxFee>=amount)revert Restricted();
        uint256 today=block.timestamp/1 days;
        if(today!=day){day=today;sentToday=0;}
        if(sentToday+amount>dailyLimit)revert Restricted();
        sentToday+=amount;totalRouted+=amount;
        uint256 beforeBalance=usdc.balanceOf(address(this));
        usdc.forceApprove(address(messenger),amount);
        // 2000 = standard finality. No caller-supplied hook, recipient or domain.
        messenger.depositForBurn(amount,destinationDomain,mintRecipient,address(usdc),bytes32(0),maxFee,2000);
        usdc.forceApprove(address(messenger),0);
        if(usdc.balanceOf(address(this))+amount!=beforeBalance)revert Restricted();
        emit Routed(amount,maxFee,destinationDomain,mintRecipient);
    }
}
