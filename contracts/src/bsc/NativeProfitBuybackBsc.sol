// SPDX-License-Identifier: MIT
pragma solidity ^0.8.30;
import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {SafeERC20} from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import {ReentrancyGuard} from "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
interface IFlapFactoryBsc {function vaultOf(address) external view returns(address);}
interface ITaxVaultBsc {function creator() external view returns(address);function taxToken() external view returns(address);}
interface ITaxTokenBsc {function state() external view returns(uint8);function buyTaxRate() external view returns(uint16);function sellTaxRate() external view returns(uint16);function v2Router() external view returns(address);}
interface IFlapTradeBsc {
    struct Exact {address inputToken;address outputToken;uint256 inputAmount;uint256 minOutputAmount;bytes permitData;}
    struct Quote {address inputToken;address outputToken;uint256 inputAmount;}
    function swapExactInput(Exact calldata) external payable returns(uint256);
    function quoteExactInput(Quote calldata) external returns(uint256);
}
interface IRouterBsc {
    function WETH() external view returns(address);
    function getAmountsOut(uint256,address[] calldata) external view returns(uint256[] memory);
    function swapExactETHForTokensSupportingFeeOnTransferTokens(uint256,address[] calldata,address,uint256) external payable;
}
/// @notice Owner-funded, fixed-token profit buyback. Cross-chain profit provenance is verified by the keeper, not this contract.
contract NativeProfitBuybackBsc is ReentrancyGuard {
    using SafeERC20 for IERC20;
    address public constant DEAD=0x000000000000000000000000000000000000dEaD;
    address public immutable dev;address public immutable guardian;IFlapFactoryBsc public immutable factory;IFlapTradeBsc public immutable portal;IRouterBsc public immutable router;
    address public projectToken;bool public paused;uint256 public nativeBudget;uint256 public escrowedTokens;uint256 public totalTokensSentDead;uint256 public totalBnbSpent;
    mapping(bytes32=>bool) public funded;uint256 public constant PROBE=1e14;uint32 public constant window=600;
    uint256 public pendingRate;uint256 public anchorRate;uint64 public lastObservation;uint64 public anchorAt;uint8 public observedState;
    event Bound(address indexed token,address indexed vault);event ProfitFunded(bytes32 indexed source,uint256 amount);event Bought(uint256 bnb,uint256 tokens,bool escrow);event Burned(uint256 tokens);
    constructor(address d,address g,IFlapFactoryBsc f,IFlapTradeBsc p,IRouterBsc r){require(block.chainid==56&&d!=address(0)&&g!=address(0)&&address(f).code.length>0&&address(p).code.length>0&&address(r).code.length>0);dev=d;guardian=g;factory=f;portal=p;router=r;}
    receive() external payable {require(msg.sender==address(portal)||msg.sender==address(router),"ONLY_SWAP_REFUND");}
    function bind(address token) external {
        require(msg.sender==dev&&projectToken==address(0)&&token.code.length>0,"BIND_RESTRICTED");
        address v=factory.vaultOf(token);require(v.code.length>0&&ITaxVaultBsc(v).creator()==dev&&ITaxVaultBsc(v).taxToken()==token,"WRONG_VAULT");
        require(ITaxTokenBsc(token).buyTaxRate()==100&&ITaxTokenBsc(token).sellTaxRate()==100&&ITaxTokenBsc(token).v2Router()==address(router),"WRONG_TOKEN");
        projectToken=token;emit Bound(token,v);
    }
    function pause(bool value) external {require(msg.sender==guardian);paused=value;}
    function fundProfit(bytes32 source) external payable {require(msg.sender==dev&&projectToken!=address(0)&&msg.value>0&&source!=0&&!funded[source]);funded[source]=true;nativeBudget+=msg.value;emit ProfitFunded(source,msg.value);}
    function _path() internal view returns(address[] memory p){p=new address[](2);p[0]=router.WETH();p[1]=projectToken;}
    function _quote(uint256 amount,uint8 state_) internal returns(uint256) {
        require(state_!=1,"MIGRATING");
        if(state_==0)return portal.quoteExactInput(IFlapTradeBsc.Quote(address(0),projectToken,amount));
        uint256[] memory n=router.getAmountsOut(amount,_path());return n[1];
    }
    function quoteFor(uint256 amount) external returns(uint256) {require(projectToken!=address(0));return _quote(amount,ITaxTokenBsc(projectToken).state());}
    function observe() external nonReentrant {
        require(projectToken!=address(0));uint8 state_=ITaxTokenBsc(projectToken).state();uint8 phase=state_==0?0:2;uint256 rate=_quote(PROBE,state_);require(rate>0);
        if(lastObservation==0||observedState!=phase){pendingRate=rate;lastObservation=uint64(block.timestamp);observedState=phase;anchorRate=0;return;}
        require(block.timestamp>=lastObservation+window);anchorRate=pendingRate;anchorAt=uint64(block.timestamp);pendingRate=rate;lastObservation=uint64(block.timestamp);
    }
    function buy(uint256 amount,uint256 minimum) external nonReentrant {
        require(msg.sender==dev&&!paused&&amount>0&&amount<=nativeBudget&&anchorRate>0&&block.timestamp<=anchorAt+window*2);
        uint8 state_=ITaxTokenBsc(projectToken).state();require(state_!=1&&(state_==0?0:2)==observedState,"PHASE_CHANGED");
        uint256 floor=amount*anchorRate/PROBE*90/100;require(floor>0&&minimum>=floor&&_quote(amount,state_)>=minimum,"PRICE_BOUND");
        uint256 beforeNative=address(this).balance;nativeBudget-=amount;uint256 beforeBalance=IERC20(projectToken).balanceOf(state_==0?address(this):DEAD);
        if(state_==0)portal.swapExactInput{value:amount}(IFlapTradeBsc.Exact(address(0),projectToken,amount,minimum,""));
        else router.swapExactETHForTokensSupportingFeeOnTransferTokens{value:amount}(minimum,_path(),DEAD,block.timestamp+60);
        uint256 got=IERC20(projectToken).balanceOf(state_==0?address(this):DEAD)-beforeBalance;require(got>=minimum,"OUTPUT_MISMATCH");
        uint256 spent=beforeNative-address(this).balance;require(spent>0&&spent<=amount);nativeBudget+=amount-spent;
        totalBnbSpent+=spent;if(state_==0)escrowedTokens+=got;else totalTokensSentDead+=got;emit Bought(spent,got,state_==0);
    }
    function flushEscrow() external nonReentrant {
        require(projectToken!=address(0)&&ITaxTokenBsc(projectToken).state()>=2&&escrowedTokens>0);
        uint256 n=escrowedTokens;uint256 beforeBalance=IERC20(projectToken).balanceOf(DEAD);escrowedTokens=0;IERC20(projectToken).safeTransfer(DEAD,n);
        uint256 got=IERC20(projectToken).balanceOf(DEAD)-beforeBalance;require(got>=n*90/100);totalTokensSentDead+=got;emit Burned(got);
    }
}
