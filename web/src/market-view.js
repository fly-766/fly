export function validCandles(rows) {
  if (!Array.isArray(rows)) return [];
  const byTime = new Map();
  for (const c of rows) {
    if (!c || ['time','open','high','low','close','volume'].some(k => typeof c[k] !== 'number' || !Number.isFinite(c[k]))) continue;
    if (c.time <= 0 || c.low <= 0 || c.volume < 0 || c.low > Math.min(c.open,c.close) || c.high < Math.max(c.open,c.close)) continue;
    byTime.set(c.time,c);
  }
  return [...byTime.values()].sort((a,b)=>a.time-b.time).slice(-120);
}

export function chartSvg(rows) {
  const candles=validCandles(rows).slice(-75);
  if(!candles.length)return '';
  const min=Math.min(...candles.map(c=>c.low)),max=Math.max(...candles.map(c=>c.high));
  const spread=Math.max(max-min,max*.0002), low=min-spread*.12, range=spread*1.24;
  const y=v=>125-(v-low)/range*114, step=348/candles.length;
  let body='<svg viewBox="0 0 354 151" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">';
  for(const yy of [15,50,85,120])body+=`<path d="M0 ${yy}H354" stroke="#d7dacb" stroke-dasharray="2 4"/>`;
  candles.forEach((c,i)=>{
    const x=(i+.5)*step, color=c.close>=c.open?'#526b3f':'#bf7650';
    body+=`<path d="M${x} ${y(c.high)}V${y(c.low)}" stroke="${color}"/><rect x="${x-step*.3}" y="${Math.min(y(c.open),y(c.close))}" width="${Math.max(1,step*.6)}" height="${Math.max(1,Math.abs(y(c.open)-y(c.close)))}" fill="${color}"/>`;
  });
  body+='<text x="0" y="147" font-family="monospace" font-size="8" fill="#66705d">1 MIN / BTC</text><text x="354" y="147" text-anchor="end" font-family="monospace" font-size="8" fill="#66705d">HYPERLIQUID</text></svg>';
  return body;
}

export function isFresh(snapshot, now=Date.now()/1000) {
  return Boolean(snapshot?.ok && !snapshot.stale && Number.isFinite(snapshot.providerTime) && now-snapshot.providerTime>=-5 && now-snapshot.providerTime<30);
}
