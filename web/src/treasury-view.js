export function renderFunds(s,root=document){
  const $=id=>root.getElementById(id);
  const fresh=s?.ok&&Date.now()-s.at<90000;
  $('funds-status').textContent=!s?.ok?'Not deployed · no mainnet funds in this viewer':fresh?'On-chain snapshot checked':'Last on-chain snapshot retained · stale';
  const money=v=>v==null?'—':(Number(v)/1e6).toLocaleString('en-US',{maximumFractionDigits:2});
  const f=s?.funds||{};
  if(/^0x[0-9a-fA-F]{40}$/.test(s?.projectToken||'')){
    $('token-address').hidden=false;$('token-address').textContent='CA / '+s.projectToken;
    $('launch-link').href='https://ignix.bot/launch?token='+s.projectToken;
    $('launch-link').textContent='View token on IGNIX ↗';
  }
  if(s?.ok){
    $('execution-status').textContent=s.liveEnabled?'Live execution configured':'Live execution disabled';
    $('execution-description').textContent=fresh?'Funds from a configured contract snapshot; fills are confirmed per receipt.':'On-chain snapshot is stale; waiting for an operator update.';
  }
  for(const [id,key] of [['principal-value','costBasisE6'],['profit-value','availableProfitE6'],['return-value','nativeBudget']])$(id).textContent=money(f[key]);
  $('burn-value').textContent=f.totalTokensSentDead==null?'—':(Number(f.totalTokensSentDead)/1e18).toLocaleString('en-US',{maximumFractionDigits:2});
  $('escrow-note').textContent=f.escrowedTokens==null?'Pre-graduation buybacks remain in a fixed contract; they move to the dead address only after graduation.':'Pending dead-address inventory: '+(Number(f.escrowedTokens)/1e18).toLocaleString('en-US',{maximumFractionDigits:2})+' tokens.';
}
function renderLaunch(s){
  const summary=document.getElementById('verify-summary');
  const token=document.getElementById('verify-token');
  const list=document.getElementById('verify-checks');
  if(!summary||!list)return;
  list.replaceChildren();
  if(!s){summary.textContent='Instance API unavailable.';return;}
  if(!s.published){summary.textContent='The official instance is not published in this source tree.';if(token)token.textContent='';return;}
  summary.textContent=s.officialProduct?'Published official instance.':(s.live?(s.ok?'On-chain fields match the pin.':'On-chain fields do not match the pin.'):'Live RPC failed.');
  if(token)token.textContent=s.token?('CA / '+s.token):'';
  const items=[
    ['Holder dividend is 0',s.checks?.holderDividendZero],
    ['Buy/sell tax 1% each',s.checks?.taxBuy1pct&&s.checks?.taxSell1pct],
    ['Quote is wGOOGLx',s.checks?.quoteIsWgooglx],
    ['Creator matches the pinned address',s.checks?.creatorMatch],
    ['Not graduated',s.checks?.notGraduated],
  ];
  for(const [label,ok] of items){
    const li=document.createElement('li');
    li.textContent=(ok?'Match · ':'Review · ')+label;
    list.append(li);
  }
}
export function observeFunds(){
  let stop=false,timer;
  async function poll(){
    try{const r=await fetch('/api/operations',{cache:'no-store',signal:AbortSignal.timeout(7000)});renderFunds(await r.json());}
    catch{renderFunds(null);}
    try{const r=await fetch('/api/launch',{cache:'no-store',signal:AbortSignal.timeout(7000)});renderLaunch(await r.json());}
    catch{renderLaunch(null);}
    if(!stop)timer=setTimeout(poll,10000);
  }
  poll();return ()=>{stop=true;clearTimeout(timer);};
}
