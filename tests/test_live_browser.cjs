// Optional DOM checks: NODE_PATH=/path/to/node_modules node tests/test_live_browser.cjs
// Requires linkedom. Rendering/physics calls are stubbed; this is not visual QA.
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const {parseHTML} = require('linkedom');
const html = fs.readFileSync(require('node:path').join(__dirname, '../cmat_webviewer.html'), 'utf8');
const {document, window} = parseHTML(html);
const server = 'http://localhost:1111';
let entries = ['h1_energy', 'h2_coincidences'].map((name, i) => ({name:'Histograms/Demo/'+name,
    type:i ? 'TH2F' : 'TH1F', url:server+'/Histograms/Demo/'+name+'/root.json?compact=23'}));
let failed = false;
const requests = [];
const context = {document, window, console, Date, Number, JSON, Boolean, Math, Map, Promise, Error,
  Option: function(text, value) {const o=document.createElement('option'); o.textContent=text; o.value=value; return o;},
  fetch: async (url, options={}) => {
    requests.push([url, options]);
    if (url.startsWith('/api/live_histograms')) return {ok:!failed, json:async()=>failed ? {error:'Disconnected'} : {server_url:server,details:entries}};
    const data = JSON.parse(options.body);
    const is1D = data.url.includes('h1_energy');
    return {ok:true, json:async()=>({metadata:{is_1d:is1D,shape:[256,is1D?1:192],filename:is1D?'h1_energy':'h2_coincidences',
      live_browser_url:server,live:{url:data.url,interval:2,connected:true,paused:false,revision:1,last_checked:Date.now()/1000}}})};
  }};
vm.createContext(context);
const additions = html.slice(html.indexOf('  let rootPickerPath'), html.indexOf('  function closeRootHistogramPicker'));
vm.runInContext(`let metadata=null; let isSwitchingMatrix=false; let view={}; let gate1DState={};
function updateMatrixUI(){updateLiveUI()} function updateGateUI(){} function clearAllFits(){}
async function fetchTileAndRender(){} async function fetch1DProjection(){} async function reapplyGates(){}
async function reapplyAllPersistentFits(){} function renderBoth1DSpectra(){} function render2D(){}
function showMatrixToast(){} ${additions}`, context);
const run = code => vm.runInContext(code, context);
const pause = () => new Promise(resolve=>setTimeout(resolve,20));
(async()=>{
  await run(`browseLiveServer('${server}')`);
  assert.equal(document.querySelectorAll('.live-histogram').length, 2);
  assert.equal(document.getElementById('liveSourceURL').value, server);
  assert.equal(document.getElementById('liveBrowser').style.display, 'block');
  assert.equal(document.querySelectorAll('#liveHistogramTree details').length, 2);
  document.querySelector('.live-histogram').click(); await pause();
  assert.equal(run('metadata.is_1d'), true);
  assert.equal(document.querySelectorAll('.live-histogram').length, 2);
  assert.equal(document.querySelector('[aria-pressed="true"]').title, 'Histograms/Demo/h1_energy');
  document.querySelectorAll('.live-histogram')[1].click(); await pause();
  assert.equal(run('metadata.is_1d'), false);
  assert.equal(document.querySelector('[aria-pressed="true"]').title, 'Histograms/Demo/h2_coincidences');
  const posts = requests.filter(([url])=>url==='/api/live_connect');
  assert.equal(posts.length, 2);
  assert.equal(JSON.parse(posts[1][1].body).server_url, server);
  const search = document.getElementById('liveHistogramSearch');
  search.value='TH1F'; run('renderLiveHistogramTree()');
  assert.equal(document.querySelectorAll('.live-histogram').length, 1);
  search.value='demo'; run('renderLiveHistogramTree()');
  assert.equal(document.querySelectorAll('.live-histogram').length, 2);
  search.value='no-match'; run('renderLiveHistogramTree()');
  assert.equal(document.getElementById('liveHistogramTree').textContent,'No matching histograms.');
  search.value=''; run('renderLiveHistogramTree()');
  const previous = document.getElementById('liveHistogramTree').innerHTML;
  failed=true; await run(`browseLiveServer('${server}')`);
  assert.equal(document.getElementById('liveHistogramTree').innerHTML,previous);
  assert.match(document.getElementById('liveBrowserStatus').textContent,/retained/);
  failed=false;
  entries.push({name:'Histograms/Other/<img onerror=bad>',type:'TH1F',url:server+'/Histograms/Other/new/root.json?compact=23'});
  await run(`browseLiveServer('${server}')`);
  assert.equal(document.querySelectorAll('.live-histogram').length,3);
  assert.equal(document.querySelectorAll('#liveHistogramTree img').length,0);
  console.log('DOM checks passed: persistent folders, one-click TH1/TH2 switching, active selection, name/folder/type search, failed-list retention, list refresh, safe labels.');
})().catch(error=>{console.error(error);process.exitCode=1;});
