// SPDX-License-Identifier: MIT
pragma solidity ^0.8.30;
import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {SafeERC20} from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import {ReentrancyGuard} from "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import {StablePoolSwap} from "./StablePoolSwap.sol";
import {HopSwap} from "./HopSwap.sol";
import {IV3Pool,IV2Pair,IV2Router,IIgnixManager,IReturnReceiver} from "./ProtocolTypes.sol";
/// @notice Only authenticated profit enters the buyback budgets. TWAP warms after graduation.
contract ProfitBuyback is StablePoolSwap,HopSwap,ReentrancyGuard,IReturnReceiver {
    using SafeERC20 for IERC20;
    address public constant DEAD=0x000000000000000000000000000000000000dEaD;
    address public immutable ingress;address public immutable guardian;address public immutable projectToken;
    IIgnixManager public immutable manager;IV2Router public immutable router;
    uint32 public immutable window;uint16 public immutable haircutBps;uint16 public immutable maxReserveShareBps;uint256 public immutable maxBatch;uint256 public immutable maxQuoteBatch;
    uint256 public escrowedTokens;uint256 public nativeBudget;uint256 public usd0Buffer;uint256 public quoteBudget;uint256 public totalQuoteSpent;uint256 public totalTokensSentDead;bool public paused;
    IV2Pair public pair;bool public quoteIs0;uint256 public lastCumulative;uint32 public lastTimestamp;uint256 public averageQ112;uint64 public averageUpdatedAt;uint8 public oracleKind;uint256 public pendingCurveQ112;
    error Restricted();error OracleNotReady();
    event ProfitCredited(bytes32 indexed source,uint256 net);
    event ProfitConverted(uint256 nativeUsdc,uint256 usd0Mid,uint256 quoteOut);
    event OracleObserved(uint256 averageQ112,uint32 secondsElapsed);
    event BoughtIntoEscrow(uint256 quoteSpent,uint256 tokenAmount,uint256 minimum);
    event EscrowSentDead(uint256 sent,uint256 receivedAtDead);
    event BoughtBack(uint256 quoteSpent,uint256 receivedAtDead,uint256 minimum);
    constructor(IV3Pool pool,IERC20 u,IERC20 t,address hop,address spender,IERC20 quoteToken,IERC20 wrappedOkb,address i,address g,address token,IIgnixManager m,IV2Router r,uint256 maxAmount,uint256 maxQuote,uint32 period,uint16 haircut,uint16 reserveShare,address executor)
        StablePoolSwap(pool,u,t,50) HopSwap(hop,spender,quoteToken,wrappedOkb,t,executor) {
        if(i==address(0)||g==address(0)||token==address(0)||address(m).code.length==0||address(r).code.length==0||maxAmount==0||maxQuote==0||period<600||haircut>1500||reserveShare==0||reserveShare>100)revert Restricted();
        ingress=i;guardian=g;projectToken=token;manager=m;router=r;maxBatch=maxAmount;maxQuoteBatch=maxQuote;window=period;haircutBps=haircut;maxReserveShareBps=reserveShare;
    }
    function pause() external {if(msg.sender!=guardian)revert Restricted();paused=true;}
    function resume() external {if(msg.sender!=guardian)revert Restricted();paused=false;}
    function creditReturn(uint256 amount,uint8 kind,bytes32 id) external {
        if(msg.sender!=ingress||kind!=1||amount==0||usdc.balanceOf(address(this))<nativeBudget+amount)revert Restricted();
        nativeBudget+=amount;emit ProfitCredited(id,amount);
    }
    function convertProfit(uint256 amount) external nonReentrant {
        if(paused||amount==0||amount>nativeBudget||amount>maxBatch)revert Restricted();
        nativeBudget-=amount;uint256 mid=_swapStable(false,amount);
        if(address(quote)==address(usd0)){quoteBudget+=mid;emit ProfitConverted(amount,mid,mid);return;}
        usd0Buffer+=mid;emit ProfitConverted(amount,mid,0);
    }
    function hopProfit(uint256 minQuote,bytes calldata hopCall) external nonReentrant {
        if(paused||usd0Buffer==0||address(quote)==address(usd0))revert Restricted();
        uint256 mid=usd0Buffer;usd0Buffer=0;uint256 out=_hop(usd0,quote,mid,minQuote,hopCall);quoteBudget+=out;
        emit ProfitConverted(0,mid,out);
    }
    function _bind() internal {
        address p=manager.pairOf(projectToken);if(p.code.length==0)revert OracleNotReady();
        if(address(pair)!=address(0)){if(p!=address(pair))revert Restricted();return;}
        IV2Pair v=IV2Pair(p);address t0=v.token0();address t1=v.token1();
        if(!((t0==address(quote)&&t1==projectToken)||(t1==address(quote)&&t0==projectToken)))revert Restricted();
        pair=v;quoteIs0=t0==address(quote);
    }
    function _current() internal view returns(uint256 cumulative,uint32 stamp,uint112 quoteReserve) {
        (uint112 r0,uint112 r1,uint32 then)=pair.getReserves();if(r0==0||r1==0)revert OracleNotReady();
        stamp=uint32(block.timestamp);cumulative=quoteIs0?pair.price0CumulativeLast():pair.price1CumulativeLast();quoteReserve=quoteIs0?r0:r1;
        uint32 elapsed;unchecked {elapsed=stamp-then;cumulative+=(uint256(quoteIs0?r1:r0)<<112)/uint256(quoteIs0?r0:r1)*elapsed;}
    }
    function observe() external {
        if(manager.pairOf(projectToken)==address(0)){
            IIgnixManager.Curve memory c=manager.tokens(projectToken);
            if(c.creator==address(0)||c.quote!=address(quote)||c.vQuote==0||c.vToken==0||c.poolId!=bytes32(0))revert OracleNotReady();
            uint256 ratio=(uint256(c.vToken)<<112)/c.vQuote;uint32 now_=uint32(block.timestamp);
            if(oracleKind!=1){oracleKind=1;pendingCurveQ112=ratio;lastTimestamp=now_;averageQ112=0;return;}
            uint32 elapsed;unchecked{elapsed=now_-lastTimestamp;}if(elapsed<window)revert OracleNotReady();
            averageQ112=pendingCurveQ112;pendingCurveQ112=ratio;averageUpdatedAt=uint64(block.timestamp);lastTimestamp=now_;
            emit OracleObserved(averageQ112,elapsed);return;
        }
        _bind();if(oracleKind!=2){oracleKind=2;lastTimestamp=0;averageQ112=0;}(uint256 cumulative,uint32 now_,)=_current();
        if(lastTimestamp==0){lastCumulative=cumulative;lastTimestamp=now_;return;}
        uint32 elapsed;uint256 delta;unchecked {elapsed=now_-lastTimestamp;delta=cumulative-lastCumulative;}
        if(elapsed<window)revert OracleNotReady();
        averageQ112=delta/elapsed;averageUpdatedAt=uint64(block.timestamp);lastCumulative=cumulative;lastTimestamp=now_;
        emit OracleObserved(averageQ112,elapsed);
    }
    function buyback(uint256 amount) external nonReentrant {
        if(paused||amount==0||amount>quoteBudget||amount>maxQuoteBatch)revert Restricted();
        bool curve=manager.pairOf(projectToken)==address(0);
        if(averageQ112==0||block.timestamp>averageUpdatedAt+window*2||oracleKind!=(curve?1:2))revert OracleNotReady();
        uint256 reserve;
        if(curve){
            IIgnixManager.Curve memory c=manager.tokens(projectToken);
            if(c.quote!=address(quote)||c.vQuote==0||c.vToken==0||c.poolId!=bytes32(0))revert Restricted();
            reserve=c.vQuote;
        }else{_bind();(,,uint112 r)=_current();reserve=r;}
        if(amount>reserve*maxReserveShareBps/10000)revert Restricted();
        uint256 minimum=((amount*averageQ112)>>112)*(10000-haircutBps)/10000;if(minimum==0)revert OracleNotReady();
        uint256 boughtToEscrow=0;
        uint256 beforeToken=IERC20(projectToken).balanceOf(DEAD);uint256 beforeQuote=quote.balanceOf(address(this));quoteBudget-=amount;
        if(curve){
            uint256 beforeSelf=IERC20(projectToken).balanceOf(address(this));
            quote.forceApprove(address(manager),amount);manager.buy(projectToken,amount,0);quote.forceApprove(address(manager),0);
            uint256 received=IERC20(projectToken).balanceOf(address(this))-beforeSelf;if(received==0)revert Restricted();
            boughtToEscrow=received;
        }else{
            address[] memory path=new address[](2);path[0]=address(quote);path[1]=projectToken;
            quote.forceApprove(address(router),amount);
            router.swapExactTokensForTokensSupportingFeeOnTransferTokens(amount,minimum,path,DEAD,block.timestamp+60);
            quote.forceApprove(address(router),0);
        }
        uint256 spent=beforeQuote-quote.balanceOf(address(this));if(spent==0||spent>amount)revert Restricted();
        if(spent<amount){quoteBudget+=amount-spent;minimum=((spent*averageQ112)>>112)*(10000-haircutBps)/10000;}
        totalQuoteSpent+=spent;
        if(curve){if(boughtToEscrow<minimum)revert Restricted();escrowedTokens+=boughtToEscrow;emit BoughtIntoEscrow(spent,boughtToEscrow,minimum);}
        else{uint256 got=IERC20(projectToken).balanceOf(DEAD)-beforeToken;if(got<minimum)revert Restricted();totalTokensSentDead+=got;emit BoughtBack(spent,got,minimum);}
    }
    function flushEscrow() external nonReentrant {
        if(manager.pairOf(projectToken)==address(0)||escrowedTokens==0)revert Restricted();
        uint256 amount=escrowedTokens;uint256 beforeDead=IERC20(projectToken).balanceOf(DEAD);escrowedTokens=0;
        IERC20(projectToken).safeTransfer(DEAD,amount);
        uint256 got=IERC20(projectToken).balanceOf(DEAD)-beforeDead;
        if(got<amount*(10000-haircutBps)/10000)revert Restricted();
        totalTokensSentDead+=got;emit EscrowSentDead(amount,got);
    }

}
