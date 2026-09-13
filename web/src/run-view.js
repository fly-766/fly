const $=id=>document.getElementById(id);
export function observeRun(onDecision){
  let stopped=false,timer=null;
  async function poll(){
    if(stopped)return;
    try{
      const res=await fetch('/api/run',{cache:'no-store',signal:AbortSignal.timeout(7000)});
      if(!res.ok)throw new Error('Run unavailable');
      const s=await res.json();
      if(!s.ok){$('run-status').textContent='No run record';return;}
      const r=s.latest,b=r?.body,n=b?.neural,contract=s.mode==='contract-observer';
      $('shadow-ledger').hidden=contract;
      const fresh=s.state==='running'&&b&&Date.now()-b.wallTime<90000;
      $('run-status').textContent=fresh?'Model running':'Archived experiment';
      $('run-status').dataset.state=fresh?'live':'stale';
      $('run-count').textContent=String(s.rounds);
      for(const side of ['BUY','SELL','HOLD'])$('count-'+side.toLowerCase()).textContent=String(s.sides[side]||0);
      $('run-description').textContent=contract?'Settled account PnL feeds the full connectome; proposal, submit, and fill remain separate confirmations.':'The full connectome advances on closed candles. Each round stores input, state, raw proposal, and risk result. Fills below are simulated.';
      $('run-root').textContent=s.head;
      const account=b?.account;
      if(account){
        const format=v=>Number(v).toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2});
        $('shadow-equity').textContent=format(account.equity);
        $('shadow-net').textContent=format(Number(account.equity)-Number(account.principal));
        $('shadow-net').className=Number(account.equity)>=Number(account.principal)?'positive':'negative';
        $('shadow-fees').textContent=format(account.fees);
      }
      const replay=s.replay;
      $('replay-status').textContent=replay?.verified?'Full-brain replay checked through round '+replay.verifiedThrough:'Waiting for independent replay';
      $('run-proof').textContent=s.anchor?'On-chain through round '+s.anchor.lastRound+' · signed record, not a compute proof':'Records are not yet anchored on chain · not a compute proof';
      if(n){
        $('run-side').textContent=n.side;$('run-difference').textContent=n.difference_hz.toFixed(1)+' Hz';
        $('run-spikes').textContent=Number(n.total_spikes).toLocaleString('en-US');
        const reasons={calibration_not_accepted:'Calibration gate',no_long_position:'Flat; no sell required',existing_long_position:'Already long; observing',persistent_directional_bias:'One-sided streak; new entries paused',daily_order_limit:'Daily entry cap',stale_market:'Stale market; waiting'};
        $('run-result').textContent=b.execution.status==='VETO'?(reasons[b.execution.reason]||'Risk veto'):b.execution.status==='HOLD'?'Observing':b.execution.status==='PROPOSAL_ONLY'?'Proposal recorded, not executed':'Shadow fill';
        $('room-run-copy').textContent=fresh?'Round '+r.seq+' / '+n.side:'Experiment paused at round '+r.seq;
        $('room-run-note').textContent=contract?'Full brain · fills confirmed on contract and receipts':'Full brain · shadow execution · no live orders';
        $('run-input').src='/api/artifacts/'+b.input.name;$('run-input').hidden=false;
        $('run-time').textContent=new Date(b.wallTime).toLocaleString('en-GB',{hour12:false});
        onDecision?.(n.side,fresh);
      }
      const rr=await fetch('/api/records?limit=8',{cache:'no-store',signal:AbortSignal.timeout(7000)});
      if(rr.ok){
        const rows=await rr.json(),body=$('run-events');body.replaceChildren();
        for(const e of [...rows].reverse()){
          const tr=document.createElement('tr');
          for(const text of [e.seq,e.body.neural?.side||'—',({VETO:'Vetoed',HOLD:'Observe',SHADOW_FILLED:'Shadow fill',PROPOSAL_ONLY:'Proposal'}[e.body.execution?.status]||'—'),e.root.slice(0,12)+'…']){
            const td=document.createElement('td');td.textContent=String(text);tr.append(td);
          }
          body.append(tr);
        }
      }
    }catch{$('run-status').textContent='Records unavailable';}
    finally{if(!stopped)timer=setTimeout(poll,5000);}
  }
  poll();
  return ()=>{stopped=true;clearTimeout(timer);};
}
