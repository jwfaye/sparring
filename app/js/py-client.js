/* Pyodide client (SP-PY-RUNTIME): talks to js/py-worker.js, resolves one promise per message id, and interrupts
   a run on Stop or after RUN_TIMEOUT_MS. With cross-origin isolation the interrupt is cooperative (SharedArrayBuffer
   + Pyodide's interrupt buffer); otherwise, or when the interrupt is not honored within INTERRUPT_GRACE_MS, the
   worker is terminated and Python reloaded. */
(() => {
  'use strict';

  const WORKER_URL = 'js/py-worker.js';
  const RUN_TIMEOUT_MS = 20000;
  const INTERRUPT_GRACE_MS = 2000;
  const SIGINT = 2;

  const state = {
    worker: null, nextId: 1, pending: new Map(), buffer: null, ready: false, current: null, onStatus: () => {},
  };
  const now = () => Date.now();

  function setStatus(text, cls) { state.onStatus(text, cls || 'loading'); }

  function makeBuffer() {
    if (!self.crossOriginIsolated || typeof SharedArrayBuffer === 'undefined') return null;
    return new Uint8Array(new SharedArrayBuffer(1));
  }

  function post(action, extra) {
    return new Promise((resolve, reject) => {
      const id = state.nextId++;
      state.pending.set(id, { resolve, reject });
      state.worker.postMessage({ id, action, ...extra });
    });
  }

  function onMessage(ev) {
    const msg = ev.data || {};
    const p = state.pending.get(msg.id);
    if (!p) return;
    if (msg.status !== undefined) { setStatus(msg.status); return; }
    state.pending.delete(msg.id);
    if (state.current && state.current.id === msg.id) finishRun(msg);
    else if (msg.ok) p.resolve(msg.result);
    else p.reject(new Error(msg.error));
  }

  function interruptedResult(reason, elapsedMs, restarted) {
    const n = Math.round(elapsedMs / 1000);
    const why = reason === 'timeout' ? 'time limit of ' + RUN_TIMEOUT_MS / 1000 + ' s' : 'Stop button';
    let error = 'Execution interrupted after ' + n + ' s (' + why + ').';
    if (restarted) error += '\nPython was restarted; the next run starts once it is ready.';
    return { interrupted: true, error, output: '', ok: false, tests: [] };
  }

  function finishRun(msg) {
    const run = state.current;
    state.current = null;
    clearTimeout(run.timeoutTimer); clearTimeout(run.graceTimer);
    if (state.buffer) state.buffer[0] = 0;
    if (msg.ok) run.resolve(msg.result);
    else if (msg.interrupted && run.stopReason) run.resolve(interruptedResult(run.stopReason, now() - run.startedAt, false));
    else run.reject(new Error(msg.error));
  }

  function spawn() {
    state.worker = new Worker(WORKER_URL);
    state.worker.onmessage = onMessage;
    state.worker.onerror = ev => {
      const err = new Error(ev.message || 'Python worker error');
      if (ev.preventDefault) ev.preventDefault();
      console.error(err);
      if (state.ready) restart(err);
      else fail(err);
    };
  }

  // The worker died while loading (script blocked, CDN unreachable): report, do not loop on restarts.
  function fail(err) {
    if (state.worker) { state.worker.onerror = null; state.worker.terminate(); state.worker = null; }
    for (const p of state.pending.values()) p.reject(err);
    state.pending.clear();
  }

  // Terminate the worker, settle every pending promise, and load Python again.
  function restart(err) {
    const run = state.current;
    state.current = null;
    if (state.worker) { state.worker.onerror = null; state.worker.terminate(); }
    if (run) {
      clearTimeout(run.timeoutTimer); clearTimeout(run.graceTimer);
      state.pending.delete(run.id);
      if (run.stopReason) run.resolve(interruptedResult(run.stopReason, now() - run.startedAt, true));
      else run.reject(err || new Error('Python was restarted'));
    }
    for (const p of state.pending.values()) p.reject(err || new Error('Python was restarted'));
    state.pending.clear();
    load('Restarting Python…').catch(() => {});
  }

  async function load(firstStatus) {
    state.ready = false;
    setStatus(firstStatus);
    try {
      state.buffer = makeBuffer();
      spawn();
      await post('init', { interruptBuffer: state.buffer });
      state.ready = true;
      setStatus('Python ready', 'ok');
    } catch (e) {
      console.error(e);
      setStatus('Python unavailable: ' + e.message, 'err');
      throw e;
    }
  }

  function init(onStatus) {
    state.onStatus = onStatus || (() => {});
    return load('Loading Python…');
  }

  function run(payload) {
    if (!state.ready || state.current) return Promise.reject(new Error(state.current ? 'A run is in progress' : 'Python is not ready'));
    return new Promise((resolve, reject) => {
      const id = state.nextId++;
      const entry = { id, resolve, reject, startedAt: now(), stopReason: null, timeoutTimer: null, graceTimer: null };
      state.current = entry;
      state.pending.set(id, entry);
      if (state.buffer) state.buffer[0] = 0;
      entry.timeoutTimer = setTimeout(() => stop('timeout'), RUN_TIMEOUT_MS);
      state.worker.postMessage({ id, action: 'run', payload });
    });
  }

  function stop(reason) {
    const run = state.current;
    if (!run || run.stopReason) return;
    run.stopReason = reason || 'stop';
    clearTimeout(run.timeoutTimer);
    if (!state.buffer) { restart(); return; }
    state.buffer[0] = SIGINT;
    run.graceTimer = setTimeout(() => { if (state.current === run) restart(); }, INTERRUPT_GRACE_MS);
  }

  window.TTPY = {
    init, run, stop, isReady: () => state.ready, isRunning: () => !!state.current,
    hasInterrupt: () => !!state.buffer, RUN_TIMEOUT_MS, INTERRUPT_GRACE_MS,
  };
})();
