// SPDX-License-Identifier: MIT
pragma solidity ^0.8.30;
import {NativeCoreRead} from "../v03/NativeCoreRead.sol";
import {ICoreRead03} from "../v03/ProtocolTypes.sol";
import {PositionMathV05} from "./PositionMathV05.sol";
/// @notice Signed BTC position reads plus actual venue leverage verification. Cross margin only.
contract NativeCoreReadV05 is NativeCoreRead {
    function leverage(address user,uint16 asset) external view returns(uint32 current,uint8 maximum,uint64 totalNotionalE6) {
        (bool ok,bytes memory data)=address(0x0800).staticcall{gas:200000}(abi.encode(user,asset));if(!ok)revert BadRead();P memory p=abi.decode(data,(P));
        (ok,data)=address(0x080a).staticcall{gas:200000}(abi.encode(uint32(asset)));if(!ok)revert BadRead();A memory a=abi.decode(data,(A));
        (ok,data)=address(0x080f).staticcall{gas:200000}(abi.encode(uint32(0),user));if(!ok)revert BadRead();M memory m=abi.decode(data,(M));
        if(p.isIsolated||a.isolated||keccak256(bytes(a.coin))!=keccak256("BTC"))revert BadRead();
        return(p.leverage,a.leverage,m.notional);
    }
    function quoteOrder(address user,bool buy,uint64 capE6,uint8 leverageCap,uint16 reserveBps,uint16 slipBps) external view returns(uint64,uint64) {
        ICoreRead03.State memory s=this.state(user,0);
        if(s.quantity==0){(uint32 current,uint8 maximum,uint64 ntl)=this.leverage(user,0);if(current!=leverageCap||maximum<leverageCap||ntl!=0)revert BadRead();}
        return PositionMathV05.quote(s,buy,capE6,leverageCap,reserveBps,slipBps);
    }
}
