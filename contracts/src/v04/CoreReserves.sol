// SPDX-License-Identifier: MIT
pragma solidity ^0.8.30;
import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {SafeERC20} from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import {ReentrancyGuard} from "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import {ICoreRead03,ICoreWriter03,CoreEncoding} from "../v03/ProtocolTypes.sol";
/// @notice Only USDC and native HYPE reserves, after principal/profit accounting has finished.
abstract contract CoreReserves is ReentrancyGuard {
    using SafeERC20 for IERC20;
    error ReserveUnavailable();
    event ReserveBridgeRequested(uint64 indexed token,uint256 coreAmount);
    event ReserveReturned(uint64 indexed token,uint256 evmAmount,address indexed beneficiary);
    function _reserveContext() internal view virtual returns(IERC20,ICoreRead03,ICoreWriter03,address);
    /// @param fromCore Core amounts use 8 decimals; EVM amounts use 6 for USDC and 18 for HYPE.
    function recoverReserves(uint64 token,uint256 amount,bool fromCore) external nonReentrant {
        (IERC20 u,ICoreRead03 r,ICoreWriter03 w,address beneficiary)=_reserveContext();
        if(msg.sender!=beneficiary||amount==0||(token!=0&&token!=150))revert ReserveUnavailable();
        if(fromCore){
            if(amount>type(uint64).max||(token==0&&amount%100!=0))revert ReserveUnavailable();
            (uint64 balance,uint64 hold)=r.spot(address(this),token);
            if(amount>balance-hold)revert ReserveUnavailable();
            address system=token==0?CoreEncoding.USDC_SYSTEM:CoreEncoding.HYPE_SYSTEM;
            w.sendRawAction(abi.encodeWithSelector(bytes4(0x0100000d),system,address(0),CoreEncoding.SPOT,CoreEncoding.SPOT,token,uint64(amount)));
            emit ReserveBridgeRequested(token,amount);
        }else{
            if(token==0)u.safeTransfer(beneficiary,amount);
            else{(bool ok,)=beneficiary.call{value:amount}("");if(!ok)revert ReserveUnavailable();}
            emit ReserveReturned(token,amount,beneficiary);
        }
    }
    receive() external payable {}
}
