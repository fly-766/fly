import json,unittest
from eth_abi import encode
from flyterm.launch_status import live_status,load_instance,public_status
class LaunchStatusTests(unittest.TestCase):
    def test_instance_file_is_test_not_official(self):
        cfg=load_instance()
        self.assertFalse(cfg["officialProduct"])
        self.assertEqual(cfg["templateId"],0)
        self.assertEqual(cfg["dividendBps"],0)
        self.assertEqual(cfg["taxBuyBps"],100)
        self.assertEqual(cfg["token"].lower(),"0xbf273d796a2eb31ac20015dcdc861b23df30eeee")
        self.assertEqual(cfg["creator"].lower(),"0xd3050fbdd30ba35397e9b2fcf028978b85472b11")
    def test_live_checks_pass_on_matching_rpc(self):
        cfg=load_instance()
        types=["address","uint16","uint16","uint16","uint16","address","uint16","uint16","uint64","uint128","uint128","uint128","uint128","uint128","uint128","bytes32"]
        packed=encode(types,[cfg["creator"],100,100,100,100,cfg["quote"],0,0,1,1,1,1,1,1,1,b"\x00"*32])
        def fake_rpc(url,method,params,timeout=8):
            data=params[0]["data"]
            sel=data[:10]
            from eth_utils import keccak
            if sel=="0x"+keccak(text="tokens(address)")[:4].hex():
                return "0x"+packed.hex()
            if sel=="0x"+keccak(text="DIVIDEND_BPS()")[:4].hex():
                return "0x"+encode(["uint16"],[0]).hex()
            if sel=="0x"+keccak(text="CREATOR()")[:4].hex():
                return "0x"+encode(["address"],[cfg["creator"]]).hex()
            if sel=="0x"+keccak(text="TOKEN()")[:4].hex():
                return "0x"+encode(["address"],[cfg["token"]]).hex()
            if sel=="0x"+keccak(text="QUOTE()")[:4].hex():
                return "0x"+encode(["address"],[cfg["quote"]]).hex()
            if sel=="0x"+keccak(text="pairOf(address)")[:4].hex():
                return "0x"+encode(["address"],["0x0000000000000000000000000000000000000000"]).hex()
            if sel=="0x"+keccak(text="creatorAccrued(address,address)")[:4].hex():
                return "0x"+encode(["uint256"],[0]).hex()
            if sel=="0x"+keccak(text="balanceOf(address)")[:4].hex():
                return "0x"+encode(["uint256"],[123]).hex()
            if sel=="0x"+keccak(text="name()")[:4].hex():
                return "0x"+encode(["string"],["122"]).hex()
            if sel=="0x"+keccak(text="symbol()")[:4].hex():
                return "0x"+encode(["string"],["1221"]).hex()
            raise AssertionError(sel)
        import flyterm.launch_status as m
        old=m._rpc;m._rpc=fake_rpc
        try:
            out=live_status(instance=cfg)
        finally:
            m._rpc=old
        self.assertTrue(out["ok"])
        self.assertTrue(out["checks"]["holderDividendZero"])
        self.assertFalse(out["officialProduct"])
    def test_public_status_falls_back_without_rpc(self):
        import flyterm.launch_status as m
        old=m.live_status
        m.live_status=lambda **k: (_ for _ in ()).throw(RuntimeError("offline"))
        try:
            out=public_status()
        finally:
            m.live_status=old
        self.assertFalse(out["ok"]);self.assertFalse(out["live"]);self.assertEqual(out["token"].lower(),"0xbf273d796a2eb31ac20015dcdc861b23df30eeee")
if __name__=="__main__":unittest.main()
