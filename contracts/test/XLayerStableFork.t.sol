// SPDX-License-Identifier: MIT
pragma solidity ^0.8.30;
import {Test} from "forge-std/Test.sol";
import {Vm} from "forge-std/Vm.sol";
import {TaxTreasury} from "../src/v03/TaxTreasury.sol";
import {ICctpMessenger} from "../src/v03/ProtocolTypes.sol";
import {StablePoolSwap} from "../src/v03/StablePoolSwap.sol";
import {IV3Pool} from "../src/v03/ProtocolTypes.sol";
import {ProfitBuyback} from "../src/v03/ProfitBuyback.sol";
import {IIgnixManager,IV2Router} from "../src/v03/ProtocolTypes.sol";
import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
contract StableSwapHarness is StablePoolSwap {
    constructor(IV3Pool p,IERC20 u,IERC20 t) StablePoolSwap(p,u,t,50) {}
    function run(bool toUsdc,uint256 amount) external returns(uint256){return _swapStable(toUsdc,amount);}
}
contract XLayerStableFork is Test {
    function testForkCurveProfitBuyback() public {
        if(!vm.envOr("RUN_XLAYER_FORK",false)){vm.skip(true);return;}
        vm.createSelectFork("https://rpc.xlayer.tech");
        IERC20 u=IERC20(0xB6CEceAB302E2E4948951eE7843FC24E92933061);
        IERC20 t=IERC20(0x779Ded0c9e1022225f8E0630b35a9b54bE713736);
        address token=address(bytes20(hex"5ac39a75d2eda83d15024f6ab519093c63cfeeee"));
        address manager=address(bytes20(hex"96b51c57e5346d0c0198899243cf851d1e23c309"));
        address router=address(bytes20(hex"182a927119d56008d921126764bf884221b10f59"));
        ProfitBuyback b=new ProfitBuyback(IV3Pool(0xEEeB3C1F61DC3070C675c2670a3f2188A060012D),u,t,address(0),t,IERC20(address(0)),address(this),address(this),token,IIgnixManager(manager),IV2Router(router),100e6,100e6,600,500,50);
        deal(address(u),address(b),5e6);b.creditReturn(5e6,1,keccak256("fork-return"));
        b.convertProfit(5e6);b.observe();vm.warp(vm.getBlockTimestamp()+601);b.observe();
        uint256 beforeDead=IERC20(token).balanceOf(b.DEAD());b.buyback(1e6);
        assertGt(b.escrowedTokens(),0);
        // Graduate only this local fork, exercising the actual platform migration and V2 router.
        deal(address(t),address(this),20_000e6);t.approve(manager,20_000e6);IIgnixManager(manager).buy(token,20_000e6,0);
        assertTrue(IIgnixManager(manager).pairOf(token)!=address(0));
        b.flushEscrow();assertGt(IERC20(token).balanceOf(b.DEAD()),beforeDead);
        b.observe();vm.warp(vm.getBlockTimestamp()+601);b.observe();b.buyback(1e6);
        assertEq(t.allowance(address(b),manager),0);
        emit log_named_uint("Curve tokens sent to dead",IERC20(token).balanceOf(b.DEAD())-beforeDead);
    }
    function testForkRoundTripStableSwap() public {
        if(!vm.envOr("RUN_XLAYER_FORK",false)){vm.skip(true);return;}
        vm.createSelectFork("https://rpc.xlayer.tech");
        address u=0xB6CEceAB302E2E4948951eE7843FC24E92933061;
        address t=0x779Ded0c9e1022225f8E0630b35a9b54bE713736;
        address p=0xEEeB3C1F61DC3070C675c2670a3f2188A060012D;
        StableSwapHarness swapper=new StableSwapHarness(IV3Pool(p),IERC20(u),IERC20(t));
        deal(t,address(swapper),100e6);
        uint256 received=swapper.run(true,100e6);assertGe(received,99_500_000);assertEq(IERC20(t).balanceOf(address(swapper)),0);
        uint256 back=swapper.run(false,received);assertGe(back,99e6);
        emit log_named_uint("USDC after first swap",received);
        emit log_named_uint("USDt0 after roundtrip",back);
        emit log_named_uint("Fork block",block.number);
    }

    function testForkCircleBurnUsesRealMessengerAndExactHook() public {
        if(!vm.envOr("RUN_XLAYER_FORK",false)){vm.skip(true);return;}
        vm.createSelectFork("https://rpc.xlayer.tech");
        IERC20 u=IERC20(0xB6CEceAB302E2E4948951eE7843FC24E92933061);
        ICctpMessenger m=ICctpMessenger(0x28b5a0e9C621a5BadaA536219b3a228C8168cf5d);
        address receiver=address(0x1234);address ingress=address(0x5678);
        TaxTreasury t=new TaxTreasury(u,m,address(this),receiver,ingress,address(this),19,10e6,100e6,100e6,100);
        deal(address(u),address(t),50e6);t.creditConversion(50e6,50_010_000);
        vm.recordLogs();t.forward(50e6,500_000);Vm.Log[] memory logs=vm.getRecordedLogs();
        bytes memory message;
        for(uint256 i;i<logs.length;i++){
            if(logs[i].emitter==0x81D40F21F12A8F0E3252Bccb954D722d4c464B64&&logs[i].topics[0]==keccak256("MessageSent(bytes)"))message=abi.decode(logs[i].data,(bytes));
        }
        assertEq(message.length,536);assertEq(u.balanceOf(address(t)),0);assertEq(u.allowance(address(t),address(m)),0);
        assertEq(t.liquidPrincipal(),0);assertEq(t.basis(),0);
        this.checkMessage(message,address(t),receiver,ingress);
        emit log_named_uint("Real CCTP source message bytes",message.length);
        emit log_named_uint("Circle fork block",block.number);
    }
    function checkMessage(bytes calldata m,address sender,address receiver,address ingress) external pure {
        require(uint32(bytes4(m[4:8]))==37&&uint32(bytes4(m[8:12]))==19);
        require(bytes32(m[108:140])==bytes32(uint256(uint160(ingress))));
        require(bytes32(m[184:216])==bytes32(uint256(uint160(receiver))));
        require(bytes32(m[248:280])==bytes32(uint256(uint160(sender))));
        (bytes4 magic,uint8 kind,uint256 basis,uint64 sequence,)=abi.decode(m[376:],(bytes4,uint8,uint256,uint64,bytes32));
        require(magic==bytes4("FT03")&&kind==0&&basis==50_010_000&&sequence==1);
    }
}
