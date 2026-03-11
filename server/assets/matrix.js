/**
 * The Forge Matrix v10 — Real NC Brain + Crucible + Aurora Shield
 *
 * Visual hierarchy (top to bottom):
 *   FORGE NEURAL CORTEX  (y=42)  — GPU-shader brain with wave physics
 *   THE CRUCIBLE          (y=24)  — procedural cauldron + sprite + fire
 *   AURORA SHIELD DOME    (y=-5..18) — protective dome over model field
 *   MODEL FIELD           (y=-5..+8) — all tested models in 6 sectors
 *
 * Tier radii are proportional to node density (no wasted space).
 */

import * as THREE from 'three';
import { OrbitControls }   from 'three/addons/controls/OrbitControls.js';
import { EffectComposer }  from 'three/addons/postprocessing/EffectComposer.js';
import { RenderPass }      from 'three/addons/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js';

const BG=0x040810,DUST_N=5000,LABEL_POOL=100,LABEL_DIST=30;
const WAVE={count:3,speed:0.25,sigma:0.12,hueCenter:0.52,hueRange:0.06,intensity:0.35};

// NC brain state cycle (idle → thinking → tool_exec → idle → pass → idle)
const NC_CYCLE=[
    {d:6,wc:1,sp:0.4,si:0.18,hc:0.52,hr:0.05,br:0.55,it:0.4,sa:0.7},
    {d:3,wc:3,sp:1.2,si:0.12,hc:0.0,hr:0.5,br:0.50,it:0.8,sa:0.85},
    {d:2,wc:2,sp:1.5,si:0.10,hc:0.42,hr:0.10,br:0.50,it:0.7,sa:0.8},
    {d:4,wc:1,sp:0.4,si:0.18,hc:0.52,hr:0.05,br:0.55,it:0.4,sa:0.7},
    {d:2,wc:1,sp:0.3,si:0.35,hc:0.33,hr:0.05,br:0.70,it:0.9,sa:0.85},
    {d:3,wc:1,sp:0.4,si:0.18,hc:0.52,hr:0.05,br:0.55,it:0.4,sa:0.7},
];
const NC_LEN=NC_CYCLE.reduce((s,x)=>s+x.d,0);

const TIER_DEFS=[
    {score:0.95,label:'ELITE 95%+',color:0x00ffcc},
    {score:0.85,label:'STRONG 85%+',color:0x50ff80},
    {score:0.70,label:'MODERATE 70%+',color:0xffab00},
    {score:0,label:'WEAK <70%',color:0xff1744},
];

const SECTORS=[
    {key:'safety',label:'SAFETY',angle:Math.PI/2,color:0x50ff80},
    {key:'reliability',label:'RELIABILITY',angle:Math.PI/2+Math.PI/3,color:0x58a6ff},
    {key:'adversarial',label:'ADVERSARIAL',angle:Math.PI/2+2*Math.PI/3,color:0xff6b6b},
    {key:'tool_misuse',label:'TOOL DISCIPLINE',angle:Math.PI/2+Math.PI,color:0xbc8cff},
    {key:'exfiltration',label:'EXFIL GUARD',angle:Math.PI/2+4*Math.PI/3,color:0xffab00},
    {key:'context_integrity',label:'CONTEXT',angle:Math.PI/2+5*Math.PI/3,color:0x00d4ff},
];
const CAT_KEYS=SECTORS.map(s=>s.key);

function scoreColor(s,sc){
    const t=Math.max(0,Math.min(1,(s-0.70)/0.28));const c=new THREE.Color();
    if(t<0.33)c.lerpColors(new THREE.Color(0x661a1a),new THREE.Color(0x994400),t/0.33);
    else if(t<0.66)c.lerpColors(new THREE.Color(0x994400),new THREE.Color(0x888820),(t-0.33)/0.33);
    else c.lerpColors(new THREE.Color(0x556633),new THREE.Color(sc||0x00d4ff),(t-0.66)/0.34);
    c.multiplyScalar(0.30+t*0.20);return c;
}
function family(id){return id.split(/[:\-_]/)[0].toLowerCase();}
function easeIO(t){return t*t*(3-2*t);}
function esc(s){const d=document.createElement('div');d.textContent=s;return d.innerHTML;}
function fmtN(n){return n>=1e6?(n/1e6).toFixed(1)+'M':n>=1e3?(n/1e3).toFixed(1)+'K':String(n);}
function hash(s){let h=0;for(let i=0;i<s.length;i++)h=((h<<5)-h+s.charCodeAt(i))|0;return h;}

function makeTextSprite(text,color,size){
    const c=document.createElement('canvas');c.width=512;c.height=64;
    const ctx=c.getContext('2d');ctx.font=`300 ${size||20}px 'Segoe UI',system-ui,sans-serif`;
    ctx.textAlign='center';ctx.textBaseline='middle';ctx.fillStyle=color||'rgba(0,212,255,0.25)';
    ctx.fillText(text,256,32);
    const tex=new THREE.CanvasTexture(c);tex.minFilter=THREE.LinearFilter;
    const sp=new THREE.Sprite(new THREE.SpriteMaterial({map:tex,transparent:true,depthWrite:false,
        blending:THREE.AdditiveBlending,opacity:0.45}));
    sp.scale.set(10,1.3,1);return sp;
}

class ForgeMatrix{
constructor(el){
    this.el=el;this.clock=new THREE.Clock();
    this.raycaster=new THREE.Raycaster();this.mouse=new THREE.Vector2(-99,-99);
    this.hubs=[];this.selected=null;this.hovered=null;
    this._flying=false;this.maxDist=1;this.isDemo=false;
    this._tmp=new THREE.Color();this._m4=new THREE.Matrix4();this._v3=new THREE.Vector3();
    this.hubWires=null;this.hubInners=null;this.hubGlows=null;
    this.gridMat=null;
    this.dust=null;this.coreRings=[];
    this.labelPool=[];this._labelTimer=0;
    this.worldR=55;this._tierBounds=[6,15,30,45,55];
    this.tierRings=[];this._wallMats=[];
    this._compassCanvas=null;this._compassCtx=null;this._compassTimer=0;
    this._brightness=3.0;
    // NC + Crucible + Shield
    this._ncGroup=null;this._ncMat=null;this._ncMembraneMat=null;this._ncPlanes=[];
    this._ncMembrane=null;this._ncRings=[];this._ncLobes=[];this._ncSynapses=null;this._ncSynapseVel=null;
    this._crucibleGroup=null;this._crucibleSprite=null;this._crucibleEmbers=null;
    this._crucibleGlow=null;this._crucibleTorus=null;this._crucibleLavaMat=null;this._crucibleLava=null;
    this._shieldDome=null;this._shieldMat=null;
    this._polarityWorst=false;this._polarityLerping=false;this._polarityLerpStart=0;
    this._ncPulseActive=false;this._ncPulseStart=0;
    this._gapWisps=null;this._gapWispsVisible=false;this._gapPlasmaMat=null;
    this._conduits=[];
    this._creatorFilter=null; // active creator name for isolation mode
    this._heatmapMesh=null;this._heatmapMat=null;this._heatmapOn=false;
    this._h2hA=null;this._h2hB=null; // head-to-head compare slots
    this._historyVisible=false;
    this._dataModels=null; // store raw data for sector drilldown
}

async init(){
    this._setupScene();this._setupPost();this._setupControls();
    this._createGrid();this._createDust();

    const params=new URLSearchParams(location.search);
    const forceDemo=params.get('demo')==='1';

    let data;
    if(!forceDemo){
        try{const r=await fetch('matrix.php?fmt=json');data=await r.json();
            if(data.demo||!data.models||!data.models.length)data=null;}catch(_){data=null;}
    }
    if(!data){data=demoData();this.isDemo=true;}

    // Load textures for NC brain and Crucible
    const _tl=new THREE.TextureLoader(),_lt=u=>new Promise(r=>_tl.load(u,r,undefined,()=>r(null)));
    [this._brainTex,this._crucibleTex]=await Promise.all([_lt('assets/brain.png'),_lt('assets/crucible.png')]);

    const n=data.models.length;
    this.worldR=Math.max(25,14+Math.sqrt(n)*0.7);

    // Proportional tier radii
    const tc=[0,0,0,0];
    for(const m of data.models){
        const s=m.avg_score;
        if(s>=0.95)tc[0]++;else if(s>=0.85)tc[1]++;else if(s>=0.70)tc[2]++;else tc[3]++;
    }
    const innerR=6,range=this.worldR-innerR;
    const w=tc.map(c=>Math.sqrt(c)+0.5);
    const tw=w.reduce((a,b)=>a+b,0);
    let acc=innerR;this._tierBounds=[innerR];
    for(const wi of w){acc+=(wi/tw)*range;this._tierBounds.push(acc);}

    this._buildGraph(data);
    this._createStructure(tc);
    this._createCore();
    this._createNC();
    this._createCrucible();
    this._createShieldDome();
    this._createConduits();
    this._createSectorLabels();
    this._initLabelPool();
    this._setupInput();
    this._updateStats(data);
    this._buildLeaderboards(data);
    this._createCompass();
    this._createBrightnessSlider();
    this._createPolarityBtn();
    this._createFamilyBtn();
    this._initSearch();
    this._initTour();
    this._createHeatmapBtn();
    this._createHistoryBtn();
    this._createDataSrcBtn();
    this._initSectorDrilldown();
    this._initH2H();
    this._dataModels=data.models;

    const notice=document.getElementById('matrix-demo-notice');
    if(notice){if(this.isDemo)notice.style.display='block';else notice.remove();}
    const ld=document.getElementById('matrix-loading');
    if(ld){ld.classList.add('fade');setTimeout(()=>ld.remove(),900);}
    this._animate();

    // Handle shareable link params after everything is ready
    this._handleUrlParams(params);
}

_setupScene(){
    this.scene=new THREE.Scene();this.scene.background=new THREE.Color(BG);
    this.scene.fog=new THREE.FogExp2(BG,0.003);
    this.camera=new THREE.PerspectiveCamera(50,innerWidth/innerHeight,0.1,800);
    this.camera.position.set(0,80,110);
    this.renderer=new THREE.WebGLRenderer({antialias:true});
    this.renderer.setSize(innerWidth,innerHeight);
    this.renderer.setPixelRatio(Math.min(devicePixelRatio,2));
    this.renderer.toneMapping=THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure=this._brightness;
    this.el.appendChild(this.renderer.domElement);
    addEventListener('resize',()=>this._resize());
}
_setupPost(){
    this.composer=new EffectComposer(this.renderer);
    this.composer.addPass(new RenderPass(this.scene,this.camera));
    this.bloomPass=new UnrealBloomPass(new THREE.Vector2(innerWidth,innerHeight),0.45,0.5,0.55);
    this.composer.addPass(this.bloomPass);
}
_setupControls(){
    this.controls=new OrbitControls(this.camera,this.renderer.domElement);
    Object.assign(this.controls,{enableDamping:true,dampingFactor:0.06,
        autoRotate:true,autoRotateSpeed:0.10,minDistance:3,maxDistance:350,maxPolarAngle:Math.PI*0.88});
    this.controls.target.set(0,15,0);
}

/* ── Forge Neural Cortex — GPU-shader brain at y=42 ────────────────── */

_createNC(){
    const Y=42,group=new THREE.Group();group.position.y=Y;this.scene.add(group);this._ncGroup=group;

    // Brain wave-physics shader (cortex.js ported to GLSL)
    const bvs=`varying vec2 vUv;void main(){vUv=uv;gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.);}`;
    const bfs=`
        uniform sampler2D uBrain;uniform float uTime,uWaveCount,uSpeed,uSigma,uHueCenter,uHueRange,uBaseBri,uIntensity,uSat;
        varying vec2 vUv;
        vec3 hsv2rgb(vec3 c){vec4 K=vec4(1.,2./3.,1./3.,3.);vec3 p=abs(fract(c.xxx+K.xyz)*6.-K.www);return c.z*mix(K.xxx,clamp(p-K.xxx,0.,1.),c.y);}
        void main(){
            vec4 brain=texture2D(uBrain,vUv);float bri=max(brain.r,max(brain.g,brain.b));float a=brain.a;float ba=bri*a;
            float pm=pow(clamp(ba,0.,1.),0.7);float dm=1.-pow(clamp(ba,0.,1.),0.5);
            float da=1.-dm*0.5;float dd=dm*0.3;
            vec2 ct=vUv-0.5;float dist=length(ct)*1.414;
            float wt=0.,ha=0.,sig2=2.*uSigma*uSigma;
            for(float wi=0.;wi<5.;wi+=1.){
                if(wi>=uWaveCount)break;
                float off=wi/max(uWaveCount,1.);float wp=mod(uTime*uSpeed+off,1.3);
                float hue=mod(uHueCenter+uHueRange*sin(uTime*0.3+wi*2.09),1.);
                float adj=dist+dd;float df=adj-wp;float w=exp(-(df*df)/sig2)*pm*da*uIntensity;
                wt+=w;ha+=w*hue;
            }
            wt=clamp(wt,0.,1.5);float h=wt>0.001?mod(ha/wt,1.):uHueCenter;
            vec3 wc=hsv2rgb(vec3(h,uSat,1.));
            vec3 oc=brain.rgb*uBaseBri*vec3(1.+wt*wc.r*2.,1.+wt*wc.g*2.,1.+wt*wc.b*2.);
            gl_FragColor=vec4(oc,a*(0.7+wt*0.5));
        }`;

    if(this._brainTex){
        this._ncMat=new THREE.ShaderMaterial({transparent:true,depthWrite:false,side:THREE.DoubleSide,
            blending:THREE.AdditiveBlending,
            uniforms:{uBrain:{value:this._brainTex},uTime:{value:0},
                uWaveCount:{value:1},uSpeed:{value:0.4},uSigma:{value:0.18},
                uHueCenter:{value:0.52},uHueRange:{value:0.05},uBaseBri:{value:0.55},
                uIntensity:{value:0.4},uSat:{value:0.7}},
            vertexShader:bvs,fragmentShader:bfs});

        // Single brain plane (billboard)
        const pg=new THREE.PlaneGeometry(10,10);
        const p=new THREE.Mesh(pg,this._ncMat);
        group.add(p);this._ncPlanes.push(p);
    }

    // Orbital rings
    for(let i=0;i<4;i++){
        const r=new THREE.Mesh(new THREE.TorusGeometry(6+i*0.8,0.01,6,80),
            new THREE.MeshBasicMaterial({color:0x00d4ff,transparent:true,opacity:0.08,
                blending:THREE.AdditiveBlending,depthWrite:false}));
        r.rotation.x=Math.PI/2+i*0.4;r.rotation.z=i*0.7;r.userData._ri=i;
        this._ncRings.push(r);group.add(r);
    }

    // Synapse particles
    const sN=200,sg=new THREE.BufferGeometry();
    const sp=new Float32Array(sN*3),sc=new Float32Array(sN*3),sv=new Float32Array(sN*3);
    for(let i=0;i<sN;i++){
        const th=Math.random()*Math.PI*2,ph=Math.acos(2*Math.random()-1),rr=4+Math.random()*2;
        sp[i*3]=rr*Math.sin(ph)*Math.cos(th);sp[i*3+1]=rr*Math.sin(ph)*Math.sin(th)*0.75;
        sp[i*3+2]=rr*Math.cos(ph)*0.8;
        const c=new THREE.Color().setHSL(0.52+Math.random()*0.1,0.7,0.4+Math.random()*0.3);
        sc[i*3]=c.r;sc[i*3+1]=c.g;sc[i*3+2]=c.b;
        sv[i*3]=(Math.random()-0.5)*0.02;sv[i*3+1]=(Math.random()-0.5)*0.02;sv[i*3+2]=(Math.random()-0.5)*0.02;
    }
    sg.setAttribute('position',new THREE.BufferAttribute(sp,3));
    sg.setAttribute('color',new THREE.BufferAttribute(sc,3));
    this._ncSynapses=new THREE.Points(sg,new THREE.PointsMaterial({size:0.12,vertexColors:true,
        transparent:true,opacity:0.5,blending:THREE.AdditiveBlending,depthWrite:false,sizeAttenuation:true}));
    this._ncSynapseVel=sv;group.add(this._ncSynapses);

    // 6 neural lobe nodes
    for(let i=0;i<6;i++){
        const a=i*Math.PI/3;
        const lobe=new THREE.Mesh(new THREE.OctahedronGeometry(0.5,0),
            new THREE.MeshBasicMaterial({color:SECTORS[i].color,wireframe:true,transparent:true,opacity:0.15}));
        lobe.position.set(Math.cos(a)*8,Math.sin(a*2)*0.8,Math.sin(a)*8);group.add(lobe);
        const pts=[lobe.position.clone(),new THREE.Vector3(0,0,0)];
        group.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts),
            new THREE.LineBasicMaterial({color:SECTORS[i].color,transparent:true,opacity:0.06,
                blending:THREE.AdditiveBlending,depthWrite:false})));
        this._ncLobes.push(lobe);
    }
    // Label
    const lb=makeTextSprite('FORGE NEURAL CORTEX','rgba(0,212,255,0.6)',24);
    lb.position.set(0,10,0);lb.scale.set(16,2,1);lb.material.opacity=0.65;group.add(lb);
}

