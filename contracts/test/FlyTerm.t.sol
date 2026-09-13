// SPDX-License-Identifier: MIT
pragma solidity ^0.8.30;
import {Test} from "forge-std/Test.sol";
import {ERC20} from "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {DecisionRegistry} from "../src/DecisionRegistry.sol";
import {FixedRouteTreasury,ITokenMessengerV2} from "../src/FixedRouteTreasury.sol";
import {HyperPolicyAccount,ICoreWriter,ICoreDepositWallet} from "../src/HyperPolicyAccount.sol";
import {IHyperRead,HyperRead} from "../src/HyperRead.sol";

contract TestUSDC is ERC20 {
    constructor() ERC20("Test USDC","USDC") {}
    function decimals() public pure override returns(uint8){return 6;}
    function mint(address to,uint256 amount) external {_mint(to,amount);}
}
contract MessengerMock is ITokenMessengerV2 {
    uint32 public domain; bytes32 public recipient; uint256 public amount;uint256 public fee;bytes32 public caller;uint32 public finality;
    function depositForBurn(uint256 a,uint32 d,bytes32 r,address t,bytes32 c,uint256 f,uint32 fin) external {
        domain=d;recipient=r;amount=a;fee=f;caller=c;finality=fin;
        IERC20(t).transferFrom(msg.sender,address(this),a);
    }
}
contract CoreReadMock is IHyperRead {
    Snapshot internal state;
    function set(int64 qty,uint64 price,int64 equity,uint64 ntl,uint64 blockNo,bool exists,uint8 decimals_) external {
        state=Snapshot(qty,price,equity,ntl,blockNo,exists,decimals_);
    }
    function snapshot(address,uint16) external view returns(Snapshot memory){return state;}
}
contract WriterMock is ICoreWriter {
    bytes public last;uint256 public count;
    function sendRawAction(bytes calldata raw) external {last=raw;count++;}
}
contract DepositMock is ICoreDepositWallet {
    IERC20 public token;address public recipient;uint256 public amount;uint32 public dex;
    constructor(IERC20 t){token=t;}
    function depositFor(address r,uint256 a,uint32 d) external {
        recipient=r;amount=a;dex=d;token.transferFrom(msg.sender,address(this),a);
    }
}
contract FlyTermTest is Test {
    uint256 internal signerKey=0x123456;
    address internal guardian=address(0x777);
    DecisionRegistry internal registry;
    TestUSDC internal usdc;
    MessengerMock internal messenger;
    FixedRouteTreasury internal treasury;
    CoreReadMock internal reader;
    WriterMock internal writer;
    DepositMock internal deposit;
    HyperPolicyAccount internal account;
    function setUp() public {
        vm.warp(1000);
        registry=new DecisionRegistry(bytes32(uint256(1)),bytes32(uint256(2)),bytes32(uint256(3)),vm.addr(signerKey));
        usdc=new TestUSDC();messenger=new MessengerMock();
        treasury=new FixedRouteTreasury(usdc,messenger,19,address(0x999),guardian,50,10e6,500e6,1000e6);
        reader=new CoreReadMock();writer=new WriterMock();deposit=new DepositMock(usdc);
        account=new HyperPolicyAccount(registry,reader,writer,usdc,deposit,guardian,0,100e6,200e6,50);
        reader.set(0,100e8,0,0,1,true,5);
    }
    function decision(uint8 side) internal returns(uint64 seq) {
        seq=registry.sequence()+1;
        DecisionRegistry.Decision memory d=DecisionRegistry.Decision(seq,uint64(block.timestamp),uint64(block.timestamp+60),registry.stateRoot(),keccak256(abi.encode(seq,"next")),keccak256("input"),keccak256(abi.encode(seq,"record")),side);
        (uint8 v,bytes32 r,bytes32 s)=vm.sign(signerKey,registry.decisionDigest(d));
        registry.submit(d,abi.encodePacked(r,s,v));
    }
    function funded() internal {
        usdc.mint(address(account),500e6);account.fund(500e6);
        reader.set(0,100e8,500e6,0,2,true,5);account.reconcileFunding();
    }
    function testDecisionWrongSignerRejected() public {
        DecisionRegistry.Decision memory d=DecisionRegistry.Decision(1,1000,1060,registry.stateRoot(),bytes32(uint256(4)),bytes32(uint256(5)),bytes32(uint256(6)),1);
        (uint8 v,bytes32 r,bytes32 s)=vm.sign(123,registry.decisionDigest(d));
        vm.expectRevert(DecisionRegistry.InvalidAttestor.selector);registry.submit(d,abi.encodePacked(r,s,v));
    }
    function testDecisionCannotBeReplayedAcrossContracts() public {
        DecisionRegistry other=new DecisionRegistry(bytes32(uint256(1)),bytes32(uint256(2)),bytes32(uint256(3)),vm.addr(signerKey));
        DecisionRegistry.Decision memory d=DecisionRegistry.Decision(1,1000,1060,registry.stateRoot(),bytes32(uint256(4)),bytes32(uint256(5)),bytes32(uint256(6)),1);
        (uint8 v,bytes32 r,bytes32 s)=vm.sign(signerKey,registry.decisionDigest(d));
        vm.expectRevert(DecisionRegistry.InvalidAttestor.selector);other.submit(d,abi.encodePacked(r,s,v));
        registry.submit(d,abi.encodePacked(r,s,v));
        vm.expectRevert(DecisionRegistry.InvalidDecision.selector);registry.submit(d,abi.encodePacked(r,s,v));
    }
    function testDecisionCannotSkipSequenceOrAlterPreviousState() public {
        DecisionRegistry.Decision memory d=DecisionRegistry.Decision(2,1000,1060,registry.stateRoot(),bytes32(uint256(4)),bytes32(uint256(5)),bytes32(uint256(6)),1);
        vm.expectRevert(DecisionRegistry.InvalidDecision.selector);registry.submit(d,"");
        d.sequence=1;d.previousState=bytes32(uint256(777));
        vm.expectRevert(DecisionRegistry.InvalidDecision.selector);registry.submit(d,"");
    }
    function testExpiredDecisionRejected() public {
        DecisionRegistry.Decision memory d=DecisionRegistry.Decision(1,900,999,registry.stateRoot(),bytes32(uint256(4)),bytes32(uint256(5)),bytes32(uint256(6)),1);
        vm.expectRevert(DecisionRegistry.InvalidDecision.selector);registry.submit(d,"");
    }
    function testTreasuryRouteAndAllowanceAreFixed() public {
        usdc.mint(address(treasury),100e6);
        vm.prank(address(0x123));treasury.forward(100e6,500000);
        assertEq(messenger.domain(),19);assertEq(messenger.recipient(),bytes32(uint256(uint160(address(0x999)))));
        assertEq(messenger.finality(),2000);assertEq(messenger.caller(),bytes32(0));
        assertEq(usdc.balanceOf(address(treasury)),0);assertEq(usdc.allowance(address(treasury),address(messenger)),0);
        (bool ok,)=address(treasury).call(abi.encodeWithSignature("withdraw(address,uint256)",address(this),1));
        assertFalse(ok);
    }
    function testTreasuryFeeAndDailyBudget() public {
        usdc.mint(address(treasury),1500e6);
        vm.expectRevert(FixedRouteTreasury.Restricted.selector);treasury.forward(100e6,500001);
        treasury.forward(500e6,0);treasury.forward(500e6,0);
        vm.expectRevert(FixedRouteTreasury.Restricted.selector);treasury.forward(10e6,0);
        vm.warp(block.timestamp+1 days);treasury.forward(10e6,0);
    }
    function testPauseOnlyGuardianAndCannotResume() public {
        vm.expectRevert(FixedRouteTreasury.Restricted.selector);treasury.pause();
        vm.prank(guardian);treasury.pause();
        usdc.mint(address(treasury),100e6);
        vm.expectRevert(FixedRouteTreasury.Restricted.selector);treasury.forward(100e6,0);
        (bool ok,)=address(treasury).call(abi.encodeWithSignature("unpause()"));assertFalse(ok);
    }
    function testDepositUsesOwnCoreAccountAndWaitsForCredit() public {
        usdc.mint(address(account),500e6);account.fund(500e6);
        assertEq(deposit.recipient(),address(account));assertEq(deposit.dex(),0);
        assertEq(account.contributedE6(),500e6);assertEq(account.expectedDepositE6(),500e6);
        vm.expectRevert(HyperPolicyAccount.PendingOutcome.selector);account.reconcileFunding();
        decision(1);vm.expectRevert(HyperPolicyAccount.PendingOutcome.selector);account.execute(1,99_009_000);
        reader.set(0,100e8,500e6,0,2,true,5);account.reconcileFunding();
        assertEq(account.expectedDepositE6(),0);
    }
    function testCoreWriterEncodingAndUnknownOutcomeStop() public {
        funded();decision(1);account.execute(1,99_009_000);
        bytes memory raw=writer.last();assertEq(bytes4(raw),hex"01000001");
        bytes memory payload=new bytes(raw.length-4);for(uint256 i;i<payload.length;i++)payload[i]=raw[i+4];
        (uint32 a,bool buy,uint64 px,uint64 sz,bool reduce,uint8 tif,uint128 cloid)=abi.decode(payload,(uint32,bool,uint64,uint64,bool,uint8,uint128));
        assertEq(a,0);assertTrue(buy);assertEq(px,101e8);assertEq(sz,99_009_000);assertFalse(reduce);assertEq(tif,3);assertTrue(cloid!=0);
        vm.expectRevert(HyperPolicyAccount.PendingOutcome.selector);account.reconcilePosition();
        vm.warp(2000);reader.set(0,100e8,500e6,0,100,true,5);
        vm.expectRevert(HyperPolicyAccount.PendingOutcome.selector);account.reconcilePosition();
        account.cancelPending();assertEq(bytes4(writer.last()),hex"0100000b");assertTrue(account.pending());
    }
    function testObservedPositionAllowsOnlyReducingNext() public {
        funded();decision(1);account.execute(1,99_009_000);
        reader.set(99009,100e8,499e6,100e6,3,true,5);account.reconcilePosition();
        assertFalse(account.pending());decision(1);
        vm.expectRevert(HyperPolicyAccount.Restricted.selector);account.execute(2,5e7);
        decision(2);account.execute(3,99_009_000);assertFalse(account.pendingBuy());
        reader.set(0,100e8,498e6,0,4,true,5);account.reconcilePosition();
        assertFalse(account.pending());
    }
    function testSizeOrderAndExposureCaps() public {
        funded();decision(1);
        vm.expectRevert(HyperPolicyAccount.Restricted.selector);account.execute(1,1e8);
        vm.expectRevert(HyperPolicyAccount.Restricted.selector);account.execute(1,50000001);
        reader.set(0,100e8,250e6,0,3,true,5);
        vm.expectRevert(HyperPolicyAccount.Restricted.selector);account.execute(1,99_009_000);
    }
    function testNoShortOrAgentRegistration() public {
        funded();decision(2);
        vm.expectRevert(HyperPolicyAccount.Restricted.selector);account.execute(1,1e7);
        (bool ok,)=address(account).call(abi.encodeWithSignature("addApiWallet(address,string)",address(this),"escape"));
        assertFalse(ok);
    }
    function testLossExitBypassesNeuralBuyAndStopsFurtherEntry() public {
        funded();reader.set(50000,100e8,250e6,50e6,3,true,5);
        decision(1);account.emergencyClose();assertTrue(account.paused());assertFalse(account.pendingBuy());
        reader.set(0,100e8,249e6,0,4,true,5);account.reconcilePosition();
        vm.expectRevert(HyperPolicyAccount.Restricted.selector);account.execute(1,99_009_000);
    }
    function testPublicCallerCannotChooseDustOrPartialSizing() public {
        funded();decision(1);
        vm.expectRevert(HyperPolicyAccount.Restricted.selector);account.execute(1,1000);
        vm.expectRevert(HyperPolicyAccount.Restricted.selector);account.execute(1,5e7);
        assertFalse(account.pending());
    }
    function testCustodyPrototypeCannotDeployOnMainnet() public {
        vm.chainId(999);
        vm.expectRevert(bytes("Local research only: exit route not accepted"));
        new FixedRouteTreasury(usdc,messenger,19,address(0x999),guardian,50,10e6,500e6,1000e6);
    }
    function testFuzzFeeCap(uint128 a,uint128 f) public {
        uint256 amount=bound(a,10e6,500e6);uint256 fee=bound(f,0,amount);
        usdc.mint(address(treasury),amount);
        if(fee>amount*50/10000||fee>=amount)vm.expectRevert(FixedRouteTreasury.Restricted.selector);
        treasury.forward(amount,fee);
    }
}
