// SPDX-License-Identifier: MIT
pragma solidity ^0.8.30;
import {IERC20Metadata} from "@openzeppelin/contracts/token/ERC20/extensions/IERC20Metadata.sol";
import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {SafeERC20} from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import {IV3Pool} from "./ProtocolTypes.sol";
/// @notice Fixed USDt0/native-USDC V3 pool. No router approval or caller-selected recipient.
abstract contract StablePoolSwap {
    using SafeERC20 for IERC20;
    IV3Pool public immutable stablePool;
    IERC20 public immutable usdc;
    IERC20 public immutable usd0;
    uint16 public immutable stableSlippageBps;
    address private payingToken;
    uint256 private paymentRemaining;
    bool private inSwap;
    error UnsafeSwap();
    constructor(IV3Pool pool,IERC20 u,IERC20 t,uint16 slip) {
        if(address(pool).code.length==0||address(u).code.length==0||address(t).code.length==0||slip>100)revert UnsafeSwap();
        address a=pool.token0();address b=pool.token1();
        if(!((a==address(u)&&b==address(t))||(a==address(t)&&b==address(u))))revert UnsafeSwap();
        if(IERC20Metadata(address(u)).decimals()!=6||IERC20Metadata(address(t)).decimals()!=6)revert UnsafeSwap();
        stablePool=pool;usdc=u;usd0=t;stableSlippageBps=slip;
    }
    function _swapStable(bool toUsdc,uint256 amount) internal returns(uint256 received) {
        if(inSwap||amount==0||amount>uint256(type(int256).max))revert UnsafeSwap();
        IERC20 input=toUsdc?usd0:usdc;IERC20 output=toUsdc?usdc:usd0;
        bool zeroForOne=stablePool.token0()==address(input);
        uint256 beforeIn=input.balanceOf(address(this));uint256 beforeOut=output.balanceOf(address(this));
        inSwap=true;payingToken=address(input);paymentRemaining=amount;
        stablePool.swap(address(this),zeroForOne,int256(amount),zeroForOne?uint160(4295128740):uint160(1461446703485210103287273052203988822378723970341),"");
        inSwap=false;payingToken=address(0);
        received=output.balanceOf(address(this))-beforeOut;
        if(paymentRemaining!=0||beforeIn-input.balanceOf(address(this))!=amount||received<amount*(10000-stableSlippageBps)/10000)revert UnsafeSwap();
    }
    function uniswapV3SwapCallback(int256 d0,int256 d1,bytes calldata) external {
        if(msg.sender!=address(stablePool)||!inSwap)revert UnsafeSwap();
        int256 due=stablePool.token0()==payingToken?d0:d1;
        int256 other=stablePool.token0()==payingToken?d1:d0;
        if(due<=0||other>0||uint256(due)>paymentRemaining)revert UnsafeSwap();
        paymentRemaining-=uint256(due);IERC20(payingToken).safeTransfer(msg.sender,uint256(due));
    }
}
