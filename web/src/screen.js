export class MarketScreen {
  constructor() {
    this.canvas=document.createElement('canvas');
    this.canvas.width=768; this.canvas.height=524;
    this.ctx=this.canvas.getContext('2d');
    this.candles=[]; this.symbol='BTC / USDC'; this.mode='connecting'; this.side='OFFLINE';
    this.draw();
  }
  update(candles,symbol) { this.candles=candles; this.symbol=symbol; this.draw(); }
  status(mode) { this.mode=mode; this.draw(); }
  decision(side) { this.side=side; this.draw(); }
  draw() {
    const x=this.ctx, w=768,h=524;
    x.fillStyle='#06170d'; x.fillRect(0,0,w,h);
    x.fillStyle='#b9f681'; x.font='bold 27px monospace'; x.fillText('HYPERLIQUID / '+this.symbol,26,42);
    x.font='17px monospace'; x.fillStyle='#719b69'; x.fillText('1 MINUTE   ·   PERPETUAL',26,70);
    const rows=this.candles.slice(-46), latest=rows.at(-1);
    x.textAlign='right'; x.fillStyle=this.mode==='live'?'#b9f681':'#d6b969';
    x.fillText(({live:'LIVE',polling:'REST',connecting:'CONNECTING',stale:'STALE'})[this.mode]||'WAITING',742,40);
    x.textAlign='left';
    if (!latest) {
      x.fillStyle='#7d9d6e'; x.font='22px monospace'; x.fillText('CONNECTING TO HYPERLIQUID...',190,260);
    } else {
      x.fillStyle=latest.close>=latest.open?'#bbff80':'#f48778';
      x.font='bold 37px monospace'; x.fillText(latest.close.toLocaleString('en-US',{minimumFractionDigits:1,maximumFractionDigits:1}),26,121);
      x.font='16px monospace'; x.fillStyle='#719b69';
      x.fillText('O '+latest.open.toFixed(1)+'   H '+latest.high.toFixed(1)+'   L '+latest.low.toFixed(1),26,148);
      const top=178,bottom=387,left=28,right=649;
      const min=Math.min(...rows.map(c=>c.low)),max=Math.max(...rows.map(c=>c.high));
      const spread=Math.max(max-min,max*.0003),low=min-spread*.10,range=spread*1.2;
      const y=v=>bottom-(v-low)/range*(bottom-top);
      x.font='14px monospace';
      for(let i=0;i<=4;i++) {
        const py=top+i*(bottom-top)/4;
        x.strokeStyle='#173620'; x.beginPath();x.moveTo(left,py);x.lineTo(right,py);x.stroke();
        x.fillStyle='#6c905d';x.fillText((low+range*(1-i/4)).toFixed(0),665,py+5);
      }
      const step=(right-left)/46,offset=46-rows.length,maxVol=Math.max(1,...rows.map(c=>c.volume));
      rows.forEach((c,i)=>{
        const px=left+(i+offset+.5)*step,up=c.close>=c.open;
        x.fillStyle=up?'#b0ed75':'#e88472';x.strokeStyle=x.fillStyle;x.lineWidth=1.5;
        x.beginPath();x.moveTo(px,y(c.high));x.lineTo(px,y(c.low));x.stroke();
        x.fillRect(Math.round(px-step*.3),Math.round(Math.min(y(c.open),y(c.close))),Math.max(3,Math.floor(step*.6)),Math.max(2,Math.abs(y(c.open)-y(c.close))));
        x.globalAlpha=.35;const v=c.volume/maxVol*42;x.fillRect(px-step*.3,447-v,step*.6,v);x.globalAlpha=1;
      });
      x.setLineDash([4,5]);x.strokeStyle='#99cf67';x.beginPath();x.moveTo(left,y(latest.close));x.lineTo(right,y(latest.close));x.stroke();x.setLineDash([]);
      x.font='14px monospace';x.fillStyle='#719b69';
      x.fillText(new Date(rows[0].time).toLocaleTimeString('en-GB',{hour:'2-digit',minute:'2-digit'}),28,469);
      x.textAlign='right';x.fillText(new Date(latest.time).toLocaleTimeString('en-GB',{hour:'2-digit',minute:'2-digit'}),649,469);x.textAlign='left';
    }
    x.fillStyle='#173620';x.fillRect(0,488,w,2);
    x.fillStyle='#87b669';x.font='16px monospace';x.fillText('NEURAL '+this.side+' / SHADOW',26,514);
    x.textAlign='right';x.fillText('OHLC · HYPERLIQUID FEED',742,514);x.textAlign='left';
    // Fine phosphor scanlines live on the screen itself, not over the whole page.
    x.fillStyle='#00000016';for(let i=0;i<h;i+=4)x.fillRect(0,i,w,1);
    this.onChange?.();
  }
}
