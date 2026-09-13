// SPDX-License-Identifier: MIT
pragma solidity ^0.8.30;
import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {SafeERC20} from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import {ReentrancyGuard} from "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import {ICoreRead03,ICoreWriter03,ICctpMessenger,CoreEncoding} from "./ProtocolTypes.sol";
import {CctpMessage} from "./CctpMessage.sol";
/// @notice Segregated exit. It never receives normal tax deposits; destinations are immutable.
contract CoreExit is ReentrancyGuard {
    using SafeERC20 for IERC20;
    enum Stage {IDLE,EXPECTING_CORE,CORE_READY,EVM_PENDING,NATIVE_READY}
    address public immutable parent;IERC20 public immutable usdc;ICoreRead03 public immutable reader;ICoreWriter03 public immutable writer;ICctpMessenger public immutable messenger;
    address public immutable ingress;address public immutable profitReceiver;address public immutable recoveryReceiver;uint32 public immutable returnDomain;uint16 public immutable feeBps;uint8 public immutable fixedKind;
    Stage public stage;bytes32 public operation;uint8 public kind;uint256 public amount;uint256 public coreBefore;uint256 public evmBefore;uint64 public sentBlock;uint64 public sequence;
    error Restricted();
    event ExitExpected(bytes32 indexed operation,uint8 kind,uint256 grossAmount);
    event CoreReceived(bytes32 indexed operation,uint256 netAmount);
    event EvmBridgeQueued(bytes32 indexed operation,uint256 amount);
    event EvmReceived(bytes32 indexed operation,uint256 amount);
    event ReturnBurned(bytes32 indexed operation,uint8 kind,uint256 amount,uint256 maxFee);
    constructor(address p,IERC20 u,ICoreRead03 r,ICoreWriter03 w,ICctpMessenger m,address i,address profit,address recovery,uint32 d,uint16 f,uint8 fixedKind_) {
        if((fixedKind_!=1&&fixedKind_!=2)||p==address(0)||address(u).code.length==0||address(r).code.length==0||address(w).code.length==0||address(m).code.length==0||i==address(0)||profit==address(0)||recovery==address(0)||f>100)revert Restricted();
        fixedKind=fixedKind_;parent=p;usdc=u;reader=r;writer=w;messenger=m;ingress=i;profitReceiver=profit;recoveryReceiver=recovery;returnDomain=d;feeBps=f;
    }
    function configureCore() external {
        if(msg.sender!=parent||stage!=Stage.IDLE)revert Restricted();
        writer.sendRawAction(abi.encodePacked(uint8(1),uint24(16),abi.encode(address(this),uint8(1))));
    }
    function expect(bytes32 op,uint8 k,uint256 gross) external {
        if(msg.sender!=parent||stage!=Stage.IDLE||op==0||k!=fixedKind||gross==0||gross>type(uint64).max/100)revert Restricted();
        (uint64 balance,)=reader.spot(address(this),0);
        operation=op;kind=k;amount=gross;coreBefore=balance;stage=Stage.EXPECTING_CORE;emit ExitExpected(op,k,gross);
    }
    function confirmCore(uint256 net) external {
        if(msg.sender!=parent||stage!=Stage.EXPECTING_CORE||net==0||net>amount)revert Restricted();
        (uint64 balance,uint64 hold)=reader.spot(address(this),0);
        if(uint256(balance)<coreBefore+net*100||uint256(balance)-hold<net*100)revert Restricted();
        amount=net;stage=Stage.CORE_READY;emit CoreReceived(operation,net);
    }
    function bridgeToEvm() external nonReentrant {
        if(stage!=Stage.CORE_READY)revert Restricted();
        (uint64 balance,uint64 hold)=reader.spot(address(this),0);
        if(uint256(balance)-hold<amount*100)revert Restricted();
        coreBefore=balance;evmBefore=usdc.balanceOf(address(this));sentBlock=reader.state(parent,0).coreBlock;
        stage=Stage.EVM_PENDING;
        writer.sendRawAction(CoreEncoding.sendAsset(CoreEncoding.USDC_SYSTEM,CoreEncoding.SPOT,CoreEncoding.SPOT,uint64(amount*100)));
        emit EvmBridgeQueued(operation,amount);
    }
    function reconcileEvm() external {
        if(stage!=Stage.EVM_PENDING)revert Restricted();
        // Fixed native-USDC budget must be newly available. Extra Core spot donations
        // cannot stall an already delivered withdrawal or increase the return amount.
        if(reader.state(parent,0).coreBlock<=sentBlock||usdc.balanceOf(address(this))<evmBefore+amount)revert Restricted();
        stage=Stage.NATIVE_READY;emit EvmReceived(operation,amount);
    }
    function burnReturn(uint256 maxFee) external nonReentrant {
        if(stage!=Stage.NATIVE_READY||maxFee>=amount||maxFee>amount*feeBps/10000)revert Restricted();
        uint256 value=amount;uint8 k=kind;bytes32 op=operation;sequence++;
        address to=k==1?profitReceiver:recoveryReceiver;
        uint256 beforeBalance=usdc.balanceOf(address(this));
        stage=Stage.IDLE;amount=0;
        usdc.forceApprove(address(messenger),value);
        messenger.depositForBurnWithHook(value,returnDomain,CctpMessage.addressWord(to),address(usdc),CctpMessage.addressWord(ingress),maxFee,2000,CctpMessage.hook(k,0,sequence,op));
        usdc.forceApprove(address(messenger),0);
        if(beforeBalance-usdc.balanceOf(address(this))!=value)revert Restricted();
        emit ReturnBurned(op,k,value,maxFee);
    }
    function acceptNative(bytes32 op,uint256 value) external {
        if(msg.sender!=parent||fixedKind!=2||stage!=Stage.IDLE||value==0||usdc.balanceOf(address(this))<value)revert Restricted();
        operation=op;kind=2;amount=value;stage=Stage.NATIVE_READY;
    }
    function emergencyRecover(bool allowReset) external {
        if(msg.sender!=parent)revert Restricted();
        if(stage==Stage.EXPECTING_CORE){
            (uint64 bal,uint64 held)=reader.spot(address(this),0);
            uint256 delta=uint256(bal)>coreBefore?(uint256(bal)-coreBefore)/100:0;
            if(delta>amount)delta=amount;
            if(delta>0&&uint256(bal)-held>=delta*100){amount=delta;stage=Stage.CORE_READY;emit CoreReceived(operation,delta);}
            else if(allowReset){stage=Stage.IDLE;amount=0;}
            else revert Restricted();
        }else if(stage==Stage.EVM_PENDING){
            (uint64 bal,uint64 held)=reader.spot(address(this),0);
            if(usdc.balanceOf(address(this))>=evmBefore+amount){stage=Stage.NATIVE_READY;}
            else if(allowReset&&uint256(bal)-held>=amount*100){stage=Stage.CORE_READY;}
            else revert Restricted();
        }else revert Restricted();
    }
    function fundCoreGas() external payable nonReentrant {
        if(msg.value<1e10||msg.value%1e10!=0)revert Restricted();
        (bool ok,)=CoreEncoding.HYPE_SYSTEM.call{value:msg.value}("");if(!ok)revert Restricted();
    }
}