/* ── Crucible — procedural cauldron + sprite at y=24 ────────────────── */

_createCrucible(){
    const Y=24,group=new THREE.Group();group.position.y=Y;this.scene.add(group);this._crucibleGroup=group;

    // Procedural cauldron — lathe profile (bowl shape)
    const pts=[];
    for(let i=0;i<=20;i++){
        const t=i/20;let r;
        if(t<0.1)r=0.3+t*18;
        else if(t<0.85)r=2.1+Math.sin((t-0.1)/0.75*Math.PI)*1.5;
        else r=3.6+(t-0.85)*3;
        pts.push(new THREE.Vector2(r,(t-0.5)*8));
    }
    const cGeo=new THREE.LatheGeometry(pts,24);
    group.add(new THREE.Mesh(cGeo,new THREE.MeshBasicMaterial({color:0x1a1210,transparent:true,opacity:0.3,side:THREE.DoubleSide})));
    group.add(new THREE.Mesh(cGeo,new THREE.MeshBasicMaterial({color:0xff6600,wireframe:true,transparent:true,opacity:0.05,
        blending:THREE.AdditiveBlending,depthWrite:false})));

    // Rim torus
    this._crucibleTorus=new THREE.Mesh(new THREE.TorusGeometry(4,0.15,8,48),
        new THREE.MeshBasicMaterial({color:0xffab00,transparent:true,opacity:0.2}));
    this._crucibleTorus.rotation.x=Math.PI/2;this._crucibleTorus.position.y=3.5;
    group.add(this._crucibleTorus);

    // Lava pool shader
    const lFS=`uniform float uTime;varying vec2 vUv;void main(){
        vec2 c=vUv-0.5;float d=length(c);float r=1.-smoothstep(0.,0.5,d);
        float n=sin(c.x*8.+uTime*2.)*sin(c.y*6.+uTime*1.5)*0.3+0.5+sin(c.x*12.-uTime*3.)*cos(c.y*10.+uTime*2.)*0.2;
        vec3 col=mix(vec3(0.8,0.15,0.),vec3(1.,0.6,0.1),n)*(0.7+0.3*sin(uTime*1.5));
        gl_FragColor=vec4(col,r*0.5);}`;
    this._crucibleLavaMat=new THREE.ShaderMaterial({transparent:true,depthWrite:false,
        blending:THREE.AdditiveBlending,side:THREE.DoubleSide,
        uniforms:{uTime:{value:0}},
        vertexShader:`varying vec2 vUv;void main(){vUv=uv;gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.);}`,
        fragmentShader:lFS});
    this._crucibleLava=new THREE.Mesh(new THREE.CircleGeometry(3.5,32),this._crucibleLavaMat);
    this._crucibleLava.rotation.x=-Math.PI/2;this._crucibleLava.position.y=3.3;
    group.add(this._crucibleLava);

    // Crucible.png sprite overlay (billboard)
    if(this._crucibleTex){
        this._crucibleSprite=new THREE.Sprite(new THREE.SpriteMaterial({map:this._crucibleTex,transparent:true,
            blending:THREE.NormalBlending,depthWrite:false,opacity:0.55}));
        this._crucibleSprite.scale.set(7.5,6,1);group.add(this._crucibleSprite);
    }

    // Glow sphere
    this._crucibleGlow=new THREE.Mesh(new THREE.SphereGeometry(5,16,16),
        new THREE.MeshBasicMaterial({color:0xff4400,transparent:true,opacity:0.015,
            blending:THREE.AdditiveBlending,depthWrite:false,side:THREE.BackSide}));
    group.add(this._crucibleGlow);

    // Ember particles
    const eN=120,eg=new THREE.BufferGeometry(),ep=new Float32Array(eN*3),ec=new Float32Array(eN*3);
    for(let i=0;i<eN;i++){
        ep[i*3]=(Math.random()-0.5)*5;ep[i*3+1]=2+Math.random()*8;ep[i*3+2]=(Math.random()-0.5)*4;
        const c=new THREE.Color().setHSL(0.06+Math.random()*0.08,0.9,0.4+Math.random()*0.3);
        ec[i*3]=c.r;ec[i*3+1]=c.g;ec[i*3+2]=c.b;
    }
    eg.setAttribute('position',new THREE.BufferAttribute(ep,3));
    eg.setAttribute('color',new THREE.BufferAttribute(ec,3));
    this._crucibleEmbers=new THREE.Points(eg,new THREE.PointsMaterial({size:0.1,vertexColors:true,
        transparent:true,opacity:0.6,blending:THREE.AdditiveBlending,depthWrite:false,sizeAttenuation:true}));
    group.add(this._crucibleEmbers);

    // Label
    const sp=makeTextSprite('CRUCIBLE','rgba(255,171,0,0.55)',20);
    sp.position.set(0,7,0);sp.scale.set(12,1.6,1);sp.material.opacity=0.6;group.add(sp);
}

/* ── Aurora Borealis Shield Dome ────────────────────────────────────── */

_createShieldDome(){
    const domeR=this.worldR+5;
    const domeVS=`varying vec3 vN,vV,vP;varying vec2 vUv;void main(){
        vUv=uv;vP=position;vec4 wp=modelMatrix*vec4(position,1.);
        vN=normalize(normalMatrix*normal);vV=normalize(cameraPosition-wp.xyz);
        gl_Position=projectionMatrix*viewMatrix*wp;}`;
    const domeFS=`uniform float uTime;varying vec3 vN,vV,vP;varying vec2 vUv;void main(){
        float y=vUv.y;
        float b1=sin(y*15.+uTime*0.5+vP.x*0.05)*0.5+0.5;
        float b2=sin(y*8.-uTime*0.3+vP.z*0.04+2.)*0.5+0.5;
        float b3=cos(y*12.+uTime*0.7+vP.x*0.03+1.)*0.5+0.5;
        float shimmer=sin(vP.x*0.15+uTime*1.5)*sin(vP.z*0.12-uTime*0.8)*0.5+0.5;
        vec3 c1=vec3(0.,1.,0.4)*b1;
        vec3 c2=vec3(0.,0.5,1.)*b2;
        vec3 c3=vec3(0.6,0.,1.)*b3;
        vec3 col=(c1+c2*0.6+c3*0.4)*0.6;
        float fr=pow(1.-abs(dot(vN,vV)),2.);
        float yFade=smoothstep(0.,0.25,y)*smoothstep(1.,0.6,y);
        float pulse=0.7+0.3*sin(uTime*0.4);
        float op=(0.02+fr*0.06)*yFade*(0.4+shimmer*0.4)*pulse;
        gl_FragColor=vec4(col,op);}`;
    this._shieldMat=new THREE.ShaderMaterial({transparent:true,depthWrite:false,side:THREE.DoubleSide,
        blending:THREE.AdditiveBlending,
        uniforms:{uTime:{value:0}},
        vertexShader:domeVS,fragmentShader:domeFS});
    // Hemisphere dome covering the model field
    this._shieldDome=new THREE.Mesh(
        new THREE.SphereGeometry(domeR,48,32,0,Math.PI*2,0,Math.PI*0.5),
        this._shieldMat);
    this._shieldDome.position.y=1; // base near ground
    this._shieldDome.scale.y=0.35; // flatten — apex at ~y=22, just below Crucible
    this.scene.add(this._shieldDome);
}

/* ── Energy conduits connecting NC → Crucible → Field ─────────────── */

_createConduits(){
    const mat=new THREE.LineBasicMaterial({color:0x00d4ff,transparent:true,opacity:0.04,
        blending:THREE.AdditiveBlending,depthWrite:false});
    const matG=new THREE.LineBasicMaterial({color:0xffab00,transparent:true,opacity:0.03,
        blending:THREE.AdditiveBlending,depthWrite:false});
    // NC (y=42) → Crucible (y=24)
    for(let i=0;i<6;i++){
        const a=i*Math.PI/3,r=2.5;
        const pts=[new THREE.Vector3(Math.cos(a)*r,42,Math.sin(a)*r),
            new THREE.Vector3(Math.cos(a)*4,24,Math.sin(a)*4)];
        this.scene.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts),mat));
    }
    // Crucible (y=24) → sector line start (y=0, r=2)
    for(let i=0;i<6;i++){
        const s=SECTORS[i];
        const pts=[new THREE.Vector3(Math.cos(s.angle)*4,24,Math.sin(s.angle)*4),
            new THREE.Vector3(Math.cos(s.angle)*2,0,Math.sin(s.angle)*2)];
        this.scene.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts),matG));
    }
    // Central axis
    const axisPts=[new THREE.Vector3(0,42,0),new THREE.Vector3(0,24,0),new THREE.Vector3(0,0,0)];
    this.scene.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(axisPts),
        new THREE.LineBasicMaterial({color:0x00d4ff,transparent:true,opacity:0.06,
            blending:THREE.AdditiveBlending,depthWrite:false})));
}

/* ── Sector Health Gauges — enterprise density visualization ───────── */

_createGapScanner(hubSubset){
    // Remove old gap scanner if rebuilding
    if(this._gapWisps){this.scene.remove(this._gapWisps);this._gapWisps=null;this._gapPlasmaMat=null;}
    const group=new THREE.Group();group.visible=false;
    this._gapWisps=group;
    const R=this.worldR;

    // Use provided subset or default to inner 3/4 (score >= 0.75)
    const sourceHubs=hubSubset||this.hubs;
    const innerHubs=sourceHubs.filter(h=>h.data.avg_score>=0.75);
    const innerR=4,outerR=R*0.78;
    const arcAngle=Math.PI/3;

    // Sector health for labels
    const counts=new Array(6).fill(0);
    for(const hub of innerHubs){
        const cats=hub.data.categories||{};let bestIdx=0,bestVal=0;
        for(let j=0;j<SECTORS.length;j++){const sv=cats[SECTORS[j].key]||0;if(sv>bestVal){bestVal=sv;bestIdx=j;}}
        counts[bestIdx]++;
    }
    const avgCount=counts.reduce((a,b)=>a+b,0)/6;
    this._gapSectorIndices=new Set();
    for(let i=0;i<6;i++)if(counts[i]<avgCount*0.75)this._gapSectorIndices.add(i);

    // Build spatial index grid for fast nearest-node lookup
    const cellSz=3,grid=new Map();
    for(const h of innerHubs){
        const gx=Math.floor(h.pos.x/cellSz),gz=Math.floor(h.pos.z/cellSz);
        for(let dx=-1;dx<=1;dx++)for(let dz=-1;dz<=1;dz++){
            const k=(gx+dx)+','+(gz+dz);if(!grid.has(k))grid.set(k,[]);grid.get(k).push(h);
        }
    }
    function nearestDist(px,pz){
        const gx=Math.floor(px/cellSz),gz=Math.floor(pz/cellSz);
        const k=gx+','+gz;const bucket=grid.get(k);
        if(!bucket)return 99;
        let min=999;
        for(const h of bucket){const dx=h.pos.x-px,dz=h.pos.z-pz;const d=dx*dx+dz*dz;if(d<min)min=d;}
        return Math.sqrt(min);
    }

    // Dense sampling — every void gets plasma
    const positions=[],colors=[],opacities=[];
    const voidMin=0.8; // very sensitive void detection
    for(let i=0;i<SECTORS.length;i++){
        const s=SECTORS[i];
        for(let ri=0;ri<24;ri++){
            const r=innerR+(outerR-innerR)*((ri+0.5)/24);
            const nArc=Math.max(8,Math.round(16*(r/outerR)));
            for(let ai=0;ai<nArc;ai++){
                const a=s.angle-arcAngle*0.46+arcAngle*0.92*(ai/(nArc-1));
                const px=Math.cos(a)*r,pz=Math.sin(a)*r;
                const nd=nearestDist(px,pz);
                if(nd<voidMin)continue;
                // Void intensity: 0=barely, 1=deep void
                const vs=Math.min((nd-voidMin)/6,1);
                const py=0.15+Math.sin(px*0.5+pz*0.3)*0.2;
                positions.push(px,py,pz);
                const sc=new THREE.Color(s.color),rc=new THREE.Color(0xff2200);
                const c=sc.clone().lerp(rc,vs);
                colors.push(c.r,c.g,c.b);
                opacities.push(0.06+vs*0.18);
            }
        }
    }

    if(positions.length>0){
        const geo=new THREE.BufferGeometry();
        geo.setAttribute('position',new THREE.Float32BufferAttribute(positions,3));
        geo.setAttribute('color',new THREE.Float32BufferAttribute(colors,3));
        geo.setAttribute('aOpacity',new THREE.Float32BufferAttribute(opacities,1));
        const plasmaMat=new THREE.ShaderMaterial({
            uniforms:{uTime:{value:0}},
            vertexShader:`
                attribute float aOpacity;
                varying vec3 vColor;varying float vOp;varying vec3 vWP;
                void main(){
                    vColor=color;vOp=aOpacity;vWP=position;
                    vec3 p=position;
                    p.y+=sin(p.x*0.4+p.z*0.3)*0.3;
                    vec4 mv=modelViewMatrix*vec4(p,1.0);
                    float sz=2.0+aOpacity*8.0;
                    gl_PointSize=sz*(200.0/max(-mv.z,1.0));
                    gl_Position=projectionMatrix*mv;
                }`,
            fragmentShader:`
                uniform float uTime;
                varying vec3 vColor;varying float vOp;varying vec3 vWP;
                void main(){
                    float d=length(gl_PointCoord-0.5)*2.0;
                    if(d>1.0)discard;
                    float core=exp(-d*d*3.0);
                    float flicker=0.7+0.3*sin(uTime*1.8+vWP.x*0.6+vWP.z*0.5);
                    float pulse=0.8+0.2*sin(uTime*0.9+length(vWP.xz)*0.12);
                    float alpha=core*vOp*flicker*pulse*0.5;
                    gl_FragColor=vec4(vColor*0.7,alpha);
                }`,
            transparent:true,depthWrite:false,vertexColors:true
        });
        const pts=new THREE.Points(geo,plasmaMat);
        group.add(pts);
        this._gapPlasmaMat=plasmaMat;
    }

    // Sector labels
    this._gapLabels=[];
    const maxCount=Math.max(1,...counts);
    for(let i=0;i<SECTORS.length;i++){
        const s=SECTORS[i];const isGap=this._gapSectorIndices.has(i);
        const sCol=new THREE.Color(s.color);
        const pct=Math.round(counts[i]/maxCount*100);
        const labelColor=isGap?'#ff4422':'#'+sCol.getHexString();
        const label=makeTextSprite(`${counts[i]} INNER  ${pct}%`,labelColor,24);
        const lx=Math.cos(s.angle)*(R*0.55),lz=Math.sin(s.angle)*(R*0.55);
        label.position.set(lx,1.5,lz);label.scale.set(14,1.5,1);
        group.add(label);this._gapLabels.push(label);
        if(isGap){
            const warn=makeTextSprite('VOID DETECTED','#ff4422',20);
            warn.position.set(lx,3.5,lz);warn.scale.set(10,1.2,1);
            warn.material.opacity=0.65;
            group.add(warn);this._gapLabels.push(warn);
        }
    }

    this.scene.add(group);
}

_showGapView(skipFly){
    if(!this._gapWisps)this._createGapScanner();
    this._gapWisps.visible=true;this._gapWispsVisible=true;
    if(!skipFly)this._flyToBirdsEye();
}

_hideGapView(){
    if(this._gapWisps)this._gapWisps.visible=false;
    this._gapWispsVisible=false;
}

_flyToBirdsEye(){
    if(this._flying)return;
    const cs=this.camera.position.clone(),ls=this.controls.target.clone();
    const ce=new THREE.Vector3(0,170,3);
    const le=new THREE.Vector3(0,0,0);
    this._flying=true;this.controls.enabled=false;const t0=performance.now();
    const fly=()=>{const t=Math.min((performance.now()-t0)/1800,1),e=easeIO(t);
        this.camera.position.lerpVectors(cs,ce,e);this.controls.target.lerpVectors(ls,le,e);this.controls.update();
        if(t<1)requestAnimationFrame(fly);else{this._flying=false;this.controls.enabled=true;}};requestAnimationFrame(fly);
}

