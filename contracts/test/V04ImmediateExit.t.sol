// SPDX-License-Identifier: MIT
pragma solidity ^0.8.30;
import {Test} from "forge-std/Test.sol";
import {Coin03,Core03,Messenger03,Transmitter03} from "./V03Mocks.sol";
import {TradingAccountV04} from "../src/v04/TradingAccountV04.sol";
import {RecoveryVaultV04} from "../src/v04/RecoveryVaultV04.sol";
import {CoreExit} from "../src/v03/CoreExit.sol";
import {CctpIngress} from "../src/v03/CctpIngress.sol";
import {AttestedSettlement} from "../src/v03/AttestedSettlement.sol";
import {RunCommitRegistry} from "../src/v03/RunCommitRegistry.sol";
abstract contract V04ExitFixture is Test {
    Coin03 token;Core03 core;Messenger03 messenger;Transmitter03 transmitter;
    AttestedSettlement verifier;RunCommitRegistry registry;TradingAccountV04 account;
    RecoveryVaultV04 vault;CctpIngress ingress;
    address guardian=address(0x777);address beneficiary=address(0x888);address profitRecipient=address(0x999);
    uint256 oracleKey=0xCA11;uint256 modelKey=0xDADA;
    function makeCore(Coin03 t) internal virtual returns(Core03) {return new Core03(t);}
    function setUp() public {
        vm.warp(100000);
        token=new Coin03("USDC",6);core=makeCore(token);messenger=new Messenger03(19);transmitter=new Transmitter03(token);
        verifier=new AttestedSettlement(vm.addr(oracleKey));
        registry=new RunCommitRegistry(keccak256("run"),keccak256("model"),keccak256("r0"),keccak256("s0"),vm.addr(modelKey));
        uint64 nonce=vm.getNonce(address(this));
        address predictedVault=vm.computeCreateAddress(address(this),nonce+1);
        address predictedIngress=vm.computeCreateAddress(address(this),nonce+2);
        TradingAccountV04.Config memory c=TradingAccountV04.Config(token,core,core,core,verifier,registry,messenger,address(this),address(0xAAA),predictedIngress,profitRecipient,predictedVault,guardian,37,100e6,200e6,20,24,50,0);
        account=new TradingAccountV04(c);
        vault=new RecoveryVaultV04(token,predictedIngress,beneficiary);
        ingress=new CctpIngress(transmitter,token,19,37,address(token),address(account.recoveryExit()),address(0),address(0),address(vault));
        assertEq(address(vault),predictedVault);assertEq(address(ingress),predictedIngress);
    }
    function attest(bytes32 payload) internal view returns(bytes memory) {
        bytes32 h=verifier.digest(address(account),account.operation(),payload,core.blockNo(),uint64(vm.getBlockTimestamp()+120),keccak256("evidence"));
        (uint8 v,bytes32 r,bytes32 s)=vm.sign(oracleKey,h);return abi.encodePacked(r,s,v);
    }
    function nativeFund(uint256 amount) internal {
        token.mint(address(account),amount);account.creditPrincipal(amount,amount,keccak256(abi.encode(amount,account.costBasisE6())));
    }
    function spotFund(uint64 amount) internal {
        core.initialize(address(account));core.initialize(address(account.exit()));core.initialize(address(account.recoveryExit()));
        account.configureCore();core.processSetup();
        account.settleSetup(core.blockNo(),uint64(vm.getBlockTimestamp()+120),keccak256("evidence"),attest(keccak256(abi.encode("SETUP_DISABLED",address(account.exit()),address(account.recoveryExit())))));
        nativeFund(amount);account.fund();core.processDeposit();
        account.settleDeposit(amount,0,core.blockNo(),uint64(vm.getBlockTimestamp()+120),keccak256("evidence"),attest(keccak256(abi.encode("DEPOSIT",amount,uint64(0)))));
    }
    function perpFund(uint64 amount) internal {
        spotFund(amount);account.moveToPerp();core.processClass();
        account.settleClassTransfer(amount,0,core.blockNo(),uint64(vm.getBlockTimestamp()+120),keccak256("evidence"),attest(keccak256(abi.encode("CLASS_TRANSFER",amount,uint64(0)))));
    }
    function commit(uint8 side) internal returns(uint64 n) {
        n=registry.nonce()+1;
        RunCommitRegistry.Commit memory c=RunCommitRegistry.Commit(n,registry.lastRound()+1,registry.lastRound()+1,uint64(vm.getBlockTimestamp()),uint64(vm.getBlockTimestamp()+60),core.price(),registry.recordRoot(),keccak256(abi.encode(n,"r")),registry.stateRoot(),keccak256(abi.encode(n,"s")),keccak256("frame"),side);
        (uint8 v,bytes32 r,bytes32 s)=vm.sign(modelKey,registry.digest(c));registry.submit(c,abi.encodePacked(r,s,v));
    }
    function settleOrder() internal {
        uint64 amount=uint64(account.pendingAmount());int256 pnl=core.processOrder(amount,core.price(),0);
        TradingAccountV04.OrderReceipt memory receipt=TradingAccountV04.OrderReceipt(1,amount,core.price(),pnl,0,uint64(core.state(address(account),0).quantity)*1000);
        account.settleOrder(receipt,core.blockNo(),uint64(vm.getBlockTimestamp()+120),keccak256("evidence"),attest(keccak256(abi.encode("ORDER",account.cloid(),receipt))));
    }
    function deliverNative() internal {
        account.recoveryExit().burnReturn(0);
        ingress.receiveTransfer(messenger.last(),hex"ab");
    }
    function finishCoreExit(uint64 amount) internal {
        core.processTransfer();
        account.settleExit(amount,0,core.blockNo(),uint64(vm.getBlockTimestamp()+120),keccak256("evidence"),attest(keccak256(abi.encode("EXIT",amount,uint64(0)))));
        account.recoveryExit().bridgeToEvm();core.processTransfer();account.recoveryExit().reconcileEvm();deliverNative();
    }
}
contract V04ImmediateExit is V04ExitFixture {
    function testPerpPrincipalReturnsWithoutAdvancingTime() public {
        perpFund(100e6);uint256 now_=vm.getBlockTimestamp();
        vm.prank(guardian);account.requestExit(100e6,true);
        assertTrue(account.paused());assertTrue(account.recoveryOnly());assertEq(account.emergencyDelay(),0);
        finishCoreExit(100e6);
        assertEq(vault.delay(),0);assertEq(vault.credited(),100e6);
        vault.withdraw();
        assertEq(token.balanceOf(beneficiary),100e6);assertEq(account.costBasisE6(),0);assertEq(vm.getBlockTimestamp(),now_);
        vm.expectRevert();vault.withdraw();
    }
    function testNativePrincipalCanReturnImmediatelyBeforeCoreDeposit() public {
        nativeFund(40e6);uint256 now_=vm.getBlockTimestamp();
        vm.prank(guardian);account.recoverNative();
        assertTrue(account.paused());deliverNative();vault.withdraw();
        assertEq(token.balanceOf(beneficiary),40e6);assertEq(vm.getBlockTimestamp(),now_);
    }
    function testSpotPrincipalCanReturnImmediately() public {
        spotFund(40e6);uint256 now_=vm.getBlockTimestamp();
        vm.prank(guardian);account.recoverSpot(40e6);
        finishCoreExit(40e6);vault.withdraw();
        assertEq(token.balanceOf(beneficiary),40e6);assertEq(vm.getBlockTimestamp(),now_);
    }
    function testOperatorCannotStartPrincipalExit() public {
        perpFund(40e6);
        vm.expectRevert(TradingAccountV04.Restricted.selector);account.requestExit(40e6,true);
        vm.expectRevert(TradingAccountV04.Restricted.selector);account.recoverSpot(40e6);
        vm.expectRevert(TradingAccountV04.Restricted.selector);account.recoverNative();
        assertFalse(account.paused());
    }
    function testPendingOrderAndOpenPositionStillBlockWithdrawal() public {
        perpFund(100e6);account.execute(commit(1));
        vm.prank(guardian);vm.expectRevert(TradingAccountV04.Restricted.selector);account.requestExit(40e6,true);
        settleOrder();
        vm.prank(guardian);vm.expectRevert(TradingAccountV04.Restricted.selector);account.requestExit(40e6,true);
        nativeFund(10e6);
        vm.prank(guardian);vm.expectRevert(TradingAccountV04.Restricted.selector);account.recoverNative();
        account.execute(commit(2));settleOrder();
        vm.prank(guardian);account.requestExit(40e6,true);
        assertTrue(account.recoveryOnly());
    }
    function testPrincipalCannotTakeProfitAndRoutesStaySeparate() public {
        perpFund(100e6);account.execute(commit(1));settleOrder();core.setPrice(110e8);account.execute(commit(2));settleOrder();
        vm.prank(guardian);vm.expectRevert(TradingAccountV04.Restricted.selector);account.requestExit(101e6,true);
        vm.prank(guardian);account.requestExit(100e6,true);finishCoreExit(100e6);vault.withdraw();
        assertEq(token.balanceOf(beneficiary),100e6);assertGt(account.availableProfit(),2e6);
        account.requestExit(2e6,false);
        assertEq(account.exit().profitReceiver(),profitRecipient);assertEq(account.exit().fixedKind(),1);
    }
    function testActualDeliveryStillRequiredBeforeWithdrawal() public {
        perpFund(40e6);vm.prank(guardian);account.requestExit(40e6,true);
        CoreExit e=account.recoveryExit();vm.expectRevert(CoreExit.Restricted.selector);e.bridgeToEvm();
        vm.expectRevert(RecoveryVaultV04.Restricted.selector);vault.withdraw();
        assertEq(token.balanceOf(beneficiary),0);
    }
    function testOnlyVerifiedCreditsAndFixedBeneficiary() public {
        token.mint(address(vault),5e6);
        vm.expectRevert(RecoveryVaultV04.Restricted.selector);vault.creditReturn(5e6,2,keccak256("fake"));
        vm.prank(address(ingress));vm.expectRevert(RecoveryVaultV04.Restricted.selector);vault.creditReturn(6e6,2,keccak256("too much"));
        vm.prank(address(ingress));vault.creditReturn(5e6,2,keccak256("received"));
        address caller=address(0xBAD);vm.prank(caller);vault.withdraw();
        assertEq(token.balanceOf(beneficiary),5e6);assertEq(token.balanceOf(caller),0);
    }
    function testUnknownRecoveryKeepsConfirmationAndAccountingSafeguards() public {
        perpFund(100e6);vm.prank(guardian);account.requestExit(20e6,true);core.processTransfer();
        vm.prank(guardian);vm.expectRevert(TradingAccountV04.Restricted.selector);account.quarantineUnknown(keccak256("unknown"));
        core.tick(101);uint256 now_=vm.getBlockTimestamp();
        vm.prank(guardian);account.quarantineUnknown(keccak256("unknown"));
        vm.prank(guardian);account.recoverExit(true,false);
        assertTrue(account.accountingQuarantined());assertEq(account.availableProfit(),0);assertEq(account.costBasisE6(),80e6);
        assertEq(vm.getBlockTimestamp(),now_);
    }
    function testSubTwoUsdcPrincipalAfterLossCanExit() public {
        perpFund(20e6);account.execute(commit(1));settleOrder();core.setPrice(5e8);account.execute(commit(2));settleOrder();
        uint64 cash=uint64(core.state(address(account),0).cashE6);assertGt(cash,0);assertLt(cash,2e6);
        vm.prank(guardian);account.requestExit(cash,true);finishCoreExit(cash);vault.withdraw();
        assertEq(token.balanceOf(beneficiary),cash);
    }
    function testOneMicroUsdcSpotPrincipalCanExitThenRemainder() public {
        spotFund(2e6);
        vm.prank(guardian);account.recoverSpot(1);finishCoreExit(1);vault.withdraw();
        assertEq(token.balanceOf(beneficiary),1);
        vm.prank(guardian);account.recoverSpot(1_999_999);finishCoreExit(1_999_999);vault.withdraw();
        assertEq(token.balanceOf(beneficiary),2e6);
    }

}
