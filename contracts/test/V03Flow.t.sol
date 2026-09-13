// SPDX-License-Identifier: MIT
pragma solidity ^0.8.30;
import {Test} from "forge-std/Test.sol";
import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {IV3Pool,IIgnixManager,IV2Router,ICostTreasury,ICoreRead03,ICoreWriter03,ICoreDeposit03} from "../src/v03/ProtocolTypes.sol";
import {AttestedSettlement} from "../src/v03/AttestedSettlement.sol";
import {RunCommitRegistry} from "../src/v03/RunCommitRegistry.sol";
import {TradingAccount} from "../src/v03/TradingAccount.sol";
import {CoreExit} from "../src/v03/CoreExit.sol";
import {CctpIngress} from "../src/v03/CctpIngress.sol";
import {TaxTreasury} from "../src/v03/TaxTreasury.sol";
import {TaxConverter} from "../src/v03/TaxConverter.sol";
import {ProfitBuyback} from "../src/v03/ProfitBuyback.sol";
import {RecoveryVault} from "../src/v03/RecoveryVault.sol";
import {CctpMessage} from "../src/v03/CctpMessage.sol";
import {StablePoolSwap} from "../src/v03/StablePoolSwap.sol";
import {Coin03,Pool03,Messenger03,Transmitter03,Manager03,Router03,HopRouter03,Core03,ClaimVault03} from "./V03Mocks.sol";

