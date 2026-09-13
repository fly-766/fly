// SPDX-License-Identifier: MIT
pragma solidity ^0.8.30;
import {ICoreRead03} from "../v03/ProtocolTypes.sol";
interface ICoreRead05 is ICoreRead03 {
    function leverage(address user,uint16 asset) external view returns(uint32 current,uint8 maximum,uint64 totalNotionalE6);
    function quoteOrder(address user,bool buy,uint64 capE6,uint8 leverageCap,uint16 reserveBps,uint16 slipBps) external view returns(uint64 priceE8,uint64 sizeE8);
}
library PositionMathV05 {
    error InvalidPosition();
    function signedSize(ICoreRead03.State memory s) internal pure returns(int64) {
        if(s.sizeDecimals>6)revert InvalidPosition();
        int256 n=int256(s.quantity)*int256(10**(8-s.sizeDecimals));
        if(n>type(int64).max||n< -int256(type(int64).max))revert InvalidPosition();
        return int64(n);
    }
    function quote(ICoreRead03.State memory s,bool buy,uint64 capE6,uint8 leverageCap,uint16 reserveBps,uint16 slipBps) internal pure returns(uint64,uint64) {
        if(s.oracleE8==0||!s.exists||s.isolated||s.sizeDecimals>6||leverageCap==0||leverageCap>20||reserveBps<1000||reserveBps>5000||slipBps>100)revert InvalidPosition();
        uint256 px=uint256(s.oracleE8)*(buy?10000+slipBps:10000-slipBps)/10000;
        px=buy?((px+1e8-1)/1e8)*1e8:(px/1e8)*1e8;
        if(px==0||px>type(uint64).max)revert InvalidPosition();
        int64 current=signedSize(s);uint256 size;
        if(current==0){
            if(s.equityE6<=0)revert InvalidPosition();
            uint256 budget=uint256(uint64(s.equityE6))*leverageCap*(10000-reserveBps)/10000;
            if(budget>capE6)budget=capE6;
            uint256 sizingPx=px>s.oracleE8?px:s.oracleE8;
            uint256 step=10**(8-s.sizeDecimals);size=(budget*1e10/sizingPx/step)*step;
            if(size*px/1e10<10e6)revert InvalidPosition();
        }else{
            if((current>0&&buy)||(current<0&&!buy))revert InvalidPosition();
            size=uint256(current<0?-int256(current):int256(current));
        }
        if(size==0||size>uint256(uint64(type(int64).max)))revert InvalidPosition();
        return(uint64(px),uint64(size));
    }
}
