// SPDX-License-Identifier: MIT
pragma solidity ^0.8.30;
import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {SafeERC20} from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import {ReentrancyGuard} from "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import {StablePoolSwap} from "./StablePoolSwap.sol";
import {HopSwap} from "./HopSwap.sol";
import {IV3Pool,ICostTreasury,IIgnixManager} from "./ProtocolTypes.sol";
contract TaxConverter is StablePoolSwap,HopSwap,ReentrancyGuard {
    using SafeERC20 for IERC20;
    ICostTreasury public immutable treasury;
    IIgnixManager public immutable manager;
    address public immutable projectToken;
    address public immutable guardian;
    uint256 public immutable maxBatch;
    bytes4 public immutable claimSelector;
    bool public immutable claimHasRecipient;
    bool public paused;
    error Restricted();
    event Claimed(address indexed vault,uint256 received);
    event Converted(uint256 quoteSpent,uint256 usd0Hopped,uint256 usdcOutput);
    constructor(IV3Pool pool,IERC20 u,IERC20 t,address hop,address spender,IERC20 quoteToken,IERC20 wrappedOkb,ICostTreasury dest,IIgnixManager m,address token,address g,uint256 maxAmount,bytes4 selector,bool hasRecipient,address executor)
        StablePoolSwap(pool,u,t,50) HopSwap(hop,spender,quoteToken,wrappedOkb,t,executor) {
        if(address(dest)==address(0)||address(m).code.length==0||token==address(0)||g==address(0)||maxAmount==0||selector==bytes4(0))revert Restricted();
        treasury=dest;manager=m;projectToken=token;guardian=g;maxBatch=maxAmount;claimSelector=selector;claimHasRecipient=hasRecipient;
    }
    function pause() external {if(msg.sender!=guardian)revert Restricted();paused=true;}
    function resume() external {if(msg.sender!=guardian)revert Restricted();paused=false;}
    function claim() external nonReentrant {
        if(paused)revert Restricted();
        address vault=manager.vaultOf(projectToken);if(vault.code.length==0)revert Restricted();
        uint256 beforeBalance=quote.balanceOf(address(this));
        (bool ok,)=vault.call(claimHasRecipient?abi.encodeWithSelector(claimSelector,address(this)):abi.encodeWithSelector(claimSelector));
        if(!ok)revert Restricted();emit Claimed(vault,quote.balanceOf(address(this))-beforeBalance);
    }
    function convert(uint256 quoteAmount,uint256 minUsd0,bytes calldata hopCall) external nonReentrant returns(uint256 out) {
        if(paused||quoteAmount==0||quoteAmount>maxBatch)revert Restricted();
        uint256 usd0Got=_hop(quote,usd0,quoteAmount,minUsd0,hopCall);
        out=_swapStable(true,usd0Got);usdc.safeTransfer(address(treasury),out);treasury.creditConversion(out,usd0Got);
        emit Converted(quoteAmount,usd0Got,out);
    }
}
