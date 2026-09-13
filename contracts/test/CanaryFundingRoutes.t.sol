// SPDX-License-Identifier: MIT
pragma solidity ^0.8.30;
import {Test} from "forge-std/Test.sol";
import {ERC20} from "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import {CanaryFundingRoutes} from "../src/canary/CanaryFundingRoutes.sol";
import {RecoveryVault} from "../src/v03/RecoveryVault.sol";
contract CanaryToken is ERC20 {
    constructor() ERC20("Canary USDC","USDC") {}
    function mint(address to,uint256 amount) external {_mint(to,amount);}
}
contract CanaryPrincipalReceiver {
    uint256 public principal; uint256 public basis;
    function creditPrincipal(uint256 n,uint256 b,bytes32) external {principal+=n;basis+=b;}
}
contract CanaryFundingRoutesTest is Test {
    CanaryToken token;CanaryPrincipalReceiver account;CanaryFundingRoutes routes;RecoveryVault vault;
    address funder=address(0xF001);address profitExit=address(0xF002);address recoveryExit=address(0xF003);address guardian=address(0xF004);
    function setUp() public {
        token=new CanaryToken();account=new CanaryPrincipalReceiver();
        address predicted=vm.computeCreateAddress(address(this),vm.getNonce(address(this))+1);
        vault=new RecoveryVault(token,predicted,guardian,2 days);
        routes=new CanaryFundingRoutes(token,funder,address(account),profitExit,recoveryExit,address(vault),guardian,50e6);
        assertEq(address(routes),predicted);
        token.mint(funder,100e6);vm.prank(funder);token.approve(address(routes),100e6);
    }
    function data(uint8 kind,uint64 seq) internal pure returns(bytes memory) {return abi.encode(bytes4(0x46543033),kind,uint256(0),seq,bytes32(uint256(7)));}
    function invoke(uint8 kind,uint64 seq,uint256 amount,address destination) internal {
        routes.depositForBurnWithHook(amount,19,bytes32(uint256(uint160(destination))),address(token),bytes32(uint256(uint160(address(routes)))),0,2000,data(kind,seq));
    }
    function testFundRealTokensAndExactPrincipal() public {
        vm.prank(funder);routes.fundPrincipal(40e6);
        assertEq(token.balanceOf(address(account)),40e6);assertEq(account.principal(),40e6);assertEq(account.basis(),40e6);assertEq(routes.funded(),40e6);
    }
    function testCumulativeCapAndOnlyFunder() public {
        vm.expectRevert();routes.fundPrincipal(1e6);
        vm.prank(funder);routes.fundPrincipal(40e6);
        vm.prank(funder);vm.expectRevert();routes.fundPrincipal(11e6);
        vm.prank(funder);routes.fundPrincipal(10e6);assertEq(routes.funded(),50e6);
        vm.prank(funder);vm.expectRevert();routes.fundPrincipal(1);
    }
    function testUnfundedCreditCannotBeInvented() public {
        vm.prank(funder);token.approve(address(routes),0);
        vm.prank(funder);vm.expectRevert();routes.fundPrincipal(20e6);
        assertEq(routes.funded(),0);assertEq(account.principal(),0);
    }
    function testPrincipalUsesActualDelayedRecoveryVault() public {
        token.mint(recoveryExit,10e6);vm.prank(recoveryExit);token.approve(address(routes),10e6);
        vm.prank(recoveryExit);invoke(2,1,10e6,address(vault));
        assertEq(vault.credited(),10e6);assertEq(token.balanceOf(guardian),0);
        vm.prank(guardian);vault.schedule(10e6);
        vm.expectRevert();vault.withdraw();
        vm.warp(block.timestamp+2 days);vault.withdraw();assertEq(token.balanceOf(guardian),10e6);
    }
    function testProfitHasFixedRecipientAndCannotCreditPrincipal() public {
        token.mint(profitExit,2e6);vm.prank(profitExit);token.approve(address(routes),2e6);
        vm.prank(profitExit);invoke(1,1,2e6,guardian);
        assertEq(token.balanceOf(guardian),2e6);assertEq(vault.credited(),0);assertEq(account.principal(),0);
    }
    function testWrongCallerRecipientKindAndReplayFail() public {
        token.mint(recoveryExit,20e6);vm.prank(recoveryExit);token.approve(address(routes),20e6);
        vm.prank(funder);vm.expectRevert();invoke(2,1,10e6,address(vault));
        vm.prank(recoveryExit);vm.expectRevert();invoke(2,1,10e6,funder);
        vm.prank(recoveryExit);vm.expectRevert();invoke(1,1,10e6,guardian);
        vm.prank(recoveryExit);invoke(2,1,10e6,address(vault));
        vm.prank(recoveryExit);vm.expectRevert();invoke(2,1,10e6,address(vault));
        assertEq(vault.credited(),10e6);
    }
    function testWrongAssetDomainCallerOrFeeFail() public {
        vm.prank(recoveryExit);vm.expectRevert();
        routes.depositForBurnWithHook(1e6,19,bytes32(uint256(uint160(address(vault)))),address(1),bytes32(uint256(uint160(address(routes)))),0,2000,data(2,1));
        vm.prank(recoveryExit);vm.expectRevert();
        routes.depositForBurnWithHook(1e6,37,bytes32(uint256(uint160(address(vault)))),address(token),bytes32(uint256(uint160(address(routes)))),0,2000,data(2,1));
        vm.prank(recoveryExit);vm.expectRevert();
        routes.depositForBurnWithHook(1e6,19,bytes32(uint256(uint160(address(vault)))),address(token),bytes32(uint256(uint160(funder))),0,2000,data(2,1));
        vm.prank(recoveryExit);vm.expectRevert();
        routes.depositForBurnWithHook(1e6,19,bytes32(uint256(uint160(address(vault)))),address(token),bytes32(uint256(uint160(address(routes)))),1,2000,data(2,1));
    }
}
