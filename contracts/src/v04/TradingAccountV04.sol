// SPDX-License-Identifier: MIT
pragma solidity ^0.8.30;
import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {SafeERC20} from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import {ReentrancyGuard} from "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import {ICoreRead03,ICoreWriter03,ICoreDeposit03,ICctpMessenger,ISettlement03,IPrincipalReceiver,CoreEncoding} from "../v03/ProtocolTypes.sol";
import {RunCommitRegistry} from "../v03/RunCommitRegistry.sol";
import {CoreExitV04 as CoreExit} from "./CoreExitV04.sol";
import {CoreReserves} from "./CoreReserves.sol";
/// @notice Principal exit has no project-imposed timelock; venue settlement must still finish.
contract TradingAccountV04 is CoreReserves,IPrincipalReceiver {
    using SafeERC20 for IERC20;
    enum PendingKind {NONE,DEPOSIT,ORDER,EXIT,MOVE_TO_PERP,SETUP}
    struct Config {
        IERC20 usdc;ICoreRead03 reader;ICoreWriter03 writer;ICoreDeposit03 depositWallet;ISettlement03 settlement;
        RunCommitRegistry registry;ICctpMessenger messenger;address principalIngress;address returnIngress;address recoveryIngress;address profitReceiver;address recoveryReceiver;address guardian;
        uint32 returnDomain;uint64 maxOrderE6;uint64 lossStopE6;uint32 orderCooldown;uint16 maxOrdersPerDay;uint16 slippageBps;uint16 returnFeeBps;
    }
    struct OrderReceipt {uint8 status;uint64 filledE8;uint64 averagePriceE8;int256 closedPnlE6;uint64 feeE6;uint64 finalPositionE8;}
    IERC20 public immutable usdc;ICoreRead03 public immutable reader;ICoreWriter03 public immutable writer;ICoreDeposit03 public immutable depositWallet;
    ISettlement03 public immutable settlement;RunCommitRegistry public immutable registry;address public immutable principalIngress;address public immutable guardian;CoreExit public immutable exit;CoreExit public immutable recoveryExit;
    uint64 public immutable maxOrderE6;uint64 public immutable lossStopE6;uint32 public immutable orderCooldown;uint16 public immutable maxOrdersPerDay;uint16 public immutable slippageBps;uint64 public constant emergencyDelay=0;
    uint256 public unallocatedSpotE6;uint64 public spotBeforeE8;uint256 public costBasisE6;uint256 public nativePrincipalE6;int256 public tradingNetE6;uint256 public profitSentE6;uint256 public operatingCostE6;
    PendingKind public pending;bytes32 public operation;uint64 public operationNonce;uint64 public sentCoreBlock;uint64 public sentAt;int64 public cashBefore;uint256 public pendingAmount;
    uint64 public positionBeforeE8;uint64 public entryBeforeE6;uint64 public limitPriceE8;bool public pendingBuy;uint128 public cloid;uint8 public exitKind;
    uint64 public lastCommit;uint64 public lastOrderAt;uint256 public day;uint256 public ordersToday;uint256 public nativeBasisE6;bool public setupComplete;bool public accountingQuarantined;bool public paused;bool public recoveryOnly;
    mapping(bytes32=>bool) public bookedEvents;
    error Restricted();error Unresolved();
    event PrincipalCredited(bytes32 indexed source,uint256 net,uint256 basis);
    event OperationQueued(bytes32 indexed operation,PendingKind kind,uint256 amount);
    event OperationSettled(bytes32 indexed operation,PendingKind kind,bytes32 evidence);
    event OrderQueued(bytes32 indexed operation,uint128 indexed cloid,bool buy,uint64 sizeE8,uint64 limitE8);
    event ProfitRequested(bytes32 indexed operation,uint256 amount,uint8 kind);
    event CostBooked(bytes32 indexed id,int256 delta,bool trading);
    event Paused(bool recoveryOnly,uint64 at);
    event EmergencyQuarantine(bytes32 indexed operation,bytes32 evidence);
    constructor(Config memory c) {
        if(address(c.usdc).code.length==0||address(c.reader).code.length==0||address(c.writer).code.length==0||address(c.depositWallet).code.length==0||
           address(c.settlement).code.length==0||address(c.registry).code.length==0||c.principalIngress==address(0)||c.guardian==address(0)||
           c.maxOrderE6<10e6||c.lossStopE6==0||c.slippageBps>100||c.orderCooldown<20||c.maxOrdersPerDay==0||c.maxOrdersPerDay>100)revert Restricted();
        usdc=c.usdc;reader=c.reader;writer=c.writer;depositWallet=c.depositWallet;settlement=c.settlement;registry=c.registry;principalIngress=c.principalIngress;guardian=c.guardian;
        maxOrderE6=c.maxOrderE6;lossStopE6=c.lossStopE6;slippageBps=c.slippageBps;orderCooldown=c.orderCooldown;maxOrdersPerDay=c.maxOrdersPerDay;
        exit=new CoreExit(address(this),c.usdc,c.reader,c.writer,c.messenger,c.returnIngress,c.profitReceiver,c.recoveryReceiver,c.returnDomain,c.returnFeeBps,1);
        recoveryExit=new CoreExit(address(this),c.usdc,c.reader,c.writer,c.messenger,c.recoveryIngress,c.profitReceiver,c.recoveryReceiver,c.returnDomain,c.returnFeeBps,2);
    }
    function creditPrincipal(uint256 net,uint256 basis,bytes32 source) external {
        if(msg.sender!=principalIngress||net==0||basis==0||bookedEvents[source]||usdc.balanceOf(address(this))<nativePrincipalE6+net)revert Restricted();
        uint256 effectiveBasis=net>basis?net:basis;
        bookedEvents[source]=true;nativePrincipalE6+=net;nativeBasisE6+=effectiveBasis;costBasisE6+=effectiveBasis;emit PrincipalCredited(source,net,effectiveBasis);
    }
    function _state() internal view returns(ICoreRead03.State memory s) {s=reader.state(address(this),0);if(s.sizeDecimals>6||s.quantity<0||s.isolated)revert Restricted();}
    function _size(ICoreRead03.State memory s) internal pure returns(uint64) {
        uint256 n=uint256(uint64(s.quantity))*10**(8-s.sizeDecimals);if(n>type(uint64).max)revert Restricted();return uint64(n);
    }
    function _start(PendingKind k,uint256 amount,ICoreRead03.State memory s) internal {
        if(pending!=PendingKind.NONE)revert Unresolved();operationNonce++;
        operation=keccak256(abi.encode(block.chainid,address(this),operationNonce,k));pending=k;pendingAmount=amount;sentCoreBlock=s.coreBlock;sentAt=uint64(block.timestamp);cashBefore=s.cashE6;
        emit OperationQueued(operation,k,amount);
    }
    function _sendSetup() private {
        writer.sendRawAction(abi.encodeWithSelector(bytes4(0x01000010),address(this),uint8(1)));
        exit.configureCore();recoveryExit.configureCore();
    }
    function configureCore() external nonReentrant {
        if(paused||recoveryOnly||setupComplete)revert Restricted();
        ICoreRead03.State memory st=_state();
        if(!st.exists||!reader.state(address(exit),0).exists||!reader.state(address(recoveryExit),0).exists)revert Restricted();
        _start(PendingKind.SETUP,0,st);
        _sendSetup();
    }
    function retrySetup() external nonReentrant {
        if(msg.sender!=guardian||paused||recoveryOnly||pending!=PendingKind.SETUP||block.timestamp<sentAt+30)revert Restricted();
        // Setting the same fixed mode is idempotent. No deposit/order can be retried here.
        sentAt=uint64(block.timestamp);sentCoreBlock=_state().coreBlock;
        _sendSetup();
        emit OperationQueued(operation,PendingKind.SETUP,0);
    }
    function settleSetup(uint64 coreBlock,uint64 deadline,bytes32 evidence,bytes calldata sig) external {
        if(pending!=PendingKind.SETUP)revert Restricted();
        _attest(keccak256(abi.encode("SETUP_DISABLED",address(exit),address(recoveryExit))),coreBlock,deadline,evidence,sig);
        setupComplete=true;pending=PendingKind.NONE;emit OperationSettled(operation,PendingKind.SETUP,evidence);
    }
    function fund() external nonReentrant {
        if(paused||recoveryOnly||!setupComplete||nativePrincipalE6==0)revert Restricted();
        ICoreRead03.State memory s=_state();if(s.quantity!=0)revert Restricted();
        uint256 amount=nativePrincipalE6;if(amount<2e6||amount>uint256(uint64(type(int64).max)))revert Restricted();
        _start(PendingKind.DEPOSIT,amount,s);(spotBeforeE8,)=reader.spot(address(this),0);nativePrincipalE6=0;nativeBasisE6=0;
        uint256 beforeBalance=usdc.balanceOf(address(this));usdc.forceApprove(address(depositWallet),amount);depositWallet.depositFor(address(this),amount,CoreEncoding.SPOT);usdc.forceApprove(address(depositWallet),0);
        if(beforeBalance-usdc.balanceOf(address(this))!=amount)revert Restricted();
    }
    function _attest(bytes32 payload,uint64 coreBlock,uint64 deadline,bytes32 evidence,bytes calldata sig) internal view {
        if(coreBlock<=sentCoreBlock||reader.state(address(this),0).coreBlock<coreBlock)revert Unresolved();
        settlement.verify(address(this),operation,payload,coreBlock,deadline,evidence,sig);
    }
    function settleDeposit(uint64 creditedE6,uint64 feeE6,uint64 coreBlock,uint64 deadline,bytes32 evidence,bytes calldata sig) external {
        if(pending!=PendingKind.DEPOSIT||uint256(creditedE6)+feeE6!=pendingAmount||feeE6>2e6||creditedE6==0)revert Restricted();
        _attest(keccak256(abi.encode("DEPOSIT",creditedE6,feeE6)),coreBlock,deadline,evidence,sig);
        ICoreRead03.State memory s=_state();(uint64 balance,)=reader.spot(address(this),0);
        if(!s.exists||s.quantity!=0||uint256(balance)<uint256(spotBeforeE8)+uint256(creditedE6)*100)revert Unresolved();
        unallocatedSpotE6+=creditedE6;pending=PendingKind.NONE;emit OperationSettled(operation,PendingKind.DEPOSIT,evidence);
    }
    function moveToPerp() external nonReentrant {
        if(paused||recoveryOnly||unallocatedSpotE6==0||pending!=PendingKind.NONE)revert Restricted();
        ICoreRead03.State memory s=_state();(uint64 balance,uint64 hold)=reader.spot(address(this),0);
        uint256 amount=unallocatedSpotE6;if(s.quantity!=0||uint256(balance)-hold<amount*100||amount>type(uint64).max)revert Restricted();
        _start(PendingKind.MOVE_TO_PERP,amount,s);spotBeforeE8=balance;unallocatedSpotE6=0;
        writer.sendRawAction(abi.encodeWithSelector(bytes4(0x01000007),uint64(amount),true));
    }
    function settleClassTransfer(uint64 creditedE6,uint64 feeE6,uint64 coreBlock,uint64 deadline,bytes32 evidence,bytes calldata sig) external {
        if(pending!=PendingKind.MOVE_TO_PERP||uint256(creditedE6)+feeE6!=pendingAmount||feeE6>2e6||creditedE6==0)revert Restricted();
        _attest(keccak256(abi.encode("CLASS_TRANSFER",creditedE6,feeE6)),coreBlock,deadline,evidence,sig);
        ICoreRead03.State memory s=_state();(uint64 balance,)=reader.spot(address(this),0);
        if(s.quantity!=0||int256(s.cashE6)<int256(cashBefore)+int256(uint256(creditedE6))||uint256(balance)+pendingAmount*100<spotBeforeE8)revert Unresolved();
        pending=PendingKind.NONE;emit OperationSettled(operation,PendingKind.MOVE_TO_PERP,evidence);
    }
    function rejectClassTransfer(uint64 coreBlock,uint64 deadline,bytes32 evidence,bytes calldata sig) external {
        if(pending!=PendingKind.MOVE_TO_PERP)revert Restricted();
        _attest(keccak256(abi.encode("CLASS_REJECTED",pendingAmount)),coreBlock,deadline,evidence,sig);
        (uint64 balance,)=reader.spot(address(this),0);
        if(_state().cashE6!=cashBefore||balance!=spotBeforeE8)revert Unresolved();
        unallocatedSpotE6+=pendingAmount;pending=PendingKind.NONE;emit OperationSettled(operation,PendingKind.MOVE_TO_PERP,evidence);
    }
    function _loss(ICoreRead03.State memory s) internal view returns(bool) {
        // These transfers start only while flat. Their temporarily missing balance is not a loss.
        if(costBasisE6==0||pending==PendingKind.DEPOSIT||pending==PendingKind.MOVE_TO_PERP)return false;
        uint256 value=nativePrincipalE6+unallocatedSpotE6;
        if(s.equityE6>=0)value+=uint256(uint64(s.equityE6));
        else{uint256 debt=uint256(-int256(s.equityE6));value=debt>=value?0:value-debt;}
        return value+lossStopE6<=costBasisE6;
    }
    function pause() external {if(msg.sender!=guardian)revert Restricted();_pause(false);}
    function _pause(bool recovery) internal {paused=true;if(recovery)recoveryOnly=true;emit Paused(recoveryOnly,uint64(block.timestamp));}
    function previewOrder(bool buy) public view returns(uint64 priceE8,uint64 sizeE8) {
        ICoreRead03.State memory s=_state();uint256 px=uint256(s.oracleE8)*(buy?10000+slippageBps:10000-slippageBps)/10000;
        px=buy?((px+1e8-1)/1e8)*1e8:(px/1e8)*1e8;if(px==0||px>type(uint64).max)revert Restricted();
        uint256 size;
        if(buy){
            if(!s.exists||s.quantity!=0||unallocatedSpotE6!=0||s.equityE6<=0||_loss(s))revert Restricted();
            uint256 budget=uint256(uint64(s.equityE6))*100/101;if(budget>maxOrderE6)budget=maxOrderE6;
            uint256 step=10**(8-s.sizeDecimals);size=(budget*1e10/px/step)*step;
            if(size*px/1e10<10e6)revert Restricted();
        }else{size=_size(s);if(size==0)revert Restricted();}
        if(size>type(uint64).max)revert Restricted();return(uint64(px),uint64(size));
    }
    function execute(uint64 commit) external nonReentrant {
        if(pending!=PendingKind.NONE)revert Unresolved();
        if(recoveryOnly||commit!=registry.nonce()||commit<=lastCommit||registry.deadline()<block.timestamp)revert Restricted();
        uint8 side=registry.side();lastCommit=commit;if(side==0)return;
        bool buy=side==1;ICoreRead03.State memory s=_state();
        uint256 ref=registry.referencePriceE8();uint256 px=s.oracleE8;
        if((px>ref?px-ref:ref-px)*10000>ref*slippageBps)revert Restricted();
        if(buy&&(paused||block.timestamp<lastOrderAt+orderCooldown))revert Restricted();
        uint256 today=block.timestamp/1 days;if(day!=today){day=today;ordersToday=0;}
        if(buy&&ordersToday>=maxOrdersPerDay)revert Restricted();
        (uint64 limit,uint64 size)=previewOrder(buy);_order(buy,limit,size,s);lastOrderAt=uint64(block.timestamp);ordersToday++;
    }
    function _order(bool buy,uint64 limit,uint64 size,ICoreRead03.State memory s) internal {
        _start(PendingKind.ORDER,size,s);pendingBuy=buy;positionBeforeE8=_size(s);entryBeforeE6=s.entryNotionalE6;limitPriceE8=limit;
        cloid=uint128(uint256(operation));if(cloid==0)revert Restricted();
        writer.sendRawAction(abi.encodeWithSelector(bytes4(0x01000001),uint32(0),buy,limit,size,!buy,uint8(3),cloid));
        emit OrderQueued(operation,cloid,buy,size,limit);
    }
    function settleOrder(OrderReceipt calldata r,uint64 coreBlock,uint64 deadline,bytes32 evidence,bytes calldata sig) external {
        if(pending!=PendingKind.ORDER||r.status<1||r.status>4||r.filledE8>pendingAmount||
           (r.status==1&&r.filledE8!=pendingAmount)||(r.status==3&&r.filledE8!=0))revert Restricted();
        _attest(keccak256(abi.encode("ORDER",cloid,r)),coreBlock,deadline,evidence,sig);
        uint256 expected=pendingBuy?uint256(positionBeforeE8)+r.filledE8:uint256(positionBeforeE8)-r.filledE8;
        ICoreRead03.State memory afterState=_state();
        if(expected!=r.finalPositionE8||_size(afterState)!=r.finalPositionE8)revert Unresolved();
        if(r.filledE8==0){if(r.averagePriceE8!=0||r.closedPnlE6!=0||r.feeE6!=0)revert Restricted();}
        else{
            if(r.averagePriceE8==0||(pendingBuy?r.averagePriceE8>limitPriceE8:r.averagePriceE8<limitPriceE8))revert Restricted();
            if(pendingBuy){if(r.closedPnlE6!=0)revert Restricted();}
            else{
                if(afterState.entryNotionalE6>entryBeforeE6)revert Unresolved();
                // Native remaining entry cost accounts for venue rounding across partial fills.
                int256 expectedPnl=int256(uint256(r.filledE8)*r.averagePriceE8/1e10)-int256(uint256(entryBeforeE6-afterState.entryNotionalE6));
                int256 difference=expectedPnl-r.closedPnlE6;if(difference>10||difference< -10)revert Restricted();
            }
            if(r.feeE6>uint256(r.filledE8)*r.averagePriceE8/1e10)revert Restricted();
        }
        tradingNetE6+=r.closedPnlE6-int256(uint256(r.feeE6));pending=PendingKind.NONE;
        if(_loss(_state()))_pause(false);
        emit OperationSettled(operation,PendingKind.ORDER,evidence);
    }
    function cancelAndPause() external nonReentrant {
        ICoreRead03.State memory s=_state();if(msg.sender!=guardian&&!_loss(s))revert Restricted();_pause(false);
        if(pending==PendingKind.ORDER)writer.sendRawAction(abi.encodeWithSelector(bytes4(0x0100000b),uint32(0),cloid));
    }
    function emergencyClose() external nonReentrant {
        ICoreRead03.State memory s=_state();if(!paused&&!_loss(s))revert Restricted();_pause(false);
        if(pending!=PendingKind.NONE)revert Unresolved();(uint64 limit,uint64 size)=previewOrder(false);_order(false,limit,size,s);
    }
    function bookCost(bytes32 id,int256 delta,bool trading,uint64 coreBlock,uint64 deadline,bytes32 evidence,bytes calldata sig) external {
        if(id==0||bookedEvents[id]||coreBlock>reader.state(address(this),0).coreBlock||(!trading&&delta<0))revert Restricted();
        settlement.verify(address(this),id,keccak256(abi.encode("COST",delta,trading)),coreBlock,deadline,evidence,sig);
        bookedEvents[id]=true;if(trading)tradingNetE6+=delta;else operatingCostE6+=uint256(delta);
        emit CostBooked(id,delta,trading);
    }
    function availableProfit() public view returns(uint256) {
        ICoreRead03.State memory s=_state();
        if(accountingQuarantined||pending!=PendingKind.NONE||s.quantity!=0||nativePrincipalE6!=0||unallocatedSpotE6!=0||s.equityE6<=0||tradingNetE6<=0)return 0;
        uint256 earned=uint256(tradingNetE6);if(earned<=profitSentE6+operatingCostE6)return 0;earned-=profitSentE6+operatingCostE6;
        uint256 equity=uint256(uint64(s.equityE6));if(equity<=costBasisE6+operatingCostE6)return 0;
        uint256 excess=equity-costBasisE6-operatingCostE6;return earned<excess?earned:excess;
    }
    function requestExit(uint256 amount,bool recovery) external nonReentrant {
        ICoreRead03.State memory s=_state();if(pending!=PendingKind.NONE||s.quantity!=0||!s.exists||amount==0||amount>type(uint64).max/100)revert Restricted();
        if(recovery){if(msg.sender!=guardian||s.equityE6<=0||amount>uint256(uint64(s.equityE6))||unallocatedSpotE6!=0||amount>costBasisE6-nativeBasisE6)revert Restricted();_pause(true);}
        else{if(amount>availableProfit())revert Restricted();profitSentE6+=amount;}
        _start(PendingKind.EXIT,amount,s);positionBeforeE8=0;exitKind=recovery?2:1;CoreExit chosen=recovery?recoveryExit:exit;chosen.expect(operation,exitKind,amount);
        writer.sendRawAction(CoreEncoding.sendAsset(address(chosen),0,CoreEncoding.SPOT,uint64(amount*100)));
        emit ProfitRequested(operation,amount,exitKind);
    }
    function settleExit(uint64 netE6,uint64 feeE6,uint64 coreBlock,uint64 deadline,bytes32 evidence,bytes calldata sig) external {
        if(pending!=PendingKind.EXIT||uint256(netE6)+feeE6!=pendingAmount||netE6==0||feeE6>2e6)revert Restricted();
        _attest(keccak256(abi.encode("EXIT",netE6,feeE6)),coreBlock,deadline,evidence,sig);
        ICoreRead03.State memory s=_state();if(s.quantity!=0)revert Unresolved();
        if(positionBeforeE8==type(uint64).max){(uint64 balance,)=reader.spot(address(this),0);if(uint256(balance)+pendingAmount*100<spotBeforeE8)revert Unresolved();}
        else if(int256(s.cashE6)<int256(cashBefore)-int256(pendingAmount))revert Unresolved();
        (exitKind==2?recoveryExit:exit).confirmCore(netE6);if(exitKind==2){uint256 n=pendingAmount>costBasisE6?costBasisE6:pendingAmount;costBasisE6-=n;}
        pending=PendingKind.NONE;emit OperationSettled(operation,PendingKind.EXIT,evidence);
    }
    function rejectExit(uint64 coreBlock,uint64 deadline,bytes32 evidence,bytes calldata sig) external {
        if(pending!=PendingKind.EXIT)revert Restricted();
        _attest(keccak256(abi.encode("EXIT_REJECTED",pendingAmount,exitKind)),coreBlock,deadline,evidence,sig);
        CoreExit chosen=exitKind==2?recoveryExit:exit;
        (uint64 balance,)=reader.spot(address(chosen),0);
        if(_state().cashE6!=cashBefore||uint256(balance)!=chosen.coreBefore())revert Unresolved();
        if(positionBeforeE8==type(uint64).max){
            (uint64 ownSpot,)=reader.spot(address(this),0);if(ownSpot!=spotBeforeE8)revert Unresolved();
            unallocatedSpotE6+=pendingAmount;
        }
        chosen.emergencyRecover(true);
        if(exitKind==1)profitSentE6-=pendingAmount;pending=PendingKind.NONE;
        emit OperationSettled(operation,PendingKind.EXIT,evidence);
    }
    function quarantineUnknown(bytes32 evidence) external {
        if(msg.sender!=guardian||!paused||evidence==0||
           reader.state(address(this),0).coreBlock<=sentCoreBlock+100)revert Restricted();
        // This is openly marked emergency recovery, never an assertion of a venue fill.
        // Conservatively retire reserved recovery principal even if the receipt is missing.
        // Otherwise the same basis could authorize a second recovery of trading profit.
        if(pending==PendingKind.EXIT&&exitKind==2){
            uint256 retired=pendingAmount>costBasisE6?costBasisE6:pendingAmount;costBasisE6-=retired;
        }
        accountingQuarantined=true;
        // New trading and profit extraction remain permanently disabled after unknown accounting.
        _pause(true);pending=PendingKind.NONE;emit EmergencyQuarantine(operation,evidence);
    }
    function recoverExit(bool isRecovery,bool allowReset) external {
        if(msg.sender!=guardian||!recoveryOnly)revert Restricted();
        (isRecovery?recoveryExit:exit).emergencyRecover(allowReset);
    }
    function recoverSpot(uint256 amount) external nonReentrant {
        if(msg.sender!=guardian||pending!=PendingKind.NONE||amount==0||amount>costBasisE6-nativeBasisE6||(!accountingQuarantined&&amount>unallocatedSpotE6)||amount>type(uint64).max/100)revert Restricted();
        (uint64 balance,uint64 hold)=reader.spot(address(this),0);if(uint256(balance)-hold<amount*100)revert Restricted();
        _pause(true);ICoreRead03.State memory state_=_state();_start(PendingKind.EXIT,amount,state_);exitKind=2;
        positionBeforeE8=type(uint64).max;spotBeforeE8=balance;
        if(amount<=unallocatedSpotE6)unallocatedSpotE6-=amount;else unallocatedSpotE6=0;
        recoveryExit.expect(operation,2,amount);writer.sendRawAction(CoreEncoding.sendAsset(address(recoveryExit),CoreEncoding.SPOT,CoreEncoding.SPOT,uint64(amount*100)));
        emit ProfitRequested(operation,amount,2);
    }
    function recoverNative() external nonReentrant {
        if(msg.sender!=guardian||pending!=PendingKind.NONE||_state().quantity!=0)revert Restricted();
        _pause(true);
        uint256 amount=accountingQuarantined?usdc.balanceOf(address(this)):nativePrincipalE6;
        if(amount>costBasisE6)amount=costBasisE6;
        if(amount==0||amount>usdc.balanceOf(address(this)))revert Restricted();
        operationNonce++;bytes32 op=keccak256(abi.encode(block.chainid,address(this),"NATIVE_RECOVERY",operationNonce));
        costBasisE6-=amount;nativeBasisE6=0;nativePrincipalE6=0;
        usdc.safeTransfer(address(recoveryExit),amount);recoveryExit.acceptNative(op,amount);
        emit ProfitRequested(op,amount,2);
    }
    function fundCoreGas() external payable nonReentrant {
        if(msg.value<1e10||msg.value%1e10!=0)revert Restricted();
        (bool ok,)=CoreEncoding.HYPE_SYSTEM.call{value:msg.value}("");if(!ok)revert Restricted();
    }
    function _reserveContext() internal view override returns(IERC20,ICoreRead03,ICoreWriter03,address) {
        ICoreRead03.State memory s=_state();
        if(!paused||pending!=PendingKind.NONE||nativePrincipalE6!=0||unallocatedSpotE6!=0||s.quantity!=0||s.cashE6!=0)revert ReserveUnavailable();
        return(usdc,reader,writer,guardian);
    }

}
