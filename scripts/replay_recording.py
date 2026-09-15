"""Recompute a supplied recording with its exact archived neural source."""
import argparse,hashlib,json,sys
from pathlib import Path

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--bundle',type=Path,required=True);parser.add_argument('--expected-root',required=True);parser.add_argument('--out',type=Path);a=parser.parse_args()
    root=a.bundle.resolve()
    m=json.loads((root/'manifest.json').read_text());rows=json.loads((root/'records.json').read_text())
    canonical_hash=lambda v:hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()).hexdigest()
    previous=canonical_hash(m)
    for seq,row in enumerate(rows,1):
        if row['seq']!=seq or row['previous']!=previous or canonical_hash({'previous':previous,'body':row['body']})!=row['root']:raise ValueError('History mismatch')
        previous=row['root']
    if previous.lower()!=a.expected_root.removeprefix('0x').lower():raise ValueError('Externally referenced root differs')
    for name,expected in (m['runtimeSource']|m['model']['source']).items():
        p=(root/'source'/name).resolve()
        if not p.is_relative_to((root/'source').resolve()) or hashlib.sha256(p.read_bytes()).hexdigest()!=expected:raise ValueError('Source mismatch')
    sys.path.insert(0,str(root/'source'))
    from flyterm.neural import FullBrain,read_frame,market_frame,output_fingerprint
    from flyterm.records import digest,file_digest,atomic,canonical
    from flyterm.telemetry import NeuralSampler
    import numpy as np
    def artifact(ref):
        p=(root/'artifacts'/ref['name']).resolve()
        if not p.is_relative_to(root/'artifacts') or file_digest(p)!=ref['sha256']:raise ValueError('Artifact mismatch')
        return p
    brain=FullBrain(learning=m['model']['learning'])
    if brain.identity()!=m['model']:raise ValueError('Model/environment identity differs from recorded run')
    brain.restore(artifact(m['genesis']));sampler=NeuralSampler(brain);previous=digest(m);anchor=0
    for seq,row in enumerate(rows,1):
        b=row['body']
        if row['seq']!=seq or b.get('sequence')!=seq or b['runId']!=m['runId'] or row['previous']!=previous or digest({'previous':previous,'body':b})!=row['root']:raise ValueError('History mismatch')
        frame=read_frame(artifact(b['input']))
        if not np.array_equal(frame,market_frame(b['market'],m.get('adapter','movement'))):raise ValueError('Sensory encoding differs')
        feedback=b.get('reinforcement','none')
        if m.get('mode')=='neural-observer' and feedback!='none':raise ValueError('Unexpected financial feedback')
        if m.get('mode')=='contract-observer':
            s=b['contractSnapshot'];value=s['tradingNetE6']-s['operatingCostE6'];delta=value-anchor
            expected='reward' if delta>=10000 else 'aversive' if delta<=-10000 else 'none'
            if delta!=b['reinforcementDeltaE6'] or expected!=feedback:raise ValueError('Feedback differs')
            anchor=value
        if brain.state_fingerprint()!=b['previousState']:raise ValueError('Previous state differs')
        with sampler.capture() as captured:out=brain.observe(frame,feedback)
        if output_fingerprint(out)!=b['neuralFingerprint'] or brain.state_fingerprint()!=b['nextState']:raise ValueError('Recomputed output/state differs')
        if b.get('telemetry'):
            with np.load(artifact(b['telemetry']),allow_pickle=False) as saved:
                for name in ('times','spikes','voltage','weights','groups','weightBefore'):
                    if not np.array_equal(saved[name],np.asarray(captured[name])):raise ValueError('Recomputed telemetry differs')
        previous=row['root']
    result={'verified':True,'runId':m['runId'],'throughRound':len(rows),'head':previous,'sameEnvironment':True,'telemetryRecomputed':True,'venueIndependentlyVerified':False,'computationProof':False}
    if a.out:atomic(a.out,canonical(result))
    print(json.dumps(result))

if __name__=='__main__':main()
