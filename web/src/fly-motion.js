import * as THREE from 'three';
import {FlyBehavior} from './behavior.js';

function bindLeg(group) {
  if(!group)return null;
  const femur=group.children.find(o=>o.name.startsWith('Femur'));
  const tibia=group.children.find(o=>o.name.startsWith('Tibia'));
  const foot=group.children.find(o=>o.name.startsWith('Foot'));
  if(!femur||!tibia||!foot)return null;
  const length=o=>{o.geometry.computeBoundingBox();return o.geometry.boundingBox.max.y-o.geometry.boundingBox.min.y;};
  const elbow=femur.position.clone().multiplyScalar(2),end=tibia.position.clone().multiplyScalar(2).sub(elbow);
  const limbMaterial=new THREE.MeshStandardMaterial({color:'#556d69',roughness:.92});
  femur.material=limbMaterial;tibia.material=limbMaterial;foot.material=limbMaterial;
  const hand=new THREE.Mesh(new THREE.IcosahedronGeometry(.055,0),limbMaterial);hand.name='GroomingTip';group.add(hand);
  return {group,femur,tibia,foot,hand,limbMaterial,lengths:[length(femur),length(tibia),length(foot)],
    restEnd:end.clone().add(group.position),target:end.clone().add(group.position),pole:elbow};
}
const axis=new THREE.Vector3(0,1,0);
function segment(mesh,from,to,length){
  const delta=new THREE.Vector3().subVectors(to,from),size=delta.length();
  mesh.position.copy(from).add(to).multiplyScalar(.5);
  mesh.quaternion.setFromUnitVectors(axis,delta.normalize());mesh.scale.y=size/length;
}
function solveLeg(leg,target,tuck,side){
  const end=target.clone().sub(leg.group.position),[a,b,c]=leg.lengths;
  const distance=THREE.MathUtils.clamp(end.length(),Math.abs(a-b)+.012,a+b-.002);
  const dir=end.normalize();end.copy(dir).multiplyScalar(distance);
  const pole=leg.pole.clone().lerp(new THREE.Vector3(side*.6,.7,.1),tuck);
  pole.addScaledVector(dir,-pole.dot(dir));
  if(pole.lengthSq()<.0001)pole.set(0,0,1).addScaledVector(dir,-dir.z);
  pole.normalize();
  const along=(a*a-b*b+distance*distance)/(2*distance),height=Math.sqrt(Math.max(0,a*a-along*along));
  const elbow=dir.clone().multiplyScalar(along).addScaledVector(pole,height);
  segment(leg.femur,new THREE.Vector3(),elbow,a);segment(leg.tibia,elbow,end,b);
  const toe=end.clone().add(new THREE.Vector3(0,-.012,-c));segment(leg.foot,end,toe,c);
  leg.hand.position.copy(end);leg.hand.visible=tuck>.15;
}

