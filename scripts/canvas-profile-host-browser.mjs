// Private headless browser test of the real generated app and Entity provider.
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {createServer} from 'node:http';
import {readFile, mkdir, rm} from 'node:fs/promises';
import {dirname, basename, join, extname} from 'node:path';
import {setTimeout as delay} from 'node:timers/promises';
const html=process.argv[2], root=dirname(html), profile=join(root,'browser');
const bare=process.argv[3]==='bare';
await rm(profile,{recursive:true,force:true}); await mkdir(profile,{recursive:true});
const server=createServer(async(req,res)=>{
  try {
    const path=decodeURIComponent(new URL(req.url,'http://localhost').pathname);
    if(path.includes('..'))throw Error('invalid path');
    const data=await readFile(join(root,path));
    res.setHeader('Content-Type',extname(path)==='.wasm'?'application/wasm':extname(path)==='.js'?'text/javascript':'text/html');
    res.end(data);
  }catch{res.writeHead(404).end();}
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const url='http://127.0.0.1:'+server.address().port+'/'+basename(html);
const env={...process.env};
for(const key of ['DISPLAY','WAYLAND_DISPLAY','XAUTHORITY','DBUS_SESSION_BUS_ADDRESS','SESSION_MANAGER','GDK_DISPLAY','DESKTOP_SESSION','XDG_SESSION_ID','XDG_SESSION_TYPE'])delete env[key];
env.YUE_DESKTOP_RECOVERY='0';
const browser=spawn(process.env.CHROMIUM||'chromium',['--headless=new','--no-sandbox','--disable-gpu','--disable-dev-shm-usage','--no-first-run','--no-default-browser-check','--remote-debugging-port=0','--user-data-dir='+profile,'about:blank'],{env,stdio:['ignore','ignore','pipe']});
let errors='',socket,diagnostics='';browser.stderr.on('data',v=>errors=(errors+v).slice(-2000));
try{
  const deadline=Date.now()+45000; let port;
  while(Date.now()<deadline){try{port=(await readFile(join(profile,'DevToolsActivePort'),'utf8')).split('\n')[0];break;}catch{} if(browser.exitCode!==null)throw Error(errors);await delay(50);}
  assert(port,'No private browser endpoint: '+errors);
  const pages=await(await fetch('http://127.0.0.1:'+port+'/json/list')).json();
  socket=new WebSocket(pages.find(p=>p.type==='page').webSocketDebuggerUrl);
  await new Promise((resolve,reject)=>{socket.addEventListener('open',resolve,{once:true});socket.addEventListener('error',reject,{once:true});});
  let seq=0;const pending=new Map();
  socket.addEventListener('message',e=>{const m=JSON.parse(e.data);
    if(m.method==='Runtime.consoleAPICalled')diagnostics=(diagnostics+m.params.args.map(a=>a.value||a.description||'').join(' ')+'\n').slice(-6000);
    if(m.method==='Runtime.exceptionThrown')diagnostics=(diagnostics+JSON.stringify(m.params)+'\n').slice(-6000);
    if(pending.has(m.id)){pending.get(m.id)(m);pending.delete(m.id);}
  });
  async function call(method,params={}){const id=++seq;const response=new Promise((resolve,reject)=>{pending.set(id,resolve);setTimeout(()=>{if(pending.delete(id))reject(Error(method+' timed out '+diagnostics));},20000).unref();});socket.send(JSON.stringify({id,method,params}));const r=await response;assert(!r.error,JSON.stringify(r));return r.result;}
  async function evaluate(expression){const r=await call('Runtime.evaluate',{expression,returnByValue:true});assert(!r.exceptionDetails,JSON.stringify(r));return r.result.value;}
  async function until(fn,message,timeout=45000){const end=Date.now()+timeout;while(Date.now()<end){const value=await fn();if(value)return value;await delay(100);}throw Error(message+'\n'+diagnostics);}
  await call('Runtime.enable');await call('Page.enable');
  // This test never contacts an external node. Signed acceptance is exercised
  // separately against the adopting app's disposable Daochi fixture.
  await call('Network.enable');
  await call('Network.setBlockedURLs',{urls:['https://*']});
  await call('Emulation.setDeviceMetricsOverride',{width:960,height:1100,deviceScaleFactor:1,mobile:false});
  let serial=0;
  async function command(verb){
    const n=++serial;
    await evaluate(`(()=>{Module.FS.writeFile('/driver/next',${JSON.stringify(n+'\t'+verb+'\n')});Module.FS.rename('/driver/next','/driver/command');return true})()`);
    const reply=await until(()=>evaluate(`(()=>{try{return Module.FS.readFile('/driver/reply',{encoding:'utf8'})}catch{return ''}})()`),'Driver reply missing: '+verb);
    await evaluate("Module.FS.unlink('/driver/reply')");const result=JSON.parse(reply);assert(result.ok,JSON.stringify(result));return result;
  }
  async function nodes(){return (await command('tree')).nodes;}
  async function find(key){return (await nodes()).find(n=>Number(n.key)===key);}
  async function press(key){await command('press\tkey='+key);}
  async function ready(){await until(()=>evaluate("!!(typeof Module!=='undefined'&&"+(bare?'true':'Module.profileReady')+"&&Module.FS&&Module.FS.analyzePath('/kryon-apps/entity.canvas.test').exists)"),'Compiled app not ready');}
  await call('Page.navigate',{url});await ready();
  if(bare){
    assert(await find(20401),'Bare runner did not render game frame');
    assert.equal(await find(20400),undefined,'Bare runner exposed Profile');
    await press(20405);
    assert((await evaluate("Module.FS.readFile('/kryon-apps/entity.canvas.test/continuity',{encoding:'utf8'})")).startsWith('marker-'));
    assert.equal(await evaluate("Module.FS.analyzePath('/kryon-apps/entity.canvas.test/mini-service-leak').exists"),false,'Bare direct service bypass');
    assert.equal(await evaluate("Module.FS.analyzePath('/kryon-apps/profile/account.key').exists"),false,'Bare runner initialized account provider');
    console.log('Bare compiled canvas local test passed: null hooks render game and preserve unavailable services');
  }else{
  assert(await find(20400),'Profile key 20400 absent');
  await press(20405);
  const marker=await evaluate("Module.FS.readFile('/kryon-apps/entity.canvas.test/continuity',{encoding:'utf8'})");
  assert(marker.startsWith('marker-'),'Unique marker was not written');
  await press(20400);
  await until(async()=>!(await find(20400)),'Game callback still running under Profile');
  await until(async()=>await find(78030),'Shared My referrals entry missing');
  await press(78030);assert(await find(78005),'Signed-out referrals must offer Sign in');
  await press(78005);assert(await find(820),'Referrals did not open shared sign-in');
  await press(821);
  await until(async()=>await find(104),'Shared password field missing');
  await press(104);
  await command('type\ttext=CanvasFixture123!');
  assert.equal(await evaluate("Module.FS.analyzePath('/kryon-apps/entity.canvas.test/received-input').exists"),false,'Game received Profile input');
  await press(49001);
  await until(async()=>await find(820),'Account navigation did not return');
  await press(820);
  await until(()=>evaluate("Module.FS.analyzePath('/kryon-apps/profile/account.key').exists"),'Shared provider account creation failed',60000);
  // A frame reply waits for the provider's synchronous persistence result,
  // rather than reloading while its IndexedDB flush is still yielding.
  await command('tree');
  for(let at=0;at<8&&!await find(20400);at++)await press(49001);
  assert(await find(20400),'Profile did not close');
  await command('tree');
  assert.equal(await evaluate("Module.FS.analyzePath('/kryon-apps/entity.canvas.test/received-input').exists"),false,'Game received delayed password input after resuming');
  assert.equal(await evaluate("Module.FS.readFile('/kryon-apps/entity.canvas.test/continuity',{encoding:'utf8'})"),marker,'Profile changed private game document');
  // Reload preserves the existing private document and initializes the same provider.
  await call('Page.reload');await ready();assert(await find(20400),'Profile missing after reload');
  assert.equal(await evaluate("Module.FS.analyzePath('/kryon-apps/profile/account.key').exists"),true,'Created account missing after reload');
  assert.equal(await evaluate("Module.FS.readFile('/kryon-apps/entity.canvas.test/continuity',{encoding:'utf8'})"),marker,'Unique document lost on reload');
  await call('Page.navigate',{url:url+'?mini'});await ready();
  assert.equal(await find(20400),undefined,'Mini mode exposed Profile');
  await command('tree');
  assert.equal(await evaluate("Module.FS.analyzePath('/kryon-apps/entity.canvas.test/mini-service-leak').exists"),false,'Mini direct service bypass');
  console.log('Generated canvas Profile local tests passed: Profile key 20400, shared referrals/sign-in, real account creation/reload, input isolation, IDB documents and mini mode');
  }
}finally{
  socket?.close();browser.kill('SIGTERM');await new Promise(resolve=>{if(browser.exitCode!==null)resolve();else browser.once('exit',resolve);});server.close();
}
