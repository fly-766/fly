"""Retrieve and validate CCTP evidence; completion means destination receipt, not attestation."""
import json,urllib.request
from .codec import decode_cctp,address
class CctpPending(RuntimeError):pass
class Cctp:
    def __init__(self,base="https://iris-api.circle.com",transport=None):self.base=base;self.transport=transport
    def messages(self,source_domain,tx_hash):
        url=self.base+"/v2/messages/"+str(int(source_domain))+"?transactionHash="+tx_hash
        if self.transport:return self.transport(url)
        try:
            with urllib.request.urlopen(url,timeout=20) as r:return json.loads(r.read(2_000_000))
        except Exception:raise CctpPending("CCTP attestation unavailable") from None
    def matching(self,source_domain,tx_hash,expected):
        result=self.messages(source_domain,tx_hash)
        found=[]
        for row in result.get("messages",[]):
            if row.get("status")!="complete" or not row.get("attestation","").startswith("0x"):continue
            decoded=decode_cctp(row["message"])
            good=True
            for key,value in expected.items():
                actual=decoded.get(key)
                if isinstance(value,str) and value.startswith("0x"):good &= isinstance(actual,str) and actual.lower()==value.lower()
                else:good &= actual==value
            if good:found.append((row,decoded))
        if len(found)!=1:raise CctpPending("No unique matching completed CCTP message")
        return found[0]
