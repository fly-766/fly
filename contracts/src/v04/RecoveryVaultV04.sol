// SPDX-License-Identifier: MIT
pragma solidity ^0.8.30;
import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {SafeERC20} from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import {ReentrancyGuard} from "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import {IReturnReceiver} from "../v03/ProtocolTypes.sol";
/// @notice Confirmed principal can be forwarded immediately to one immutable beneficiary.
contract RecoveryVaultV04 is ReentrancyGuard,IReturnReceiver {
    using SafeERC20 for IERC20;
    IERC20 public immutable usdc;address public immutable ingress;address public immutable beneficiary;
    uint64 public constant delay=0;uint256 public credited;
    error Restricted();
    event Credited(bytes32 indexed source,uint256 amount);
    event Withdrawn(uint256 amount,address indexed beneficiary);
    constructor(IERC20 u,address i,address b) {
        if(address(u).code.length==0||i==address(0)||b==address(0))revert Restricted();
        usdc=u;ingress=i;beneficiary=b;
    }
    function creditReturn(uint256 amount,uint8 kind,bytes32 id) external {
        if(msg.sender!=ingress||kind!=2||amount==0||usdc.balanceOf(address(this))<credited+amount)revert Restricted();
        credited+=amount;emit Credited(id,amount);
    }
    function withdraw() external nonReentrant {
        uint256 amount=credited;if(amount==0)revert Restricted();
        credited=0;usdc.safeTransfer(beneficiary,amount);emit Withdrawn(amount,beneficiary);
    }
}
