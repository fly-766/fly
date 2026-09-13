import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { createFlyMotion } from './fly-motion.js';
import { isTapGesture } from './behavior.js';

export async function startScene(canvas, screen, options={}) {
  const renderer=new THREE.WebGLRenderer({canvas,antialias:false,powerPreference:'low-power'});
  renderer.setPixelRatio(1);
  renderer.outputColorSpace=THREE.SRGBColorSpace;
  renderer.toneMapping=THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure=1.15;
  renderer.shadowMap.enabled=true;
  renderer.shadowMap.type=THREE.PCFShadowMap;
  const world=new THREE.Scene();world.background=new THREE.Color('#080b12');
  world.fog=new THREE.Fog('#080b12',16,30);
  world.add(new THREE.HemisphereLight('#9ab8b5','#171221',1.1));
  const moon=new THREE.DirectionalLight('#a6b8e4',2.0);
  moon.position.set(-3,8,5);moon.castShadow=true;
  moon.shadow.mapSize.set(1024,1024);moon.shadow.camera.left=-7;moon.shadow.camera.right=7;
  moon.shadow.camera.top=7;moon.shadow.camera.bottom=-7;moon.shadow.normalBias=.035;world.add(moon);
  const phosphor=new THREE.PointLight('#9cf04d',15,7,1.4);
  phosphor.position.set(.9,2.8,1.05);world.add(phosphor);
  const fill=new THREE.DirectionalLight('#695179',1.0);fill.position.set(4,4,-3);world.add(fill);
  const camera=new THREE.OrthographicCamera(-5.8,5.8,3.8,-3.8,.1,60);
  camera.position.set(5.8,5.3,10.2);
  const controls=new OrbitControls(camera,canvas);
  controls.target.set(0,1.85,0);controls.enablePan=false;controls.enableZoom=false;
  controls.enableDamping=true;controls.dampingFactor=.08;
  controls.minAzimuthAngle=-.22;controls.maxAzimuthAngle=.85;
  controls.minPolarAngle=.90;controls.maxPolarAngle=1.45;controls.update();
  let gltf;
  try { gltf=await new GLTFLoader().loadAsync('/assets/flydesk-pixel.glb'); }
  catch(error) { controls.dispose();renderer.dispose();throw error; }
  world.add(gltf.scene);
  gltf.scene.traverse(o=>{
    if(!o.isMesh)return;
    o.castShadow=true;o.receiveShadow=true;
    if(o.name.startsWith('WingMembrane'))o.material.side=THREE.DoubleSide;
    if(o.material?.name.startsWith('Eye facet'))o.material=new THREE.MeshBasicMaterial({color:o.material.color});
  });
  const display=gltf.scene.getObjectByName('ScreenSurface');
  if(!display)throw new Error('Screen surface missing');
  const texture=new THREE.CanvasTexture(screen.canvas);
  texture.colorSpace=THREE.SRGBColorSpace;texture.flipY=false;
  texture.minFilter=THREE.LinearFilter;texture.magFilter=THREE.NearestFilter;texture.generateMipmaps=false;
  display.material=new THREE.MeshBasicMaterial({map:texture,toneMapped:false});
  display.castShadow=false;display.receiveShadow=false;
  screen.onChange=()=>{texture.needsUpdate=true;};
  let paused=matchMedia('(prefers-reduced-motion: reduce)').matches;
  let focused=false,last=performance.now(),lastFrame=0,disposed=false,behaviorLabel='Watching the tape',behaviorKind='idle';
  const motion=createFlyMotion(gltf.scene,world,{onBehavior(label,kind){
    behaviorLabel=label;behaviorKind=kind;
    options.onBehavior?.(paused?'Motion paused':label,paused?'paused':kind);
  }});
  const raycaster=new THREE.Raycaster(),pointer=new THREE.Vector2();
  let gesture=null;
  function hitFly(event){
    const bounds=canvas.getBoundingClientRect();
    pointer.set((event.clientX-bounds.left)/bounds.width*2-1,1-(event.clientY-bounds.top)/bounds.height*2);
    world.updateMatrixWorld(true);camera.updateMatrixWorld();raycaster.setFromCamera(pointer,camera);
    let object=raycaster.intersectObject(gltf.scene,true)[0]?.object;
    while(object){if(object===motion.fly)return true;object=object.parent;}
    return false;
  }
  function pointerDown(event){
    if(event.button!==0||paused)return;
    gesture={id:event.pointerId,x:event.clientX,y:event.clientY,at:performance.now(),distance:0,hit:hitFly(event),button:event.button};
  }
  function pointerMove(event){
    if(gesture?.id===event.pointerId)gesture.distance=Math.max(gesture.distance,Math.hypot(event.clientX-gesture.x,event.clientY-gesture.y));
  }
  function pointerUp(event){
    const g=gesture;gesture=null;
    if(!g||g.id!==event.pointerId||paused||!g.hit)return;
    const distance=Math.max(g.distance,Math.hypot(event.clientX-g.x,event.clientY-g.y));
    if(!isTapGesture({distance,duration:performance.now()-g.at,button:g.button}))return;
    const center=motion.fly.getWorldPosition(new THREE.Vector3()).project(camera),bounds=canvas.getBoundingClientRect();
    const direction=event.clientX<bounds.left+(center.x+1)*bounds.width/2?1:-1;
    motion.interact(direction);
  }
  function cancelPointer(){gesture=null;}
  function keyDown(event){if(!paused&&(event.key==='Enter'||event.key===' ')){event.preventDefault();motion.interact(1);}}
  for(const [type,fn] of [['pointerdown',pointerDown],['pointermove',pointerMove],['pointerup',pointerUp],['pointercancel',cancelPointer]])canvas.addEventListener(type,fn,true);
  canvas.addEventListener('keydown',keyDown);
  function setPaused(value){paused=Boolean(value);gesture=null;options.onBehavior?.(paused?'Motion paused':behaviorLabel,paused?'paused':behaviorKind);}
  const sceneHeight=6.4;
  function resize(){
    const r=canvas.getBoundingClientRect();if(!r.width||!r.height)return;
    const width=Math.min(768,Math.max(320,Math.round(r.width*.82)));
    renderer.setSize(width,Math.round(width*r.height/r.width),false);
    const height=focused?2.95:sceneHeight;
    camera.top=height/2;camera.bottom=-height/2;camera.left=-height*r.width/r.height/2;camera.right=-camera.left;camera.updateProjectionMatrix();
  }
  const observer=new ResizeObserver(resize);observer.observe(canvas);resize();
  let raf=0, visible=true;
  const inView=new IntersectionObserver(entries=>{visible=entries[0]?.isIntersecting??true;});inView.observe(canvas);
  function frame(now){
    if(disposed)return;
    raf=requestAnimationFrame(frame);
    if(document.hidden || !visible || now-lastFrame<1000/30)return;
    const dt=Math.min((now-last)/1000,.1);last=now;
    lastFrame=now;
    if(!paused)motion.advance(dt);
    controls.update();renderer.render(world,camera);
  }
  raf=requestAnimationFrame(frame);
  return {
    setPaused, isPaused(){return paused;},
    play(action){
      const accepted=action==='react'?motion.interact(1):motion.play(action);
      if(accepted)setPaused(false);return accepted;
    },
    focusScreen(value){
      focused=Boolean(value);controls.enabled=!focused;
      if(focused){camera.position.set(1,2.72,8);controls.target.set(1,2.63,.015);}
      else{camera.position.set(5.8,5.3,10.2);controls.target.set(0,1.85,0);}
      controls.update();resize();return focused;
    },
    decision(row,fresh){
      motion.decision(row,fresh);
    },
    dispose(){
      if(disposed)return;disposed=true;cancelAnimationFrame(raf);inView.disconnect();observer.disconnect();controls.dispose();motion.dispose();
      for(const [type,fn] of [['pointerdown',pointerDown],['pointermove',pointerMove],['pointerup',pointerUp],['pointercancel',cancelPointer]])canvas.removeEventListener(type,fn,true);
      canvas.removeEventListener('keydown',keyDown);texture.dispose();
      const geometries=new Set(),materials=new Set(),textures=new Set();
      world.traverse(o=>{if(o.geometry)geometries.add(o.geometry);for(const m of (Array.isArray(o.material)?o.material:o.material?[o.material]:[])){materials.add(m);for(const value of Object.values(m))if(value?.isTexture)textures.add(value);}});
      for(const t of textures)t.dispose();for(const m of materials)m.dispose();for(const g of geometries)g.dispose();
      renderer.dispose();screen.onChange=null;
    },
  };
}
