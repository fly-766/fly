// Decorative behavior only. This module has no market, broker or ledger access.
export const DURATIONS = {groom:7.4,inspect:5.8,flight:5.6,nap:8,wake:1.5,look:3,dodge:2.2,trade:3};
const clamp=x=>Math.max(0,Math.min(1,x));
export const smooth=x=>{x=clamp(x);return x*x*(3-2*x);};
const window=(p,a=.18,b=.80)=>smooth(p/a)*(1-smooth((p-b)/(1-b)));
export function isTapGesture({distance,duration,button=0}) {
  return button===0 && Number.isFinite(distance) && distance<=6 && distance>=0 && duration>=0 && duration<=650;
}

export function behaviorPose(kind, age=0, direction=1) {
  const p=clamp(age/(DURATIONS[kind]||1)), e=window(p);
  const pose={kind,p,weight:e,offset:[0,0,0],body:[0,0,0],head:[0,0,0],
    wingAmp:.07,wingSpeed:12,wingLift:.04,antenna:1,tuck:0,groom:0,wash:0,press:0,symbol:'',label:'Watching the tape'};
  if(kind==='groom'){
    pose.groom=e;pose.wash=smooth((p-.40)/.20);
    pose.head=[-.1*e,Math.sin(age*2.3)*.08*e,Math.sin(age*3)*.10*e];
    pose.offset[1]=.045*e;pose.wingAmp=.025;
    pose.label=p<.5?'Grooming':'Washing';
  }else if(kind==='inspect'){
    pose.offset=[.32*e,.045*e,-.10*e];pose.body=[-.11*e,0,-.035*e];
    pose.head=[-.13*e,Math.sin(age*2.1)*.26*e,Math.sin(age*1.9)*.29*e];
    pose.antenna=1.7;pose.symbol='?';pose.label=p<.2?'Looking up':'Leaning in';
  }else if(kind==='flight'){
    const lift=smooth(p/.24)*(1-smooth((p-.68)/.29));
    pose.offset=[Math.sin(p*Math.PI)*-.35,1.08*lift+Math.sin(age*8)*.055*lift,Math.sin(p*Math.PI*2)*.18*lift];
    pose.body=[-.14*lift,Math.sin(age*2)*.17*lift,Math.sin(age*3)*.07*lift];
    pose.tuck=lift;pose.wingAmp=.07+.78*lift;pose.wingSpeed=12+64*lift;pose.wingLift=.12*lift;
    pose.head=[.13*lift,0,0];pose.label=p<.24?'Takeoff':p<.70?'In flight':'Landing';
  }else if(kind==='nap'){
    // Nap deliberately ends asleep; wake supplies the next part of the sequence.
    const d=smooth(p/.18);
    pose.offset[1]=-.10*d+Math.sin(age*1.7)*.018*d;
    pose.body=[.08*d,0,.055*d];pose.head=[.36*d,0,Math.sin(age)*.055*d];
    pose.wingAmp=.005;pose.wingLift=-.055*d;pose.antenna=.15;pose.tuck=.08*d;
    pose.symbol='Z z';pose.weight=d;pose.label=p<.2?'Drowsy':'Napping';
  }else if(kind==='wake'){
    pose.offset[1]=Math.sin(Math.PI*p)*.22;
    pose.head=[-.32*e,Math.sin(age*14)*.20*e,Math.sin(age*17)*.12*e];
    pose.wingAmp=.07+.5*e;pose.wingSpeed=60;pose.antenna=2.6;
    pose.symbol='!';pose.label='Waking';
  }else if(kind==='look'){
    pose.body[1]=direction*.22*e;pose.head=[-.08*e,direction*.55*e,-direction*.16*e];
    pose.antenna=1.8;pose.symbol='?';pose.label='Who tapped?';
  }else if(kind==='dodge'){
    pose.offset=[direction*.43*e,Math.sin(Math.PI*p)*.24,.18*e];
    pose.body=[-.12*e,-direction*.21*e,-direction*.19*e];
    pose.head=[-.16*e,direction*.28*e,0];pose.wingAmp=.07+.40*e;pose.wingSpeed=53;pose.tuck=.5*e;
    pose.symbol='!';pose.label='Dodge';
  }else if(kind==='trade'){
    pose.press=e;pose.wingAmp=.25;pose.wingSpeed=40;pose.label='Pressing trade';
  }
  return pose;
}

export class FlyBehavior {
  constructor({random=Math.random}={}) {
    this.random=random;this.time=0;this.kind='idle';this.since=0;this.direction=1;
    this.nextAuto=2.5;this.lastFill=0;this.lastSleep=-Infinity;this.lastFillTick=null;
    this.bag=[];this.first=true;this.reactions=0;this.queued=null;
  }
  begin(kind,direction=1){this.kind=kind;this.since=this.time;this.direction=direction;if(kind==='nap')this.lastSleep=this.time;}
  play(kind){
    if(!Object.hasOwn(DURATIONS,kind)||kind==='trade')return false;
    if(this.kind==='trade'){this.queued=kind;return true;}
    this.begin(kind);return true;
  }
  interact(direction=1){
    if(this.kind==='trade')return false;
    if(this.kind==='nap'){this.begin('wake');return true;}
    const kind=this.reactions++%2===0?'look':'dodge';this.begin(kind,direction);return true;
  }
  fill(tick){
    if(tick===this.lastFillTick)return;
    this.lastFillTick=tick;this.lastFill=this.time;this.queued=null;this.begin('trade');
  }
  choose(){
    if(this.first){this.first=false;return 'groom';}
    if(this.time-this.lastFill>=90 && this.time-this.lastSleep>=65)return 'nap';
    if(!this.bag.length){
      this.bag=['groom','inspect','flight'];
      for(let i=this.bag.length-1;i>0;i--){const j=Math.floor(this.random()*(i+1));[this.bag[i],this.bag[j]]=[this.bag[j],this.bag[i]];}
    }
    return this.bag.pop();
  }
  advance(dt){
    if(!Number.isFinite(dt)||dt<=0)return this.sample();
    this.time+=dt;
    if(this.kind!=='idle' && this.time-this.since>=DURATIONS[this.kind]){
      if(this.kind==='nap')this.begin('wake');
      else if(this.queued){const q=this.queued;this.queued=null;this.begin(q);}
      else{this.begin('idle');this.nextAuto=this.time+5+this.random()*5;}
    }
    if(this.kind==='idle'&&this.time>=this.nextAuto)this.begin(this.choose());
    return this.sample();
  }
  sample(){return behaviorPose(this.kind,this.time-this.since,this.direction);}
}
