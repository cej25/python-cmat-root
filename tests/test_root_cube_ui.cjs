// TH3 control-flow tests with rendering stubs; no browser dependency.
const fs=require('node:fs'), vm=require('node:vm'), assert=require('node:assert/strict');
const html=fs.readFileSync(require('node:path').join(__dirname,'../cmat3d_webviewer.html'),'utf8');
const elements=new Map();
function element(id){if(!elements.has(id))elements.set(id,{style:{},textContent:'',value:'5'});return elements.get(id)}
const metadata={root_cube:true,axis_labels:{0:'E1 [keV]',1:'E2 [keV]',2:'dT [ns]'},axis_units:{0:'keV',1:'keV',2:'ns'},
 cal_0:[0,2,0],cal_1:[0,2,0],cal_2:[-200,.4,0],total_counts:6902,live:{enabled:true,paused:false,generation:0}};
let next=structuredClone(metadata), requests=[];
const context={console,Math,Number,JSON,Date,Error,document:{getElementById:element},
 setTimeout:()=>1,clearTimeout:()=>{},fetch:async url=>{requests.push(url);return {ok:true,json:async()=>structuredClone(next)}}};
vm.createContext(context);
vm.runInContext(`let metadata=${JSON.stringify(metadata)};
let spec1D=[[1],[1],[1,2,3]], gates1D=[{w:[],b:[]},{w:[],b:[]},{w:[],b:[]}];
let maxCountGlobal=1,lastGateConfigKey='same',gambaGateActive=false,gambaGateResult=null,bananaGateActive=false;
let projectionCalls=0,tileCalls=0,bananaCalls=0;
function getVisible1DRange(){return {start:0,end:2}}
async function fetchProjections(){projectionCalls++}
async function fetchTileAndRender(){tileCalls++}
async function applyBananaGate(){bananaCalls++}
`,context);
let helpers=html.slice(html.indexOf('  function axisCoordinateLabel'),html.indexOf('  function vmaxSliderToValue'));
let snapshot=html.slice(html.indexOf('  function getCurrent1DSnapshot'),html.indexOf('  // The popup requests'));
let live=html.slice(html.indexOf('  let cubeLiveBusy'),html.indexOf('  // --- App Initialization'));
vm.runInContext(helpers+snapshot+live,context);
const run=code=>vm.runInContext(code,context);
(async()=>{
 const snap=run('getCurrent1DSnapshot(2)');
 assert.equal(snap.x_axis_label,'dT [ns]');assert.equal(snap.x_unit,'ns');
 assert(Math.abs(snap.x_energy[0]+199.8)<1e-8);assert(Math.abs(snap.x_energy[2]+199)<1e-8);
 next.live.generation=1;await run('refreshCubeLive(false)');
 assert.equal(run('projectionCalls'),1);assert.equal(run('tileCalls'),1);assert.equal(run('lastGateConfigKey'),'');
 assert.match(element('liveCubeStatus').textContent,/Live/);
 run('metadata.live.paused=true');const before=requests.length;await run('refreshCubeLive(false)');assert.equal(requests.length,before);
 next.live.paused=true;next.live.generation=2;await run('refreshCubeLive(true)');assert.equal(run('projectionCalls'),2);
 next.live.error='source unavailable';await run('refreshCubeLive(true)');assert.match(element('liveCubeStatus').textContent,/retained/);
 run('metadata.live.paused=false; bananaGateActive=true');next.live.error=null;next.live.generation=3;
 await run('refreshCubeLive(false)');assert.equal(run('bananaCalls'),1);
 run('gambaGateActive=true');const old=requests.length;await run('refreshCubeLive(false)');assert.equal(requests.length,old);
 console.log('TH3 UI: calibrated snapshot, live refresh, pause/manual update, error retention, polygon refresh and fit-cut hold passed.');
})().catch(err=>{console.error(err);process.exitCode=1});
