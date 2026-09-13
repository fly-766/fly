import test from 'node:test';
import assert from 'node:assert/strict';
import {validCandles,chartSvg,isFresh} from '../web/src/market-view.js';
const c={time:1000,open:100,high:102,low:99,close:101,volume:1};
test('malformed quote values never enter chart markup',()=>{
  assert.deepEqual(validCandles([{...c,open:null},{...c,high:Infinity},{...c,low:105},{...c,time:'<script>'}]),[]);
});
test('late snapshots remain sorted and replace a candle only by timestamp',()=>{
  const out=validCandles([{...c,time:2000},c,{...c,close:102}]);
  assert.deepEqual(out.map(x=>x.time),[1000,2000]);assert.equal(out[0].close,102);
});
test('empty or non-numeric data does not fabricate a price series',()=>{
  assert.equal(chartSvg([]),'');assert.equal(chartSvg([{...c,close:'101'}]),'');
});
test('flat valid prices generate finite geometry',()=>{
  const out=chartSvg([{...c,open:100,close:100,low:100,high:100}]);
  assert.ok(out.includes('<svg'));assert.ok(!/NaN|Infinity/.test(out));
});
test('stale, future and missing timestamps cannot show live',()=>{
  assert.equal(isFresh({ok:true,providerTime:99},100),true);
  for(const s of [{ok:true,providerTime:1},{ok:true,providerTime:110},{ok:true,providerTime:null},{ok:true,providerTime:99,stale:true}]) assert.equal(isFresh(s,100),false);
});
