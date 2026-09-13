// SPDX-License-Identifier: MIT
pragma solidity ^0.8.30;
/// @dev ABI and normalization from hyperliquid-dev/hyper-evm-lib
/// commit 4eb7ab044d0a368e0c01ec5b38d5ea48a3e3b427, MIT.
interface IHyperRead {
    struct Snapshot {int64 quantity; uint64 priceE8; int64 equityE6; uint64 notionalE6;uint64 coreBlock;bool exists;uint8 sizeDecimals;}
    function snapshot(address user,uint16 asset) external view returns(Snapshot memory);
}
contract HyperRead is IHyperRead {
    struct Position {int64 szi;uint64 entryNtl;int64 isolatedRawUsd;uint32 leverage;bool isIsolated;}
    struct Margin {int64 accountValue;uint64 marginUsed;uint64 ntlPos;int64 rawUsd;}
    struct AssetInfo {string coin;uint32 marginTableId;uint8 szDecimals;uint8 maxLeverage;bool onlyIsolated;}
    error InvalidCoreState();
    function read(address target,bytes memory input) private view returns(bytes memory result) {
        bool ok;(ok,result)=target.staticcall{gas:200000}(input);
        if(!ok||result.length==0)revert InvalidCoreState();
    }
    function snapshot(address user,uint16 asset) external view returns(Snapshot memory s) {
        AssetInfo memory a=abi.decode(read(address(0x080a),abi.encode(uint32(asset))),(AssetInfo));
        if(keccak256(bytes(a.coin))!=keccak256("BTC")||a.szDecimals>6)revert InvalidCoreState();
        Position memory p=abi.decode(read(address(0x0800),abi.encode(user,asset)),(Position));
        Margin memory m=abi.decode(read(address(0x080f),abi.encode(uint32(0),user)),(Margin));
        uint64 px=abi.decode(read(address(0x0807),abi.encode(uint32(asset))),(uint64));
        uint256 price=uint256(px)*10**(uint256(a.szDecimals)+2);
        if(price==0||price>type(uint64).max)revert InvalidCoreState();
        s=Snapshot(p.szi,uint64(price),m.accountValue,m.ntlPos,
                   abi.decode(read(address(0x0809),""),(uint64)),
                   abi.decode(read(address(0x0810),abi.encode(user)),(bool)),a.szDecimals);
    }
}