/* ── Core (small nexus at model field center y=0) ─────────────────── */

_createCore(){
    this.coreMesh=new THREE.Mesh(new THREE.IcosahedronGeometry(0.6,1),
        new THREE.MeshBasicMaterial({color:0x00d4ff,wireframe:true,transparent:true,opacity:0.25}));
    this.scene.add(this.coreMesh);
    this.coreGlow=new THREE.Mesh(new THREE.IcosahedronGeometry(1.8,2),
        new THREE.MeshBasicMaterial({color:0x00d4ff,transparent:true,opacity:0.008,
            blending:THREE.AdditiveBlending,depthWrite:false,side:THREE.BackSide}));
    this.scene.add(this.coreGlow);
    for(let i=0;i<3;i++){
        const r=new THREE.Mesh(new THREE.TorusGeometry(1.5+i*0.6,0.003,6,80),
            new THREE.MeshBasicMaterial({color:0x00d4ff,transparent:true,opacity:0.05,
                blending:THREE.AdditiveBlending,depthWrite:false}));
        r.rotation.x=Math.PI/2+i*0.35;r.rotation.z=i*0.6;r.userData._ri=i;
        this.coreRings.push(r);this.scene.add(r);
    }
}

/* ── Structure — proportional tier rings + sector walls ───────────── */

_createStructure(tc){
    const R=this.worldR,b=this._tierBounds,total=this.hubs.length||1;

    // Tier rings at computed boundaries
    for(let ti=0;ti<TIER_DEFS.length;ti++){
        const tier=TIER_DEFS[ti];
        const tr=b[ti+1]; // outer boundary of this tier
        const count=tc[ti]||0;
        const density=count/total;
        const thick=0.03+density*0.8;
        // Main ring
        const ring=new THREE.Mesh(new THREE.RingGeometry(tr-thick,tr+thick,128),
            new THREE.MeshBasicMaterial({color:tier.color,transparent:true,opacity:0.07,
                blending:THREE.AdditiveBlending,depthWrite:false,side:THREE.DoubleSide}));
        ring.rotation.x=-Math.PI/2;this.scene.add(ring);
        // Glow ring
        const gt=thick*3;
        const glow=new THREE.Mesh(new THREE.RingGeometry(tr-gt,tr+gt,128),
            new THREE.MeshBasicMaterial({color:tier.color,transparent:true,opacity:0.02,
                blending:THREE.AdditiveBlending,depthWrite:false,side:THREE.DoubleSide}));
        glow.rotation.x=-Math.PI/2;this.scene.add(glow);
        this.tierRings.push({main:ring,glow,baseOpacity:0.07,glowBaseOpacity:0.02,phase:ti*1.5});
        // Label
        const la=Math.PI*0.25;
        const cl=fmtN(count);
        const sp=makeTextSprite(`${tier.label} (${cl})`,'#'+new THREE.Color(tier.color).getHexString()+'88',14);
        sp.position.set(Math.cos(la)*(tr+1.5),2,Math.sin(la)*(tr+1.5));this.scene.add(sp);
    }

    // Sector boundary walls
    const wallVS=`varying vec2 vUv;void main(){vUv=uv;gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.);}`;
    const wallFS=`uniform vec3 uColor;uniform float uTime;varying vec2 vUv;void main(){
        float rf=smoothstep(0.,0.15,vUv.x)*(0.5+0.5*vUv.x);float vf=1.-pow(abs(vUv.y-0.5)*2.,2.);
        float sc=0.6+0.4*sin(vUv.y*40.+uTime*2.5);float pu=0.7+0.3*sin(uTime*1.2+vUv.x*6.);
        float a=rf*vf*sc*pu*0.04;gl_FragColor=vec4(uColor,a);}`;
    for(let i=0;i<SECTORS.length;i++){
        const ba=SECTORS[i].angle+Math.PI/6;
        const dx=Math.cos(ba),dz=Math.sin(ba),wh=14;
        const verts=new Float32Array([3*dx,-wh/2,3*dz,R*dx,-wh/2,R*dz,R*dx,wh/2,R*dz,3*dx,wh/2,3*dz]);
        const uvs=new Float32Array([0,0,1,0,1,1,0,1]);
        const geo=new THREE.BufferGeometry();
        geo.setAttribute('position',new THREE.BufferAttribute(verts,3));
        geo.setAttribute('uv',new THREE.BufferAttribute(uvs,2));
        geo.setIndex(new THREE.BufferAttribute(new Uint16Array([0,1,2,0,2,3]),1));
        const c1=new THREE.Color(SECTORS[i].color),c2=new THREE.Color(SECTORS[(i+1)%6].color);
        const mat=new THREE.ShaderMaterial({transparent:true,depthWrite:false,side:THREE.DoubleSide,
            uniforms:{uColor:{value:c1.clone().lerp(c2,0.5)},uTime:{value:0}},
            vertexShader:wallVS,fragmentShader:wallFS});
        this._wallMats.push(mat);this.scene.add(new THREE.Mesh(geo,mat));
    }

    // Sector divider center lines
    for(const s of SECTORS){
        const dx=Math.cos(s.angle),dz=Math.sin(s.angle);
        this.scene.add(new THREE.Line(
            new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(2*dx,0,2*dz),new THREE.Vector3(dx*(R+3),0,dz*(R+3))]),
            new THREE.LineBasicMaterial({color:s.color,transparent:true,opacity:0.08,blending:THREE.AdditiveBlending,depthWrite:false})));
    }
}

_createGrid(){
    this.gridMat=new THREE.ShaderMaterial({transparent:true,depthWrite:false,side:THREE.DoubleSide,
        uniforms:{uTime:{value:0},uColor:{value:new THREE.Color(0x061018)}},
        vertexShader:`varying vec3 vP;void main(){vP=(modelMatrix*vec4(position,1.)).xyz;gl_Position=projectionMatrix*viewMatrix*vec4(vP,1.);}`,
        fragmentShader:`uniform float uTime;uniform vec3 uColor;varying vec3 vP;void main(){vec2 g=abs(fract(vP.xz*0.12)-0.5);float ln=min(g.x,g.y);float m=1.-smoothstep(0.,0.012,ln);float d=length(vP.xz)/140.;float f=1.-smoothstep(0.05,1.,d);float p=0.5+0.5*sin(uTime*0.15+d*3.);gl_FragColor=vec4(uColor,m*f*p*0.025);}`});
    const p=new THREE.Mesh(new THREE.PlaneGeometry(350,350,1,1),this.gridMat);
    p.rotation.x=-Math.PI/2;p.position.y=-20;this.scene.add(p);
}
_createDust(){
    const g=new THREE.BufferGeometry();
    const pos=new Float32Array(DUST_N*3),col=new Float32Array(DUST_N*3);
    for(let i=0;i<DUST_N;i++){
        const r=10+Math.random()*100,th=Math.random()*Math.PI*2,ph=Math.acos(2*Math.random()-1);
        pos[i*3]=r*Math.sin(ph)*Math.cos(th);pos[i*3+1]=r*Math.sin(ph)*Math.sin(th)*0.5;
        pos[i*3+2]=r*Math.cos(ph);
        const c=new THREE.Color().setHSL(0.55+Math.random()*0.08,0.25,0.12+Math.random()*0.06);
        col[i*3]=c.r;col[i*3+1]=c.g;col[i*3+2]=c.b;
    }
    g.setAttribute('position',new THREE.BufferAttribute(pos,3));
    g.setAttribute('color',new THREE.BufferAttribute(col,3));
    this.dust=new THREE.Points(g,new THREE.PointsMaterial({size:0.03,vertexColors:true,transparent:true,opacity:0.08,
        blending:THREE.AdditiveBlending,depthWrite:false,sizeAttenuation:true}));
    this.scene.add(this.dust);
}
_createSectorLabels(){
    const R=this.worldR;
    for(const s of SECTORS){
        const lr=R*0.45,x=Math.cos(s.angle)*lr,z=Math.sin(s.angle)*lr;
        const c='#'+new THREE.Color(s.color).getHexString();
        const sp=makeTextSprite(s.label,c+'cc',28);sp.position.set(x,14,z);
        sp.scale.set(16,2.5,1);sp.material.opacity=0.7;this.scene.add(sp);
    }
}

/* ── Graph ────────────────────────────────────────────────────────── */

_buildGraph(data){
    const models=data.models;
    for(const m of models){m._pos=this._pos(m);m._family=family(m.id);}
    this.maxDist=Math.max(1,...models.map(m=>m._pos.length()));
    this._createHubs(models);
}

_scoreToRadius(score){
    const s=Math.max(0.3,Math.min(1,score)),b=this._tierBounds;
    // Within each tier band, higher score = closer to inner edge
    if(s>=0.95){const t=(s-0.95)/0.05;return b[0]+(1-t)*(b[1]-b[0]);}
    if(s>=0.85){const t=(s-0.85)/0.10;return b[1]+(1-t)*(b[2]-b[1]);}
    if(s>=0.70){const t=(s-0.70)/0.15;return b[2]+(1-t)*(b[3]-b[2]);}
    const t=Math.max(0,s/0.70);return b[3]+(1-t)*(b[4]-b[3]);
}

_pos(m,useWorst){
    const cats=m.categories||{};let pickIdx=0,pickVal=useWorst?2:0;
    for(let i=0;i<SECTORS.length;i++){const v=cats[SECTORS[i].key]||0;
        if(useWorst?v<pickVal:v>pickVal){pickVal=v;pickIdx=i;}}
    const dom=SECTORS[pickIdx];
    const baseR=this._scoreToRadius(m.avg_score);
    const h=hash(m.id),h2=hash(m.id+'x'),h3=hash(m.id+'y');
    const r1=((h&0xffff)/65535),r2=(((h>>16)&0xffff)/65535);
    const r3=((h2&0xffff)/65535),r4=(((h2>>16)&0xffff)/65535),r5=((h3&0xffff)/65535);
    const radius=Math.max(3,baseR+(r1-0.5)*4);
    const angle=dom.angle+(r2-0.5)*0.98;
    const trend=m.trend||0;const y=trend*100+(r3-0.5)*4+(r4-0.5)*2;
    return new THREE.Vector3(Math.cos(angle)*radius,y,Math.sin(angle)*radius+(r5-0.5)*2);
}

_togglePolarity(){
    this._polarityWorst=!this._polarityWorst;
    // Recalculate positions + compute displacement
    let maxDisp=0;
    for(const hub of this.hubs){
        const np=this._pos(hub.data,this._polarityWorst);
        hub._targetPos=np;hub._fromPos=hub.pos.clone();hub._lerpT=0;
        hub._displacement=hub._fromPos.distanceTo(np);
        if(hub._displacement>maxDisp)maxDisp=hub._displacement;
        hub._orbitR=np.length();hub._orbitA=Math.atan2(np.z,np.x);hub._baseY=np.y;
    }
    // Tag balance: low displacement = balanced, high = unbalanced
    for(const hub of this.hubs){
        hub._balance=1-Math.min(hub._displacement/(maxDisp||1),1); // 1=perfectly balanced, 0=max displacement
    }
    this._polarityLerping=true;this._polarityLerpStart=performance.now();
    // NC pulse cascade: pulse starts at NC (y=42), flows through Crucible (y=24) into field
    this._ncPulseActive=true;this._ncPulseStart=performance.now();
    // Update button label
    const btn=document.getElementById('polarity-btn');
    if(btn)btn.textContent=this._polarityWorst?'SHOWING: WEAKEST':'SHOWING: STRONGEST';
    // Fly to birds-eye + show sector health gauges (skip during tour)
    if(!this._tourActive){
        this._flyToBirdsEye();
        if(!this._gapWisps)this._createGapScanner();
        this._gapWisps.visible=true;this._gapWispsVisible=true;
    }
}

_createHubs(models){
    const n=models.length;
    this.hubWires=new THREE.InstancedMesh(new THREE.IcosahedronGeometry(1,1),
        new THREE.MeshBasicMaterial({color:0xffffff,wireframe:true,transparent:true,opacity:0.18}),n);
    this.hubWires.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
    this.hubInners=new THREE.InstancedMesh(new THREE.SphereGeometry(1,6,6),
        new THREE.MeshBasicMaterial({color:0xffffff}),n);
    this.hubInners.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
    this.hubGlows=new THREE.InstancedMesh(new THREE.SphereGeometry(1,8,8),
        new THREE.MeshBasicMaterial({color:0xffffff,transparent:true,opacity:0.008,
            blending:THREE.AdditiveBlending,depthWrite:false,side:THREE.BackSide}),n);
    const m4=this._m4;
    for(let i=0;i<n;i++){
        const model=models[i],pos=model._pos;
        let domSec=SECTORS[0],domVal=0;
        for(const s of SECTORS){const v=model.categories?.[s.key]||0;if(v>domVal){domVal=v;domSec=s;}}
        const bc=scoreColor(model.avg_score,domSec.color);
        const sz=0.08+Math.pow(Math.min(model.run_count,40000)/40000,0.4)*0.9;
        m4.makeScale(sz*1.4,sz*1.4,sz*1.4);m4.setPosition(pos.x,pos.y,pos.z);
        this.hubWires.setMatrixAt(i,m4);this.hubWires.setColorAt(i,bc);
        m4.makeScale(sz*0.25,sz*0.25,sz*0.25);m4.setPosition(pos.x,pos.y,pos.z);
        this.hubInners.setMatrixAt(i,m4);this.hubInners.setColorAt(i,bc);
        m4.makeScale(sz*2.5,sz*2.5,sz*2.5);m4.setPosition(pos.x,pos.y,pos.z);
        this.hubGlows.setMatrixAt(i,m4);this.hubGlows.setColorAt(i,bc);
        this.hubs.push({data:model,pos,baseColor:bc.clone(),baseSize:sz,
            _phase:Math.random()*Math.PI*2,_wave:0,_waveHue:0.52,idx:i,
            _orbit:((hash(model.id+'o')&0xffff)/65535)*0.003+0.001,
            _orbitR:pos.length(),_orbitA:Math.atan2(pos.z,pos.x),_baseY:pos.y});
    }
    for(const mesh of[this.hubWires,this.hubInners,this.hubGlows]){
        mesh.instanceMatrix.needsUpdate=true;mesh.instanceColor.needsUpdate=true;this.scene.add(mesh);}
}

_createEdges(models){}

/* ── Labels ──────────────────────────────────────────────────────── */
_initLabelPool(){for(let i=0;i<LABEL_POOL;i++){
    const canvas=document.createElement('canvas');canvas.width=256;canvas.height=48;
    const tex=new THREE.CanvasTexture(canvas);tex.minFilter=THREE.LinearFilter;
    const sprite=new THREE.Sprite(new THREE.SpriteMaterial({map:tex,transparent:true,depthWrite:false,sizeAttenuation:true}));
    sprite.scale.set(2.8,0.5,1);sprite.visible=false;this.scene.add(sprite);
    this.labelPool.push({sprite,canvas,ctx:canvas.getContext('2d'),tex,modelId:null});}}
_drawLabel(lbl,hub){const ctx=lbl.ctx,c=lbl.canvas;ctx.clearRect(0,0,c.width,c.height);
    ctx.fillStyle='rgba(4,8,16,0.6)';ctx.strokeStyle='rgba(0,212,255,0.15)';ctx.lineWidth=1;
    ctx.beginPath();ctx.roundRect(4,2,248,44,4);ctx.fill();ctx.stroke();
    ctx.font='bold 12px Consolas,monospace';ctx.fillStyle='rgba(160,190,200,0.7)';
    ctx.textAlign='center';ctx.textBaseline='middle';
    const name=hub.data.id.length>26?hub.data.id.slice(0,24)+'..':hub.data.id;
    ctx.fillText(name,128,16);ctx.font='10px Consolas,monospace';
    const pct=Math.round(hub.data.avg_score*100);
    ctx.fillStyle=pct>=95?'rgba(0,255,200,0.5)':pct>=85?'rgba(80,255,128,0.6)':pct>=70?'rgba(255,171,0,0.5)':'rgba(255,23,68,0.5)';
    ctx.fillText(pct+'%  '+fmtN(hub.data.run_count)+' runs',128,34);
    lbl.tex.needsUpdate=true;lbl.modelId=hub.data.id;}
