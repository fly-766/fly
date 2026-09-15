// SPDX-License-Identifier: MIT
pragma solidity ^0.8.30;
import {NativeCoreRead} from "../v03/NativeCoreRead.sol";
import {ICoreRead03} from "../v03/ProtocolTypes.sol";
import {PositionMathV05} from "./PositionMathV05.sol";
import {ICoreWriter03} from "../v03/ProtocolTypes.sol";
interface IBootstrapAccount05 {
    function registry() external view returns(address);
    function guardian() external view returns(address);
    function reader() external view returns(address);
    function writer() external view returns(ICoreWriter03);
    function setupComplete() external view returns(bool);
    function pending() external view returns(uint8);
    function costBasisE6() external view returns(uint256);
    function nativePrincipalE6() external view returns(uint256);
}
interface IRunSigner05 {function signer() external view returns(address);}
/// @notice Signed BTC position reads plus actual venue leverage verification. Cross margin only.
contract NativeCoreReadV05 is NativeCoreRead {
    bytes32 private constant BOOTSTRAP_SLOT=keccak256("flyterm.v05.leverage.bootstrap");
    /// @dev Called by delegatecall only from the account's fixed reader. It can
    /// only add the existing guardian or remove it, before principal arrives.
    function bootstrapLeverage(bool revoke) external {
        IBootstrapAccount05 account=IBootstrapAccount05(address(this));
        address signer=IRunSigner05(account.registry()).signer();
        if(msg.sender!=signer||account.setupComplete()||(account.pending()!=0&&account.pending()!=5)||account.costBasisE6()!=0||account.nativePrincipalE6()!=0)revert BadRead();
        NativeCoreReadV05 nativeReader=NativeCoreReadV05(account.reader());
        ICoreRead03.State memory s=nativeReader.state(address(this),0);
        (uint64 spotBalance,)=nativeReader.spot(address(this),0);
        (uint32 current,,uint64 notional)=nativeReader.leverage(address(this),0);
        // A newly activated Core account may hold one micro-USDC of seed dust.
        if(!s.exists||(!revoke&&(s.quantity!=0||s.cashE6!=0||s.equityE6!=0||spotBalance>100||notional!=0)))revert BadRead();
        bytes32 slot=BOOTSTRAP_SLOT;uint256 stage;
        assembly {stage:=sload(slot)}
        if(revoke){if(stage==0||current!=10)revert BadRead();stage=2;}
        else{if(stage!=0)revert BadRead();stage=1;}
        assembly {sstore(slot,stage)}
        // Name is constant so removal replaces exactly this authorization.
        account.writer().sendRawAction(abi.encodeWithSelector(bytes4(0x01000009),revoke?address(0):account.guardian(),"FlyTerm10x"));
    }
    function positionStop(address user,uint8 leverageCap,uint16 stopRoiBps) external view returns(bool) {
        return PositionMathV05.stopped(this.state(user,0),leverageCap,stopRoiBps);
    }
    function leverage(address user,uint16 asset) external view returns(uint32 current,uint8 maximum,uint64 totalNotionalE6) {
        (bool ok,bytes memory data)=address(0x0800).staticcall{gas:200000}(abi.encode(user,asset));if(!ok)revert BadRead();P memory p=abi.decode(data,(P));
        (ok,data)=address(0x080a).staticcall{gas:200000}(abi.encode(uint32(asset)));if(!ok)revert BadRead();A memory a=abi.decode(data,(A));
        (ok,data)=address(0x080f).staticcall{gas:200000}(abi.encode(uint32(0),user));if(!ok)revert BadRead();M memory m=abi.decode(data,(M));
        if(p.isIsolated||a.isolated||keccak256(bytes(a.coin))!=keccak256("BTC"))revert BadRead();
        return(p.leverage,a.leverage,m.notional);
    }
    function quoteOrder(address user,bool buy,uint8 leverageCap,uint16 reserveBps,uint16 slipBps) external view returns(uint64,uint64) {
        ICoreRead03.State memory s=this.state(user,0);
        int64 signed=PositionMathV05.signedSize(s);bool increasing=signed==0||(signed>0&&buy)||(signed<0&&!buy);
        if(increasing){(uint32 current,uint8 maximum,uint64 ntl)=this.leverage(user,0);if(current!=leverageCap||maximum<leverageCap||(signed==0&&ntl!=0))revert BadRead();}
        return PositionMathV05.quote(s,buy,leverageCap,reserveBps,slipBps);
    }
}
