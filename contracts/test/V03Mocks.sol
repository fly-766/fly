// SPDX-License-Identifier: MIT
pragma solidity ^0.8.30;
import {ERC20} from "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {ICoreRead03,ICoreWriter03,ICoreDeposit03,ICctpMessenger,ICctpTransmitter,IV3Pool,IIgnixManager,IV2Router,CoreEncoding} from "../src/v03/ProtocolTypes.sol";
interface ICallback {function uniswapV3SwapCallback(int256,int256,bytes calldata) external;}
contract Coin03 is ERC20 {
    uint8 private immutable d;
    constructor(string memory n,uint8 dec) ERC20(n,n){d=dec;}
    function decimals() public view override returns(uint8){return d;}
    function mint(address to,uint256 amount) external {_mint(to,amount);}
}
contract Pool03 is IV3Pool {
    address public immutable token0;address public immutable token1;uint24 public constant fee=100;uint256 public rateBps=9999;
    constructor(address a,address b){token0=a;token1=b;}
    function setRate(uint256 r) external {rateBps=r;}
    function swap(address to,bool z,int256 amount,uint160,bytes calldata) external returns(int256 d0,int256 d1){
        uint256 n=uint256(amount);uint256 out=n*rateBps/10000;Coin03(z?token1:token0).mint(to,out);
        d0=z?amount:-int256(out);d1=z?-int256(out):amount;ICallback(msg.sender).uniswapV3SwapCallback(d0,d1,"");
    }
}
contract Messenger03 is ICctpMessenger {
    uint32 public immutable sourceDomain;uint256 public nonce;uint256 public fee;bytes public last;
    constructor(uint32 d){sourceDomain=d;}
    function setFee(uint256 f) external {fee=f;}
    function depositForBurnWithHook(uint256 amount,uint32 domain,bytes32 recipient,address token,bytes32 caller,uint256 maxFee,uint32 finality,bytes calldata hook) external {
        require(fee<=maxFee);IERC20(token).transferFrom(msg.sender,address(this),amount);nonce++;
        last=abi.encodePacked(uint32(1),sourceDomain,domain,bytes32(nonce),bytes32(uint256(uint160(address(this)))),bytes32(uint256(99)),caller,finality,finality,
             uint32(1),bytes32(uint256(uint160(token))),recipient,amount,bytes32(uint256(uint160(msg.sender))),maxFee,fee,uint256(0),hook);
    }
}
contract Transmitter03 is ICctpTransmitter {
    Coin03 public immutable localToken;mapping(bytes32=>bool) public used;
    constructor(Coin03 token){localToken=token;}
    function receiveMessage(bytes calldata m,bytes calldata attestation) external returns(bool){
        require(keccak256(attestation)==keccak256(hex"ab"),"bad attestation");
        bytes32 id=keccak256(m[4:44]);require(!used[id],"nonce used");
        address caller=address(uint160(uint256(bytes32(m[108:140]))));require(caller==msg.sender,"caller");
        used[id]=true;address to=address(uint160(uint256(bytes32(m[184:216]))));
        uint256 gross=uint256(bytes32(m[216:248]));uint256 fee=uint256(bytes32(m[312:344]));
        localToken.mint(to,gross-fee);return true;
    }
}
contract Manager03 is IIgnixManager {
    mapping(address=>address) public vaults;mapping(address=>address) public pairs;mapping(address=>Curve) internal curves;
    function setVault(address token,address vault) external {vaults[token]=vault;}
    function setPair(address token,address pair_) external {pairs[token]=pair_;}
    function setup(address token,address quote) external {
        Curve storage c=curves[token];c.creator=msg.sender;c.quote=quote;
        uint256 unit=10**uint256(Coin03(quote).decimals());
        c.vQuote=uint128(3000*unit);c.vToken=1e27;c.sellable=8e26;c.reserve=2e26;c.taxBuyBps=100;c.buyFeeBps=100;
    }
    function vaultOf(address t) external view returns(address){return vaults[t];}
    function pairOf(address t) external view returns(address){return pairs[t];}
    function tokens(address t) external view returns(Curve memory){return curves[t];}
    function buy(address token,uint256 amount,uint256) external payable {
        Curve storage c=curves[token];IERC20(c.quote).transferFrom(msg.sender,address(this),amount);
        uint256 net=amount*9900/10000;uint256 raw=uint256(c.vToken)*net/(uint256(c.vQuote)+net);
        c.vQuote+=uint128(net);c.vToken-=uint128(raw);c.sold+=uint128(raw);c.collected+=uint128(net);
        Coin03(token).mint(msg.sender,raw*9900/10000);
    }
}
contract ClaimVault03 {
    Coin03 public immutable token;address public immutable recipient;uint256 public claimable;
    constructor(Coin03 t,address r){token=t;recipient=r;}
    function claimableNow(address who) external view returns(uint256){return who==recipient?claimable:0;}
    function shareBpsOf(address who) external view returns(uint16){return who==recipient?10000:0;}
    function accrue(uint256 n) external {claimable+=n;token.mint(address(this),n);}
    function claim() external {require(msg.sender==recipient);uint256 n=claimable;claimable=0;token.transfer(recipient,n);}
}
contract Router03 is IV2Router {
    function swapExactTokensForTokensSupportingFeeOnTransferTokens(uint256 amount,uint256,address[] calldata path,address to,uint256 deadline) external {
        require(deadline>=block.timestamp);IERC20(path[0]).transferFrom(msg.sender,address(this),amount);
        Coin03(path[1]).mint(to,amount);
    }
}
contract HopRouter03 {
    Coin03 public immutable quote;Coin03 public immutable usd0;
    constructor(Coin03 q,Coin03 u){quote=q;usd0=u;}
    function hopQuoteToUsd0(uint256 minOut) external {
        uint256 amount=quote.allowance(msg.sender,address(this));require(amount>0);
        quote.transferFrom(msg.sender,address(this),amount);
        uint256 out=amount/1e12;require(out>=minOut);usd0.mint(msg.sender,out);
    }
    function hopUsd0ToQuote(uint256 minOut) external {
        uint256 amount=usd0.allowance(msg.sender,address(this));require(amount>0);
        usd0.transferFrom(msg.sender,address(this),amount);
        uint256 out=amount*1e12;require(out>=minOut);quote.mint(msg.sender,out);
    }
}
contract Core03 is ICoreRead03,ICoreWriter03,ICoreDeposit03 {
    struct Account {int64 quantity;uint64 entry;int64 cash;uint64 spotUsdc;bool exists;}
    mapping(address=>Account) public accounts;Coin03 public immutable token;
    uint64 public blockNo=10;uint64 public price=100e8;uint64 public depositFee=0;uint64 public transferFee=0;
    address public lastSender;bytes public lastAction;address public depositTo;uint256 public depositAmount;uint32 public depositDex;
    constructor(Coin03 t){token=t;}
    function state(address u,uint16) external view returns(State memory){
        Account memory a=accounts[u];int256 equity=int256(a.cash)+int256(uint256(uint64(a.quantity))*1000*price/1e10)-int256(uint256(a.entry));
        return State(a.quantity,a.entry,price,int64(equity),a.cash,blockNo,5,a.exists,false);
    }
    function spot(address u,uint64) external view virtual returns(uint64,uint64){return(accounts[u].spotUsdc,0);}
    function retainRoundedEntry(address u,uint64 rounding) external {accounts[u].entry+=rounding;accounts[u].cash+=int64(rounding);}
    function setPrice(uint64 p) external {price=p;blockNo++;}
    function tick(uint64 count) external {blockNo+=count;}
    function setFees(uint64 a,uint64 b) external {depositFee=a;transferFee=b;}
    function giveSpot(address a,uint64 n) external {accounts[a].spotUsdc+=n;accounts[a].exists=true;token.mint(address(this),n/100);blockNo++;}
    function depositFor(address to,uint256 amount,uint32 dex) external {token.transferFrom(msg.sender,address(this),amount);depositTo=to;depositAmount=amount;depositDex=dex;}
    function processDeposit() external {
        require(depositDex==type(uint32).max);accounts[depositTo].spotUsdc+=uint64((depositAmount-depositFee)*100);accounts[depositTo].exists=true;
        depositAmount=0;blockNo++;
    }
    function sendRawAction(bytes calldata raw) external {lastAction=raw;lastSender=msg.sender;}
    function _payload() internal view returns(bytes memory p){p=new bytes(lastAction.length-4);for(uint256 i;i<p.length;i++)p[i]=lastAction[i+4];}
    function initialize(address user) external {accounts[user].exists=true;}
    function processSetup() external {blockNo++;}
    function processClass() external {
        require(bytes4(lastAction)==hex"01000007");(uint64 n,bool toPerp)=abi.decode(_payload(),(uint64,bool));require(toPerp);
        Account storage a=accounts[lastSender];require(a.spotUsdc>=uint256(n)*100);a.spotUsdc-=n*100;a.cash+=int64(n);blockNo++;
    }
    function processOrder(uint64 filled,uint64 average,uint64 fee) external returns(int256 pnl){
        require(bytes4(lastAction)==hex"01000001");
        (,bool buy,,uint64 requested,bool reduce,uint8 tif,)=abi.decode(_payload(),(uint32,bool,uint64,uint64,bool,uint8,uint128));
        require(tif==3&&filled<=requested&&filled%1000==0);
        Account storage a=accounts[lastSender];uint256 notional=uint256(filled)*average/1e10;
        if(filled>0){
            if(buy){require(!reduce);a.quantity+=int64(filled/1000);a.entry+=uint64(notional);}
            else{require(reduce&&uint256(uint64(a.quantity))*1000>=filled);uint256 basis=uint256(a.entry)*filled/(uint256(uint64(a.quantity))*1000);pnl=int256(notional)-int256(basis);a.cash+=int64(pnl);a.entry-=uint64(basis);a.quantity-=int64(filled/1000);if(pnl>0)token.mint(address(this),uint256(pnl));}
        }
        a.cash-=int64(fee);blockNo++;
    }
    function processTransfer() public virtual {
        require(bytes4(lastAction)==hex"0100000d");(address to,,uint32 src,uint32 dest,uint64 index,uint64 n)=abi.decode(_payload(),(address,address,uint32,uint32,uint64,uint64));require(index==0&&dest==type(uint32).max);
        Account storage a=accounts[lastSender];
        if(src==0){require(a.cash>=int64(n/100));a.cash-=int64(n/100);}
        else{require(a.spotUsdc>=n);a.spotUsdc-=n;}
        if(to==CoreEncoding.USDC_SYSTEM){token.transfer(lastSender,n/100);}
        else{accounts[to].spotUsdc+=n-transferFee*100;accounts[to].exists=true;}
        blockNo++;
    }
}