_updateLabels(){const camPos=this.camera.position,sorted=[],cf=this._creatorFilter;
    for(const h of this.hubs){if(cf&&h.data._family!==cf)continue;const dsq=h.pos.distanceToSquared(camPos);if(dsq<LABEL_DIST*LABEL_DIST)sorted.push({hub:h,dsq});}
    sorted.sort((a,b)=>a.dsq-b.dsq);
    for(let i=0;i<this.labelPool.length;i++){const lbl=this.labelPool[i];
        if(i<sorted.length){const hub=sorted[i].hub;if(lbl.modelId!==hub.data.id)this._drawLabel(lbl,hub);
            lbl.sprite.position.set(hub.pos.x,hub.pos.y+hub.baseSize*3.5+0.5,hub.pos.z);lbl.sprite.visible=true;
        }else{lbl.sprite.visible=false;lbl.modelId=null;}}}

/* ── Compass ─────────────────────────────────────────────────────── */
_createCompass(){
    let c=document.getElementById('matrix-compass');
    if(!c){c=document.createElement('canvas');c.id='matrix-compass';document.body.appendChild(c);}
    c.width=160;c.height=160;
    this._compassCanvas=c;this._compassCtx=c.getContext('2d');
    // Draw immediately so it's visible before first animate tick
    this._updateCompass();
}
_updateCompass(){const ctx=this._compassCtx;if(!ctx)return;
    const w=this._compassCanvas.width,cx=w/2,cy=w/2,cr=w*0.34;
    ctx.clearRect(0,0,w,w);
    // Camera azimuth in math convention (atan2(z,x)) — matches sector angle convention
    const cam=this.camera,tgt=this.controls.target;
    const camAz=Math.atan2(cam.position.z-tgt.z,cam.position.x-tgt.x);
    // Rings
    ctx.beginPath();ctx.arc(cx,cy,cr+8,0,Math.PI*2);ctx.strokeStyle='rgba(0,212,255,0.15)';ctx.lineWidth=1;ctx.stroke();
    ctx.beginPath();ctx.arc(cx,cy,cr,0,Math.PI*2);ctx.strokeStyle='rgba(0,212,255,0.25)';ctx.stroke();
    // "You are here" arrow at BOTTOM (nearest sector side)
    ctx.beginPath();ctx.moveTo(cx,cy+cr+12);ctx.lineTo(cx-5,cy+cr+4);ctx.lineTo(cx+5,cy+cr+4);ctx.closePath();
    ctx.fillStyle='rgba(0,212,255,0.5)';ctx.fill();
    for(const s of SECTORS){
        // Minimap-style: +PI so nearest sector appears at BOTTOM (your side)
        // Far-side sectors appear at TOP (what you're looking at)
        const rel=camAz-s.angle+Math.PI;
        const px=cx+Math.sin(rel)*cr,py=cy-Math.cos(rel)*cr;
        const c6='#'+new THREE.Color(s.color).getHexString();
        // Dot (6px radius for visibility)
        ctx.beginPath();ctx.arc(px,py,6,0,Math.PI*2);ctx.fillStyle=c6;ctx.globalAlpha=0.85;ctx.fill();ctx.globalAlpha=1;
        // Colored arc segment on the ring
        const arcA=rel-Math.PI/2;
        ctx.beginPath();ctx.arc(cx,cy,cr,arcA-Math.PI/6,arcA+Math.PI/6);
        ctx.strokeStyle=c6;ctx.globalAlpha=0.2;ctx.lineWidth=6;ctx.stroke();ctx.globalAlpha=1;ctx.lineWidth=1;
        // Label
        ctx.font='bold 9px Consolas,monospace';ctx.fillStyle=c6;ctx.globalAlpha=0.9;ctx.textAlign='center';ctx.textBaseline='middle';
        const lx=cx+Math.sin(rel)*(cr+18),ly=cy-Math.cos(rel)*(cr+18);
        const sl=s.key==='context_integrity'?'CTX':s.key==='tool_misuse'?'TOOL':s.key==='exfiltration'?'EXFIL':s.label.slice(0,5);
        ctx.fillText(sl,lx,ly);ctx.globalAlpha=1;}
    // Center dot
    ctx.beginPath();ctx.arc(cx,cy,3,0,Math.PI*2);ctx.fillStyle='rgba(0,212,255,0.4)';ctx.fill();}

/* ── Brightness ──────────────────────────────────────────────────── */
_createBrightnessSlider(){
    const el=document.getElementById('matrix-legend');if(!el)return;
    const wrap=document.createElement('div');
    wrap.style.cssText='margin-top:8px;border-top:1px solid rgba(0,212,255,0.06);padding-top:6px;';
    wrap.innerHTML=`<div style="font-size:0.5rem;color:rgba(0,212,255,0.3);letter-spacing:0.1em;text-transform:uppercase;margin-bottom:2px">BRIGHTNESS</div>
        <input type="range" id="matrix-brightness" min="25" max="500" value="${Math.round(this._brightness*100)}" style="width:100%;accent-color:#00d4ff;opacity:0.7;cursor:pointer;pointer-events:auto;height:18px">`;
    el.appendChild(wrap);el.style.pointerEvents='auto';
    document.getElementById('matrix-brightness').addEventListener('input',e=>{
        this._brightness=parseInt(e.target.value)/100;this.renderer.toneMappingExposure=this._brightness;});
}

_createPolarityBtn(){
    const btn=document.createElement('div');
    btn.id='polarity-btn';
    btn.textContent='SHOWING: STRONGEST';
    btn.style.cssText='position:fixed;top:72px;right:24px;z-index:6;cursor:pointer;font-family:Consolas,monospace;font-size:0.6rem;letter-spacing:0.1em;color:rgba(120,220,255,0.8);background:rgba(4,8,16,0.75);border:1px solid rgba(0,212,255,0.25);border-radius:4px;padding:6px 12px;text-transform:uppercase;pointer-events:auto;transition:all 0.3s;font-weight:600;text-shadow:0 0 6px rgba(0,180,255,0.15);';
    btn.addEventListener('mouseenter',()=>{btn.style.color='#00d4ff';btn.style.borderColor='rgba(0,212,255,0.4)';});
    btn.addEventListener('mouseleave',()=>{btn.style.color='rgba(0,212,255,0.6)';btn.style.borderColor='rgba(0,212,255,0.15)';});
    btn.addEventListener('click',()=>this._togglePolarity());
    document.body.appendChild(btn);
}

_createFamilyBtn(){
    this._familyMode=false;this._familyColors={};
    const btn=document.createElement('div');
    btn.id='family-btn';
    btn.textContent='COLOR BY CREATOR';
    btn.style.cssText='position:fixed;top:72px;right:340px;z-index:6;cursor:pointer;font-family:Consolas,monospace;font-size:0.6rem;letter-spacing:0.1em;color:rgba(120,220,255,0.8);background:rgba(4,8,16,0.75);border:1px solid rgba(0,212,255,0.25);border-radius:4px;padding:6px 12px;text-transform:uppercase;pointer-events:auto;transition:all 0.3s;font-weight:600;text-shadow:0 0 6px rgba(0,180,255,0.15);';
    btn.addEventListener('mouseenter',()=>{btn.style.color='#00d4ff';btn.style.borderColor='rgba(0,212,255,0.4)';});
    btn.addEventListener('mouseleave',()=>{if(!this._familyMode){btn.style.color='rgba(0,212,255,0.6)';btn.style.borderColor='rgba(0,212,255,0.15)';}});
    btn.addEventListener('click',()=>this._toggleFamilyMode(btn));
    document.body.appendChild(btn);
}
_toggleFamilyMode(btn){
    this._familyMode=!this._familyMode;
    if(this._familyMode){
        // Assign unique bright hues to each family
        const families=new Set();
        for(const hub of this.hubs)families.add(hub.data._family);
        const sorted=[...families].sort();
        const n=sorted.length;
        this._familyColors={};
        for(let i=0;i<n;i++){
            const hue=(i/n+0.05)%1;
            this._familyColors[sorted[i]]=new THREE.Color().setHSL(hue,0.9,0.55);
        }
        // Store original baseColor so we can restore
        for(const hub of this.hubs){
            if(!hub._origColor)hub._origColor=hub.baseColor.clone();
            hub.baseColor.copy(this._familyColors[hub.data._family]||hub._origColor);
        }
        btn.textContent='RESET COLORS';
        btn.style.color='#ffab00';btn.style.borderColor='rgba(255,171,0,0.4)';
        btn.style.background='rgba(255,171,0,0.08)';
    }else{
        for(const hub of this.hubs){if(hub._origColor)hub.baseColor.copy(hub._origColor);}
        btn.textContent='COLOR BY CREATOR';
        btn.style.color='rgba(0,212,255,0.6)';btn.style.borderColor='rgba(0,212,255,0.15)';
        btn.style.background='rgba(4,8,16,0.75)';
    }
}

/* ── Creator Filter — isolate one creator's models ────────────────── */
_applyCreatorFilter(creator){
    this._creatorFilter=creator;
    // Find all unique sub-families for this creator (e.g. qwen3, qwen2.5, qwen2)
    const creatorHubs=this.hubs.filter(h=>h.data._family===creator);
    // Group by model base name (strip size/quant suffix)
    const subfams=new Map();
    for(const h of creatorHubs){
        const parts=h.data.id.split(':');
        const base=parts[0]; // e.g. "qwen3", "qwen2.5"
        if(!subfams.has(base))subfams.set(base,[]);
        subfams.get(base).push(h);
    }
    // Assign distinct bright hues to each sub-family
    const bases=[...subfams.keys()].sort();
    const n=Math.max(bases.length,1);
    const subColors={};
    for(let i=0;i<bases.length;i++){
        const hue=(i/n+0.08)%1;
        subColors[bases[i]]=new THREE.Color().setHSL(hue,0.95,0.6);
    }
    // Apply: creator's models get bright sub-family colors, others hidden by animate loop
    for(const hub of this.hubs){
        if(!hub._origColor)hub._origColor=hub.baseColor.clone();
        if(hub.data._family===creator){
            const base=hub.data.id.split(':')[0];
            hub.baseColor.copy(subColors[base]||hub._origColor);
        }
    }
    // Rebuild plasma for just this creator's nodes — shows their coverage gaps
    this._createGapScanner(creatorHubs);
    this._gapWisps.visible=true;this._gapWispsVisible=true;
    // Show a mini legend of sub-families
    let legendEl=document.getElementById('creator-legend');
    if(!legendEl){legendEl=document.createElement('div');legendEl.id='creator-legend';document.body.appendChild(legendEl);}
    legendEl.style.cssText='position:fixed;bottom:60px;right:24px;z-index:7;font-family:Consolas,monospace;font-size:0.55rem;background:rgba(4,8,16,0.85);border:1px solid rgba(255,171,0,0.2);border-radius:5px;padding:8px 12px;pointer-events:none;max-width:200px;';
    let lHtml=`<div style="color:#ffab00;font-weight:700;letter-spacing:0.12em;margin-bottom:4px">${esc(creator).toUpperCase()} MODELS</div>`;
    for(const base of bases){
        const c='#'+subColors[base].getHexString();
        const cnt=subfams.get(base).length;
        lHtml+=`<div style="display:flex;align-items:center;gap:6px;margin:2px 0"><span style="width:8px;height:8px;border-radius:50%;background:${c};display:inline-block;flex-shrink:0"></span><span style="color:${c}">${esc(base)}</span><span style="color:rgba(255,255,255,0.3)">(${cnt})</span></div>`;
    }
    legendEl.innerHTML=lHtml;
}

_clearCreatorFilter(){
    if(!this._creatorFilter)return;
    this._creatorFilter=null;
    // Restore all original colors
    for(const hub of this.hubs){if(hub._origColor)hub.baseColor.copy(hub._origColor);}
    const legendEl=document.getElementById('creator-legend');
    if(legendEl)legendEl.remove();
    // Rebuild plasma for all models and hide it
    this._createGapScanner();
    this._gapWisps.visible=false;this._gapWispsVisible=false;
}

/* ── Model Search ────────────────────────────────────────────────── */
_initSearch(){
    const input=document.getElementById('model-search-input');
    const results=document.getElementById('model-search-results');
    if(!input||!results)return;
    let debounce=null;

    input.addEventListener('input',()=>{
        clearTimeout(debounce);
        debounce=setTimeout(()=>{
            const q=input.value.trim().toLowerCase();
            if(q.length<2){results.style.display='none';results.innerHTML='';return;}
            const matches=this.hubs.filter(h=>h.data.id.toLowerCase().includes(q))
                .sort((a,b)=>{
                    const ai=a.data.id.toLowerCase().indexOf(q),bi=b.data.id.toLowerCase().indexOf(q);
                    return ai!==bi?ai-bi:b.data.avg_score-a.data.avg_score;
                }).slice(0,20);
            if(!matches.length){results.style.display='none';results.innerHTML='';return;}
            results.innerHTML=matches.map(h=>{
                const d=h.data,pct=Math.round(d.avg_score*100);
                const vc=pct>=95?'#00ffcc':pct>=85?'#50ff80':pct>=70?'#ffab00':'#ff1744';
                return `<div class="search-result" data-idx="${h.idx}"><span>${esc(d.id)}</span><span class="sr-score" style="color:${vc}">${pct}%</span></div>`;
            }).join('');
            results.style.display='block';
            results.querySelectorAll('.search-result').forEach(el=>{
                el.addEventListener('click',()=>{
                    const idx=parseInt(el.dataset.idx);
                    const hub=this.hubs.find(h=>h.idx===idx);
                    if(hub){
                        // If in compare mode, complete comparison via search
                        if(this._h2hA&&this._tryCompare(hub.data)){
                            results.style.display='none';input.value='';input.blur();
                            return;
                        }
                        this.selected=hub;this._showInfo(hub.data);this._flyTo(hub.pos);
                        this.controls.autoRotate=false;
                    }
                    results.style.display='none';input.value='';input.blur();
                });
            });
        },150);
    });

    input.addEventListener('focus',()=>{if(input.value.trim().length>=2)input.dispatchEvent(new Event('input'));});
    document.addEventListener('click',e=>{
        if(!input.contains(e.target)&&!results.contains(e.target))results.style.display='none';
    });
}

/* ── Guided Tour ─────────────────────────────────────────────────── */
_initTour(){
    this._tourActive=false;this._tourAbort=false;
    this._tourContinueResolve=null;
    window._fmTour=()=>this._startTour();
    window._fmTourContinue=()=>{if(this._tourContinueResolve){this._tourContinueResolve('continue');this._tourContinueResolve=null;}};
    window._fmTourExit=()=>{this._tourAbort=true;if(this._tourContinueResolve){this._tourContinueResolve('exit');this._tourContinueResolve=null;}};
}

_startTour(){
    if(this._tourActive)return;
    this._tourActive=true;this._tourAbort=false;
    this.controls.autoRotate=false;this.controls.enabled=false;
    document.getElementById('tour-btn').style.display='none';
    const pb=document.getElementById('polarity-btn');if(pb)pb.style.display='none';
    const fb=document.getElementById('family-btn');if(fb)fb.style.display='none';
    const lb=document.getElementById('matrix-leaderboards');if(lb)lb.style.opacity='0';
    const lg=document.getElementById('matrix-legend');if(lg)lg.style.opacity='0';
    const st=document.getElementById('matrix-stats');if(st)st.style.opacity='0';
    const sr=document.getElementById('model-search');if(sr)sr.style.opacity='0';
    this._runTourSequence();
}

_endTour(){
    this._tourActive=false;
    document.getElementById('tour-modal').style.display='none';
    document.getElementById('tour-btn').style.display='block';
    const pb=document.getElementById('polarity-btn');if(pb)pb.style.display='block';
    const fb=document.getElementById('family-btn');if(fb)fb.style.display='block';
    this._hideInfo();this.selected=null;
    this._hideGapView();
    if(this._polarityWorst)this._togglePolarity();
    const lb=document.getElementById('matrix-leaderboards');if(lb)lb.style.opacity='1';
    const lg=document.getElementById('matrix-legend');if(lg)lg.style.opacity='1';
    const st=document.getElementById('matrix-stats');if(st)st.style.opacity='1';
    const sr=document.getElementById('model-search');if(sr)sr.style.opacity='1';
    // Fly back to initial position then re-enable controls
    this.controls.enabled=false;
    const cs=this.camera.position.clone(),ls=this.controls.target.clone();
    const ce=new THREE.Vector3(0,80,110),le=new THREE.Vector3(0,15,0);
    const t0=performance.now();
    const fly=()=>{
        const t=Math.min((performance.now()-t0)/2000,1),e=easeIO(t);
        this.camera.position.lerpVectors(cs,ce,e);
        this.controls.target.lerpVectors(ls,le,e);
        this.controls.update();
        if(t<1)requestAnimationFrame(fly);
        else{this.controls.enabled=true;this.controls.autoRotate=true;}
    };requestAnimationFrame(fly);
}

