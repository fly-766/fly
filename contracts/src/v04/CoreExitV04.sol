// SPDX-License-Identifier: MIT
pragma solidity ^0.8.30;
import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {CoreExit} from "../v03/CoreExit.sol";
import {ICoreRead03,ICoreWriter03,ICctpMessenger} from "../v03/ProtocolTypes.sol";
import {CoreReserves} from "./CoreReserves.sol";
interface IReserveParent04 {
    function guardian() external view returns(address);
    function paused() external view returns(bool);
    function pending() external view returns(uint8);
    function nativePrincipalE6() external view returns(uint256);
    function unallocatedSpotE6() external view returns(uint256);
}
contract CoreExitV04 is CoreExit,CoreReserves {
    constructor(address p,IERC20 u,ICoreRead03 r,ICoreWriter03 w,ICctpMessenger m,address i,address profit,address recovery,uint32 d,uint16 f,uint8 k)
        CoreExit(p,u,r,w,m,i,profit,recovery,d,f,k) {}
    function _reserveContext() internal view override returns(IERC20,ICoreRead03,ICoreWriter03,address) {
        IReserveParent04 p=IReserveParent04(parent);
        ICoreRead03.State memory s=reader.state(parent,0);
        if(stage!=Stage.IDLE||!p.paused()||p.pending()!=0||p.nativePrincipalE6()!=0||p.unallocatedSpotE6()!=0||s.quantity!=0||s.cashE6!=0)revert ReserveUnavailable();
        return(usdc,reader,writer,p.guardian());
    }
}