export function createFlyMotion(model,world,{onBehavior=()=>{}}={}) {
  const find=name=>model.getObjectByName(name),fly=find('FlyRoot'),head=find('HeadPivot');
  if(!fly||!head)throw new Error('Fly animation pivots missing');
  const wings=[find('WingL'),find('WingR')],antenna=[find('AntennaL'),find('AntennaR')];
  const forelegs=[bindLeg(find('ForelegL')),bindLeg(find('ForelegR'))];
  const hindlegs=['Leg1L','Leg1R','Leg2L','Leg2R'].map(find);
  const objects=[fly,head,...wings,...antenna,...hindlegs].filter(Boolean);
  const rest=new Map(objects.map(o=>[o,{position:o.position.clone(),quaternion:o.quaternion.clone(),rotation:o.rotation.clone()}]));
  const keyRest=new Map(['BuyKey','SellKey'].map(name=>{const key=find(name);return [name,{key,y:key?.position.y}];}));
  const director=new FlyBehavior();let side='HOLD',lastLabel='',symbolValue='';
  const glyph=document.createElement('canvas');glyph.width=128;glyph.height=80;
  const ctx=glyph.getContext('2d'),texture=new THREE.CanvasTexture(glyph);
  texture.magFilter=THREE.NearestFilter;texture.minFilter=THREE.NearestFilter;
  const symbol=new THREE.Sprite(new THREE.SpriteMaterial({map:texture,transparent:true,depthTest:false,toneMapped:false}));
  symbol.scale.set(.75,.46,1);symbol.renderOrder=10;world.add(symbol);
  const targetPos=new THREE.Vector3(),rotation=new THREE.Euler(),quat=new THREE.Quaternion();
  let disposed=false,age=0;

  function apply(dt,pose) {
    age+=dt;const t=age,blend=1-Math.exp(-dt*11);
    targetPos.copy(rest.get(fly).position).add(new THREE.Vector3(...pose.offset));
    targetPos.y+=Math.sin(t*1.7)*.014;
    fly.position.lerp(targetPos,blend);
    rotation.set(...pose.body);quat.copy(rest.get(fly).quaternion).multiply(new THREE.Quaternion().setFromEuler(rotation));
    fly.quaternion.slerp(quat,blend);
    rotation.set(pose.head[0]+Math.sin(t*1.5)*.016,pose.head[1],pose.head[2]);
    quat.copy(rest.get(head).quaternion).multiply(new THREE.Quaternion().setFromEuler(rotation));head.quaternion.slerp(quat,blend);
    wings.forEach((o,i)=>{if(o)o.rotation.z=rest.get(o).rotation.z+(i?1:-1)*(pose.wingLift+Math.sin(t*pose.wingSpeed)*pose.wingAmp);});
    antenna.forEach((o,i)=>{if(o)o.rotation.x=rest.get(o).rotation.x+Math.sin(t*3.4+i*2)*.14*pose.antenna;});
    hindlegs.forEach((o,i)=>{if(o){o.rotation.x=THREE.MathUtils.lerp(o.rotation.x,rest.get(o).rotation.x+.62*pose.tuck,blend);o.rotation.z=THREE.MathUtils.lerp(o.rotation.z,rest.get(o).rotation.z+(i%2?1:-1)*.16*pose.tuck,blend);}});
    forelegs.forEach((leg,i)=>{
      if(!leg)return;
      const sign=i?1:-1,target=leg.restEnd.clone();
      target.y+=Math.sin(t*1.5+i)*.012-Math.max(0,Math.sin(t*15+i*2))*.06*pose.press;
      const rubbing=new THREE.Vector3(sign*(.035+.014*Math.sin(t*15)),1.12+sign*Math.sin(t*15)*.075,-1.05+Math.cos(t*8)*.035);
      const washing=new THREE.Vector3(sign*(.46+.045*Math.sin(t*9)),1.72+Math.sin(t*9+i*.5)*.17,-.70+Math.cos(t*9)*.045);
      rubbing.lerp(washing,pose.wash);target.lerp(rubbing,pose.groom);
      target.lerp(new THREE.Vector3(sign*.18,.84,-.65),pose.tuck);
      leg.target.lerp(target,blend);solveLeg(leg,leg.target,Math.max(pose.groom,pose.tuck),sign);
    });
    for(const {key,y} of keyRest.values())if(key)key.position.y=y;
    const active=keyRest.get(side==='SELL'?'SellKey':'BuyKey');
    if(active?.key)active.key.position.y=active.y-Math.max(0,Math.sin(t*15))*.035*pose.press;
    if(symbolValue!==pose.symbol){
      symbolValue=pose.symbol;ctx.clearRect(0,0,128,80);ctx.font='bold 46px monospace';ctx.textAlign='center';ctx.fillStyle='#d7efb8';ctx.fillText(symbolValue,64,56);texture.needsUpdate=true;
    }
    symbol.visible=Boolean(pose.symbol);symbol.material.opacity=pose.weight;
    fly.updateWorldMatrix(true,false);symbol.position.copy(fly.localToWorld(new THREE.Vector3(.14,2.42,-.25)));
    symbol.position.y+=Math.sin(t*2)*.05;
    if(lastLabel!==pose.label){lastLabel=pose.label;onBehavior(pose.label,pose.kind);}
  }
  apply(1/30,director.sample());
  return {
    fly,
    advance(dt){if(!disposed)apply(dt,director.advance(dt));},
    play(action){return director.play(action);},
    interact(direction){return director.interact(direction);},
    decision(row,fresh){side=fresh?row.neural?.side||'HOLD':'HOLD';if(fresh&&row.execution?.status==='FILLED')director.fill(row.tick);},
    dispose(){disposed=true;world.remove(symbol);symbol.material.dispose();texture.dispose();for(const leg of forelegs){if(leg){leg.hand.geometry.dispose();leg.limbMaterial.dispose();}}},
  };
}