_tourFly(camEnd,lookEnd,dur){
    return new Promise(resolve=>{
        const cs=this.camera.position.clone(),ls=this.controls.target.clone();
        const ce=new THREE.Vector3(camEnd.x,camEnd.y,camEnd.z);
        const le=new THREE.Vector3(lookEnd.x,lookEnd.y,lookEnd.z);
        const t0=performance.now();
        const fly=()=>{
            if(this._tourAbort){resolve();return;}
            const t=Math.min((performance.now()-t0)/dur,1),e=easeIO(t);
            this.camera.position.lerpVectors(cs,ce,e);
            this.controls.target.lerpVectors(ls,le,e);
            this.controls.update();
            if(t<1)requestAnimationFrame(fly);else resolve();
        };requestAnimationFrame(fly);
    });
}

_tourOrbit(center,radius,yOff,dur,lookY){
    return new Promise(resolve=>{
        const t0=performance.now();
        const startAngle=Math.atan2(this.camera.position.z-center.z,this.camera.position.x-center.x);
        const orbit=()=>{
            if(this._tourAbort){resolve();return;}
            const t=Math.min((performance.now()-t0)/dur,1);
            const a=startAngle+t*Math.PI*0.5;
            this.camera.position.set(center.x+Math.cos(a)*radius,center.y+yOff,center.z+Math.sin(a)*radius);
            this.controls.target.set(center.x,lookY!==undefined?lookY:center.y,center.z);
            this.controls.update();
            if(t<1)requestAnimationFrame(orbit);else resolve();
        };requestAnimationFrame(orbit);
    });
}

_tourModal(html,x,y,btnLabel){
    const modal=document.getElementById('tour-modal');
    const btns=`<div class="tour-btns">
        <button class="tour-continue" onclick="window._fmTourContinue()">${btnLabel||'CONTINUE'}</button>
        <button class="tour-exit" onclick="window._fmTourExit()">EXIT</button></div>`;
    modal.innerHTML=html+btns;
    modal.style.display='block';
    const mw=340,mh=300;
    const px=Math.min(Math.max(20,x),innerWidth-mw-20);
    const py=Math.min(Math.max(80,y),innerHeight-mh-20);
    modal.style.left=px+'px';modal.style.top=py+'px';
    modal.style.animation='none';modal.offsetHeight;modal.style.animation='tourFadeIn 0.6s ease-out';
}

_tourWaitUser(){
    return new Promise(resolve=>{this._tourContinueResolve=resolve;});
}

async _runTourSequence(){
    const modal=document.getElementById('tour-modal');
    const S=8;
    const tag=(n)=>`<div class="tour-step-indicator">Step ${n} / ${S}</div>`;

    // ── 1: Establishing shot ──
    await this._tourFly({x:0,y:80,z:180},{x:0,y:20,z:0},2000);
    if(this._tourAbort){this._endTour();return;}
    this._tourModal(`<h3>The Forge Matrix</h3>
        <div class="tour-sub">Decentralized Model Intelligence Network</div>
        <p>Welcome to a <span class="tour-highlight">real-time 3D visualization</span> of AI model safety and reliability data,
        crowdsourced from Forge users worldwide.</p>
        <p>Every glowing node is a unique model variant that has been stress-tested through Forge's
        <span class="tour-highlight">/break</span> and <span class="tour-highlight">/assure</span> pipelines.</p>
        ${tag(1)}`,innerWidth/2-170,innerHeight/2-120);
    await this._tourWaitUser();

    // ── 2: NC Brain — steep angle, NC visible above modal ──
    if(this._tourAbort){this._endTour();return;}
    modal.style.display='none';
    await this._tourFly({x:18,y:62,z:35},{x:0,y:38,z:0},2500);
    if(this._tourAbort){this._endTour();return;}
    const mob=innerWidth<768;
    this._tourModal(`<h3>Forge Neural Cortex</h3>
        <div class="tour-sub">The Brain of the System</div>
        <p>The <span class="tour-highlight">Neural Cortex</span> is Forge's AI engine — it designs adversarial scenarios,
        analyzes behavioral fingerprints, and detects model drift in real-time.</p>
        <p>The pulsing waves represent its <span class="tour-highlight">six cognitive states</span>:
        idle, thinking, tool execution, analysis, pass evaluation, and synthesis.</p>
        <p>The six orbital lobes map to the six evaluation sectors below.</p>
        ${tag(2)}`,mob?innerWidth/2-170:innerWidth-380,mob?innerHeight*0.55:100);
    await this._tourWaitUser();

    // ── 3: Crucible — steep angle, Crucible visible above modal ──
    if(this._tourAbort){this._endTour();return;}
    modal.style.display='none';
    await this._tourFly({x:16,y:44,z:32},{x:0,y:20,z:0},2000);
    await this._tourOrbit({x:0,y:20,z:0},36,24,3000,20);
    if(this._tourAbort){this._endTour();return;}
    this._tourModal(`<h3>Crucible</h3>
        <div class="tour-sub">Where Models Are Forged</div>
        <p>The <span class="tour-highlight">Crucible</span> is the assurance engine — every model must pass through
        its fire to earn a trust score.</p>
        <p>13 scenario categories, from safety probes to adversarial injections,
        are run against each model. The results feed the <span class="tour-highlight">aurora shield dome</span>
        below — a visual representation of the protection Crucible provides to the ecosystem.</p>
        ${tag(3)}`,mob?innerWidth/2-170:30,mob?innerHeight*0.55:innerHeight/2-100);
    await this._tourWaitUser();

    // ── 4: Model field + polarity switcher ──
    if(this._tourAbort){this._endTour();return;}
    modal.style.display='none';
    await this._tourFly(mob?{x:10,y:70,z:80}:{x:30,y:12,z:35},mob?{x:0,y:0,z:0}:{x:0,y:2,z:0},2500);
    if(this._tourAbort){this._endTour();return;}
    this._tourModal(`<h3>The Model Field</h3>
        <div class="tour-sub">6 Sectors \u00b7 4 Tiers \u00b7 Thousands of Nodes</div>
        <p>Models are arranged in <span class="tour-highlight">6 sectors</span>:
        Safety, Reliability, Adversarial, Tool Discipline, Exfil Guard, and Context Integrity.</p>
        <p>Each model is placed in the sector where it scored <span class="tour-highlight">highest</span>.
        Distance from center = quality: <span class="tour-highlight">elite models orbit the core</span>,
        weaker ones drift to the outer rings.</p>
        <p>Node size scales with test run count. Use the <span class="tour-highlight">polarity switcher</span>
        to flip nodes to their <span class="tour-highlight">weakest</span> sector — instantly revealing where each model struggles most.</p>
        ${tag(4)}`,mob?10:30,mob?10:innerHeight/2-80);
    await this._tourWaitUser();

    // ── 5: Mind the gap — birds-eye, matrix pushed to bottom of screen on mobile ──
    if(this._tourAbort){this._endTour();return;}
    modal.style.display='none';
    this._showGapView(true);
    // On mobile: pan both camera+target in -Z so matrix appears in bottom half of screen
    await this._tourFly(mob?{x:0,y:170,z:-20}:{x:0,y:120,z:8},mob?{x:0,y:0,z:-23}:{x:0,y:0,z:0},3000);
    if(this._tourAbort){this._hideGapView();this._endTour();return;}
    this._tourModal(`<h3>Mind the Gap</h3>
        <div class="tour-sub">Void Density Analysis</div>
        <p>The <span class="tour-highlight">plasma</span> fills the empty space between inner-ring models
        (75%+ score). The <span style="color:#ff2200;font-weight:700">redder</span> and brighter the plasma,
        the <span class="tour-highlight">larger the void</span> — fewer models competing in that region.</p>
        <p>Sectors marked <span style="color:#ff4422;font-weight:700">VOID DETECTED</span> have the largest
        empty stretches — the hardest categories to crack at the top level.</p>
        <p>Only the inner 3/4 of the field matters. Outer-ring gaps just mean most models score better.</p>
        ${tag(5)}`,mob?10:innerWidth-380,mob?10:60);
    await this._tourWaitUser();
    this._hideGapView();

    // ── 6: Polarity switch — same birds-eye, matrix in bottom half on mobile ──
    if(this._tourAbort){this._endTour();return;}
    modal.style.display='none';
    this._togglePolarity(); // switch to weakest
    await this._tourFly(mob?{x:0,y:170,z:-20}:{x:0,y:120,z:8},mob?{x:0,y:0,z:-23}:{x:0,y:0,z:0},2000);
    if(this._tourAbort){this._endTour();return;}
    this._tourModal(`<h3>Polarity Reversed</h3>
        <div class="tour-sub">Showing Weakest Sectors</div>
        <p>Every model just moved to the sector where it scored <span class="tour-highlight">lowest</span>.
        Watch the NC pulse cascade flow down through the field.</p>
        <p><span class="tour-highlight">Crowded sectors = common weaknesses</span>.
        Where nodes pile up, that's where models fail the most.
        Sparse sectors mean few models struggle there.</p>
        <p><span class="tour-highlight">Gold-glowing nodes</span> barely moved — the most
        balanced models. <span style="color:#ff6b6b">Red-tinted nodes</span> moved farthest — specialized,
        great at one thing but weak at another.</p>
        ${tag(6)}`,mob?10:innerWidth-380,mob?10:60);
    await this._tourWaitUser();
    this._togglePolarity(); // switch back to strongest

    // ── 7: Top node deep-dive ──
    if(this._tourAbort){this._endTour();return;}
    modal.style.display='none';
    const topHub=this.hubs.slice().sort((a,b)=>b.data.avg_score-a.data.avg_score)[0];
    if(topHub){
        const hp=topHub.pos;
        await this._tourFly({x:hp.x+8,y:hp.y+3,z:hp.z+8},{x:hp.x,y:hp.y,z:hp.z},2000);
        if(this._tourAbort){this._endTour();return;}
        this.selected=topHub;this._showInfo(topHub.data);
        const infoPanel=document.getElementById('matrix-info');
        if(mob&&infoPanel){
            infoPanel.style.top='50%';infoPanel.style.maxHeight='50vh';
            // Add pulsing border to Load Detail button + scroll arrow
            const ldBtn=document.getElementById('mi-load-detail');
            if(ldBtn){ldBtn.style.cssText+=';border:2px solid #ffab00;border-radius:4px;padding:6px;animation:tourPulseBtn 1.2s ease-in-out infinite;';}
            // Inject scroll arrow
            const arrow=document.createElement('div');arrow.id='tour-scroll-arrow';
            arrow.innerHTML='<div style="text-align:center;color:#ffab00;font-size:1.8rem;animation:tourBounceDown 1s ease-in-out infinite;">&#8595;</div><div style="text-align:center;color:rgba(255,171,0,0.7);font-size:0.55rem;font-family:Consolas,monospace;letter-spacing:0.1em;">SCROLL FOR MORE</div>';
            arrow.style.cssText='position:fixed;left:50%;transform:translateX(-50%);top:calc(50% + 50px);z-index:16;pointer-events:none;';
            document.body.appendChild(arrow);
        }
        this._tourModal(`<h3>${topHub.data.id}</h3>
            <div class="tour-sub">Model Deep-Dive</div>
            <p>Double-clicking any node opens its <span class="tour-highlight">detail panel</span> — scores across
            all six categories, score distribution histogram, recent run history, and trend data.</p>
            <p>For models with enough runs, you'll also see the <span class="tour-highlight">Behavioral Fingerprint</span> —
            30 probes that characterize how the model thinks, where it excels, and where it fails.</p>
            ${tag(7)}`,mob?10:30,mob?10:innerHeight/2-100);
        await this._tourWaitUser();
        // Restore panel position + remove arrow
        if(mob&&infoPanel){infoPanel.style.top='';infoPanel.style.maxHeight='';
            const ldBtn=document.getElementById('mi-load-detail');if(ldBtn){ldBtn.style.animation='';ldBtn.style.border='';}
            const arrow=document.getElementById('tour-scroll-arrow');if(arrow)arrow.remove();}
    }

    // ── 8: Finale ──
    if(this._tourAbort){this._endTour();return;}
    modal.style.display='none';this._hideInfo();this.selected=null;
    await this._tourFly({x:0,y:80,z:110},{x:0,y:15,z:0},3000);
    if(this._tourAbort){this._endTour();return;}
    this._tourModal(`<h3>Explore the Matrix</h3>
        <div class="tour-sub">Your Turn</div>
        <p><span class="tour-highlight">Orbit</span> — click and drag to rotate the scene</p>
        <p><span class="tour-highlight">Zoom</span> — scroll wheel to dive in or pull back</p>
        <p><span class="tour-highlight">Inspect</span> — double-click any node to see its full report</p>
        <p>Run <span class="tour-highlight">forge /break --share</span> to add your own model data to the Matrix.</p>
        ${tag(8)}`,innerWidth/2-170,innerHeight/2-100,'FINISH');
    await this._tourWaitUser();

    this._endTour();
}

/* ── Interaction ─────────────────────────────────────────────────── */
_setupInput(){const cv=this.renderer.domElement;cv.addEventListener('pointermove',e=>this._onMove(e));cv.addEventListener('dblclick',e=>this._onClick(e));
    cv.addEventListener('touchend',()=>{const tip=document.getElementById('matrix-tooltip');if(tip)tip.style.display='none';this.hovered=null;cv.style.cursor='default';});
    cv.addEventListener('touchcancel',()=>{const tip=document.getElementById('matrix-tooltip');if(tip)tip.style.display='none';this.hovered=null;});}
_pickHub(mx,my){const projected=this._v3,cands=[],cf=this._creatorFilter;
    for(const hub of this.hubs){
        if(cf&&hub.data._family!==cf)continue; // skip hidden nodes
        projected.copy(hub.pos).project(this.camera);if(projected.z>1)continue;
        const sx=(projected.x*0.5+0.5)*innerWidth,sy=(-projected.y*0.5+0.5)*innerHeight;
        const sd=Math.sqrt((sx-mx)**2+(sy-my)**2);
        if(sd<30)cands.push({hub,screenDist:sd});}
    if(!cands.length)return null;
    cands.sort((a,b)=>a.screenDist-b.screenDist);
    return cands[0].hub;}
_onMove(e){const tip=document.getElementById('matrix-tooltip'),cv=this.renderer.domElement;
    if(this._tourActive){tip.style.display='none';return;}
    const best=this._pickHub(e.clientX,e.clientY);
    if(best){cv.style.cursor='pointer';const d=best.data;
        tip.textContent=`${d.id}  ${Math.round(d.avg_score*100)}%  (${fmtN(d.run_count)} runs)`;
        tip.style.cssText=`display:block;left:${e.clientX+14}px;top:${e.clientY-10}px`;this.hovered=best;
    }else{cv.style.cursor='default';tip.style.display='none';this.hovered=null;}}
_onClick(e){const best=this._pickHub(e.clientX,e.clientY),panel=document.getElementById('matrix-info');
    if(best){
        // If in compare mode, complete the comparison instead of opening info
        if(this._h2hA&&this._tryCompare(best.data))return;
        this.selected=best;this._showInfo(best.data);this._flyTo(best.pos);this.controls.autoRotate=false;
    }
    else if(!panel.classList.contains('open')||!(e.clientX>=panel.getBoundingClientRect().left)){
        this.selected=null;this._hideInfo();this.controls.autoRotate=true;}}
_flyTo(tgt){if(this._flying)return;const cs=this.camera.position.clone();
    const dir=cs.clone().sub(tgt).normalize();
    const ce=tgt.clone().add(dir.multiplyScalar(8)).add(new THREE.Vector3(0,2,0));
    const ls=this.controls.target.clone(),le=tgt.clone();
    this._flying=true;this.controls.enabled=false;const t0=performance.now();
    const fly=()=>{const t=Math.min((performance.now()-t0)/1200,1),e=easeIO(t);
        this.camera.position.lerpVectors(cs,ce,e);this.controls.target.lerpVectors(ls,le,e);this.controls.update();
        if(t<1)requestAnimationFrame(fly);else{this._flying=false;this.controls.enabled=true;}};requestAnimationFrame(fly);}

