// SPDX-License-Identifier: MIT
pragma solidity ^0.8.30;
import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {SafeERC20} from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import {ReentrancyGuard} from "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
interface IExitBindingsBsc {function exit() external view returns(address);function recoveryExit() external view returns(address);}
interface IReturnOutboxBsc {function release(uint256 amount,uint8 kind,bytes32 operation,uint64 sequence) external;}
/// @notice Only account-approved exits can release funds; owner relays profit, recovery goes to its fixed beneficiary.
contract ReturnOutboxBsc is ReentrancyGuard,IReturnOutboxBsc {
    using SafeERC20 for IERC20;
    IERC20 public immutable usdc;address public immutable account;address public immutable dev;address public immutable recoveryBeneficiary;
    mapping(bytes32=>bool) public released;
    event Released(bytes32 indexed id,uint8 indexed kind,address indexed recipient,uint256 amount,bytes32 operation);
    constructor(IERC20 u,address a,address d,address recovery){require(address(u).code.length>0&&a!=address(0)&&d!=address(0)&&recovery!=address(0));usdc=u;account=a;dev=d;recoveryBeneficiary=recovery;}
    function release(uint256 amount,uint8 kind,bytes32 operation,uint64 sequence) external nonReentrant {
        require(amount>0&&operation!=0&&(kind==1||kind==2),"INVALID_RELEASE");
        require(msg.sender==(kind==1?IExitBindingsBsc(account).exit():IExitBindingsBsc(account).recoveryExit()),"ONLY_FIXED_EXIT");
        bytes32 id=keccak256(abi.encode(block.chainid,address(this),msg.sender,kind,operation,sequence));require(!released[id],"ALREADY_RELEASED");released[id]=true;
        address recipient=kind==1?dev:recoveryBeneficiary;uint256 beforeBalance=usdc.balanceOf(recipient);
        usdc.safeTransferFrom(msg.sender,recipient,amount);require(usdc.balanceOf(recipient)-beforeBalance==amount,"TRANSFER_MISMATCH");
        emit Released(id,kind,recipient,amount,operation);
    }
}
