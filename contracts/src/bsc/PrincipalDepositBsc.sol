// SPDX-License-Identifier: MIT
pragma solidity ^0.8.30;
import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {SafeERC20} from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import {ReentrancyGuard} from "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import {IPrincipalReceiver} from "../v03/ProtocolTypes.sol";
/// @notice Credits only newly transferred HyperEVM USDC. Bridge provenance is published by the keeper.
contract PrincipalDepositBsc is ReentrancyGuard {
    using SafeERC20 for IERC20;
    IERC20 public immutable usdc; address public immutable account; address public immutable dev;
    mapping(bytes32=>bool) public consumed;
    event Deposited(bytes32 indexed source,uint256 amount);
    constructor(IERC20 u,address a,address d){require(address(u).code.length>0&&a!=address(0)&&d!=address(0));usdc=u;account=a;dev=d;}
    function deposit(uint256 amount,bytes32 source) external nonReentrant {
        require(msg.sender==dev&&amount>0&&source!=0&&!consumed[source],"INVALID_DEPOSIT");
        consumed[source]=true;uint256 beforeBalance=usdc.balanceOf(account);
        usdc.safeTransferFrom(dev,account,amount);
        require(usdc.balanceOf(account)-beforeBalance==amount,"TRANSFER_MISMATCH");
        IPrincipalReceiver(account).creditPrincipal(amount,amount,source);
        emit Deposited(source,amount);
    }
}
