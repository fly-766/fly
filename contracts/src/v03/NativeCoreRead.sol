// SPDX-License-Identifier: MIT
pragma solidity ^0.8.30;
import {ICoreRead03} from "./ProtocolTypes.sol";
/// @dev HyperCore ABI from the documented precompiles and hyper-evm-lib.
contract NativeCoreRead is ICoreRead03 {
    struct P {int64 szi;uint64 entryNtl;int64 isolatedRawUsd;uint32 leverage;bool isIsolated;}
    struct M {int64 value;uint64 margin;uint64 notional;int64 raw;}
    struct A {string coin;uint32 table;uint8 decimals;uint8 leverage;bool isolated;}
    error BadRead();
    function _read(address at,bytes memory data) private view returns(bytes memory out) {bool ok;(ok,out)=at.staticcall{gas:200000}(data);if(!ok||out.length==0)revert BadRead();}
    function state(address user,uint16 asset) external view returns(State memory s) {
        A memory a=abi.decode(_read(address(0x080a),abi.encode(uint32(asset))),(A));
        if(keccak256(bytes(a.coin))!=keccak256("BTC")||a.decimals>6||a.isolated)revert BadRead();
        P memory p=abi.decode(_read(address(0x0800),abi.encode(user,asset)),(P));
        M memory m=abi.decode(_read(address(0x080f),abi.encode(uint32(0),user)),(M));
        uint256 px=uint256(abi.decode(_read(address(0x0807),abi.encode(uint32(asset))),(uint64)))*10**(uint256(a.decimals)+2);
        if(px==0||px>type(uint64).max)revert BadRead();
        s=State(p.szi,p.entryNtl,uint64(px),m.value,m.raw,abi.decode(_read(address(0x0809),""),(uint64)),a.decimals,abi.decode(_read(address(0x0810),abi.encode(user)),(bool)),p.isIsolated);
    }
    function spot(address user,uint64 token) external view returns(uint64 total,uint64 hold) {
        (total,hold,)=abi.decode(_read(address(0x0801),abi.encode(user,token)),(uint64,uint64,uint64));
    }
}
