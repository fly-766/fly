// SPDX-License-Identifier: MIT
pragma solidity ^0.8.30;
import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {SafeERC20} from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import {ReentrancyGuard} from "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import {IReturnReceiver} from "./ProtocolTypes.sol";
/// @notice Explicit emergency return: one immutable beneficiary, visible immutable delay.
contract RecoveryVault is ReentrancyGuard,IReturnReceiver {
    using SafeERC20 for IERC20;
    IERC20 public immutable usdc;address public immutable ingress;address public immutable beneficiary;uint64 public immutable delay;
    uint256 public credited;uint256 public requested;uint64 public availableAt;
    error Restricted();
    event Credited(bytes32 indexed source,uint256 amount);
    event WithdrawalScheduled(uint256 amount,uint64 availableAt);
    event Withdrawn(uint256 amount,address indexed beneficiary);
    constructor(IERC20 u,address i,address b,uint64 d) {if(address(u).code.length==0||i==address(0)||b==address(0)||d<1 days)revert Restricted();usdc=u;ingress=i;beneficiary=b;delay=d;}
    function creditReturn(uint256 amount,uint8 kind,bytes32 id) external {
        if(msg.sender!=ingress||kind!=2||amount==0||usdc.balanceOf(address(this))<credited+amount)revert Restricted();
        credited+=amount;emit Credited(id,amount);
    }
    function schedule(uint256 amount) external {
        if(msg.sender!=beneficiary||amount==0||amount>credited||requested!=0)revert Restricted();
        requested=amount;availableAt=uint64(block.timestamp)+delay;emit WithdrawalScheduled(amount,availableAt);
    }
    function withdraw() external nonReentrant {
        if(requested==0||block.timestamp<availableAt)revert Restricted();
        uint256 amount=requested;requested=0;credited-=amount;usdc.safeTransfer(beneficiary,amount);emit Withdrawn(amount,beneficiary);
    }
}