/* ── Info panel ───────────────────────────────────────────────────── */
_showInfo(m){const panel=document.getElementById('matrix-info');const pct=Math.round(m.avg_score*100);
    const vc=pct>=95?'#50ff80':pct>=75?'#ffab00':'#ff1744';
    const verdict=pct>=95?'ELITE':pct>=85?'STRONG':pct>=70?'MODERATE':'WEAK';
    const stabK=['safety','reliability','adversarial','tool_misuse','context_integrity','exfiltration'];
    const stabL=['Safety','Reason','Policy','Tools','Context','Exfil'];let bars='';
    for(let i=0;i<stabK.length;i++){const v=Math.round((m.categories?.[stabK[i]]||0)*100),hue=(m.categories?.[stabK[i]]||0)*130;
        bars+=`<div class="mi-cat"><span class="mi-cat-name">${stabL[i]}</span><div class="mi-bar"><div class="mi-bar-fill" style="width:${v}%;background:hsl(${hue},70%,45%)"></div></div><span class="mi-cat-pct">${v}%</span></div>`;}
    const tp=Math.round((m.trend||0)*100);const trend=tp?`<span style="color:${tp>0?'#50ff80':'#ff1744'};font-size:0.6rem">${tp>0?'+':''}${tp}%</span>`:'';
    let runs='';for(const r of(m.recent_runs||[]).slice(-3).reverse()){
        const b=r.type==='assure'?'<span style="color:#bc8cff">A</span>':'<span style="color:#58a6ff">B</span>';
        runs+=`<span class="mi-run">${b}${Math.round(r.score*100)}%</span> `;}
    const creator=family(m.id);
    const isFiltered=this._creatorFilter===creator;
    const creatorCount=this.hubs.filter(h=>h.data._family===creator).length;
    panel.innerHTML=`<div class="mi-close" id="mi-close-btn">&times;</div>
        <h3>${esc(m.id)}</h3><div class="mi-score">${pct}%</div>
        <div style="font-size:0.6rem;color:${vc};font-weight:600;margin-bottom:3px">${verdict} ${trend}</div>
        <div class="mi-meta">${fmtN(m.run_count)} runs | ${fmtN(m.unique_users||0)} users</div>
        <div style="display:flex;gap:4px;margin:6px 0">
        <div id="mi-creator-btn" style="flex:1;cursor:pointer;padding:5px 8px;border-radius:4px;font-size:0.55rem;letter-spacing:0.1em;text-transform:uppercase;text-align:center;transition:all 0.3s;pointer-events:auto;font-weight:700;${isFiltered?'background:rgba(255,171,0,0.12);border:1px solid rgba(255,171,0,0.4);color:#ffab00':'background:rgba(0,212,255,0.08);border:1px solid rgba(0,212,255,0.25);color:rgba(120,220,255,0.85)'}">${isFiltered?'SHOW ALL':'ISOLATE '+esc(creator).toUpperCase()}</div>
        <div id="mi-compare-btn" style="cursor:pointer;padding:5px 8px;border-radius:4px;font-size:0.55rem;letter-spacing:0.1em;text-transform:uppercase;text-align:center;transition:all 0.3s;pointer-events:auto;font-weight:700;background:rgba(0,212,255,0.08);border:1px solid rgba(0,212,255,0.25);color:rgba(120,220,255,0.85)">${this._h2hA?'CANCEL':'COMPARE'}</div>
        <div id="mi-share-btn" style="cursor:pointer;padding:5px 8px;border-radius:4px;font-size:0.55rem;letter-spacing:0.1em;text-transform:uppercase;text-align:center;transition:all 0.3s;pointer-events:auto;font-weight:700;background:rgba(0,212,255,0.08);border:1px solid rgba(0,212,255,0.25);color:rgba(120,220,255,0.85)">SHARE</div>
        </div>
        <div class="mi-section">Stability</div>${bars}
        <div class="mi-section">Recent</div>
        <div style="font-family:Consolas;font-size:0.6rem;color:rgba(176,190,197,0.5)">${runs||'--'}</div>
        <div class="mi-section" style="cursor:pointer;color:rgba(0,212,255,0.5)" id="mi-load-detail">Load Detail</div>
        <div id="mi-detail-area"></div>`;
    panel.classList.add('open');
    // On mobile, hide compass when info panel is open
    if(innerWidth<768){const comp=document.getElementById('matrix-compass');if(comp)comp.style.display='none';}
    document.getElementById('mi-close-btn').onclick=()=>{this._clearCreatorFilter();this._hideInfo();this.selected=null;this.controls.autoRotate=true;};
    document.getElementById('mi-creator-btn').onclick=()=>{
        if(this._creatorFilter===creator)this._clearCreatorFilter();
        else this._applyCreatorFilter(creator);
        this._showInfo(m); // refresh panel to update button state
    };
    const db=document.getElementById('mi-load-detail');if(db)db.onclick=()=>this._loadDetail(m.id);
    const sb=document.getElementById('mi-share-btn');if(sb)sb.onclick=()=>{
        const url=this._getShareUrl({model:m.id});
        navigator.clipboard.writeText(url).then(()=>{sb.textContent='COPIED';setTimeout(()=>sb.textContent='SHARE',1500);});
    };}

async _loadDetail(modelId){const area=document.getElementById('mi-detail-area');if(!area)return;
    area.innerHTML='<div class="mi-dim">Loading...</div>';
    const detail=this.isDemo?demoDetail(modelId):await(async()=>{
        try{const r=await fetch(`matrix.php?detail=${encodeURIComponent(modelId)}`);
            const d=await r.json();return d.error?null:d;}catch(_){return null;}})();
    if(!detail){area.innerHTML='<div class="mi-dim">No detail</div>';return;}
    let html='';
    if(detail.calibration_score>=0)html+=`<div style="font-size:0.65rem;color:rgba(0,212,255,0.5);margin:4px 0">Calibration: <b>${Math.round(detail.calibration_score*100)}%</b></div>`;
    if(detail.fingerprint&&Object.keys(detail.fingerprint).length){
        html+='<div class="mi-section">Behavioral Fingerprint</div><div class="mi-fp-scroll">';
        const sorted=Object.entries(detail.fingerprint).sort((a,b)=>a[1]-b[1]);
        for(const[probe,score] of sorted){const p=Math.round(score*100),hue=score*130;
            html+=`<div class="mi-cat"><span class="mi-cat-name" style="width:110px;font-size:0.55rem">${probe}</span><div class="mi-bar"><div class="mi-bar-fill" style="width:${p}%;background:hsl(${hue},70%,45%)"></div></div><span class="mi-cat-pct">${p}%</span></div>`;}
        html+='</div>';}
    if(detail.runs&&detail.runs.length){html+='<div class="mi-section">History</div>';
        for(const r of detail.runs.slice(0,15)){const d=r.at?new Date(r.at*1000).toLocaleDateString():'--';
            const s=Math.round(r.score*100);
            const b=r.type==='assure'?'<span style="color:#bc8cff">A</span>':'<span style="color:#58a6ff">B</span>';
            const lat=r.latency_ms?`<span style="color:rgba(176,190,197,0.25)">${r.latency_ms}ms</span>`:'';
            html+=`<div class="mi-run">${b} ${s}% ${d} ${lat}</div>`;}}
    area.innerHTML=html;}
_hideInfo(){this._clearCreatorFilter();document.getElementById('matrix-info').classList.remove('open');
    // Restore compass on mobile
    if(innerWidth<768){const comp=document.getElementById('matrix-compass');if(comp)comp.style.display='';}
}
_updateStats(data){const models=data.models||[];
    const runs=data.total_runs||models.reduce((s,m)=>s+m.run_count,0);
    const users=models.reduce((s,m)=>s+(m.unique_users||0),0);
    document.getElementById('stat-models').textContent=fmtN(models.length);
    document.getElementById('stat-runs').textContent=fmtN(runs);
    document.getElementById('stat-nodes').textContent=fmtN(users||(models.length+runs));}

/* ── Leaderboards ────────────────────────────────────────────────── */
_buildLeaderboards(data){const models=data.models||[];
    const el=document.getElementById('matrix-leaderboards');if(!el)return;let html='';
    html+=`<div class="lb-header-bar" style="display:flex;justify-content:space-between;align-items:center;width:100%;pointer-events:auto;margin-bottom:4px">`;
    html+=`<div class="legend-header" style="color:rgba(0,212,255,0.35);font-size:0.5rem;letter-spacing:0.15em;text-transform:uppercase;margin:0">SECTOR LEADERBOARDS</div>`;
    html+=`<div class="lb-close-btn" style="cursor:pointer;color:rgba(255,60,60,0.7);font-size:1.4rem;font-weight:700;line-height:1;padding:0 4px">&times;</div></div>`;
    html+=`<div class="panel-body" style="display:flex;flex-wrap:wrap;gap:6px;width:100%">`;
    for(const s of SECTORS){
        const above0=[...models].filter(m=>(m.categories?.[s.key]||0)>0)
            .sort((a,b)=>(b.categories?.[s.key]||0)-(a.categories?.[s.key]||0));
        const sorted=above0.length>=3?above0.slice(0,3)
            :[...models].filter(m=>m.categories?.hasOwnProperty(s.key))
            .sort((a,b)=>(b.categories?.[s.key]||0)-(a.categories?.[s.key]||0)).slice(0,3);
        const c='#'+new THREE.Color(s.color).getHexString();
        html+=`<div class="lb-sector"><div class="lb-title" style="color:${c}">${s.label}</div>`;
        for(let i=0;i<sorted.length;i++){const m=sorted[i],pct=Math.round((m.categories?.[s.key]||0)*100);
            html+=`<div class="lb-row"><span class="lb-rank">#${i+1}</span><span class="lb-name">${esc(m.id)}</span><span class="lb-pct" style="color:${c}">${pct}%</span></div>`;}
        html+='</div>';}
    html+='</div>';
    el.innerHTML=html;
    const cb=el.querySelector('.lb-close-btn');if(cb)cb.onclick=()=>window._togglePanel(el);}

/* ── Shareable Links ─────────────────────────────────────────────── */
_handleUrlParams(params){
    const modelParam=params.get('model');
    const sectorParam=params.get('sector');
    const creatorParam=params.get('creator');
    // Auto-select a model
    if(modelParam){
        const hub=this.hubs.find(h=>h.data.id.toLowerCase()===modelParam.toLowerCase());
        if(hub){setTimeout(()=>{this.selected=hub;this._showInfo(hub.data);this._flyTo(hub.pos);this.controls.autoRotate=false;},600);}
    }
    // Auto-zoom to a sector
    if(sectorParam){
        const sec=SECTORS.find(s=>s.key===sectorParam);
        if(sec){setTimeout(()=>this._drilldownSector(sec),800);}
    }
    // Auto-isolate a creator
    if(creatorParam){
        const match=this.hubs.find(h=>h.data._family===creatorParam.toLowerCase());
        if(match){setTimeout(()=>this._applyCreatorFilter(creatorParam.toLowerCase()),600);}
    }
}

_getShareUrl(opts){
    const base=location.origin+location.pathname;
    const u=new URL(base);
    if(opts.model)u.searchParams.set('model',opts.model);
    if(opts.sector)u.searchParams.set('sector',opts.sector);
    if(opts.creator)u.searchParams.set('creator',opts.creator);
    if(this.isDemo)u.searchParams.set('demo','1');
    return u.toString();
}

/* ── Data Source Toggle ──────────────────────────────────────────── */
_createDataSrcBtn(){
    const btn=document.createElement('div');
    btn.id='datasrc-btn';
    btn.textContent=this.isDemo?'DATA: DEMO':'DATA: LIVE';
    btn.style.cssText='position:fixed;top:100px;right:220px;z-index:6;cursor:pointer;font-family:Consolas,monospace;font-size:0.6rem;letter-spacing:0.1em;color:rgba(255,200,100,0.8);background:rgba(4,8,16,0.75);border:1px solid rgba(255,171,0,0.25);border-radius:4px;padding:6px 12px;text-transform:uppercase;pointer-events:auto;transition:all 0.3s;font-weight:600;text-shadow:0 0 6px rgba(255,171,0,0.15);';
    btn.addEventListener('mouseenter',()=>{btn.style.color='#ffab00';btn.style.borderColor='rgba(255,171,0,0.4)';});
    btn.addEventListener('mouseleave',()=>{btn.style.color='rgba(255,171,0,0.6)';btn.style.borderColor='rgba(255,171,0,0.15)';});
    btn.addEventListener('click',()=>{
        const isDemo=new URLSearchParams(location.search).get('demo')==='1';
        const u=new URL(location.href);
        if(isDemo)u.searchParams.delete('demo');
        else u.searchParams.set('demo','1');
        location.href=u.toString();
    });
    document.body.appendChild(btn);
}

/* ── Heatmap Overlay — ground-plane density ──────────────────────── */
_createHeatmapBtn(){
    const btn=document.createElement('div');
    btn.id='heatmap-btn';
    btn.textContent='HEATMAP';
    btn.style.cssText='position:fixed;top:100px;right:24px;z-index:6;cursor:pointer;font-family:Consolas,monospace;font-size:0.6rem;letter-spacing:0.1em;color:rgba(120,220,255,0.8);background:rgba(4,8,16,0.75);border:1px solid rgba(0,212,255,0.25);border-radius:4px;padding:6px 12px;text-transform:uppercase;pointer-events:auto;transition:all 0.3s;font-weight:600;text-shadow:0 0 6px rgba(0,180,255,0.15);';
    btn.addEventListener('mouseenter',()=>{btn.style.color='#00d4ff';btn.style.borderColor='rgba(0,212,255,0.4)';});
    btn.addEventListener('mouseleave',()=>{if(!this._heatmapOn){btn.style.color='rgba(0,212,255,0.6)';btn.style.borderColor='rgba(0,212,255,0.15)';}});
    btn.addEventListener('click',()=>this._toggleHeatmap(btn));
    document.body.appendChild(btn);
}

_toggleHeatmap(btn){
    this._heatmapOn=!this._heatmapOn;
    if(this._heatmapOn){
        if(!this._heatmapMesh)this._buildHeatmap();
        this._heatmapMesh.visible=true;
        btn.textContent='HEATMAP ON';btn.style.color='#ffab00';btn.style.borderColor='rgba(255,171,0,0.4)';
        btn.style.background='rgba(255,171,0,0.08)';
    }else{
        if(this._heatmapMesh)this._heatmapMesh.visible=false;
        btn.textContent='HEATMAP';btn.style.color='rgba(0,212,255,0.6)';btn.style.borderColor='rgba(0,212,255,0.15)';
        btn.style.background='rgba(4,8,16,0.75)';
    }
}

_buildHeatmap(){
    const R=this.worldR,res=64;
    const density=new Float32Array(res*res);
    const step=R*2.2/res;
    // Accumulate gaussian splats for each hub
    for(const hub of this.hubs){
        const gx=Math.floor((hub.pos.x+R*1.1)/step);
        const gz=Math.floor((hub.pos.z+R*1.1)/step);
        const sigma=3;
        for(let dx=-sigma;dx<=sigma;dx++)for(let dz=-sigma;dz<=sigma;dz++){
            const cx=gx+dx,cz=gz+dz;
            if(cx<0||cx>=res||cz<0||cz>=res)continue;
            const dist2=dx*dx+dz*dz;
            density[cz*res+cx]+=Math.exp(-dist2/4);
        }
    }
    const maxD=Math.max(1,...density);
    // Build texture from density
    const texData=new Uint8Array(res*res*4);
    for(let i=0;i<res*res;i++){
        const v=density[i]/maxD;
        // cold(blue) → warm(green) → hot(red)
        let r,g,b;
        if(v<0.33){r=0;g=Math.floor(v/0.33*255);b=Math.floor((1-v/0.33)*180);}
        else if(v<0.66){const t=(v-0.33)/0.33;r=Math.floor(t*255);g=255;b=0;}
        else{const t=(v-0.66)/0.34;r=255;g=Math.floor((1-t)*255);b=0;}
        texData[i*4]=r;texData[i*4+1]=g;texData[i*4+2]=b;
        texData[i*4+3]=Math.floor(v*120);
    }
    const tex=new THREE.DataTexture(texData,res,res,THREE.RGBAFormat);
    tex.needsUpdate=true;tex.minFilter=THREE.LinearFilter;tex.magFilter=THREE.LinearFilter;
    const geo=new THREE.PlaneGeometry(R*2.2,R*2.2);
    this._heatmapMat=new THREE.MeshBasicMaterial({map:tex,transparent:true,opacity:0.6,
        blending:THREE.AdditiveBlending,depthWrite:false,side:THREE.DoubleSide});
    this._heatmapMesh=new THREE.Mesh(geo,this._heatmapMat);
    this._heatmapMesh.rotation.x=-Math.PI/2;this._heatmapMesh.position.y=-8;
    this._heatmapMesh.visible=false;
    this.scene.add(this._heatmapMesh);
}

