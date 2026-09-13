import json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from flyterm.live import LiveBrain,replay
root=Path(__file__).resolve().parents[1]
out=root/("runs/"+(sys.argv[1] if len(sys.argv)>1 else "v03-contract-observer-final"))
markets=json.loads((root/"runs/v03-archived-markets.json").read_text())
state={"pending":0,"nativePrincipalE6":0,"unallocatedSpotE6":0,"tradingNetE6":0,"operatingCostE6":0,"evidenceKind":"local contract snapshot fixture, not mainnet"}
brain=LiveBrain(out)
assert not brain.rows,"Use a new directory; never overwrite accepted observations"
brain.observe(state,markets[0]);run=brain.manifest["runId"];brain.close()
brain=LiveBrain(out);assert brain.manifest["runId"]==run
brain.observe(state|{"tradingNetE6":-20000},markets[1]);brain.close()
result=replay(out);assert result["rounds"]==2
print(json.dumps(result))