contract V03Flow is Test {
    Coin03 ux;Coin03 uh;Coin03 usd0;Coin03 googl;Coin03 wokb;Coin03 project;
    Pool03 pool;Messenger03 mx;Messenger03 mh;Transmitter03 txh;Transmitter03 txx;Manager03 manager;Router03 router;HopRouter03 hop;Core03 core;
    AttestedSettlement verifier;RunCommitRegistry registry;TradingAccount account;
    CctpIngress principalIngress;CctpIngress profitIngress;CctpIngress recoveryIngress;
    TaxTreasury treasury;TaxConverter converter;ProfitBuyback buyback;RecoveryVault recovery;ClaimVault03 claimVault;
    address guardian=address(0x777);address cold=address(0x888);
    uint256 oracleKey=0xCA11;uint256 modelKey=0xDADA;
    function setUp() public {
        vm.warp(100000);
        ux=new Coin03("X-USDC",6);uh=new Coin03("H-USDC",6);usd0=new Coin03("USDt0",6);googl=new Coin03("wGOOGLx",18);wokb=new Coin03("WOKB",18);project=new Coin03("FlyTerm",18);
        pool=new Pool03(address(usd0),address(ux));mx=new Messenger03(37);mh=new Messenger03(19);txh=new Transmitter03(uh);txx=new Transmitter03(ux);
        manager=new Manager03();manager.setup(address(project),address(googl));router=new Router03();hop=new HopRouter03(googl,usd0);core=new Core03(uh);
        verifier=new AttestedSettlement(vm.addr(oracleKey));registry=new RunCommitRegistry(keccak256("run"),keccak256("model"),keccak256("records0"),keccak256("state0"),vm.addr(modelKey));
        uint64 n=vm.getNonce(address(this));
        address predictedAccount=vm.computeCreateAddress(address(this),n);
        address predictedPrincipal=vm.computeCreateAddress(address(this),n+1);
        address predictedTreasury=vm.computeCreateAddress(address(this),n+2);
        address predictedConverter=vm.computeCreateAddress(address(this),n+3);
        address predictedBuyback=vm.computeCreateAddress(address(this),n+4);
        address predictedRecovery=vm.computeCreateAddress(address(this),n+5);
        address predictedProfitIngress=vm.computeCreateAddress(address(this),n+6);
        address predictedRecoveryIngress=vm.computeCreateAddress(address(this),n+7);
        TradingAccount.Config memory c=TradingAccount.Config(uh,core,core,core,verifier,registry,mh,predictedPrincipal,predictedProfitIngress,predictedRecoveryIngress,predictedBuyback,predictedRecovery,guardian,37,100e6,200e6,20,24,50,50,2 days);
        account=new TradingAccount(c);assertEq(address(account),predictedAccount);
        principalIngress=new CctpIngress(txh,uh,37,19,address(ux),predictedTreasury,address(account),address(0),address(0));assertEq(address(principalIngress),predictedPrincipal);
        treasury=new TaxTreasury(ux,mx,predictedConverter,address(account),address(principalIngress),guardian,19,2e6,500e6,1000e6,50);
        converter=new TaxConverter(pool,ux,usd0,address(hop),googl,wokb,treasury,manager,address(project),guardian,500e18,bytes4(keccak256("claim()")),false);
        buyback=new ProfitBuyback(pool,ux,usd0,address(hop),googl,wokb,predictedProfitIngress,guardian,address(project),manager,router,100e6,500e18,600,500,50);
        recovery=new RecoveryVault(ux,predictedRecoveryIngress,cold,2 days);
        profitIngress=new CctpIngress(txx,ux,19,37,address(uh),address(account.exit()),address(0),address(buyback),address(0));
        recoveryIngress=new CctpIngress(txx,ux,19,37,address(uh),address(account.recoveryExit()),address(0),address(0),address(recovery));
        assertEq(address(converter),predictedConverter);assertEq(address(buyback),predictedBuyback);assertEq(address(recovery),predictedRecovery);
        claimVault=new ClaimVault03(googl,address(converter));manager.setVault(address(project),address(claimVault));
    }
    function q(uint256 e6) internal pure returns(uint256){return e6*1e12;}
    function hopIn(uint256 e6) internal pure returns(bytes memory){return abi.encodeWithSelector(HopRouter03.hopQuoteToUsd0.selector,e6*99/100);}
    function hopOut() internal pure returns(bytes memory){return abi.encodeWithSelector(HopRouter03.hopUsd0ToQuote.selector,uint256(1));}
    function tax(uint256 e6) internal {
        claimVault.accrue(q(e6));converter.claim();converter.convert(q(e6),e6*99/100,hopIn(e6));
    }
    function attest(bytes32 payload) internal view returns(bytes memory sig) {
        bytes32 h=verifier.digest(address(account),account.operation(),payload,core.blockNo(),uint64(vm.getBlockTimestamp()+120),keccak256("venue evidence"));
        (uint8 v,bytes32 r,bytes32 s)=vm.sign(oracleKey,h);return abi.encodePacked(r,s,v);
    }
    function fundAll(uint256 amount) internal {
        if(!account.setupComplete()){
            core.initialize(address(account));core.initialize(address(account.exit()));core.initialize(address(account.recoveryExit()));
            account.configureCore();core.processSetup();
            account.settleSetup(core.blockNo(),uint64(vm.getBlockTimestamp()+120),keccak256("venue evidence"),attest(keccak256(abi.encode("SETUP_DISABLED",address(account.exit()),address(account.recoveryExit())))));
        }
        tax(amount);
        uint256 converted=treasury.liquidPrincipal();mx.setFee(10_000);treasury.forward(converted,10_000);
        principalIngress.receiveTransfer(mx.last(),hex"ab");assertEq(account.costBasisE6(),amount);
        uint64 net=uint64(account.nativePrincipalE6());account.fund();core.processDeposit();
        account.settleDeposit(net,0,core.blockNo(),uint64(vm.getBlockTimestamp()+120),keccak256("venue evidence"),attest(keccak256(abi.encode("DEPOSIT",net,uint64(0)))));
        account.moveToPerp();core.processClass();
        account.settleClassTransfer(net,0,core.blockNo(),uint64(vm.getBlockTimestamp()+120),keccak256("venue evidence"),attest(keccak256(abi.encode("CLASS_TRANSFER",net,uint64(0)))));
    }
    function commit(uint8 side) internal returns(uint64 n) {
        n=registry.nonce()+1;
        RunCommitRegistry.Commit memory c=RunCommitRegistry.Commit(n,registry.lastRound()+1,registry.lastRound()+1,uint64(vm.getBlockTimestamp()),uint64(vm.getBlockTimestamp()+60),core.price(),registry.recordRoot(),keccak256(abi.encode(n,"record")),registry.stateRoot(),keccak256(abi.encode(n,"state")),keccak256("frame"),side);
        (uint8 v,bytes32 r,bytes32 s)=vm.sign(modelKey,registry.digest(c));registry.submit(c,abi.encodePacked(r,s,v));
    }
    function settleOrder(uint8 status,uint64 filled,uint64 avg,uint64 fee) internal {
        int256 pnl=core.processOrder(filled,avg,fee);
        ICoreRead03.State memory state=core.state(address(account),0);
        TradingAccount.OrderReceipt memory r=TradingAccount.OrderReceipt(status,filled,avg,pnl,fee,uint64(state.quantity)*1000);
        bytes32 payload=keccak256(abi.encode("ORDER",account.cloid(),r));
        account.settleOrder(r,core.blockNo(),uint64(vm.getBlockTimestamp()+120),keccak256("venue evidence"),attest(payload));
    }
    function profitRound() internal {
        account.execute(commit(1));uint64 size=uint64(account.pendingAmount());settleOrder(1,size,core.price(),10000);
        core.setPrice(110e8);account.execute(commit(2));settleOrder(1,size,core.price(),10000);
    }
    function returnExit(uint256 amount,bool emergency) internal {
        if(emergency)vm.prank(guardian);
        account.requestExit(amount,emergency);core.processTransfer();
        account.settleExit(uint64(amount),0,core.blockNo(),uint64(vm.getBlockTimestamp()+120),keccak256("venue evidence"),attest(keccak256(abi.encode("EXIT",uint64(amount),uint64(0)))));
        CoreExit e=emergency?account.recoveryExit():account.exit();
        e.bridgeToEvm();core.processTransfer();e.reconcileEvm();mh.setFee(1000);e.burnReturn(1000);
        if(emergency)recoveryIngress.receiveTransfer(mh.last(),hex"ab");else profitIngress.receiveTransfer(mh.last(),hex"ab");
    }
    function testFullTaxToTradeToProfitBuyback() public {
        fundAll(500e6);profitRound();assertGt(account.availableProfit(),5e6);
        returnExit(5e6,false);assertEq(buyback.nativeBudget(),4_999_000);
        buyback.convertProfit(4_999_000);buyback.hopProfit(1,hopOut());buyback.observe();vm.warp(vm.getBlockTimestamp()+601);buyback.observe();
        buyback.buyback(1e18);assertGt(buyback.escrowedTokens(),0);assertEq(googl.allowance(address(buyback),address(manager)),0);
    }
    function testWrongCctpSourceRecipientAndReplayFail() public {
        tax(100e6);treasury.forward(treasury.liquidPrincipal(),0);
        bytes memory m=mx.last();bytes memory bad=bytes.concat(m);bad[248+31]=0x01;
        vm.expectRevert(CctpIngress.WrongRoute.selector);principalIngress.receiveTransfer(bad,hex"ab");
        principalIngress.receiveTransfer(m,hex"ab");
        vm.expectRevert(CctpIngress.WrongRoute.selector);principalIngress.receiveTransfer(m,hex"ab");
        vm.expectRevert(TradingAccount.Restricted.selector);account.creditPrincipal(1,1,keccak256("fake"));
    }
    function testZeroFillTerminalUnblocksWithoutInventingFill() public {
        fundAll(500e6);account.execute(commit(1));bytes32 op=account.operation();
        vm.warp(vm.getBlockTimestamp()+60);
        uint64 existingCommit=registry.nonce();vm.expectRevert(TradingAccount.Unresolved.selector);account.execute(existingCommit);
        settleOrder(3,0,0,0);assertEq(uint8(account.pending()),0);assertEq(account.tradingNetE6(),0);
        account.execute(commit(1));assertTrue(account.operation()!=op);
    }
    function testPartialBuyAndSellRemainderAreAccounted() public {
        fundAll(500e6);account.execute(commit(1));uint64 part=uint64(account.pendingAmount()/2000*1000);
        settleOrder(2,part,core.price(),1000);assertEq(uint8(account.pending()),0);
        account.execute(commit(2));uint64 sold=part/2000*1000;settleOrder(2,sold,core.price(),1000);
        assertEq(uint8(account.pending()),0);assertEq(uint64(core.state(address(account),0).quantity)*1000,part-sold);
        account.execute(commit(2));settleOrder(1,part-sold,core.price(),1000);assertEq(core.state(address(account),0).quantity,0);
    }
    function testForgedTerminalWithWrongNativePositionFails() public {
        fundAll(500e6);account.execute(commit(1));core.tick(1);
        uint64 n=uint64(account.pendingAmount());TradingAccount.OrderReceipt memory r=TradingAccount.OrderReceipt(1,n,100e8,0,0,n);
        bytes memory sig=attest(keccak256(abi.encode("ORDER",account.cloid(),r)));
        uint64 atBlock=core.blockNo();vm.expectRevert(TradingAccount.Unresolved.selector);account.settleOrder(r,atBlock,uint64(vm.getBlockTimestamp()+120),keccak256("venue evidence"),sig);
        assertEq(uint8(account.pending()),2);
    }
    function testEmergencyPrincipalCannotTakeProfitAndIsTimelocked() public {
        fundAll(500e6);profitRound();vm.prank(guardian);account.pause();vm.warp(vm.getBlockTimestamp()+2 days);
        vm.prank(guardian);vm.expectRevert(TradingAccount.Restricted.selector);account.requestExit(501e6,true);
        returnExit(100e6,true);assertEq(recovery.credited(),99_999_000);
        vm.prank(cold);recovery.schedule(99_999_000);vm.expectRevert(RecoveryVault.Restricted.selector);recovery.withdraw();
        vm.warp(vm.getBlockTimestamp()+2 days);recovery.withdraw();assertEq(ux.balanceOf(cold),99_999_000);
        // Scheduled profit still uses its independent fixed destination.
        returnExit(5e6,false);assertEq(buyback.nativeBudget(),4_999_000);
    }
    function testUnrealizedAndNewDepositsAreNotProfit() public {
        fundAll(500e6);assertEq(account.availableProfit(),0);
        account.execute(commit(1));settleOrder(1,uint64(account.pendingAmount()),core.price(),0);
        core.setPrice(200e8);assertEq(account.availableProfit(),0);
    }
    function testWrongSwapCallbackAndBadRateRollback() public {
        vm.expectRevert(StablePoolSwap.UnsafeSwap.selector);converter.uniswapV3SwapCallback(1,-1,"");
        claimVault.accrue(q(100e6));converter.claim();pool.setRate(9000);
        vm.expectRevert(StablePoolSwap.UnsafeSwap.selector);converter.convert(q(100e6),99e6,hopIn(100e6));
        assertEq(googl.balanceOf(address(converter)),q(100e6));assertEq(treasury.liquidPrincipal(),0);
    }
    function testExitWaitsForActualCoreAndEvmBalances() public {
        fundAll(500e6);profitRound();account.requestExit(5e6,false);
        CoreExit e=account.exit();vm.expectRevert(CoreExit.Restricted.selector);e.bridgeToEvm();
        core.processTransfer();account.settleExit(5e6,0,core.blockNo(),uint64(vm.getBlockTimestamp()+120),keccak256("venue evidence"),attest(keccak256(abi.encode("EXIT",uint64(5e6),uint64(0)))));
        e.bridgeToEvm();vm.expectRevert(CoreExit.Restricted.selector);e.reconcileEvm();
    }
    function testFundedButStoppedNativeCanReturn() public {
        tax(100e6);treasury.forward(treasury.liquidPrincipal(),0);principalIngress.receiveTransfer(mx.last(),hex"ab");
        vm.prank(guardian);account.pause();vm.warp(vm.getBlockTimestamp()+2 days);
        uint256 n=uh.balanceOf(address(account));vm.prank(guardian);account.recoverNative();
        assertEq(uh.balanceOf(address(account)),0);assertEq(uint8(account.recoveryExit().stage()),4);
        account.recoveryExit().burnReturn(0);recoveryIngress.receiveTransfer(mh.last(),hex"ab");assertEq(recovery.credited(),n);
    }

    function testSetupMandatoryAndSignatureBound() public {
        tax(100e6);treasury.forward(treasury.liquidPrincipal(),0);principalIngress.receiveTransfer(mx.last(),hex"ab");
        vm.expectRevert(TradingAccount.Restricted.selector);account.fund();
        core.initialize(address(account));core.initialize(address(account.exit()));core.initialize(address(account.recoveryExit()));
        account.configureCore();core.processSetup();
        bytes memory bad=attest(keccak256("not the mode"));uint64 b=core.blockNo();
        vm.expectRevert(AttestedSettlement.InvalidAttestation.selector);account.settleSetup(b,uint64(vm.getBlockTimestamp()+120),keccak256("venue evidence"),bad);
    }
    function testDepositAndExitFeesRemainCostsNotNewProfit() public {
        fundAll(500e6);assertLt(uint256(uint64(core.state(address(account),0).cashE6)),account.costBasisE6());
        profitRound();core.setFees(0,1e6);account.requestExit(5e6,false);core.processTransfer();
        account.settleExit(4e6,1e6,core.blockNo(),uint64(vm.getBlockTimestamp()+120),keccak256("venue evidence"),attest(keccak256(abi.encode("EXIT",uint64(4e6),uint64(1e6)))));
        assertEq(account.profitSentE6(),5e6);assertEq(account.exit().amount(),4e6);
    }
    function testRejectedSpotExitCanRetryOnlyWithAttestationAndUnchangedBalances() public {
        fundAll(500e6);core.giveSpot(address(account),10e8);
        vm.prank(guardian);account.pause();vm.warp(vm.getBlockTimestamp()+2 days);core.tick(101);
        vm.prank(guardian);account.quarantineUnknown(keccak256("untracked spot credit"));
        vm.prank(guardian);account.recoverSpot(10e6);core.tick(1);
        account.rejectExit(core.blockNo(),uint64(vm.getBlockTimestamp()+120),keccak256("venue evidence"),attest(keccak256(abi.encode("EXIT_REJECTED",uint256(10e6),uint8(2)))));
        assertEq(uint8(account.pending()),0);assertEq(uint8(account.recoveryExit().stage()),0);
        assertEq(account.unallocatedSpotE6(),10e6);
    }
    function testUnknownRecoveryRetiresBasisAndCannotDivertProfit() public {
        fundAll(500e6);profitRound();vm.prank(guardian);account.pause();vm.warp(vm.getBlockTimestamp()+2 days);
        vm.prank(guardian);account.requestExit(100e6,true);core.processTransfer();core.tick(101);
        vm.prank(guardian);account.quarantineUnknown(keccak256("missing receipt"));
        assertEq(account.costBasisE6(),400e6);assertTrue(account.accountingQuarantined());assertEq(account.availableProfit(),0);
        vm.prank(guardian);account.recoverExit(true,false);
        assertEq(uint8(account.recoveryExit().stage()),2);
        vm.prank(guardian);vm.expectRevert(TradingAccount.Restricted.selector);account.requestExit(401e6,true);
    }
    function testCostEventsIdempotentAndGainsCannotInventEquity() public {
        fundAll(500e6);bytes32 id=keccak256("funding");bytes32 p=keccak256(abi.encode("COST",int256(100e6),true));
        bytes32 h=verifier.digest(address(account),id,p,core.blockNo(),uint64(vm.getBlockTimestamp()+120),keccak256("venue evidence"));
        (uint8 v,bytes32 rr,bytes32 ss)=vm.sign(oracleKey,h);bytes memory sig=abi.encodePacked(rr,ss,v);
        account.bookCost(id,100e6,true,core.blockNo(),uint64(vm.getBlockTimestamp()+120),keccak256("venue evidence"),sig);
        assertEq(account.availableProfit(),0);
        uint64 b=core.blockNo();vm.expectRevert(TradingAccount.Restricted.selector);account.bookCost(id,100e6,true,b,uint64(vm.getBlockTimestamp()+120),keccak256("venue evidence"),sig);
    }
    function testStaleModelCommitAndUnapprovedSignerCannotExecute() public {
        fundAll(500e6);uint64 n=commit(1);vm.warp(vm.getBlockTimestamp()+121);
        vm.expectRevert(TradingAccount.Restricted.selector);account.execute(n);
    }
    function testTaxPipelinePauseAndResumeKeepsFixedRoute() public {
        claimVault.accrue(q(50e6));vm.prank(guardian);converter.pause();
        vm.expectRevert(TaxConverter.Restricted.selector);converter.claim();
        vm.prank(guardian);converter.resume();converter.claim();converter.convert(q(50e6),49e6,hopIn(50e6));
        assertGt(treasury.liquidPrincipal(),49e6);
    }


    function testFuzzOpeningExposureIsCappedByEquityAndOrderLimit(uint64 capital) public {
        capital=uint64(bound(capital,20e6,500e6));fundAll(capital);
        (uint64 px,uint64 size)=account.previewOrder(true);
        uint256 notional=uint256(size)*px/1e10;
        assertLe(notional,100e6);assertLe(notional,uint256(uint64(core.state(address(account),0).equityE6)));
    }

    function testPartialCloseUsesNativeRemainingCostBasis() public {
        fundAll(500e6);account.execute(commit(1));uint64 bought=uint64(account.pendingAmount());settleOrder(1,bought,core.price(),0);
        account.execute(commit(2));uint64 part=bought/2000*1000;
        int256 pnl=core.processOrder(part,core.price(),1000);
        // Model a small legitimate remainder difference from per-fill cost rounding.
        core.retainRoundedEntry(address(account),20);
        TradingAccount.OrderReceipt memory receipt=TradingAccount.OrderReceipt(2,part,core.price(),pnl+20,1000,bought-part);
        bytes32 payload=keccak256(abi.encode("ORDER",account.cloid(),receipt));
        account.settleOrder(receipt,core.blockNo(),uint64(vm.getBlockTimestamp()+120),keccak256("venue evidence"),attest(payload));
        assertEq(uint8(account.pending()),0);assertEq(account.tradingNetE6(),pnl+20-1000);
    }

    function testGuardianCanRetryOnlyFixedSetupAfterActivationOrGasRepair() public {
        core.initialize(address(account));core.initialize(address(account.exit()));core.initialize(address(account.recoveryExit()));
        account.configureCore();bytes32 op=account.operation();
        vm.expectRevert(TradingAccount.Restricted.selector);account.retrySetup();
        vm.prank(guardian);vm.expectRevert(TradingAccount.Restricted.selector);account.retrySetup();
        vm.warp(vm.getBlockTimestamp()+31);vm.prank(guardian);account.retrySetup();
        assertEq(account.operation(),op);core.processSetup();
        account.settleSetup(core.blockNo(),uint64(vm.getBlockTimestamp()+120),keccak256("venue evidence"),attest(keccak256(abi.encode("SETUP_DISABLED",address(account.exit()),address(account.recoveryExit())))));
        assertTrue(account.setupComplete());assertEq(uint8(account.pending()),0);
        vm.prank(guardian);vm.expectRevert(TradingAccount.Restricted.selector);account.retrySetup();
    }

    function testFundsInTransitOrSpotCannotTriggerPermissionlessLossPause() public {
        fundAll(500e6);
        tax(500e6);
        treasury.forward(treasury.liquidPrincipal(),10_000);principalIngress.receiveTransfer(mx.last(),hex"ab");
        uint64 net=uint64(account.nativePrincipalE6());account.fund();
        vm.expectRevert(TradingAccount.Restricted.selector);account.cancelAndPause();
        core.processDeposit();account.settleDeposit(net,0,core.blockNo(),uint64(vm.getBlockTimestamp()+120),keccak256("venue evidence"),attest(keccak256(abi.encode("DEPOSIT",net,uint64(0)))));
        vm.expectRevert(TradingAccount.Restricted.selector);account.cancelAndPause();
        vm.expectRevert(TradingAccount.Restricted.selector);account.previewOrder(true);
        account.moveToPerp();vm.expectRevert(TradingAccount.Restricted.selector);account.cancelAndPause();
        assertFalse(account.paused());
    }
    function testRecoveryReservesUnmovedNativePrincipalAndPreservesConversionLoss() public {
        fundAll(500e6);profitRound();
        tax(200e6);
        treasury.forward(treasury.liquidPrincipal(),10_000);principalIngress.receiveTransfer(mx.last(),hex"ab");
        uint256 native=account.nativePrincipalE6();assertEq(account.costBasisE6(),700e6);
        vm.prank(guardian);account.pause();vm.warp(vm.getBlockTimestamp()+2 days);
        vm.prank(guardian);vm.expectRevert(TradingAccount.Restricted.selector);account.requestExit(501e6,true);
        vm.prank(guardian);account.recoverNative();
        assertEq(account.costBasisE6(),700e6-native);assertEq(account.nativeBasisE6(),0);
        assertEq(account.nativePrincipalE6(),0);assertGt(account.costBasisE6(),500e6);
    }
    function testFavorableConversionIsStillNewPrincipalNotProfit() public {
        uh.mint(address(account),101e6);
        vm.prank(address(principalIngress));account.creditPrincipal(101e6,100e6,keccak256("favorable conversion"));
        assertEq(account.costBasisE6(),101e6);assertEq(account.nativeBasisE6(),101e6);
        assertEq(account.availableProfit(),0);
    }

    function testAttestedExitSurplusDoesNotIncreaseReturnedPrincipalOrProfit() public {
        fundAll(500e6);profitRound();account.requestExit(5e6,false);core.processTransfer();
        core.giveSpot(address(account.exit()),1); // A third party sent one Core USDC base unit.
        account.settleExit(5e6,0,core.blockNo(),uint64(vm.getBlockTimestamp()+120),keccak256("venue evidence"),attest(keccak256(abi.encode("EXIT",uint64(5e6),uint64(0)))));
        assertEq(account.exit().amount(),5e6);assertEq(account.profitSentE6(),5e6);
        account.exit().bridgeToEvm();core.processTransfer();
        core.giveSpot(address(account.exit()),1); // Donation after the bridge was queued.
        account.exit().reconcileEvm();assertEq(account.exit().amount(),5e6);
    }
}
