// Canvas command checks: geometry, contrast, persistence, zoom and clipping.
const fs=require('node:fs'), vm=require('node:vm'), assert=require('node:assert/strict');
const html=fs.readFileSync(require('node:path').join(__dirname,'../cmat3d_webviewer.html'),'utf8');
const helper=html.slice(html.indexOf('  function drawBananaGateOverlays'),html.indexOf('  function render2D()'));
const calls=[];
const ctx=new Proxy({measureText:t=>({width:t.length*6})},{get:(o,key)=>key in o?o[key]:(...args)=>calls.push([key,...args]),set:(o,k,v)=>{o[k]=v;calls.push(['set',k,v]);return true}});
const env={console,Number,Math,ctx,pr:{x:10,y:20,w:200,h:100}};
vm.createContext(env);
vm.runInContext(`let bananaPolygonPeak=[{x:10,y:10},{x:20,y:10},{x:20,y:20}];
let bananaPolygonBg=[{x:30,y:30},{x:40,y:30},{x:40,y:40}];
let bananaMode=null,bananaGateActive=true,zoom=1;
function chToPx2D(x,y){return {x:10+x*zoom,y:120-y*zoom}}
${helper}`,env);
const run=c=>vm.runInContext(c,env);
run('drawBananaGateOverlays(ctx,pr)');
assert.equal(calls.filter(c=>c[0]==='closePath').length,2);
assert(calls.some(c=>c[0]==='fillText'&&c[1]==='Peak gate (applied)'));
assert(calls.some(c=>c[0]==='fillText'&&c[1]==='Background gate (applied)'));
for(const width of [7,5,3])assert(calls.some(c=>c[0]==='set'&&c[1]==='lineWidth'&&c[2]===width));
assert(calls.some(c=>c[0]==='setLineDash'&&String(c[1])==='8,5'));
const before=JSON.stringify(run('bananaPolygonPeak'));calls.length=0;
run('zoom=2;drawBananaGateOverlays(ctx,pr)');assert(calls.some(c=>c[0]==='moveTo'&&c[1]===30&&c[2]===100));
assert.equal(JSON.stringify(run('bananaPolygonPeak')),before);
calls.length=0;run('bananaMode="peak";drawBananaGateOverlays(ctx,pr)');
assert.equal(calls.filter(c=>c[0]==='closePath').length,1);assert(calls.some(c=>c[0]==='fillText'&&c[1].includes('(drawing)')));
calls.length=0;run('bananaPolygonPeak=[];bananaPolygonBg=[];drawBananaGateOverlays(ctx,pr)');assert.equal(calls.length,0);
const render=html.slice(html.indexOf('  function render2D()'),html.indexOf('  // --- Canvas Rendering: 1D'));
assert(render.lastIndexOf('drawBananaGateOverlays')>render.lastIndexOf('ctx2d.restore'));
console.log('Banana overlays: closed borders, peak/background labels, contrasting strokes, topmost layer, zoom and clearing passed.');
