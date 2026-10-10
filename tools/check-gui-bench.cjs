// Real Edge regression for the Tauri/React comparison list (same HTML/JS as WebView2).
// Usage after npm build in experiments/gui-compare/tauri-react: node tools/check-gui-bench.cjs
const {chromium} = require('playwright');
const {spawn} = require('node:child_process');
const {mkdtempSync,rmSync} = require('node:fs');
const {tmpdir} = require('node:os');
const path = require('node:path');
const assert = require('node:assert/strict');

const root = path.resolve(__dirname, '..');
const dist = path.join(root, 'experiments', 'gui-compare', 'tauri-react', 'dist');
const temp = mkdtempSync(path.join(tmpdir(), 'aredoko-bench-'));
let server, browser;

async function start() {
  return new Promise((resolve, reject) => {
    server = spawn(process.env.PYTHON || (process.platform === 'win32' ? 'python' : 'python3'),
      ['-u', 'app/server.py', '--port', '0', '--db', path.join(temp, 'fixture.sqlite'), '--benchmark-dist', dist],
      {cwd:root, stdio:['ignore','pipe','pipe'], windowsHide:true});
    let output = '', errs = '', done = false;
    const finish = (err, url) => {if(done)return; done=true; clearTimeout(timer); err?reject(err):resolve(url)};
    const timer=setTimeout(()=>finish(Error('Server start timeout: '+errs)),120000);
    server.stderr.on('data', chunk=>{errs += String(chunk).slice(0,2048)});
    server.on('error',e=>finish(e));
    server.once('exit',code=>finish(Error('Server exited: '+code+' '+errs)));
    server.stdout.on('data',chunk=>{
      output += String(chunk);
      const m=output.match(/Aredoko demo: (http:\/\/127\.0\.0\.1:\d+)/);
      if(m)finish(null,m[1]);
    });
  });
}

async function main() {
  const base=await start();
  browser = await chromium.launch({channel:'msedge', headless:true});
  const page=await browser.newPage({viewport:{width:1440,height:900}});
  const errors=[];
  page.on('pageerror',err=>errors.push(err.message));
  await page.goto(base+'/bench/');
  await page.waitForFunction(()=>document.querySelector('.item')?.textContent.includes('00001'));
  const list=page.locator('.list');
  await list.evaluate(el=>{el.scrollTop=el.scrollHeight});
  await page.waitForFunction(()=>document.querySelector('.list').scrollTop > 500);
  // Change page while scrolled. It must reset BOTH React state and the DOM scroll container.
  await page.getByRole('button',{name:'次へ'}).click();
  try {
    await page.waitForFunction(()=>{
      const first=document.querySelector('.item');
      const container=document.querySelector('.list');
      return container?.scrollTop===0 && first?.textContent.includes('00061') && first.getBoundingClientRect().top < container.getBoundingClientRect().bottom;
    }, {timeout: 12000});
  } catch (e) {
    const diagnostics = await page.evaluate(() => ({
      scrollTop: document.querySelector('.list')?.scrollTop,
      first: document.querySelector('.item')?.textContent,
      displayedRows: document.querySelectorAll('.item').length,
      footer: document.querySelector('footer')?.textContent,
      status: document.querySelector('.message')?.textContent,
      benchmark: window.__aredokoBench
    }));
    console.error('Virtual paging diagnostics:', JSON.stringify(diagnostics));
    throw e;
  }
  assert.match(await page.locator('.item').first().textContent(),/00061/);
  await list.evaluate(el=>{el.scrollTop=el.scrollHeight});
  await page.waitForFunction(()=>document.querySelector('.list').scrollTop > 500);
  await page.getByRole('button',{name:'前へ'}).click();
  await page.waitForFunction(()=>document.querySelector('.list').scrollTop===0 && document.querySelector('.item')?.textContent.includes('00001'));
  assert.match(await page.locator('.item').first().textContent(),/00001/);
  assert.deepEqual(errors,[]);
  console.log('PASS: virtualized list remains visible at top after scrolled page changes');
}

main().catch(err=>{console.error(err);process.exitCode=1}).finally(async()=>{
  if(browser)await browser.close();
  if(server && server.exitCode===null){server.kill();await new Promise(resolve=>{server.once('exit',resolve);setTimeout(resolve,3000)})}
  rmSync(temp,{recursive:true,force:true});
});