/* ── Head-to-Head Compare ────────────────────────────────────────── */
_initH2H(){
    document.addEventListener('click',e=>{
        if(e.target.id==='mi-compare-btn'){
            if(!this.selected)return;
            if(this._h2hA){
                // Already have A selected — clicking again clears compare mode
                this._h2hA=null;
                e.target.textContent='COMPARE';e.target.style.color='rgba(0,212,255,0.6)';
                e.target.style.background='rgba(0,212,255,0.06)';e.target.style.borderColor='rgba(0,212,255,0.15)';
                return;
            }
            this._h2hA=this.selected.data;
            e.target.textContent='CANCEL';e.target.style.color='#ff6b6b';
            e.target.style.background='rgba(255,60,60,0.08)';e.target.style.borderColor='rgba(255,60,60,0.3)';
        }
        if(e.target.classList.contains('h2h-close')){
            document.getElementById('h2h-overlay').style.display='none';
            this._h2hA=null;this._h2hB=null;
        }
    });
}

_tryCompare(hubData){
    if(!this._h2hA)return false;
    if(this._h2hA.id===hubData.id)return false;
    this._h2hB=hubData;
    this._showH2H();
    return true;
}

_showH2H(){
    const overlay=document.getElementById('h2h-overlay');if(!overlay)return;
    const a=this._h2hA,b=this._h2hB;
    if(!a||!b)return;

    // Radar chart (canvas)
    let html=`<div class="h2h-close">&times;</div><h3>Head-to-Head</h3>`;
    html+=`<div style="display:flex;justify-content:space-between;margin-bottom:12px">`;
    html+=`<span class="h2h-name" style="color:#00d4ff">${esc(a.id)}</span>`;
    html+=`<span class="h2h-name" style="color:#ff6b6b">${esc(b.id)}</span></div>`;
    html+=`<div class="h2h-radar-wrap"><canvas id="h2h-radar" width="280" height="280"></canvas></div>`;

    // Category comparison bars
    for(const s of SECTORS){
        const va=Math.round((a.categories?.[s.key]||0)*100);
        const vb=Math.round((b.categories?.[s.key]||0)*100);
        const ca=va>=vb?'#00d4ff':'rgba(0,212,255,0.4)';
        const cb=vb>=va?'#ff6b6b':'rgba(255,107,107,0.4)';
        html+=`<div class="h2h-row"><span class="h2h-label">${s.label.slice(0,6)}</span>`;
        html+=`<span class="h2h-pct" style="color:${ca}">${va}%</span>`;
        html+=`<div class="h2h-bar-wrap"><div class="h2h-bar" style="width:${va}%;background:${ca}"></div></div>`;
        html+=`<div class="h2h-bar-wrap" style="direction:rtl"><div class="h2h-bar" style="width:${vb}%;background:${cb}"></div></div>`;
        html+=`<span class="h2h-pct" style="color:${cb}">${vb}%</span></div>`;
    }

    // Overall
    const oa=Math.round(a.avg_score*100),ob=Math.round(b.avg_score*100);
    html+=`<div style="display:flex;justify-content:space-between;margin-top:12px;font-family:Consolas,monospace;font-size:0.8rem">`;
    html+=`<span style="color:#00d4ff;font-weight:700">${oa}% overall</span>`;
    html+=`<span style="color:#ff6b6b;font-weight:700">${ob}% overall</span></div>`;

    overlay.innerHTML=html;
    overlay.style.display='block';

    // Draw radar
    this._drawRadar(a,b);
    this._h2hA=null;this._h2hB=null;
}

_drawRadar(a,b){
    const canvas=document.getElementById('h2h-radar');if(!canvas)return;
    const ctx=canvas.getContext('2d'),cx=140,cy=140,R=110;
    ctx.clearRect(0,0,280,280);
    // Grid
    for(let r=0.25;r<=1;r+=0.25){
        ctx.beginPath();
        for(let i=0;i<=6;i++){
            const ang=i*Math.PI/3-Math.PI/2;
            const x=cx+Math.cos(ang)*R*r,y=cy+Math.sin(ang)*R*r;
            i===0?ctx.moveTo(x,y):ctx.lineTo(x,y);
        }
        ctx.strokeStyle='rgba(0,212,255,0.1)';ctx.lineWidth=1;ctx.stroke();
    }
    // Axes + labels
    for(let i=0;i<6;i++){
        const ang=i*Math.PI/3-Math.PI/2;
        ctx.beginPath();ctx.moveTo(cx,cy);ctx.lineTo(cx+Math.cos(ang)*R,cy+Math.sin(ang)*R);
        ctx.strokeStyle='rgba(0,212,255,0.12)';ctx.stroke();
        ctx.font='bold 8px Consolas';ctx.fillStyle='rgba(176,190,197,0.5)';ctx.textAlign='center';ctx.textBaseline='middle';
        const lbl=SECTORS[i].key==='context_integrity'?'CTX':SECTORS[i].key==='tool_misuse'?'TOOL':SECTORS[i].key==='exfiltration'?'EXFIL':SECTORS[i].label.slice(0,5);
        ctx.fillText(lbl,cx+Math.cos(ang)*(R+14),cy+Math.sin(ang)*(R+14));
    }
    // Model A polygon
    const drawPoly=(model,color,alpha)=>{
        ctx.beginPath();
        for(let i=0;i<=6;i++){
            const idx=i%6,ang=idx*Math.PI/3-Math.PI/2;
            const v=model.categories?.[SECTORS[idx].key]||0;
            const x=cx+Math.cos(ang)*R*v,y=cy+Math.sin(ang)*R*v;
            i===0?ctx.moveTo(x,y):ctx.lineTo(x,y);
        }
        ctx.closePath();ctx.fillStyle=color.replace('1)',alpha+')');ctx.fill();
        ctx.strokeStyle=color;ctx.lineWidth=2;ctx.stroke();
    };
    drawPoly(a,'rgba(0,212,255,1)',0.12);
    drawPoly(b,'rgba(255,107,107,1)',0.12);
}

/* ── Sector Drilldown ────────────────────────────────────────────── */
_initSectorDrilldown(){
    // Click on sector label sprites would be hard; instead use leaderboard sector title clicks
    document.addEventListener('click',e=>{
        const sectorEl=e.target.closest('.lb-title');
        if(sectorEl){
            const label=sectorEl.textContent.trim();
            const sec=SECTORS.find(s=>s.label===label);
            if(sec)this._drilldownSector(sec);
        }
        if(e.target.classList.contains('sd-close')){
            document.getElementById('sector-drilldown').style.display='none';
        }
        const sdRow=e.target.closest('.sd-row');
        if(sdRow&&sdRow.dataset.model){
            const hub=this.hubs.find(h=>h.data.id===sdRow.dataset.model);
            if(hub){this.selected=hub;this._showInfo(hub.data);this._flyTo(hub.pos);this.controls.autoRotate=false;
                document.getElementById('sector-drilldown').style.display='none';}
        }
    });
}

_drilldownSector(sec){
    const overlay=document.getElementById('sector-drilldown');if(!overlay)return;
    const above0=(this._dataModels||[]).filter(m=>(m.categories?.[sec.key]||0)>0)
        .sort((a,b)=>(b.categories?.[sec.key]||0)-(a.categories?.[sec.key]||0));
    const models=above0.length>=3?above0.slice(0,50)
        :(this._dataModels||[]).filter(m=>m.categories?.hasOwnProperty(sec.key))
        .sort((a,b)=>(b.categories?.[sec.key]||0)-(a.categories?.[sec.key]||0)).slice(0,50);
    const c='#'+new THREE.Color(sec.color).getHexString();
    let html=`<div class="sd-close">&times;</div><h3 style="color:${c}">${sec.label} Drilldown</h3>`;
    html+=`<div style="font-size:0.6rem;color:rgba(176,190,197,0.4);margin-bottom:10px">${models.length} models ranked by ${sec.label} score</div>`;
    for(let i=0;i<models.length;i++){
        const m=models[i],pct=Math.round((m.categories?.[sec.key]||0)*100);
        const sc=pct>=95?'#00ffcc':pct>=85?'#50ff80':pct>=70?'#ffab00':'#ff1744';
        html+=`<div class="sd-row" data-model="${esc(m.id)}"><span class="sd-rank">#${i+1}</span><span class="sd-name">${esc(m.id)}</span><span class="sd-score" style="color:${sc}">${pct}%</span></div>`;
    }
    // Share link
    html+=`<div style="margin-top:12px;text-align:center"><span id="sd-share-link" style="font-size:0.55rem;color:rgba(176,190,197,0.5);cursor:pointer;text-decoration:underline">Share this sector</span></div>`;
    overlay.innerHTML=html;overlay.style.display='block';
    const sdShare=document.getElementById('sd-share-link');
    if(sdShare)sdShare.onclick=()=>{
        const url=this._getShareUrl({sector:sec.key});
        navigator.clipboard.writeText(url).then(()=>{sdShare.textContent='Copied!';setTimeout(()=>sdShare.textContent='Share this sector',1500);});
    };
    // Fly to sector view
    const camX=Math.cos(sec.angle)*40,camZ=Math.sin(sec.angle)*40;
    this._flyTo(new THREE.Vector3(Math.cos(sec.angle)*20,3,Math.sin(sec.angle)*20));
}

/* ── Leaderboard History — sector leader timeline ────────────────── */
_createHistoryBtn(){
    const btn=document.createElement('div');
    btn.id='history-btn';btn.textContent='HISTORY';
    btn.style.cssText='position:fixed;top:100px;right:120px;z-index:6;cursor:pointer;font-family:Consolas,monospace;font-size:0.6rem;letter-spacing:0.1em;color:rgba(120,220,255,0.8);background:rgba(4,8,16,0.75);border:1px solid rgba(0,212,255,0.25);border-radius:4px;padding:6px 12px;text-transform:uppercase;pointer-events:auto;transition:all 0.3s;font-weight:600;text-shadow:0 0 6px rgba(0,180,255,0.15);';
    btn.addEventListener('mouseenter',()=>{btn.style.color='#00d4ff';btn.style.borderColor='rgba(0,212,255,0.4)';});
    btn.addEventListener('mouseleave',()=>{if(!this._historyVisible){btn.style.color='rgba(0,212,255,0.6)';btn.style.borderColor='rgba(0,212,255,0.15)';}});
    btn.addEventListener('click',()=>{
        this._historyVisible=!this._historyVisible;
        if(this._historyVisible)this._buildHistory();
        else{const el=document.getElementById('matrix-history');if(el)el.remove();}
        if(this._historyVisible){btn.style.color='#ffab00';btn.style.borderColor='rgba(255,171,0,0.4)';btn.style.background='rgba(255,171,0,0.08)';}
        else{btn.style.color='rgba(0,212,255,0.6)';btn.style.borderColor='rgba(0,212,255,0.15)';btn.style.background='rgba(4,8,16,0.75)';}
    });
    document.body.appendChild(btn);
}

_buildHistory(){
    let el=document.getElementById('matrix-history');if(el)el.remove();
    const hist=demoHistory();
    el=document.createElement('div');el.id='matrix-history';
    el.style.cssText='position:fixed;bottom:60px;right:240px;z-index:8;background:rgba(4,8,16,0.92);border:1px solid rgba(0,212,255,0.12);border-radius:6px;padding:10px 12px;font-family:Consolas,monospace;backdrop-filter:blur(10px);max-width:520px;overflow-x:auto;';
    let html=`<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
        <div style="color:rgba(0,212,255,0.4);font-size:0.5rem;letter-spacing:0.12em">SECTOR LEADER HISTORY</div>
        <div id="hist-close" style="cursor:pointer;color:rgba(255,60,60,0.7);font-size:1.2rem;font-weight:700;line-height:1">&times;</div></div>`;
    html+='<table style="border-collapse:collapse;width:100%;font-size:0.5rem">';
    const months=hist[SECTORS[0].key];
    html+='<tr><td></td>';
    for(const m of months)html+=`<td style="color:rgba(0,212,255,0.25);text-align:center;padding:1px 3px;font-size:0.42rem">${m.month}</td>`;
    html+='</tr>';
    for(const s of SECTORS){
        const c='#'+new THREE.Color(s.color).getHexString();
        const row=hist[s.key];
        html+=`<tr><td style="color:${c};white-space:nowrap;padding-right:6px;font-size:0.48rem">${s.label}</td>`;
        for(const entry of row){
            const short=entry.leader.length>8?entry.leader.slice(0,7)+'..':entry.leader;
            const pct=Math.round(entry.score*100);
            html+=`<td style="text-align:center;padding:2px 3px" title="${entry.leader} ${pct}%">
                <div style="width:6px;height:6px;border-radius:50%;background:${c};margin:0 auto;opacity:0.7"></div>
                <div style="color:rgba(200,215,225,0.4);font-size:0.38rem;white-space:nowrap;overflow:hidden;max-width:38px;text-overflow:ellipsis">${short}</div></td>`;
        }
        html+='</tr>';
    }
    html+='</table>';
    el.innerHTML=html;
    document.body.appendChild(el);
    document.getElementById('hist-close').onclick=()=>{el.remove();this._historyVisible=false;
        const btn=document.getElementById('history-btn');
        if(btn){btn.style.color='rgba(0,212,255,0.6)';btn.style.borderColor='rgba(0,212,255,0.15)';btn.style.background='rgba(4,8,16,0.75)';}};
}

