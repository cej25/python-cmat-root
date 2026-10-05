// Source-aware branding and TH3 navigation checks without rendering dependencies.
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const read=name=>fs.readFileSync(path.join(__dirname,'..',name),'utf8');
const html=read('cmat_webviewer.html'),cube=read('cmat3d_webviewer.html');
const nodes={viewerBrand:{textContent:''},backToHistogramBrowser:{style:{}},liveInterval:{value:'2'}};
const document={title:'',getElementById:id=>nodes[id]};
const navigation=[];let body;
const context={document,window:{location:{assign:url=>navigation.push(url)}},console,Number,
 livePost:async(url,data)=>{body=data;return {viewer_url:'/cube/'}},showMatrixToast:()=>{}};
vm.createContext(context);
vm.runInContext('let metadata=null,liveUpdateBusy=false,isSwitchingMatrix=false;',context);
const brand=html.slice(html.indexOf('  function updateViewerBrand()'),html.indexOf('  function updateMatrixUI()'));
vm.runInContext(brand,context);
const run=s=>vm.runInContext(s,context);
for(const [metadata,expected] of [[{source_format:'ROOT'},'ROOT visualiser'],[{source_format:'GASP',live_browser_url:'http://source'},'GASP visualiser'],[{pending_live_server:'http://source'},'ROOT visualiser'],[{root_histogram:'h1'},'ROOT visualiser'],[{},'GASP visualiser']]){
 run(`metadata=${JSON.stringify(metadata)};updateViewerBrand()`);assert.equal(document.title,expected);assert.equal(nodes.viewerBrand.textContent,expected);
}
const connect=html.slice(html.indexOf('  async function connectLiveHistogram'),html.indexOf('  async function refreshLiveHistogram'));
vm.runInContext(connect,context);
(async()=>{
 assert(await run(`connectLiveHistogram('http://source/h3/root.json','http://source','TH3F')`));
 assert.equal(body.type,'TH3F');assert.equal(navigation[0],'/cube/');assert.equal(run('liveUpdateBusy'),false);
 const cubeBrand=cube.slice(cube.indexOf('  function updateViewerBrand()'),cube.indexOf('  function updateUIWithMetadata()'));
 vm.runInContext(cubeBrand,context);
 run('metadata={root_cube:true,mounted_browser:true};updateViewerBrand()');
 assert.equal(document.title,'ROOT visualiser — 3D');assert.equal(nodes.backToHistogramBrowser.style.display,'');
 run('metadata={root_cube:false,mounted_browser:false};updateViewerBrand()');
 assert.equal(document.title,'GASP visualiser — 3D');assert.equal(nodes.backToHistogramBrowser.style.display,'none');
 console.log('Viewer titles: ROOT/CMAT switching, pending ROOT browser, 3D title and TH3 menu navigation passed.');
})().catch(err=>{console.error(err);process.exitCode=1});
