// SPDX-License-Identifier: MIT
pragma solidity ^0.8.30;
import {Coin03} from "./V03Mocks.sol";
import {ICoreRead03,ICoreWriter03,ICoreDeposit03,CoreEncoding} from "../src/v03/ProtocolTypes.sol";
import {PositionMathV05} from "../src/v05/PositionMathV05.sol";
contract Core05 is ICoreRead03,ICoreWriter03,ICoreDeposit03 {
    struct Account {int64 quantity;uint64 entry;int64 cash;uint64 spotUsdc;bool exists;}
    mapping(address=>Account) public accounts;Coin03 public immutable token;
    uint64 public blockNo=10;uint64 public price=100e8;uint64 public depositFee=0;uint64 public transferFee=0;
    address public lastSender;bytes public lastAction;address public depositTo;uint256 public depositAmount;uint32 public depositDex;
    constructor(Coin03 t){token=t;}
    function state(address u,uint16) external view returns(State memory){
        Account memory a=accounts[u];uint256 absq=uint256(a.quantity<0?-int256(a.quantity):int256(a.quantity));int256 unrealized=int256(absq*1000*price/1e10)-int256(uint256(a.entry));if(a.quantity<0)unrealized=-unrealized;int256 equity=int256(a.cash)+unrealized;
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
    uint32 public currentLeverage=20;
    function setLeverage(uint32 n) external {currentLeverage=n;}
    function leverage(address user,uint16) external view returns(uint32,uint8,uint64){Account memory a=accounts[user];uint256 n=uint256(a.quantity<0?-int256(a.quantity):int256(a.quantity))*1000*price/1e10;return(currentLeverage,40,uint64(n));}
    function quoteOrder(address user,bool buy,uint64 capE6,uint8 leverageCap,uint16 reserveBps,uint16 slipBps) external view returns(uint64,uint64){
        State memory s=this.state(user,0);if(s.quantity==0)require(currentLeverage==leverageCap);
        return PositionMathV05.quote(s,buy,capE6,leverageCap,reserveBps,slipBps);
    }
    function forcePosition(address user,int64 q,uint64 entry,int64 cash) external {accounts[user].quantity=q;accounts[user].entry=entry;accounts[user].cash=cash;blockNo++;}
    function processOrder(uint64 filled,uint64 average,uint64 fee) external returns(int256 pnl){
        require(bytes4(lastAction)==hex"01000001");
        (,bool buy,,uint64 requested,bool reduce,uint8 tif,)=abi.decode(_payload(),(uint32,bool,uint64,uint64,bool,uint8,uint128));
        require(tif==3&&filled<=requested&&filled%1000==0);
        Account storage a=accounts[lastSender];uint256 notional=uint256(filled)*average/1e10;
        if(filled>0){
            if(!reduce){require(a.quantity==0);a.quantity=buy?int64(filled/1000):-int64(filled/1000);a.entry=uint64(notional);}
            else{
                bool short_=a.quantity<0;uint256 oldSize=uint256(short_?-int256(a.quantity):int256(a.quantity))*1000;
                require(a.quantity!=0&&buy==short_&&filled<=oldSize);
                uint256 basis=uint256(a.entry)*filled/oldSize;pnl=short_?int256(basis)-int256(notional):int256(notional)-int256(basis);
                a.cash+=int64(pnl);a.entry-=uint64(basis);a.quantity+=buy?int64(filled/1000):-int64(filled/1000);
                if(pnl>0)token.mint(address(this),uint256(pnl));
            }
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