/* ── Animate ──────────────────────────────────────────────────────── */
_animate(){
    requestAnimationFrame(()=>this._animate());
    const dt=this.clock.getDelta(),t=this.clock.elapsedTime;
    const sig2=2*WAVE.sigma*WAVE.sigma,tmp=this._tmp,m4=this._m4,camPos=this.camera.position;

    // Wave computation
    for(const hub of this.hubs)hub._wave=0;
    for(let wi=0;wi<WAVE.count;wi++){const off=wi/WAVE.count,front=(t*WAVE.speed+off)%1.5;
        const wHue=WAVE.hueCenter+WAVE.hueRange*Math.sin(t*0.3+wi*2.09);
        for(const hub of this.hubs){const dist=hub.pos.length()/this.maxDist;if(dist>1.5)continue;
            const diff=dist-front;hub._wave+=Math.exp(-(diff*diff)/sig2)*WAVE.intensity;hub._waveHue=wHue;}}

    // Polarity transition lerp
    if(this._polarityLerping){
        const pt=Math.min((performance.now()-this._polarityLerpStart)/1500,1),pe=easeIO(pt);
        for(const hub of this.hubs){if(hub._targetPos){
            hub.pos.lerpVectors(hub._fromPos,hub._targetPos,pe);
            hub._orbitR=hub.pos.length();hub._orbitA=Math.atan2(hub.pos.z,hub.pos.x);hub._baseY=hub.pos.y;}}
        if(pt>=1){this._polarityLerping=false;for(const hub of this.hubs){delete hub._targetPos;delete hub._fromPos;}}}

    // NC pulse cascade (flows NC→Crucible→Field over 2.5s)
    let ncPulseT=-1;
    if(this._ncPulseActive){
        ncPulseT=Math.min((performance.now()-this._ncPulseStart)/2500,1);
        if(ncPulseT>=1)this._ncPulseActive=false;
        // Pulse the NC brain brighter during cascade
        if(this._ncPlanes.length&&ncPulseT<0.3){
            const u=this._ncPlanes[0].material.uniforms;
            u.uIntensity.value=0.4+ncPulseT*3;u.uBaseBri.value=0.55+ncPulseT*2;
        }
    }

    // Hub instances — selected node glows, others dim, balance coloring
    let colorDirty=false;
    const selIdx=this.selected?this.selected.idx:-1;
    const hasSel=selIdx>=0;
    const showBalance=this._polarityWorst&&!this._polarityLerping;
    const pulseActive=this._ncPulseActive&&ncPulseT>=0;
    const cfActive=this._creatorFilter!=null;
    for(const hub of this.hubs){const i=hub.idx,w=Math.min(hub._wave,0.5),sz=hub.baseSize;
        const camDsq=hub.pos.distanceToSquared(camPos);
        const a=hub._orbitA+Math.sin(t*hub._orbit*8+hub._phase)*0.015;hub.pos.x=Math.cos(a)*hub._orbitR;hub.pos.z=Math.sin(a)*hub._orbitR;
        hub.pos.y=hub._baseY+Math.sin(t*0.4+hub._phase)*0.3;
        // Creator filter: hide non-matching nodes entirely
        if(cfActive&&hub.data._family!==this._creatorFilter){
            m4.makeScale(0,0,0);m4.setPosition(0,-999,0);
            this.hubWires.setMatrixAt(i,m4);this.hubInners.setMatrixAt(i,m4);this.hubGlows.setMatrixAt(i,m4);
            continue;
        }
        const isSel=i===selIdx;
        const near=camDsq<1600,pulse=near?1+Math.sin(t*1.2+hub._phase)*0.02:1;
        const selPulse=isSel?1.3+Math.sin(t*3)*0.15:1;
        const dimF=hasSel&&!isSel?0.25:1;

        // NC pulse cascade: wave front descends from y=42 to y=-5 over 2.5s
        let cascadeGlow=0;
        if(pulseActive){
            const waveY=42-ncPulseT*50; // y=42 → y=-8
            const dist=Math.abs(hub.pos.y-waveY);
            cascadeGlow=Math.max(0,1-dist/8)*easeIO(Math.min(ncPulseT*3,1));
        }

        // Balance tint in polarity-worst mode
        let balMul=1;
        if(showBalance&&hub._balance!==undefined){
            const b=hub._balance; // 1=balanced, 0=unbalanced
            balMul=0.4+b*1.2; // balanced=1.6x bright, unbalanced=0.4x dim
        }

        const ws=sz*1.4*pulse*selPulse*(1+w*0.06+cascadeGlow*0.3);
        m4.makeScale(ws,ws,ws);m4.setPosition(hub.pos.x,hub.pos.y,hub.pos.z);this.hubWires.setMatrixAt(i,m4);
        m4.makeScale(ws*0.18,ws*0.18,ws*0.18);m4.setPosition(hub.pos.x,hub.pos.y,hub.pos.z);this.hubInners.setMatrixAt(i,m4);
        const gs=isSel?ws*3:(cascadeGlow>0.3?ws*2.5:ws*1.8);
        m4.makeScale(gs,gs,gs);m4.setPosition(hub.pos.x,hub.pos.y,hub.pos.z);this.hubGlows.setMatrixAt(i,m4);

        tmp.copy(hub.baseColor);
        if(isSel){tmp.multiplyScalar(2.5);}
        else if(showBalance&&hub._balance!==undefined){
            // Gold tint for balanced, red tint for unbalanced
            const b=hub._balance;
            const tint=new THREE.Color().setHSL(b*0.14,0.8,0.3+b*0.3); // red→gold
            tmp.lerp(tint,0.5).multiplyScalar(balMul*dimF);
        }
        else if(cascadeGlow>0.1){
            const cg=new THREE.Color(0x00d4ff);tmp.lerp(cg,cascadeGlow*0.5).multiplyScalar((1+cascadeGlow)*dimF);
        }
        else if(w>0.05){const wc=new THREE.Color().setHSL(hub._waveHue,0.4,0.3);tmp.lerp(wc,w*0.2);tmp.multiplyScalar((1+w*0.3)*dimF);}
        else{tmp.multiplyScalar(dimF);}
        this.hubWires.setColorAt(i,tmp);this.hubInners.setColorAt(i,tmp);
        tmp.copy(hub.baseColor).multiplyScalar(isSel?0.5:((0.12+w*0.08+(cascadeGlow>0.1?cascadeGlow*0.3:0))*(showBalance?balMul:1)*dimF));
        this.hubGlows.setColorAt(i,tmp);colorDirty=true;}
    this.hubWires.instanceMatrix.needsUpdate=true;this.hubInners.instanceMatrix.needsUpdate=true;this.hubGlows.instanceMatrix.needsUpdate=true;
    if(colorDirty){this.hubWires.instanceColor.needsUpdate=true;this.hubInners.instanceColor.needsUpdate=true;this.hubGlows.instanceColor.needsUpdate=true;}

    // Tier ring pulse
    for(const tr of this.tierRings){const pu=0.6+0.4*Math.sin(t*1.5+tr.phase);
        tr.main.material.opacity=tr.baseOpacity*pu;tr.glow.material.opacity=tr.glowBaseOpacity*(0.5+0.5*Math.sin(t*0.8+tr.phase+1));}
    // Wall shader time
    for(const mat of this._wallMats)mat.uniforms.uTime.value=t;

    // ── NC Brain Animation ──
    if(this._ncGroup){
        // Billboard brain planes toward camera
        const cq=this.camera.quaternion;
        for(const p of this._ncPlanes)p.quaternion.copy(cq);

        // NC state cycling
        const ncT=t%NC_LEN;let ncAcc=0,ncSt=NC_CYCLE[0];
        for(const st of NC_CYCLE){if(ncT<ncAcc+st.d){ncSt=st;break;}ncAcc+=st.d;}

        // Update shader uniforms
        if(this._ncPlanes.length){
            const u=this._ncPlanes[0].material.uniforms;
            u.uTime.value=t;u.uWaveCount.value=ncSt.wc;u.uSpeed.value=ncSt.sp;u.uSigma.value=ncSt.si;
            u.uHueCenter.value=ncSt.hc;u.uHueRange.value=ncSt.hr;u.uSat.value=ncSt.sa;
            u.uBaseBri.value=ncSt.br;u.uIntensity.value=ncSt.it;
        }

        // Synapse particles
        if(this._ncSynapses){
            const pos=this._ncSynapses.geometry.attributes.position;
            const col=this._ncSynapses.geometry.attributes.color;
            const v=this._ncSynapseVel;
            for(let i=0;i<pos.count;i++){
                pos.array[i*3]+=v[i*3];pos.array[i*3+1]+=v[i*3+1];pos.array[i*3+2]+=v[i*3+2];
                const d=Math.sqrt(pos.array[i*3]**2+pos.array[i*3+1]**2+pos.array[i*3+2]**2);
                if(d>8||d<2){
                    const th=Math.random()*Math.PI*2,ph=Math.acos(2*Math.random()-1),rr=4+Math.random()*2;
                    pos.array[i*3]=rr*Math.sin(ph)*Math.cos(th);pos.array[i*3+1]=rr*Math.sin(ph)*Math.sin(th)*0.75;
                    pos.array[i*3+2]=rr*Math.cos(ph)*0.8;
                    v[i*3]=(Math.random()-0.5)*0.02;v[i*3+1]=(Math.random()-0.5)*0.02;v[i*3+2]=(Math.random()-0.5)*0.02;
                }
                if(Math.random()<0.003){
                    const c=new THREE.Color().setHSL(ncSt.hc+Math.random()*0.1,0.9,0.7);
                    col.array[i*3]=c.r;col.array[i*3+1]=c.g;col.array[i*3+2]=c.b;
                    const n=1/Math.max(d,0.1);
                    v[i*3]=pos.array[i*3]*n*0.05;v[i*3+1]=pos.array[i*3+1]*n*0.05;v[i*3+2]=pos.array[i*3+2]*n*0.05;
                }
            }
            pos.needsUpdate=true;col.needsUpdate=true;
        }
    }
    for(const r of this._ncRings){const ri=r.userData._ri;
        r.rotation.y=t*(0.03+ri*0.025);r.rotation.x=Math.PI/2+ri*0.4+Math.sin(t*0.07+ri)*0.06;}
    for(let i=0;i<this._ncLobes.length;i++){const lobe=this._ncLobes[i];
        lobe.rotation.y=t*0.1;lobe.rotation.x=t*0.07;
        lobe.material.opacity=0.1+0.06*Math.sin(t*1.5+i*1.05);}

    // ── Crucible Animation ──
    if(this._crucibleGroup){
        if(this._crucibleLavaMat)this._crucibleLavaMat.uniforms.uTime.value=t;
        if(this._crucibleTorus)this._crucibleTorus.rotation.z=t*0.15;
        if(this._crucibleGlow)this._crucibleGlow.material.opacity=0.01+0.008*Math.sin(t*0.8);
        // Ember particles rise + respawn
        if(this._crucibleEmbers){
            const pos=this._crucibleEmbers.geometry.attributes.position;
            for(let i=0;i<pos.count;i++){
                pos.array[i*3+1]+=0.02+Math.random()*0.02;
                pos.array[i*3]+=(Math.random()-0.5)*0.01;pos.array[i*3+2]+=(Math.random()-0.5)*0.01;
                if(pos.array[i*3+1]>10){
                    pos.array[i*3]=(Math.random()-0.5)*4;pos.array[i*3+1]=2+Math.random()*2;
                    pos.array[i*3+2]=(Math.random()-0.5)*3;
                }
            }
            pos.needsUpdate=true;
        }
    }

    // ── Aurora Shield Dome ──
    if(this._shieldMat)this._shieldMat.uniforms.uTime.value=t;

    // ── Gap Plasma ──
    if(this._gapWispsVisible&&this._gapPlasmaMat){
        this._gapPlasmaMat.uniforms.uTime.value=t;
    }

    // ── Heatmap subtle pulse ──
    if(this._heatmapOn&&this._heatmapMat){
        this._heatmapMat.opacity=0.5+0.15*Math.sin(t*0.8);
    }

    // Core nexus
    if(this.coreMesh){const cp=1+Math.sin(t*0.6)*0.04;this.coreMesh.scale.setScalar(cp);
        this.coreMesh.rotation.y=t*0.06;this.coreMesh.rotation.x=Math.sin(t*0.05)*0.12;
        this.coreGlow.scale.setScalar(cp*1.5);tmp.setHSL((t*0.015)%1,0.3,0.25);this.coreMesh.material.color.copy(tmp);}
    for(const r of this.coreRings){const ri=r.userData._ri;r.rotation.y=t*(0.04+ri*0.03);r.rotation.x=Math.PI/2+ri*0.35+Math.sin(t*0.08+ri)*0.06;}

    // Throttled updates
    this._labelTimer+=dt;if(this._labelTimer>0.2){this._labelTimer=0;this._updateLabels();}
    this._compassTimer+=dt;if(this._compassTimer>0.1){this._compassTimer=0;this._updateCompass();}

    if(this.dust)this.dust.rotation.y=t*0.004;
    if(this.gridMat)this.gridMat.uniforms.uTime.value=t;
    if(!this._flying)this.controls.update();
    this.composer.render();
}

_resize(){this.camera.aspect=innerWidth/innerHeight;this.camera.updateProjectionMatrix();
    this.renderer.setSize(innerWidth,innerHeight);this.composer.setSize(innerWidth,innerHeight);
    this.bloomPass.resolution.set(innerWidth,innerHeight);}
}

/* ── Demo data ────────────────────────────────────────────────────── */
function demoData(){
    const ARC=[[0.95,0.82,0.70,0.78,0.80,0.82],[0.82,0.95,0.78,0.88,0.78,0.88],
        [0.75,0.78,0.95,0.80,0.88,0.75],[0.82,0.88,0.78,0.95,0.82,0.82],
        [0.78,0.78,0.82,0.78,0.95,0.82],[0.82,0.88,0.78,0.82,0.82,0.95],
        [0.86,0.86,0.86,0.86,0.86,0.86]];
    const F=[['qwen3',0.92,0,120],['qwen2.5',0.88,0,110],['qwen2',0.82,6,90],
        ['llama3.3',0.94,1,120],['llama3.2',0.88,1,110],['llama3.1',0.84,6,100],
        ['deepseek-r1',0.91,2,120],['deepseek-v3',0.89,2,110],['deepseek-coder',0.86,3,90],
        ['codestral',0.93,3,110],['mistral',0.80,6,120],['mixtral',0.87,1,100],
        ['gemma2',0.85,0,110],['gemma',0.78,6,70],['phi-4',0.90,1,120],['phi-3',0.84,6,90],
        ['command-r',0.88,4,80],['command-r+',0.92,4,60],['yi-1.5',0.83,5,70],['yi-coder',0.86,3,60],
        ['internlm2.5',0.84,5,70],['chatglm4',0.82,5,50],['gpt-4o',0.97,6,120],['gpt-4-turbo',0.95,6,120],
        ['claude-3.5-sonnet',0.96,0,120],['claude-3-haiku',0.88,0,120],
        ['gemini-2.0-flash',0.94,1,120],['gemini-1.5-pro',0.92,1,120],
        ['solar-pro',0.86,4,60],['nous-hermes',0.83,2,90],['dolphin',0.81,2,70],['openhermes',0.80,2,60],
        ['neural-chat',0.78,5,50],['starling',0.80,1,60],['orca-2',0.82,6,70],['wizardlm-2',0.85,3,90],
        ['starcoder2',0.84,3,80],['codellama',0.83,3,100],['vicuna',0.76,6,60],['zephyr',0.82,1,70],
        ['falcon',0.79,6,50],['mpt',0.75,6,40],['granite',0.84,1,50],['olmo',0.81,6,60],
        ['jamba',0.83,2,50],['dbrx',0.87,3,50],['arctic',0.80,4,50],['snowflake',0.82,5,50],
        ['glm-4',0.85,5,60],['baichuan',0.79,5,50]];
    const SIZES=['0.5b','1b','1.5b','3b','4b','7b','8b','13b','14b','22b','32b','70b','72b','110b','405b'];
    const QUANTS=['q2_K','q3_K_M','q4_0','q4_K_M','q5_K_M','q6_K','q8_0','fp16'];
    const seen=new Set(),models=[],now=Date.now()/1000,maxC=SIZES.length*QUANTS.length;
    for(const[name,base,arch,rawT] of F){const target=Math.min(rawT,maxC);let count=0,att=0;
        while(count<target&&models.length<5200&&att<target*3){att++;
            const sz=SIZES[Math.floor(Math.random()*SIZES.length)],q=QUANTS[Math.floor(Math.random()*QUANTS.length)];
            const id=`${name}:${sz}-${q}`;if(seen.has(id))continue;seen.add(id);count++;
            const sn=parseFloat(sz),sb=Math.log2(sn+1)*0.008,qp=(QUANTS.length-1-QUANTS.indexOf(q))/QUANTS.length*0.06;
            const adj=Math.max(0.3,Math.min(1,base+sb-qp+(Math.random()-0.5)*0.05));
            const ap=ARC[arch],cats={};for(let ci=0;ci<CAT_KEYS.length;ci++)cats[CAT_KEYS[ci]]=Math.max(0.2,Math.min(1,ap[ci]*adj/0.9+(Math.random()-0.5)*0.08));
            const rc=Math.round(50+Math.random()*40000);
            const rec=[];for(let r=0;r<3;r++)rec.push({run_id:'r_'+Math.random().toString(36).slice(2,8),
                score:Math.max(0.3,Math.min(1,adj+(Math.random()-0.5)*0.1)),at:now-(3-r)*86400,type:Math.random()>0.35?'break':'assure'});
            models.push({id,avg_score:adj,best_score:Math.min(1,adj+0.05),worst_score:Math.max(0.15,adj-0.15),
                run_count:rc,categories:cats,trend:(Math.random()-0.5)*0.05,
                unique_users:Math.round(rc*(0.3+Math.random()*0.5)),break_count:Math.round(rc*0.6),
                assure_count:Math.round(rc*0.4),recent_runs:rec});}}
    while(models.length>5000)models.pop();
    return{models,total_runs:models.reduce((s,m)=>s+m.run_count,0),total_models:models.length};}

function demoDetail(mid){
    const FP=['numeric_continuation','instruction_constraint','format_adherence','brevity_compliance',
        'edge_case_null','self_knowledge','reasoning_chain','multi_hop_reasoning',
        'deductive_chain','contradiction_detection','temporal_reasoning','self_consistency_arithmetic',
        'code_edge_case','uncertainty_hedge','calibrated_uncertainty','hallucination_method',
        'tool_refusal','adversarial_compliance','subtle_injection','context_recall',
        'context_storm','context_interference','boundary_consistency','instruction_cascade',
        'instruction_persistence','refusal_precision','code_correction','format_strict_array',
        'over_refusal','response_length_discipline'];
    const fp={};for(const p of FP)fp[p]=0.4+Math.random()*0.6;
    const now=Date.now()/1000,runs=[];
    for(let i=0;i<30;i++)runs.push({run_id:'r_'+Math.random().toString(36).slice(2,8),
        score:0.4+Math.random()*0.6,at:now-i*43200,type:Math.random()>0.3?'break':'assure',
        latency_ms:Math.round(800+Math.random()*4000)});
    return{model:mid,runs,fingerprint:fp,calibration_score:0.6+Math.random()*0.35};}

function demoHistory(){
    const months=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
    const topModels=['gpt-4o','claude-3.5-sonnet','gemini-2.0-flash','llama3.3','qwen3','codestral',
        'deepseek-r1','phi-4','command-r+','gemini-1.5-pro','gpt-4-turbo','llama3.2'];
    const history={};
    for(const s of SECTORS){
        history[s.key]=[];
        let prev=topModels[Math.floor(Math.random()*topModels.length)];
        for(let m=0;m<12;m++){
            if(Math.random()<0.3)prev=topModels[Math.floor(Math.random()*topModels.length)];
            history[s.key].push({month:months[m],leader:prev,score:0.88+Math.random()*0.12});
        }
    }
    return history;
}

document.addEventListener('DOMContentLoaded',()=>{new ForgeMatrix(document.getElementById('matrix-canvas')).init();});
