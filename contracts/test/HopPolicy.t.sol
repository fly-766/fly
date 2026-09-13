// SPDX-License-Identifier: MIT
pragma solidity ^0.8.30;
import {Test} from "forge-std/Test.sol";
import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {HopSwap} from "../src/v03/HopSwap.sol";
import {Coin03} from "./V03Mocks.sol";
contract HopApprovalProxy {
    function pull(IERC20 token,address owner,uint256 amount) external {require(token.transferFrom(owner,address(this),amount));}
}
contract SeparateHopRouter {
    HopApprovalProxy public proxy;
    constructor(HopApprovalProxy p){proxy=p;}
    function swap(Coin03 src,Coin03 dst,uint256 amount,uint256 out,address receiver) external {
        proxy.pull(src,msg.sender,amount);dst.mint(receiver,out);
    }
}
contract HopHarness is HopSwap {
    constructor(address router,address spender,IERC20 quoteToken,IERC20 w,IERC20 usd,address executor) HopSwap(router,spender,quoteToken,w,usd,executor){}
    function convert(IERC20 src,IERC20 dst,uint256 amount,uint256 minimum,bytes calldata data) external returns(uint256){return _hop(src,dst,amount,minimum,data);}
}
contract HopPolicyTest is Test {
    Coin03 src;Coin03 dst;Coin03 w;HopApprovalProxy proxy;SeparateHopRouter router;HopHarness h;
    function setUp() public {src=new Coin03("quote",18);dst=new Coin03("usd",6);w=new Coin03("w",18);proxy=new HopApprovalProxy();router=new SeparateHopRouter(proxy);h=new HopHarness(address(router),address(proxy),src,w,dst,address(this));src.mint(address(h),10e18);}
    function data(uint256 amount,uint256 out,address receiver) internal view returns(bytes memory){return abi.encodeCall(router.swap,(src,dst,amount,out,receiver));}
    function testSeparateSpenderAndRouterClearAllowance() public {assertEq(h.convert(src,dst,1e18,300e6,data(1e18,301e6,address(h))),301e6);assertEq(src.allowance(address(h),address(proxy)),0);assertEq(src.allowance(address(h),address(router)),0);}
    function testWrongCallerCannotChooseMinimumOrCalldata() public {vm.prank(address(0xBAD));vm.expectRevert(HopSwap.UnsafeHop.selector);h.convert(src,dst,1e18,1,data(1e18,1,address(h)));}
    function testWrongReceiverRollsBackInput() public {vm.expectRevert(HopSwap.UnsafeHop.selector);h.convert(src,dst,1e18,300e6,data(1e18,301e6,address(0xBAD)));assertEq(src.balanceOf(address(h)),10e18);assertEq(src.allowance(address(h),address(proxy)),0);}
    function testUnderMinimumRollsBackInput() public {vm.expectRevert(HopSwap.UnsafeHop.selector);h.convert(src,dst,1e18,300e6,data(1e18,299e6,address(h)));assertEq(src.balanceOf(address(h)),10e18);}
    function testUnrelatedWrappedDustCannotBlockConversion() public {w.mint(address(h),1);assertEq(h.convert(src,dst,1e18,300e6,data(1e18,301e6,address(h))),301e6);assertEq(w.balanceOf(address(h)),1);}
    function testPartialSpendRejected() public {vm.expectRevert(HopSwap.UnsafeHop.selector);h.convert(src,dst,1e18,300e6,data(5e17,301e6,address(h)));}
    function testWrongApprovalTargetCannotSpend() public {HopHarness bad=new HopHarness(address(router),address(router),src,w,dst,address(this));src.mint(address(bad),1e18);vm.expectRevert(HopSwap.UnsafeHop.selector);bad.convert(src,dst,1e18,300e6,data(1e18,301e6,address(bad)));}
}
