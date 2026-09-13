"""Bounded public event indexing and permissionless CCTP delivery planning."""
import json
from eth_utils import keccak
from eth_abi import decode,encode
from .codec import raw,address,object_hash
from .planner import action
from .cctp import CctpPending
class BridgeIndex:
    def __init__(self,journal):
        self.j=journal;self.db=journal.db
        self.db.executescript("""CREATE TABLE IF NOT EXISTS bridge_cursor(route TEXT PRIMARY KEY,next_block INTEGER NOT NULL);
          CREATE TABLE IF NOT EXISTS bridge_events(id TEXT PRIMARY KEY,route TEXT NOT NULL,tx TEXT NOT NULL,body TEXT NOT NULL,delivered INTEGER NOT NULL DEFAULT 0);""");self.db.commit()
    def scan(self,rpc,route):
        key=object_hash(route);r=self.db.execute("SELECT next_block FROM bridge_cursor WHERE route=?",(key,)).fetchone()
        start=r[0] if r else int(route["fromBlock"]);head=int(rpc.call("eth_blockNumber",[]),16)-int(route.get("confirmations",12))+1
        if start>head:return 0
        end=min(head,start+499);principal=route["kind"]==0
        topic="0x"+keccak(text="PrincipalBurned(uint64,uint256,uint256,uint256)" if principal else "ReturnBurned(bytes32,uint8,uint256,uint256)").hex()
        logs=rpc.call("eth_getLogs",[{"address":route["sourceSender"],"topics":[topic],"fromBlock":hex(start),"toBlock":hex(end)}])
        if len(logs)>2000:raise ValueError("Bridge log page too large")
        with self.db:
            for l in logs:
                if l.get("removed"):raise ValueError("Removed bridge event")
                if l["address"].lower()!=route["sourceSender"].lower() or l["topics"][0].lower()!=topic:raise ValueError("Bridge log identity mismatch")
                receipt=rpc.receipt(l["transactionHash"]);block=rpc.call("eth_getBlockByNumber",[l["blockNumber"],False])
                if not receipt or receipt["status"]!="0x1" or receipt["blockHash"].lower()!=block["hash"].lower():raise ValueError("Source bridge receipt not canonical")
                if principal:
                    amount,basis,max_fee=decode(["uint256"]*3,raw(l["data"]));sequence=int(l["topics"][1],16);evidence="0x"+"00"*32
                else:
                    k,amount,max_fee=decode(["uint8","uint256","uint256"],raw(l["data"]))
                    if k!=route["kind"]:raise ValueError("Return kind mismatch")
                    basis=0;sequence=None;evidence=l["topics"][1]
                body={"sourceTx":l["transactionHash"],"blockHash":l["blockHash"],"logIndex":l["logIndex"],"amount":amount,"basis":basis,"maxFee":max_fee,"sequence":sequence,"evidence":evidence}
                id=object_hash({"route":key,"tx":l["transactionHash"],"index":l["logIndex"]})
                self.db.execute("INSERT OR IGNORE INTO bridge_events(id,route,tx,body) VALUES (?,?,?,?)",(id,key,l["transactionHash"],json.dumps(body,sort_keys=True)))
            self.db.execute("INSERT OR REPLACE INTO bridge_cursor VALUES (?,?)",(key,end+1))
        return len(logs)
    def next(self,dest_snapshot,route,cctp):
        key=object_hash(route)
        for event in self.db.execute("SELECT * FROM bridge_events WHERE route=? AND delivered=0 ORDER BY rowid LIMIT 20",(key,)).fetchall():
            b=json.loads(event["body"]);expected={k:route[k] for k in ("sourceDomain","destinationDomain","burnToken","mintRecipient","messageSender","destinationCaller","kind")}
            expected.update(amount=b["amount"],basis=b["basis"],evidence=b["evidence"])
            if b["sequence"] is not None:expected["sequence"]=b["sequence"]
            try:row,t=cctp.matching(route["sourceDomain"],b["sourceTx"],expected)
            except CctpPending:continue
            id=keccak(encode(["uint32","bytes32"],[t["sourceDomain"],raw(t["nonce"],32)]))
            ing=route["destinationCaller"]
            consumed=dest_snapshot.get(ing,"consumed(bytes32)",["bool"],["bytes32"],[id])
            if consumed:
                net,kind,recipient,mhash=dest_snapshot.get(ing,"receipts(bytes32)",["uint256","uint8","address","bytes32"],["bytes32"],[id])
                if net!=t["amount"]-t["fee"] or kind!=t["kind"] or recipient.lower()!=t["mintRecipient"].lower() or mhash!=raw(t["messageHash"],32):raise ValueError("Destination CCTP receipt differs")
                with self.db:self.db.execute("UPDATE bridge_events SET delivered=1 WHERE id=?",(event["id"],))
                continue
            plan=action(route["destinationChainId"],ing,"receiveTransfer(bytes,bytes)",["bytes","bytes"],[raw(row["message"]),raw(row["attestation"])],"cctp_receive")
            plan["evidence"]={"source":b,"decoded":t,"attestationStatus":"complete","delivered":False};return plan
        return None
