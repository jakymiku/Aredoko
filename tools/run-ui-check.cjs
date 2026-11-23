// Automatically run the Edge UI smoke test on a disposable fictional SQLite DB.
// Unlike launching server.py normally, this never touches data/demo.sqlite.
const {spawn} = require('node:child_process');
const {mkdtempSync, rmSync} = require('node:fs');
const {tmpdir} = require('node:os');
const path = require('node:path');
const {once} = require('node:events');

const root = path.resolve(__dirname, '..');
const temp = mkdtempSync(path.join(tmpdir(), 'aredoko-ui-'));
const python = process.env.PYTHON || (process.platform === 'win32' ? 'python' : 'python3');
let server;

async function main() {
  server = spawn(python, ['-u', 'app/server.py', '--port', '0', '--db', path.join(temp, 'fixture.sqlite')], {
    cwd: root, stdio: ['ignore', 'pipe', 'pipe'], windowsHide: true
  });
  let stderr = '';
  server.stderr.on('data', chunk => { stderr += String(chunk).slice(0, 4096); });
  const base = await new Promise((resolve, reject) => {
    let output = '';
    const timeout = setTimeout(() => reject(Error('Timed out starting demo server: ' + stderr)), 120000);
    const finish = (error, url) => { clearTimeout(timeout); if (error) reject(error); else resolve(url); };
    server.once('error', error => finish(error));
    server.once('exit', code => finish(Error(`Server exited (${code}): ${stderr}`)));
    server.stdout.on('data', chunk => {
      output += String(chunk);
      const match = output.match(/Aredoko demo: (http:\/\/127\.0\.0\.1:\d+)/);
      if (match) finish(null, match[1]);
    });
  });
  console.log(`UI test server: ${base} (temporary fixture)`);
  const test = spawn(process.execPath, ['tools/check-ui.cjs'], {
    cwd: root, env: {...process.env, AREDOKO_BASE_URL: base}, stdio: 'inherit', windowsHide: true
  });
  const [code, signal] = await once(test, 'exit');
  if (code !== 0) throw Error(`UI test failed (exit=${code}, signal=${signal})`);
  console.log('UI test passed. Temporary fixture will be removed.');
}

main().catch(error => { console.error(error); process.exitCode = 1; }).finally(async () => {
  if (server && server.exitCode === null) {
    server.kill();
    await Promise.race([once(server, 'exit'), new Promise(resolve => setTimeout(resolve, 5000))]);
  }
  try { rmSync(temp, {recursive: true, force: true}); }
  catch (error) { console.warn('Temporary DB cleanup: ' + error.message); }
});
