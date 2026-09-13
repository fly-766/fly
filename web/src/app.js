import {observeFunds} from './treasury-view.js';
import {observeRun} from './run-view.js';
import {chartSvg, validCandles, isFresh} from './market-view.js';
const $=id=>document.getElementById(id);
const money=(n,d=1)=>typeof n==='number'&&Number.isFinite(n)?n.toLocaleString('en-US',{minimumFractionDigits:d,maximumFractionDigits:d}):'—';
const time=s=>new Date(s*1000).toLocaleTimeString('en-GB',{hour12:false});
let snapshot=null, stopped=false, timer=null, scene=null, screen=null, focused=false, request=null;
function refreshStatus(){
  const fresh=isFresh(snapshot);
  $('feed-state').textContent=fresh?'Feed live':snapshot?'Feed stale':'Waiting for feed';
  $('feed-state').dataset.state=fresh?'live':'stale';
  screen?.status(fresh?'live':'stale');
}
async function poll(){
  if(stopped)return;
  if(document.hidden){timer=setTimeout(poll,8000);return;}
  request=new AbortController();const timeout=setTimeout(()=>request?.abort(),14000);
  try{
    const res=await fetch('/api/market',{cache:'no-store',signal:request.signal});
    if(!res.ok)throw new Error('Market unavailable');
    const data=await res.json();
    if(!data.ok||!Number.isFinite(data.markPrice)||data.markPrice<=0)throw new Error('Invalid market response');
    snapshot=data;
    $('price').textContent=money(data.markPrice);
    const delta=(data.markPrice/data.previousDayPrice-1)*100;
    $('change').textContent=(delta>=0?'+':'')+money(delta,2)+'%  /  24H';
    $('change').className='price-change '+(delta>=0?'positive':'negative');
    $('book').textContent=money(data.bid)+' / '+money(data.ask);
    $('funding').textContent=money(data.funding*100,4)+'%';
    $('market-time').textContent=time(data.providerTime);
    $('global-time').textContent='HYPERLIQUID / '+time(data.providerTime);
    const candles=validCandles(data.candles), svg=chartSvg(candles);
    if(svg)$('chart').innerHTML=svg;
    screen?.update(candles,'BTC / USDC');
    $('market-error').hidden=!data.stale;
    $('market-error').textContent=data.stale?'Feed interrupted; last quote retained.':'';
  }catch{
    if(snapshot)snapshot={...snapshot,stale:true};
    $('market-error').hidden=false;
    $('market-error').textContent='Feed unavailable. Retrying; an old quote is not presented as live.';
  }finally{
    clearTimeout(timeout);request=null;refreshStatus();if(!stopped)timer=setTimeout(poll,8000);
  }
}

const experiments={
  baseline:['Resting baseline','Same neural state, neutral frame, measure the circuit’s own left–right bias. Not yet run; a historical 12 Hz median is not treated as calibration.'],
  mirror:['Mirrored input','From one checkpoint, original versus horizontal mirror, frozen learning. Separate picture bias from circuit bias before touching the encoder.'],
  replay:['Fixed-tape replay','Freeze the window and decoder on unseen candles. Compare original, candidate, and hold, with fees and funding included.']
};
document.querySelectorAll('[data-experiment]').forEach(button=>button.addEventListener('click',()=>{
  document.querySelectorAll('[data-experiment]').forEach(b=>b.setAttribute('aria-pressed',String(b===button)));
  const [name,copy]=experiments[button.dataset.experiment];$('experiment-name').textContent=name;$('experiment-description').textContent=copy;
}));

$('load-scene').addEventListener('click',async()=>{
  const button=$('load-scene');button.disabled=true;button.textContent='Opening…';
  try{
    const [{startScene},{MarketScreen}]=await Promise.all([import('./scene.js'),import('./screen.js')]);
    if(stopped)return;
    screen=new MarketScreen();if(snapshot)screen.update(validCandles(snapshot.candles),'BTC / USDC');
    $('scene').hidden=false;
    scene=await startScene($('scene'),screen,{onBehavior:label=>{$('scene-status').textContent=label+' · decorative';}});
    if(stopped){scene.dispose();return;}
    scene.setPaused(true);$('scene-image').hidden=true;button.hidden=true;
    $('motion').hidden=false;$('focus').hidden=false;
    $('motion').setAttribute('aria-pressed','true');
    $('scene-caption').textContent='3D decoration · screen is a live public feed';
    refreshStatus();
  }catch{
    scene?.dispose();scene=null;$('scene').hidden=true;$('scene-image').hidden=false;
    button.disabled=false;button.textContent='Retry 3D desk';
    $('scene-status').textContent='3D unavailable; pixel still holds';
  }
});
$('motion').addEventListener('click',()=>{
  if(!scene)return;const paused=!scene.isPaused();scene.setPaused(paused);
  $('motion').textContent=paused?'Resume motion':'Pause motion';$('motion').setAttribute('aria-pressed',String(paused));
});
$('focus').addEventListener('click',()=>{
  if(!scene)return;focused=scene.focusScreen(!focused);$('focus').textContent=focused?'Back to desk':'Lean in';$('focus').setAttribute('aria-pressed',String(focused));
});
$('scene').addEventListener('webglcontextlost',event=>{
  event.preventDefault();scene?.dispose();scene=null;$('scene').hidden=true;$('scene-image').hidden=false;
  $('motion').hidden=true;$('focus').hidden=true;$('scene-caption').textContent='Pixel scene · records below';
  $('scene-status').textContent='3D context lost; pixel still holds';
});
const stopFunds=observeFunds();
const stopRun=observeRun((side,fresh)=>{screen?.decision(fresh?side:'RECORDED');});
const freshnessTimer=setInterval(refreshStatus,1000);
poll();
window.addEventListener('pagehide',()=>{stopped=true;stopRun();stopFunds();clearTimeout(timer);clearInterval(freshnessTimer);request?.abort();scene?.dispose();});
window.addEventListener('pageshow',event=>{if(event.persisted)location.reload();});
