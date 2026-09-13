// SPDX-License-Identifier: MIT
pragma solidity ^0.8.30;
import {DecisionRegistry} from "./DecisionRegistry.sol";
import {IHyperRead} from "./HyperRead.sol";
import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {SafeERC20} from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import {ReentrancyGuard} from "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
interface ICoreWriter {function sendRawAction(bytes calldata data) external;}
interface ICoreDepositWallet {function depositFor(address recipient,uint256 amount,uint32 destinationId) external;}
/// @notice Constrained CoreWriter research account; live deployment is release-gated.
/// @dev Strict flat/long and one pending IOC. No API-wallet registration or arbitrary call.
/// Zero-fill/unknown outcomes remain blocked, not unlocked by a timeout or operator claim.
/// Core profit withdrawal is deliberately not exposed until its full return path is accepted.
contract HyperPolicyAccount is ReentrancyGuard {
    using SafeERC20 for IERC20;
    DecisionRegistry public immutable registry;
    IHyperRead public immutable reader;
    ICoreWriter public immutable writer;
    IERC20 public immutable usdc;
    ICoreDepositWallet public immutable depositWallet;
    address public immutable guardian;
    uint16 public immutable asset;
    uint64 public immutable maxOrderE6;
    uint64 public immutable lossStopE6;
    uint16 public immutable slippageBps;
    uint256 public contributedE6;
    uint256 public lastDecision;
    bool public paused;
    bool public pending;
    bool public pendingBuy;
    uint64 public pendingCoreBlock;
    uint64 public pendingSizeE8;
    uint128 public pendingCloid;
    uint64 public depositCoreBlock;
    int64 public equityBeforeDeposit;
    uint256 public expectedDepositE6;
    error Restricted();
    error PendingOutcome();
    event FundingQueued(uint256 amount);
    event FundingObserved(uint256 amount,uint64 coreBlock);
    event OrderQueued(uint64 indexed decision,uint128 indexed cloid,bool buy,uint64 priceE8,uint64 sizeE8,bool reduceOnly);
    event PositionObserved(uint128 indexed cloid,int64 quantity,uint64 coreBlock);
    event Paused(address caller);
    event CancelRequested(uint128 cloid);
    constructor(DecisionRegistry records,IHyperRead coreReader,ICoreWriter coreWriter,IERC20 token,ICoreDepositWallet deposits,address pauseGuardian,uint16 perp,uint64 maxOrder,uint64 lossStop,uint16 slip) {
        require(block.chainid==31337, "Local research only: exit route not accepted");
        if(address(records).code.length==0||address(coreReader).code.length==0||address(coreWriter).code.length==0||
           address(token).code.length==0||address(deposits).code.length==0||pauseGuardian==address(0)||
           maxOrder==0||lossStop==0||slip>100)revert Restricted();
        registry=records;reader=coreReader;writer=coreWriter;usdc=token;depositWallet=deposits;guardian=pauseGuardian;
        asset=perp;maxOrderE6=maxOrder;lossStopE6=lossStop;slippageBps=slip;
    }
    function fund(uint256 amount) external nonReentrant {
        if(paused||pending||expectedDepositE6!=0||amount==0||amount>uint256(uint64(type(int64).max)))revert Restricted();
        IHyperRead.Snapshot memory s=reader.snapshot(address(this),asset);
        if(s.quantity!=0)revert Restricted();
        uint256 beforeBalance=usdc.balanceOf(address(this));
        if(amount>beforeBalance)revert Restricted();
        expectedDepositE6=amount;equityBeforeDeposit=s.equityE6;depositCoreBlock=s.coreBlock;
        contributedE6+=amount;
        usdc.forceApprove(address(depositWallet),amount);
        depositWallet.depositFor(address(this),amount,0);
        usdc.forceApprove(address(depositWallet),0);
        if(usdc.balanceOf(address(this))+amount!=beforeBalance)revert Restricted();
        emit FundingQueued(amount);
    }
    function reconcileFunding() external {
        IHyperRead.Snapshot memory s=reader.snapshot(address(this),asset);
        if(expectedDepositE6==0||s.coreBlock<=depositCoreBlock||!s.exists||
           int256(s.equityE6)<int256(equityBeforeDeposit)+int256(expectedDepositE6))revert PendingOutcome();
        uint256 amount=expectedDepositE6;expectedDepositE6=0;emit FundingObserved(amount,s.coreBlock);
    }
    function pause() external {
        if(msg.sender!=guardian)revert Restricted();paused=true;emit Paused(msg.sender);
    }
    function execute(uint64 decision,uint64 sizeE8) external nonReentrant {
        if(pending||expectedDepositE6!=0)revert PendingOutcome();
        if(decision<=lastDecision||decision!=registry.sequence()||registry.deadlines(decision)<block.timestamp)revert Restricted();
        uint8 side=registry.sides(decision);lastDecision=decision;
        if(side==0){if(sizeE8!=0)revert Restricted();return;}
        IHyperRead.Snapshot memory s=reader.snapshot(address(this),asset);
        bool buy=side==1;
        if(!s.exists||s.sizeDecimals>6||s.quantity<0||sizeE8==0||sizeE8%10**(8-s.sizeDecimals)!=0)revert Restricted();
        if(buy) {
            if(paused||s.quantity!=0||s.notionalE6!=0||s.equityE6<=0||contributedE6==0||
               uint256(uint64(s.equityE6))+lossStopE6<=contributedE6)revert Restricted();
        } else if(s.quantity<=0||sizeE8>uint256(uint64(s.quantity))*10**(8-s.sizeDecimals))revert Restricted();
        uint256 px=uint256(s.priceE8)*(buy?10000+slippageBps:10000-slippageBps)/10000;
        // Prices at this BTC magnitude use whole dollars; round to a valid integer price.
        px=buy?((px+1e8-1)/1e8)*1e8:(px/1e8)*1e8;
        if(px==0||px>type(uint64).max)revert Restricted();
        uint256 ntl=px*sizeE8/1e10;
        if(buy) {
            uint256 budget=uint256(uint64(s.equityE6))*100/101;
            if(budget>maxOrderE6)budget=maxOrderE6;
            uint256 step=10**(8-s.sizeDecimals);
            uint256 expectedSize=(budget*1e10/px/step)*step;
            if(sizeE8!=expectedSize||ntl<10e6)revert Restricted();
        } else if(sizeE8!=uint256(uint64(s.quantity))*10**(8-s.sizeDecimals))revert Restricted();
        if(buy&&(ntl>maxOrderE6||ntl*101>uint256(uint64(s.equityE6))*100))revert Restricted();
        _queue(decision,buy,uint64(px),sizeE8,!buy,s.coreBlock);
    }
    function emergencyClose() external nonReentrant {
        IHyperRead.Snapshot memory s=reader.snapshot(address(this),asset);
        bool loss=s.equityE6<=0||(uint256(uint64(s.equityE6))+lossStopE6<=contributedE6);
        if(!paused&&!loss)revert Restricted();
        paused=true;
        if(pending)revert PendingOutcome();
        if(s.quantity<=0||s.sizeDecimals>6)revert Restricted();
        uint256 sz=uint256(uint64(s.quantity))*10**(8-s.sizeDecimals);
        uint256 px=uint256(s.priceE8)*(10000-slippageBps)/10000/1e8*1e8;
        if(sz>type(uint64).max||px==0||px>type(uint64).max)revert Restricted();
        _queue(0,false,uint64(px),uint64(sz),true,s.coreBlock);
    }
    function _queue(uint64 decision,bool buy,uint64 px,uint64 size,bool reduce,uint64 coreBlock) private {
        pending=true;pendingBuy=buy;pendingCoreBlock=coreBlock;pendingSizeE8=size;
        pendingCloid=uint128(uint256(keccak256(abi.encode(block.chainid,address(this),decision,registry.stateRoot(),coreBlock,buy,size))));
        if(pendingCloid==0)revert Restricted();
        writer.sendRawAction(abi.encodePacked(uint8(1),uint24(1),abi.encode(uint32(asset),buy,px,size,reduce,uint8(3),pendingCloid)));
        emit OrderQueued(decision,pendingCloid,buy,px,size,reduce);
    }
    function reconcilePosition() external {
        if(!pending)revert PendingOutcome();
        IHyperRead.Snapshot memory s=reader.snapshot(address(this),asset);
        if(s.coreBlock<=pendingCoreBlock||s.quantity<0||s.sizeDecimals>6)revert PendingOutcome();
        uint256 qty=uint256(uint64(s.quantity))*10**(8-s.sizeDecimals);
        // A queued BUY starts from flat; an observed nonzero position proves this account's IOC ran.
        // A SELL may be partial: do not clear the slot until completely flat.
        if(pendingBuy?(qty==0||qty>pendingSizeE8):(qty!=0))revert PendingOutcome();
        pending=false;emit PositionObserved(pendingCloid,s.quantity,s.coreBlock);
    }
    function cancelPending() external {
        if(!pending)revert PendingOutcome();
        writer.sendRawAction(abi.encodePacked(uint8(1),uint24(11),abi.encode(uint32(asset),pendingCloid)));
        emit CancelRequested(pendingCloid);
        // Cancellation request is not a confirmed terminal outcome.
    }
}
