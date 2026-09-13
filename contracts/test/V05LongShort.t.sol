// SPDX-License-Identifier: MIT
pragma solidity ^0.8.30;
import {Test} from "forge-std/Test.sol";
import {Coin03,Messenger03,Transmitter03} from "./V03Mocks.sol";
import {Core05} from "./V05Mocks.sol";
import {TradingAccountV05} from "../src/v05/TradingAccountV05.sol";
import {RecoveryVaultV04} from "../src/v04/RecoveryVaultV04.sol";
import {CoreExit} from "../src/v03/CoreExit.sol";
import {CctpIngress} from "../src/v03/CctpIngress.sol";
import {AttestedSettlement} from "../src/v03/AttestedSettlement.sol";
import {RunCommitRegistry} from "../src/v03/RunCommitRegistry.sol";
abstract contract V05Fixture is Test {
    Coin03 token;Core05 core;Messenger03 messenger;Transmitter03 transmitter;
    AttestedSettlement verifier;RunCommitRegistry registry;TradingAccountV05 account;
    RecoveryVaultV04 vault;CctpIngress ingress;
    address guardian=address(0x777);address beneficiary=address(0x888);address profitRecipient=address(0x999);
    uint256 oracleKey=0xCA11;uint256 modelKey=0xDADA;
    function makeCore(Coin03 t) internal virtual returns(Core05) {return new Core05(t);}
    function setUp() public {
        vm.warp(100000);
        token=new Coin03("USDC",6);core=makeCore(token);messenger=new Messenger03(19);transmitter=new Transmitter03(token);
        verifier=new AttestedSettlement(vm.addr(oracleKey));
        registry=new RunCommitRegistry(keccak256("run"),keccak256("model"),keccak256("r0"),keccak256("s0"),vm.addr(modelKey));
        uint64 nonce=vm.getNonce(address(this));
        address predictedVault=vm.computeCreateAddress(address(this),nonce+1);
        address predictedIngress=vm.computeCreateAddress(address(this),nonce+2);
        TradingAccountV05.Config memory c=TradingAccountV05.Config(token,core,core,core,verifier,registry,messenger,address(this),address(0xAAA),predictedIngress,profitRecipient,predictedVault,guardian,37,200e6,2e6,20,24,50,0,20,1000);
        account=new TradingAccountV05(c);
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
        TradingAccountV05.OrderReceipt memory receipt=TradingAccountV05.OrderReceipt(1,amount,core.price(),pnl,0,core.state(address(account),0).quantity*1000);
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
contract V05LongShort is V05Fixture {
    function fill(uint8 status,uint64 size,uint64 px,uint64 fee) internal {
        int256 pnl=core.processOrder(size,px,fee);int64 finalSize=core.state(address(account),0).quantity*1000;
        TradingAccountV05.OrderReceipt memory r=TradingAccountV05.OrderReceipt(status,size,px,pnl,fee,finalSize);
        account.settleOrder(r,core.blockNo(),uint64(vm.getBlockTimestamp()+120),keccak256("evidence"),attest(keccak256(abi.encode("ORDER_V05",account.cloid(),r))));
    }
    function open(uint8 side) internal returns(uint64 n){account.execute(commit(side));n=uint64(account.pendingAmount());fill(1,n,core.price(),10000);}
    function testOpenShortUsesSellWithoutReduceOnly() public {
        perpFund(10e6);account.execute(commit(2));assertFalse(account.pendingBuy());assertFalse(account.pendingReduceOnly());
        (,bool buy,,uint64 size,bool reduce,,)=abi.decode(slice(core.lastAction()),(uint32,bool,uint64,uint64,bool,uint8,uint128));assertFalse(buy);assertFalse(reduce);
        assertLe(uint256(size)*core.price()/1e10,180e6);fill(1,size,core.price(),10000);assertLt(account.settledPositionE8(),0);
    }
    function slice(bytes memory a) internal pure returns(bytes memory b){b=new bytes(a.length-4);for(uint256 i;i<b.length;i++)b[i]=a[i+4];}
    function testShortProfitAndFeesUseOppositeSign() public {
        perpFund(10e6);uint64 n=open(2);core.setPrice(99e8);account.execute(commit(1));assertTrue(account.pendingBuy());assertTrue(account.pendingReduceOnly());
        fill(1,n,99e8,10000);assertEq(account.settledPositionE8(),0);assertGt(account.tradingNetE6(),0);assertGt(account.availableProfit(),0);
    }
    function testShortLossTriggersBuyToCloseAndPauses() public {
        perpFund(10e6);uint64 n=open(2);core.setPrice(102e8);account.emergencyClose();assertTrue(account.pendingBuy());assertTrue(account.pendingReduceOnly());fill(1,n,102e8,10000);
        assertTrue(account.paused());assertEq(account.settledPositionE8(),0);assertLt(account.tradingNetE6(),0);assertEq(account.availableProfit(),0);
    }
    function testLongCloseThenNewCommitCanOpenShort() public {
        perpFund(10e6);uint64 n=open(1);uint64 closeCommit=commit(2);account.execute(closeCommit);assertTrue(account.pendingReduceOnly());fill(1,n,core.price(),10000);
        vm.expectRevert(TradingAccountV05.Restricted.selector);account.execute(closeCommit);
        vm.warp(vm.getBlockTimestamp()+21);open(2);assertLt(account.settledPositionE8(),0);
    }
    function testRepeatedSellCannotAddToShort() public {
        perpFund(10e6);open(2);uint64 n=commit(2);vm.expectRevert();account.execute(n);
    }
    function testPartialShortCoverRetainsSignedRemainder() public {
        perpFund(10e6);uint64 n=open(2);account.execute(commit(1));uint64 part=n/2000*1000;fill(2,part,core.price(),1000);
        assertEq(account.settledPositionE8(),-int64(n-part));account.execute(commit(1));fill(1,n-part,core.price(),1000);assertEq(account.settledPositionE8(),0);
    }
    function testNativeLeverageMismatchBlocksEntryButNotClose() public {
        perpFund(10e6);core.setLeverage(10);uint64 c=commit(2);vm.expectRevert();account.execute(c);
        core.setLeverage(20);uint64 n=open(2);core.setLeverage(10);account.execute(commit(1));fill(1,n,core.price(),1000);
    }
    function testUnknownPositionChangeCannotBecomeNewEntryOrProfit() public {
        perpFund(10e6);open(2);core.forcePosition(address(account),0,0,2e6);uint64 c=commit(1);vm.expectRevert(TradingAccountV05.Unresolved.selector);account.execute(c);
        account.quarantinePositionDrift();assertTrue(account.accountingQuarantined());assertTrue(account.recoveryOnly());assertEq(account.availableProfit(),0);
    }
    function testDisableShortsStillAllowsCover() public {
        perpFund(10e6);vm.prank(guardian);account.setShortEnabled(false);uint64 c=commit(2);vm.expectRevert();account.execute(c);
        vm.prank(guardian);account.setShortEnabled(true);uint64 n=open(2);vm.prank(guardian);account.setShortEnabled(false);account.execute(commit(1));fill(1,n,core.price(),1000);
        vm.expectRevert(TradingAccountV05.Restricted.selector);account.setShortEnabled(true);
    }
    function testPrincipalExitAfterShortHasNoArtificialDelay() public {
        perpFund(10e6);uint64 n=open(2);account.execute(commit(1));fill(1,n,core.price(),10000);
        uint256 now_=vm.getBlockTimestamp();uint256 amount=uint256(uint64(core.state(address(account),0).cashE6));
        vm.prank(guardian);account.requestExit(amount,true);finishCoreExit(uint64(amount));vault.withdraw();
        assertEq(token.balanceOf(beneficiary),amount);assertEq(vm.getBlockTimestamp(),now_);
    }
    function testFuzzEntryExposureRespectsCapitalAndNotionalCaps(uint64 value,bool buy) public {
        uint64 equity=uint64(bound(value,2e6,100e6));core.initialize(address(account));core.forcePosition(address(account),0,0,int64(equity));
        (uint64 px,uint64 size)=account.previewOrder(buy);
        uint256 ntl=uint256(size)*px/1e10;assertLe(ntl,uint256(equity)*20*9000/10000);assertLe(ntl,200e6);
    }
    function testWrongSignedFinalPositionCannotSettle() public {
        perpFund(10e6);account.execute(commit(2));uint64 n=uint64(account.pendingAmount());core.processOrder(n,core.price(),1000);
        TradingAccountV05.OrderReceipt memory r=TradingAccountV05.OrderReceipt(1,n,core.price(),0,1000,int64(n));
        bytes memory sig=attest(keccak256(abi.encode("ORDER_V05",account.cloid(),r)));uint64 b=core.blockNo();uint64 deadline=uint64(vm.getBlockTimestamp()+120);vm.expectRevert(TradingAccountV05.Unresolved.selector);account.settleOrder(r,b,deadline,keccak256("evidence"),sig);
    }
}
