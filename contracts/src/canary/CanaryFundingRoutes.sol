// SPDX-License-Identifier: MIT
pragma solidity ^0.8.30;
import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {SafeERC20} from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import {ReentrancyGuard} from "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import {IPrincipalReceiver,IReturnReceiver,ICctpMessenger} from "../v03/ProtocolTypes.sol";
/// @notice Hyper-only funded canary. No tax collection, cross-chain messaging or token burn.
/// Implements the exit adapter interface solely to preserve the production TradingAccount.
contract CanaryFundingRoutes is ReentrancyGuard,ICctpMessenger {
    using SafeERC20 for IERC20;
    IERC20 public immutable usdc; address public immutable funder;
    address public immutable account; address public immutable profitExit; address public immutable recoveryExit;
    address public immutable recoveryVault; address public immutable profitBeneficiary;
    uint256 public immutable cap; uint256 public funded; uint64 public fundingSequence;
    mapping(bytes32=>bool) public returned;
    error Restricted();
    event CanaryPrincipalFunded(bytes32 indexed source,uint256 amount);
    event CanaryLocalReturn(bytes32 indexed source,uint8 kind,uint256 amount,address indexed recipient);
    constructor(IERC20 u,address f,address a,address p,address r,address vault,address beneficiary,uint256 limit) {
        if(address(u).code.length==0||f==address(0)||a==address(0)||p==address(0)||r==address(0)||p==r||vault==address(0)||beneficiary==address(0)||limit==0||limit>50e6)revert Restricted();
        usdc=u;funder=f;account=a;profitExit=p;recoveryExit=r;recoveryVault=vault;profitBeneficiary=beneficiary;cap=limit;
    }
    function fundPrincipal(uint256 amount) external nonReentrant {
        if(msg.sender!=funder||amount==0||amount>cap-funded)revert Restricted();
        funded+=amount;fundingSequence++;
        bytes32 source=keccak256(abi.encode(block.chainid,address(this),fundingSequence,amount));
        uint256 beforeBalance=usdc.balanceOf(account);
        usdc.safeTransferFrom(funder,account,amount);
        if(usdc.balanceOf(account)!=beforeBalance+amount)revert Restricted();
        IPrincipalReceiver(account).creditPrincipal(amount,amount,source);
        emit CanaryPrincipalFunded(source,amount);
    }
    function depositForBurnWithHook(uint256 amount,uint32 domain,bytes32 recipient,address token,bytes32 caller,uint256 maxFee,uint32 finality,bytes calldata hook) external nonReentrant {
        if(amount==0||domain!=19||token!=address(usdc)||caller!=bytes32(uint256(uint160(address(this))))||maxFee!=0||finality!=2000||hook.length!=160)revert Restricted();
        (bytes4 magic,uint8 kind,uint256 basis,uint64 sequence,bytes32 evidence)=abi.decode(hook,(bytes4,uint8,uint256,uint64,bytes32));
        if(magic!=0x46543033||basis!=0||sequence==0||evidence==0||(kind!=1&&kind!=2))revert Restricted();
        address expectedExit=kind==1?profitExit:recoveryExit;
        address destination=kind==1?profitBeneficiary:recoveryVault;
        if(msg.sender!=expectedExit||recipient!=bytes32(uint256(uint160(destination))))revert Restricted();
        bytes32 source=keccak256(abi.encode(msg.sender,sequence,evidence));
        if(returned[source])revert Restricted();returned[source]=true;
        uint256 beforeBalance=usdc.balanceOf(destination);
        usdc.safeTransferFrom(msg.sender,destination,amount);
        if(usdc.balanceOf(destination)!=beforeBalance+amount)revert Restricted();
        if(kind==2)IReturnReceiver(recoveryVault).creditReturn(amount,2,source);
        emit CanaryLocalReturn(source,kind,amount,destination);
    }
}
