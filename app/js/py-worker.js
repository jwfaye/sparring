/* Pyodide runtime worker (SP-PY-RUNTIME): loads Python once, then runs harness payloads off the main thread.
   Messages in:  {id, action: "init", interruptBuffer}  |  {id, action: "run", payload}
   Messages out: {id, status}  |  {id, ok: true, result}  |  {id, ok: false, error, interrupted} */
'use strict';

const PYODIDE_URL = 'https://cdn.jsdelivr.net/pyodide/v0.27.7/full/';
const HARNESS_URL = new URL('../py/harness.py', self.location.href).href;

let pyodide = null;

importScripts(PYODIDE_URL + 'pyodide.js');

async function init(msg) {
  self.postMessage({ id: msg.id, status: 'Loading Python (Pyodide)… about 20 s the first time' });
  pyodide = await loadPyodide({ indexURL: PYODIDE_URL });
  if (msg.interruptBuffer) pyodide.setInterruptBuffer(msg.interruptBuffer);
  self.postMessage({ id: msg.id, status: 'Loading pandas, numpy, sqlite3…' });
  await pyodide.loadPackage(['numpy', 'pandas', 'sqlite3']);
  const res = await fetch(HARNESS_URL, { cache: 'no-store' });
  if (!res.ok) throw new Error('harness.py: HTTP ' + res.status);
  pyodide.runPython(await res.text());
  return { ready: true };
}

function run(msg) {
  if (!pyodide) throw new Error('Python is not loaded');
  pyodide.globals.set('_payload', JSON.stringify(msg.payload));
  return JSON.parse(pyodide.runPython('run_json(_payload)'));
}

self.onmessage = async ev => {
  const msg = ev.data || {};
  try {
    const result = msg.action === 'init' ? await init(msg) : msg.action === 'run' ? run(msg) : null;
    if (result === null) throw new Error('Unknown action: ' + msg.action);
    self.postMessage({ id: msg.id, ok: true, result });
  } catch (e) {
    const interrupted = !!(e && e.type === 'KeyboardInterrupt');
    self.postMessage({ id: msg.id, ok: false, error: String(e && e.message || e), interrupted });
  }
};
