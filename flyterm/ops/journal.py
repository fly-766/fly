"""Versioned, private transaction intent and replacement ledger."""
import json,sqlite3,time,os
from pathlib import Path
from .codec import object_hash
class OperationJournal:
    def __init__(self,path):
        p=Path(path);p.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        self.db=sqlite3.connect(p);self.db.row_factory=sqlite3.Row
        os.chmod(p,0o600)
        self.db.execute("PRAGMA journal_mode=WAL");self.db.execute("PRAGMA synchronous=FULL")
        self.db.executescript("""
          CREATE TABLE IF NOT EXISTS ops(id TEXT PRIMARY KEY,chain INTEGER NOT NULL,signer TEXT NOT NULL,config TEXT NOT NULL,
            kind TEXT NOT NULL,state TEXT NOT NULL,intent TEXT NOT NULL,nonce INTEGER,receipt TEXT,created INTEGER NOT NULL);
          CREATE UNIQUE INDEX IF NOT EXISTS nonce_owner ON ops(chain,signer,nonce) WHERE nonce IS NOT NULL;
          CREATE TABLE IF NOT EXISTS attempts(hash TEXT PRIMARY KEY,op TEXT NOT NULL,raw TEXT NOT NULL,gas INTEGER NOT NULL,price INTEGER NOT NULL,created INTEGER NOT NULL);
          CREATE TABLE IF NOT EXISTS evidence(id TEXT PRIMARY KEY,body TEXT NOT NULL);
        """);self.db.commit()
    def close(self):self.db.close()
    def plan(self,chain,signer,config_hash,kind,intent):
        signer=signer.lower();id=object_hash({"chain":int(chain),"signer":signer,"config":config_hash,"kind":kind,"intent":intent})
        if "creatorClaimTx" in intent:
            for existing in self.db.execute("SELECT id,intent FROM ops WHERE chain=? AND signer=?",(int(chain),signer)):
                if json.loads(existing["intent"]).get("creatorClaimTx")==intent["creatorClaimTx"] and existing["id"]!=id:raise ValueError("Creator claim already assigned to an operation")
        with self.db:self.db.execute("INSERT OR IGNORE INTO ops VALUES (?,?,?,?,?,?,?,NULL,NULL,?)",(id,int(chain),signer,config_hash,kind,"PLANNED",json.dumps(intent,sort_keys=True),int(time.time())))
        return self.get(id)
    def get(self,id):
        r=self.db.execute("SELECT * FROM ops WHERE id=?",(id,)).fetchone()
        return dict(r) if r else None
    def attempts(self,id):return [dict(r) for r in self.db.execute("SELECT * FROM attempts WHERE op=? ORDER BY created,rowid",(id,))]
    def pending(self,chain,signer):
        return [dict(r) for r in self.db.execute("SELECT * FROM ops WHERE chain=? AND signer=? AND state IN ('SIGNED','SUBMITTED','UNKNOWN','MINED')",(chain,signer.lower()))]
    def signed(self,id,nonce,raw,txhash,gas,price):
        with self.db:
            row=self.get(id)
            if row["state"]=="PLANNED":
                if self.pending(row["chain"],row["signer"]):raise ValueError("Previous transaction is unresolved")
            elif row["state"] not in ("SIGNED","SUBMITTED","UNKNOWN") or row["nonce"]!=nonce:raise ValueError("Cannot replace this intent")
            self.db.execute("UPDATE ops SET state='SIGNED',nonce=? WHERE id=?",(nonce,id))
            self.db.execute("INSERT INTO attempts VALUES (?,?,?,?,?,?)",(txhash,id,raw,int(gas),int(price),int(time.time())))
    def state(self,id,state):
        if state not in ("SUBMITTED","UNKNOWN","MINED","CONFIRMED","REVERTED"):raise ValueError("Invalid operational state")
        with self.db:
            if state=="UNKNOWN":self.db.execute("UPDATE ops SET state=?,receipt=NULL WHERE id=?",(state,id))
            else:self.db.execute("UPDATE ops SET state=? WHERE id=?",(state,id))
    def mined(self,id,receipt,confirmed):
        hashes={x["hash"].lower() for x in self.attempts(id)}
        if receipt["transactionHash"].lower() not in hashes:raise ValueError("Receipt hash mismatch")
        receipt=dict(receipt)
        previous=self.get(id).get("receipt")
        old=json.loads(previous) if previous else {}
        receipt["observedAt"]=old.get("observedAt",int(time.time())) if old.get("blockHash")==receipt["blockHash"] else int(time.time())
        state=("CONFIRMED" if int(receipt["status"],16)==1 else "REVERTED") if confirmed else "MINED"
        with self.db:self.db.execute("UPDATE ops SET state=?,receipt=? WHERE id=?",(state,json.dumps(receipt,sort_keys=True),id))
    def daily_gas(self,chain,signer,day=None,exclude=None):
        day=int(time.time())//86400 if day is None else int(day);total=0
        rows=self.db.execute("SELECT * FROM ops WHERE chain=? AND signer=?",(chain,signer.lower())).fetchall()
        for row in rows:
            if row["id"]==exclude:continue
            attempts=self.attempts(row["id"])
            if not attempts:continue
            if row["receipt"]:
                receipt=json.loads(row["receipt"])
                if int(receipt.get("observedAt",row["created"]))//86400!=day:continue
                matched=next(x for x in attempts if x["hash"].lower()==receipt["transactionHash"].lower())
                total+=int(receipt["gasUsed"],16)*int(receipt.get("effectiveGasPrice",hex(matched["price"])),16)
            else:total+=max(x["gas"]*x["price"] for x in attempts)
            if not row["receipt"] or int(json.loads(row["receipt"])["status"],16)==1:total+=int(json.loads(row["intent"]).get("value","0"))
        return total
    def save_evidence(self,value):
        id=object_hash(value)
        with self.db:self.db.execute("INSERT OR IGNORE INTO evidence VALUES (?,?)",(id,json.dumps(value,sort_keys=True)))
        return id
