// SPDX-License-Identifier: MIT
pragma solidity ^0.8.30;
import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";

interface ICctpMessenger {
    function depositForBurnWithHook(uint256,uint32,bytes32,address,bytes32,uint256,uint32,bytes calldata) external;
}
interface ICctpTransmitter {function receiveMessage(bytes calldata,bytes calldata) external returns(bool);}
interface IPrincipalReceiver {function creditPrincipal(uint256 netAmount,uint256 costBasis,bytes32 sourceId) external;}
interface IReturnReceiver {function creditReturn(uint256 amount,uint8 kind,bytes32 sourceId) external;}
interface ICostTreasury {function creditConversion(uint256 amount,uint256 costBasis) external;}
interface IV3Pool {
    function token0() external view returns(address);
    function token1() external view returns(address);
    function fee() external view returns(uint24);
    function swap(address,bool,int256,uint160,bytes calldata) external returns(int256,int256);
}
interface IV2Pair {
    function token0() external view returns(address);
    function token1() external view returns(address);
    function getReserves() external view returns(uint112,uint112,uint32);
    function price0CumulativeLast() external view returns(uint256);
    function price1CumulativeLast() external view returns(uint256);
}
interface IV2Router {
    function swapExactTokensForTokensSupportingFeeOnTransferTokens(uint256,uint256,address[] calldata,address,uint256) external;
}

interface ICoreWriter03 {function sendRawAction(bytes calldata) external;}
interface ICoreDeposit03 {function depositFor(address,uint256,uint32) external;}
interface ICoreRead03 {
    struct State {int64 quantity;uint64 entryNotionalE6;uint64 oracleE8;int64 equityE6;int64 cashE6;uint64 coreBlock;uint8 sizeDecimals;bool exists;bool isolated;}
    function state(address user,uint16 asset) external view returns(State memory);
    function spot(address user,uint64 token) external view returns(uint64 total,uint64 hold);
}
interface ISettlement03 {
    function verify(address account,bytes32 operation,bytes32 payload,uint64 coreBlock,uint64 deadline,bytes32 evidence,bytes calldata signature) external view;
}
library CoreEncoding {
    uint32 internal constant SPOT=type(uint32).max;
    address internal constant USDC_SYSTEM=0x2000000000000000000000000000000000000000;
    address internal constant HYPE_SYSTEM=0x2222222222222222222222222222222222222222;
    function sendAsset(address to,uint32 fromDex,uint32 toDex,uint64 amountE8) internal pure returns(bytes memory) {
        return abi.encodePacked(uint8(1),uint24(13),abi.encode(to,address(0),fromDex,toDex,uint64(0),amountE8));
    }
}
