// SPDX-License-Identifier: MIT
pragma solidity ^0.8.30;
import {V04ExitFixture} from "./V04ImmediateExit.t.sol";
import {Coin03,Core03} from "./V03Mocks.sol";
import {CoreReserves} from "../src/v04/CoreReserves.sol";
import {CoreExitV04} from "../src/v04/CoreExitV04.sol";
import {CoreEncoding} from "../src/v03/ProtocolTypes.sol";
contract ReserveCore04 is Core03 {
    uint64 public bridgeFeeE8;
    mapping(address=>uint64) public hype;
    mapping(address=>mapping(uint64=>uint64)) public held;
    constructor(Coin03 t) Core03(t) {}
    function giveHype(address to,uint64 amount) external {hype[to]+=amount;}
    function setBridgeFee(uint64 fee) external {bridgeFeeE8=fee;}
    function setHold(address to,uint64 token_,uint64 amount) external {held[to][token_]=amount;}
    function spot(address user,uint64 token_) external view override returns(uint64,uint64) {
        return(token_==150?hype[user]:accounts[user].spotUsdc,held[user][token_]);
    }
    function processTransfer() public override {
        require(bytes4(lastAction)==hex"0100000d");
        (address to,,uint32 src,uint32 dest,uint64 index,uint64 n)=abi.decode(_payload(),(address,address,uint32,uint32,uint64,uint64));
        if(to==CoreEncoding.USDC_SYSTEM){require(hype[lastSender]>=bridgeFeeE8);hype[lastSender]-=bridgeFeeE8;}
        if(index==0){super.processTransfer();return;}
        require(index==150&&src==type(uint32).max&&dest==type(uint32).max);
        require(n<=hype[lastSender]-held[lastSender][150]);hype[lastSender]-=n;
        if(to==CoreEncoding.HYPE_SYSTEM){(bool ok,)=lastSender.call{value:uint256(n)*1e10}("");require(ok);}
        else{hype[to]+=n;}
        blockNo++;
    }
    receive() external payable {}
}
contract V04ReserveRecovery is V04ExitFixture {
    function makeCore(Coin03 t) internal override returns(Core03) {return new ReserveCore04(t);}
    function terminateWithPrincipalReturned() internal {
        perpFund(40e6);vm.prank(guardian);account.requestExit(40e6,true);finishCoreExit(40e6);vault.withdraw();
    }
    function testParentCoreUsdcReserveReturnsAfterPrincipal() public {
        terminateWithPrincipalReturned();core.giveSpot(address(account),101_000_000);
        vm.prank(guardian);account.recoverReserves(0,101_000_000,true);
        assertEq(token.balanceOf(guardian),0);core.processTransfer();
        vm.prank(guardian);account.recoverReserves(0,1_010_000,false);
        assertEq(token.balanceOf(guardian),1_010_000);assertEq(token.balanceOf(beneficiary),40e6);
        (uint64 left,)=core.spot(address(account),0);assertEq(left,0);
    }
    function testBothExitUsdcReservesReturnToFixedGuardian() public {
        terminateWithPrincipalReturned();
        CoreExitV04[2] memory exits=[account.exit(),account.recoveryExit()];
        for(uint256 i;i<2;i++){
            core.giveSpot(address(exits[i]),101_000_000);
            vm.prank(guardian);exits[i].recoverReserves(0,101_000_000,true);core.processTransfer();
            vm.prank(guardian);exits[i].recoverReserves(0,1_010_000,false);
        }
        assertEq(token.balanceOf(guardian),2_020_000);
    }
    function testAllThreeCoreHypeReservesReachGuardianEvm() public {
        terminateWithPrincipalReturned();vm.deal(address(core),1 ether);
        address[3] memory users=[address(account),address(account.exit()),address(account.recoveryExit())];
        for(uint256 i;i<3;i++){
            ReserveCore04(payable(address(core))).giveHype(users[i],10000);
            vm.prank(guardian);CoreReserves(payable(users[i])).recoverReserves(150,10000,true);
            assertEq(users[i].balance,0);core.processTransfer();assertEq(users[i].balance,10000*1e10);
            vm.prank(guardian);CoreReserves(payable(users[i])).recoverReserves(150,10000*1e10,false);
            assertEq(users[i].balance,0);
        }
        assertEq(guardian.balance,3*10000*1e10);
    }
    function testEvmUsdcAndHypeDonationsAreRecoverable() public {
        terminateWithPrincipalReturned();
        token.mint(address(account),1234);vm.deal(address(account),7e12);
        vm.prank(guardian);account.recoverReserves(0,1234,false);
        vm.prank(guardian);account.recoverReserves(150,7e12,false);
        assertEq(token.balanceOf(guardian),1234);assertEq(guardian.balance,7e12);
    }
    function testReservesCannotBeTakenWhileCapitalOrProfitRemains() public {
        perpFund(100e6);
        vm.prank(guardian);account.pause();
        vm.prank(guardian);vm.expectRevert();account.recoverReserves(0,100,true);
        vm.prank(guardian);account.requestExit(50e6,true);finishCoreExit(50e6);
        vm.prank(guardian);vm.expectRevert();account.recoverReserves(0,100,true);
        CoreExitV04 e=account.recoveryExit();vm.prank(guardian);vm.expectRevert();e.recoverReserves(0,100,true);
    }
    function testProfitCannotEscapeThroughReserveRecovery() public {
        perpFund(100e6);account.execute(commit(1));settleOrder();core.setPrice(110e8);account.execute(commit(2));settleOrder();
        vm.prank(guardian);account.requestExit(100e6,true);finishCoreExit(100e6);
        assertGt(account.availableProfit(),0);
        core.giveSpot(address(account),100);
        vm.prank(guardian);vm.expectRevert();account.recoverReserves(0,100,true);
    }
    function testPendingExitCannotBeSwept() public {
        perpFund(40e6);vm.prank(guardian);account.requestExit(40e6,true);
        CoreExitV04 e=account.recoveryExit();
        vm.prank(guardian);vm.expectRevert();account.recoverReserves(0,100,true);
        vm.prank(guardian);vm.expectRevert();e.recoverReserves(0,100,true);
    }
    function testOperatorWrongAssetPrecisionAndHeldBalancesFail() public {
        terminateWithPrincipalReturned();core.giveSpot(address(account),1000);
        vm.expectRevert();account.recoverReserves(0,100,true);
        vm.prank(guardian);vm.expectRevert();account.recoverReserves(151,100,true);
        vm.prank(guardian);vm.expectRevert();account.recoverReserves(0,99,true);
        ReserveCore04(payable(address(core))).setHold(address(account),0,950);
        vm.prank(guardian);vm.expectRevert();account.recoverReserves(0,100,true);
        vm.prank(guardian);vm.expectRevert();account.recoverReserves(150,1,false);
        assertEq(token.balanceOf(guardian),0);
    }
    function testUsdcBridgeFeeAndFullNativeHypeRecovery() public {
        terminateWithPrincipalReturned();vm.deal(address(core),1 ether);
        ReserveCore04 gasCore=ReserveCore04(payable(address(core)));
        gasCore.giveHype(address(account),10000);gasCore.setBridgeFee(2000);core.giveSpot(address(account),100);
        vm.prank(guardian);account.recoverReserves(0,100,true);core.processTransfer();assertEq(gasCore.hype(address(account)),8000);
        vm.prank(guardian);account.recoverReserves(150,8000,true);core.processTransfer();
        assertEq(gasCore.hype(address(account)),0);assertEq(address(account).balance,8000*1e10);
        vm.prank(guardian);account.recoverReserves(150,8000*1e10,false);
        assertEq(guardian.balance,8000*1e10);
    }

    function testEmptyPausedAccountCanRecoverWithoutInventingUnknownOperation() public {
        token.mint(address(account),1234);vm.deal(address(account),1e12);
        vm.prank(guardian);account.pause();assertFalse(account.recoveryOnly());
        vm.prank(guardian);account.recoverReserves(0,1234,false);
        vm.prank(guardian);account.recoverReserves(150,1e12,false);
        assertEq(token.balanceOf(guardian),1234);assertEq(guardian.balance,1e12);
    }

}
