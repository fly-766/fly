// SPDX-License-Identifier: MIT
pragma solidity ^0.8.30;
import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {IERC20Metadata} from "@openzeppelin/contracts/token/ERC20/extensions/IERC20Metadata.sol";
import {SafeERC20} from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
/// @notice Balance-delta hop through a fixed router. GOOGL/OKB has no IGNIX V2 pair, so the
///         calldata may be an aggregator route; the contract only accepts quote spent and usd0
///         received, with the recipient enforced by measuring this contract's balances.
abstract contract HopSwap {
    using SafeERC20 for IERC20;
    address public immutable hopRouter;
    address public immutable hopSpender;
    address public immutable hopExecutor;
    IERC20 public immutable quote;
    IERC20 public immutable wokb;
    error UnsafeHop();
    constructor(address router, address spender, IERC20 quoteToken, IERC20 wrappedOkb, IERC20 usd0Token,address executor) {
        if(executor==address(0))revert UnsafeHop();
        hopExecutor=executor;
        if(address(usd0Token)==address(0)||address(usd0Token).code.length==0)revert UnsafeHop();
        if(address(quoteToken)==address(usd0Token)){
            if(router!=address(0)||spender!=address(0)||address(wrappedOkb)!=address(0))revert UnsafeHop();
            hopRouter=address(0);hopSpender=address(0);quote=usd0Token;wokb=IERC20(address(0));return;
        }
        if(router==address(0)||router.code.length==0||spender.code.length==0||address(quoteToken).code.length==0||address(wrappedOkb).code.length==0)revert UnsafeHop();
        if(address(quoteToken)==router||address(wrappedOkb)==router||address(quoteToken)==address(wrappedOkb))revert UnsafeHop();
        if(IERC20Metadata(address(quoteToken)).decimals()!=18||IERC20Metadata(address(wrappedOkb)).decimals()!=18)revert UnsafeHop();
        hopRouter=router;hopSpender=spender;quote=quoteToken;wokb=wrappedOkb;
    }
    function _hop(IERC20 src, IERC20 dst, uint256 amount, uint256 minOut, bytes memory data) internal returns(uint256 received) {
        if(address(src)==address(dst)){
            if(data.length!=0||amount<minOut||amount==0)revert UnsafeHop();
            return amount;
        }
        if(msg.sender!=hopExecutor||hopRouter==address(0)||data.length==0||amount==0||minOut==0)revert UnsafeHop();
        uint256 srcBefore=src.balanceOf(address(this));uint256 dstBefore=dst.balanceOf(address(this));
        uint256 wrappedBefore=address(wokb)==address(0)?0:wokb.balanceOf(address(this));
        if(srcBefore<amount)revert UnsafeHop();
        src.forceApprove(hopSpender,amount);
        (bool ok,)=hopRouter.call(data);
        src.forceApprove(hopSpender,0);
        if(!ok)revert UnsafeHop();
        uint256 spent=srcBefore-src.balanceOf(address(this));
        received=dst.balanceOf(address(this))-dstBefore;
        if(spent!=amount||received<minOut)revert UnsafeHop();
        if(address(wokb)!=address(0)&&wokb.balanceOf(address(this))!=wrappedBefore)revert UnsafeHop();
    }
}
