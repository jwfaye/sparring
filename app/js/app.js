/* Training app, step 1: exercise engine (Python via Pyodide in a worker, SQL via sqlite3). */
(() => {
  'use strict';

  const { $, $$, NS, selectTab, loadJSON, saveJSON, escapeHtml, fmtTime, shuffle, inline, renderMd, twoClick } = window.TT;
  const LS = { progress: NS + 'progress', settings: NS + 'settings', exam: NS + 'exam', order: NS + 'order', lastId: NS + 'lastId' };
  const DIFF_RANK = { easy: 0, medium: 1, hard: 2 };

  const state = {
    bank: [], byId: {}, order: [], idx: -1, current: null,
    progress: {}, settings: { examMinutes: 45 }, exam: null,
    pyReady: false, busy: false, editor: null, view: 'exercises', outputCollapsed: false,
    pendingConfirm: null,
  };
  const nextPaint = () => new Promise(r => setTimeout(r, 30));

  // ------------------------------------------------------------ progress
  function prog(id) {
    if (!state.progress[id]) state.progress[id] = { code: null, status: 'todo', attempts: 0, time: 0, solutionSeen: false, hintsUsed: 0, lastCheck: null };
    return state.progress[id];
  }
  const saveProgress = () => saveJSON(LS.progress, state.progress);
  const statusIcon = st => ({ ok: '<span class="st-ok" aria-hidden="true">✓</span>', fail: '<span class="st-fail" aria-hidden="true">✗</span>' }[st] || '<span class="st-todo" aria-hidden="true">○</span>');
  const statusWord = st => ({ ok: 'solved', fail: 'failed' }[st] || 'to do');

  // ------------------------------------------------------------ filters & order
  const filters = () => ({ theme: $('#f-theme').value, difficulty: $('#f-difficulty').value, language: $('#f-language').value });
  function pool() {
    const f = filters();
    return state.bank.filter(e => (!f.theme || e.theme === f.theme) && (!f.difficulty || e.difficulty === f.difficulty) && (!f.language || e.language === f.language));
  }
  // Draw the undone exercises while alternating themes, then the ones already solved.
  function buildOrder() {
    const p = pool();
    const todo = shuffle(p.filter(e => prog(e.id).status !== 'ok'));
    const done = p.filter(e => prog(e.id).status === 'ok');
    const byTheme = {};
    todo.forEach(e => (byTheme[e.theme] ||= []).push(e));
    const themes = shuffle(Object.keys(byTheme));
    const out = [];
    while (themes.some(t => byTheme[t].length)) for (const t of themes) if (byTheme[t].length) out.push(byTheme[t].shift());
    return [...out, ...done].map(e => e.id);
  }
  function restoreOrCreateOrder(force = false) {
    const key = JSON.stringify(filters());
    const saved = loadJSON(LS.order, null, sessionStorage);
    if (!force && saved && saved.key === key && saved.ids.every(id => state.byId[id])) {
      state.order = saved.ids;
    } else {
      state.order = buildOrder();
      saveJSON(LS.order, { key, ids: state.order }, sessionStorage);
    }
  }

  // ------------------------------------------------------------ editor
  function initEditor() {
    state.editor = CodeMirror.fromTextArea($('#editor'), {
      mode: 'python', theme: 'default', lineNumbers: true, indentUnit: 4, tabSize: 4,
      smartIndent: true, indentWithTabs: false, matchBrackets: true, autoCloseBrackets: true, lineWrapping: false, scrollPastEnd: true,
      extraKeys: {
        'Ctrl-Enter': onRun, 'Cmd-Enter': onRun,
        'Shift-Ctrl-Enter': onCheck, 'Shift-Cmd-Enter': onCheck,
        'Ctrl-/': cm => cm.toggleComment(), 'Cmd-/': cm => cm.toggleComment(),
        'Tab': cm => cm.somethingSelected() ? cm.indentSelection('add') : cm.replaceSelection('    ', 'end'),
        'Shift-Tab': cm => cm.indentSelection('subtract'),
        'Esc': cm => cm.getInputField().blur(),
      },
    });
    state.editor.getInputField().setAttribute('aria-label', 'Code editor (Escape, then Tab, leaves it)');
    let t = null;
    state.editor.on('change', () => { clearTimeout(t); t = setTimeout(saveCode, 400); });
  }
  const getCode = () => state.editor.getValue();
  function saveCode() {
    if (!state.current) return;
    prog(state.current.id).code = getCode();
    saveProgress();
  }

  // ------------------------------------------------------------ navigation
  function showExercise(idx) {
    saveCode();
    state.idx = idx;
    const ex = state.byId[state.order[idx]];
    state.current = ex || null;
    state.pendingConfirm = null;
    if (ex) saveJSON(LS.lastId, ex.id, sessionStorage);
    renderList();
    renderStatement();
    $('#output').textContent = ''; $('#output').classList.remove('error');
    $('#results').innerHTML = '';
    $('#output-title').textContent = 'Output';
    layoutOutput();
    $('#btn-prev').disabled = idx <= 0;
    $('#btn-next').disabled = idx >= state.order.length - 1;
    if (ex) {
      const p = prog(ex.id);
      state.editor.setOption('mode', ex.language === 'sql' ? 'text/x-sql' : 'python');
      state.editor.setValue(p.code ?? ex.starter);
      state.editor.clearHistory();
      state.editor.focus();
      updateExTimer();
    } else {
      state.editor.setValue('');
    }
  }
  function gotoId(id) { const i = state.order.indexOf(id); if (i >= 0) showExercise(i); }

  function renderList() {
    const ol = $('#ex-list');
    if (!state.order.length) { ol.innerHTML = '<li class="empty">No exercise matches these filters.</li>'; return; }
    ol.innerHTML = state.order.map((id, i) => {
      const e = state.byId[id], p = prog(id);
      return `<li data-i="${i}" class="${i === state.idx ? 'active' : ''}" title="${escapeHtml(e.title)}">
        <button type="button" class="ex-item" ${i === state.idx ? 'aria-current="true"' : ''}>
        <span class="st">${statusIcon(p.status)}</span><span class="visually-hidden">${statusWord(p.status)}</span>
        <span class="t">${escapeHtml(e.title)}</span>
        <span class="d">${escapeHtml(e.language === 'sql' ? 'SQL' : 'py')} · ${escapeHtml(e.difficulty[0])}</span></button></li>`;
    }).join('');
  }

  function renderStatement() {
    const box = $('#statement');
    const ex = state.current;
    if (!ex) {
      const all = state.bank.length, p = pool().length;
      box.innerHTML = p === 0 && all > 0
        ? `<h2>No exercise</h2><p>No exercise matches the filters. Widen the filters or ask me to generate some: <code>generate N X exercises on the theme Y</code>.</p>`
        : `<h2>Empty bank</h2><p>No exercise loaded. Check that <code>bank/exercises/*.json</code> exists and that the server is running.</p>`;
      return;
    }
    const p = prog(ex.id);
    const todoLeft = state.order.filter(id => prog(id).status !== 'ok').length;
    const exhausted = todoLeft === 0
      ? `<div class="exhausted">Every exercise in this selection is solved. To get more, ask me: <code>generate 10 medium exercises on the theme merge</code> (or any theme / difficulty), then reload the page.</div>`
      : '';
    box.innerHTML = `${exhausted}
      <h2>${escapeHtml(ex.title)}</h2>
      <div class="badges">
        <span class="badge">${escapeHtml(ex.language === 'sql' ? 'SQL (SQLite)' : 'Python / pandas')}</span>
        <span class="badge ${escapeHtml(ex.difficulty)}">${escapeHtml(ex.difficulty)}</span>
        <span class="badge">${escapeHtml(ex.theme)}</span>
        <span class="badge">${state.idx + 1} / ${state.order.length}</span>
      </div>
      <div class="md">${renderMd(ex.statement)}</div>
      <div class="meta">
        <span>Status: ${statusIcon(p.status)} ${statusWord(p.status)}</span>
        <span>Attempts: ${p.attempts}</span>
        <span>Time: <span id="meta-time">${fmtTime(p.time)}</span></span>
        ${p.hintsUsed ? `<span>Hints: ${p.hintsUsed}</span>` : ''}
        ${p.solutionSeen ? '<span>Solution viewed</span>' : ''}
      </div>
      <div class="hint-box" id="hint-box"></div>
      <div class="solution-box" id="solution-box"></div>`;
    renderHintBox();
    renderSolutionBox();
  }

  function renderHintBox() {
    const box = $('#hint-box'); if (!box || !state.current) return;
    const hints = state.current.hints || [];
    if (!hints.length) { box.innerHTML = ''; return; }
    const p = prog(state.current.id), n = Math.min(p.hintsUsed || 0, hints.length);
    box.innerHTML = hints.slice(0, n).map((h, i) => `<div class="hint">Hint ${i + 1}: ${inline(h)}</div>`).join('') +
      (n < hints.length ? `<button class="btn small" id="hint-next">Hint ${n + 1} / ${hints.length}</button>` : '');
    const b = $('#hint-next');
    if (b) b.onclick = () => { p.hintsUsed = n + 1; saveProgress(); renderStatement(); };
  }

  function renderSolutionBox() {
    const box = $('#solution-box'); if (!box || !state.current) return;
    const ex = state.current;
    if (state.pendingConfirm === 'solution') {
      box.innerHTML = `<div class="confirm">Show the solution? The exercise will be marked "solution viewed" in the summary.
        <br><button class="btn warn small" id="sol-yes">Yes, show it</button><button class="btn small" id="sol-no">Cancel</button></div>`;
      $('#sol-yes').onclick = () => { prog(ex.id).solutionSeen = true; saveProgress(); state.pendingConfirm = 'shown'; renderStatement(); };
      $('#sol-no').onclick = () => { state.pendingConfirm = null; renderSolutionBox(); };
    } else if (state.pendingConfirm === 'shown') {
      box.innerHTML = `<h4>Solution</h4><pre tabindex="0"><code>${escapeHtml(ex.solution)}</code></pre>
        <button class="btn small" id="sol-copy">Copy into the editor</button> <button class="btn small" id="sol-hide" aria-expanded="true" aria-controls="solution-box">Hide</button>`;
      $('#sol-copy').onclick = () => { state.editor.setValue(ex.solution); saveCode(); };
      $('#sol-hide').onclick = () => { state.pendingConfirm = null; renderSolutionBox(); };
    } else {
      box.innerHTML = `<button class="btn small" id="sol-show" aria-expanded="false" aria-controls="solution-box">Show the solution</button>`;
      $('#sol-show').onclick = () => { state.pendingConfirm = 'solution'; renderSolutionBox(); };
    }
  }

  // ------------------------------------------------------------ Python / execution (SP-PY-RUNTIME: js/py-client.js)
  function setStatus(text, cls) {
    const el = $('#py-status'); el.textContent = text; el.className = 'status ' + (cls || 'loading'); el.title = text;
    state.pyReady = cls === 'ok';
  }
  async function initPython() {
    try { await window.TTPY.init(setStatus); } catch (e) { console.error(e); }
  }
  // Resolves with the harness result; an interrupted run resolves with {interrupted, error} (see py-client.js).
  function runPy(payload) {
    $('#btn-stop').disabled = false;
    return window.TTPY.run(payload).finally(() => { $('#btn-stop').disabled = true; });
  }
  function onStop() { window.TTPY.stop('stop'); }
  function ready() {
    if (!state.current) return false;
    if (!state.pyReady) { setOutput('Python is still loading…', true); return false; }
    if (state.busy) return false;
    return true;
  }
  function setOutput(text, isError) {
    const o = $('#output'); o.textContent = text || ''; o.classList.toggle('error', !!isError);
    layoutOutput();
  }
  // Output pane collapsed while empty; expanded as soon as there is something to show.
  function layoutOutput(force) {
    const pane = $('#output-pane');
    const empty = !$('#output').textContent && !$('#results').innerHTML.trim();
    const collapsed = force === undefined ? (empty || state.outputCollapsed) : force;
    pane.classList.toggle('collapsed', collapsed);
    $('#output-caret').textContent = collapsed ? '▸' : '▾';
    $('#output-head').setAttribute('aria-expanded', String(!collapsed));
    if (state.editor) setTimeout(() => state.editor.refresh(), 0);
  }
  function initSplitter() {
    const pane = $('#output-pane'), sp = $('#splitter'), parent = $('.editor-pane');
    const setHeight = h => { pane.style.setProperty('--out-h', h + 'px'); state.settings.outputHeight = Math.round(h); sp.setAttribute('aria-valuenow', String(Math.round(h))); };
    if (state.settings.outputHeight) setHeight(state.settings.outputHeight);
    sp.addEventListener('mousedown', ev => {
      ev.preventDefault(); sp.classList.add('dragging'); state.outputCollapsed = false; layoutOutput(false);
      const onMove = e => {
        const rect = parent.getBoundingClientRect();
        const h = Math.max(60, Math.min(rect.bottom - e.clientY - 4, rect.height - 150));
        setHeight(h);
      };
      const onUp = () => { sp.classList.remove('dragging'); document.removeEventListener('mousemove', onMove); document.removeEventListener('mouseup', onUp); saveJSON(LS.settings, state.settings); state.editor.refresh(); };
      document.addEventListener('mousemove', onMove); document.addEventListener('mouseup', onUp);
    });
    $('#output-head').addEventListener('click', () => { state.outputCollapsed = !pane.classList.contains('collapsed'); layoutOutput(state.outputCollapsed); });
    // Keyboard alternative to the drag: the arrow keys resize the output pane by 20 px.
    sp.addEventListener('keydown', e => {
      const step = { ArrowUp: 20, ArrowDown: -20 }[e.key];
      if (!step) return;
      e.preventDefault(); state.outputCollapsed = false; layoutOutput(false);
      const h = Math.max(60, Math.min(pane.getBoundingClientRect().height + step, parent.getBoundingClientRect().height - 150));
      setHeight(h); saveJSON(LS.settings, state.settings); state.editor.refresh();
    });
  }

  async function onRun() {
    if (!ready()) return;
    const ex = state.current; saveCode();
    state.busy = true; $('#btn-run').disabled = true;
    $('#output-title').textContent = 'Output'; $('#results').innerHTML = ''; state.outputCollapsed = false;
    setOutput('Running…'); await nextPaint();
    try {
      const r = await runPy({ mode: 'run', language: ex.language, setup: ex.setup, code: getCode(), run_call: ex.run_call || null });
      let text = r.output || '';
      if (r.error) text += (text && !text.endsWith('\n') ? '\n' : '') + (text ? '\n' : '') + r.error;
      if (!text) text = '(no output: use print(...) to display something)';
      setOutput(text, !!r.error);
    } catch (e) { setOutput('Error: ' + e.message, true); }
    finally { state.busy = false; $('#btn-run').disabled = false; state.editor.focus(); }
  }

  async function onCheck() {
    if (!ready()) return;
    const ex = state.current; saveCode();
    state.busy = true; $('#btn-check').disabled = true;
    $('#output-title').textContent = 'Check'; state.outputCollapsed = false; $('#results').innerHTML = '<div class="muted">Running tests…</div>'; setOutput('');
    await nextPaint();
    try {
      const r = await runPy({ mode: 'check', language: ex.language, setup: ex.setup, code: getCode(), tests: ex.tests });
      const p = prog(ex.id);
      p.attempts += 1; p.lastCheck = Date.now();
      if (r.error) { setOutput(r.error, true); $('#results').innerHTML = ''; p.status = 'fail'; }
      else {
        p.status = r.ok ? 'ok' : 'fail';
        const n = r.tests.length, nOk = r.tests.filter(t => t.ok).length;
        $('#results').innerHTML = `<div class="verdict ${r.ok ? 'ok' : 'fail'}">${r.ok ? 'OK' : 'FAIL'} · ${nOk}/${n} test(s) passed</div>` +
          r.tests.map(t => `<details class="result ${t.ok ? 'ok' : 'fail'}" ${t.ok ? '' : 'open'}>
            <summary><span class="mark">${t.ok ? '✓' : '✗'}</span>${escapeHtml(t.name)}</summary>
            ${t.ok ? '' : `<pre tabindex="0">${escapeHtml(t.message || '')}${t.stdout ? '\n\n--- standard output during this test ---\n' + escapeHtml(t.stdout) : ''}</pre>`}
          </details>`).join('');
      }
      saveProgress(); renderList(); renderStatement(); layoutOutput();
    } catch (e) { setOutput('Error: ' + e.message, true); }
    finally { state.busy = false; $('#btn-check').disabled = false; state.editor.focus(); }
  }

  // ------------------------------------------------------------ timers
  function updateExTimer() {
    if (!state.current) return;
    const t = prog(state.current.id).time;
    $('#ex-timer').textContent = fmtTime(t);
    const m = $('#meta-time'); if (m) m.textContent = fmtTime(t);
  }
  let tickCount = 0;
  function tick() {
    if (state.view === 'exercises' && state.current && document.visibilityState === 'visible') {
      prog(state.current.id).time += 1;
      updateExTimer();
      if (++tickCount % 10 === 0) saveProgress();
    }
    renderExam();
  }
  function renderExam() {
    const clock = $('#exam-clock'), btn = $('#exam-toggle'), banner = $('#exam-banner');
    if (!state.exam) {
      clock.textContent = fmtTime(Number($('#exam-minutes').value || 45) * 60);
      clock.className = 'clock'; btn.textContent = 'Start'; banner.classList.add('hidden');
      return;
    }
    const left = Math.round((state.exam.endsAt - Date.now()) / 1000);
    clock.textContent = left >= 0 ? fmtTime(left) : '-' + fmtTime(-left);
    clock.className = 'clock ' + (left < 0 ? 'over' : left < 300 ? 'warning' : 'running');
    btn.textContent = 'Stop';
    banner.classList.toggle('hidden', left >= 0);
  }
  function toggleExam() {
    if (state.exam) { state.exam = null; }
    else {
      const minutes = Math.max(1, Number($('#exam-minutes').value || 45));
      state.settings.examMinutes = minutes; saveJSON(LS.settings, state.settings);
      state.exam = { startedAt: Date.now(), endsAt: Date.now() + minutes * 60000, minutes };
    }
    saveJSON(LS.exam, state.exam); renderExam();
  }

  // ------------------------------------------------------------ recap
  function renderRecap() {
    const items = state.bank;
    const P = items.map(e => ({ e, p: prog(e.id) }));
    const nOk = P.filter(x => x.p.status === 'ok').length, nFail = P.filter(x => x.p.status === 'fail').length;
    const total = P.reduce((s, x) => s + x.p.time, 0), attempts = P.reduce((s, x) => s + x.p.attempts, 0);
    $('#recap-summary').innerHTML = [
      [items.length, 'exercises'], [nOk, 'solved'], [nFail, 'failing'], [items.length - nOk - nFail, 'not attempted'],
      [attempts, 'checks'], [fmtTime(total), 'total time'],
    ].map(([v, l]) => `<div class="card"><div class="v">${v}</div><div class="l">${l}</div></div>`).join('');

    const themes = {};
    P.forEach(({ e, p }) => { const t = themes[e.theme] ||= { n: 0, ok: 0, time: 0, solution: 0 }; t.n++; if (p.status === 'ok') t.ok++; t.time += p.time; if (p.solutionSeen) t.solution++; });
    $('#recap-themes').innerHTML = `<tr><th>Theme</th><th>Solved</th><th>Progress</th><th>Time</th><th>Solutions viewed</th></tr>` +
      Object.entries(themes).sort().map(([t, v]) => `<tr><td>${escapeHtml(t)}</td><td>${v.ok} / ${v.n}</td><td><div class="bar"><span style="width:${v.n ? 100 * v.ok / v.n : 0}%"></span></div></td><td>${fmtTime(v.time)}</td><td>${v.solution}</td></tr>`).join('');

    const sorted = [...P].sort((a, b) => (a.e.theme.localeCompare(b.e.theme)) || (DIFF_RANK[a.e.difficulty] - DIFF_RANK[b.e.difficulty]));
    $('#recap-exercises').innerHTML = `<tr><th><span class="visually-hidden">Status</span></th><th>Exercise</th><th>Theme</th><th>Difficulty</th><th>Language</th><th>Attempts</th><th>Time</th><th>Hints</th><th>Solution</th></tr>` +
      sorted.map(({ e, p }) => `<tr class="clickable" data-id="${escapeHtml(e.id)}"><td>${statusIcon(p.status)}<span class="visually-hidden">${statusWord(p.status)}</span></td><td>${escapeHtml(e.title)}</td><td>${escapeHtml(e.theme)}</td><td class="${escapeHtml(e.difficulty)}">${escapeHtml(e.difficulty)}</td><td>${e.language}</td><td>${p.attempts}</td><td>${fmtTime(p.time)}</td><td>${p.hintsUsed || ''}</td><td>${p.solutionSeen ? 'viewed' : ''}</td></tr>`).join('');
    $$('#recap-exercises tr.clickable').forEach(tr => tr.onclick = () => {
      const id = tr.dataset.id;
      if (!state.order.includes(id)) { $('#f-theme').value = ''; $('#f-difficulty').value = ''; $('#f-language').value = ''; restoreOrCreateOrder(true); }
      switchView('exercises'); gotoId(id);
    });
  }
  function switchView(v) {
    state.view = v;
    selectTab(v);
    $('#view-exercises').classList.toggle('hidden', v !== 'exercises');
    $('#view-recap').classList.toggle('hidden', v !== 'recap');
    $('#view-qcm').classList.toggle('hidden', v !== 'qcm');
    $('#view-theory').classList.toggle('hidden', v !== 'theory');
    if (v === 'recap') { saveCode(); renderRecap(); }
    else if (v === 'qcm') { saveCode(); if (window.TTQCM) window.TTQCM.open(); }
    else if (v === 'theory') { saveCode(); if (window.TTTHEORY) window.TTTHEORY.open(); }
    else if (state.editor) state.editor.refresh();
  }

  // ------------------------------------------------------------ init
  async function loadBank() {
    const r = await fetch('/api/exercises', { cache: 'no-store' });
    if (!r.ok) throw new Error('HTTP ' + r.status);
    const data = await r.json();
    if (data.errors?.length) console.warn('Ignored bank files:', data.errors);
    state.bank = data.items.filter(e => e && e.id);
    state.byId = Object.fromEntries(state.bank.map(e => [e.id, e]));
    const themes = [...new Set(state.bank.map(e => e.theme))].sort();
    $('#f-theme').innerHTML = '<option value="">All themes</option>' + themes.map(t => `<option value="${escapeHtml(t)}">${escapeHtml(t)}</option>`).join('');
  }

  async function main() {
    window.tt = state;
    state.progress = loadJSON(LS.progress, {});
    state.settings = { examMinutes: 45, ...loadJSON(LS.settings, {}) };
    state.exam = loadJSON(LS.exam, null);
    $('#exam-minutes').value = state.settings.examMinutes;
    initEditor();

    $('#btn-run').onclick = onRun;
    $('#btn-check').onclick = onCheck;
    $('#btn-stop').onclick = onStop;
    $('#btn-prev').onclick = () => state.idx > 0 && showExercise(state.idx - 1);
    $('#btn-next').onclick = () => state.idx < state.order.length - 1 && showExercise(state.idx + 1);
    twoClick($('#btn-reset'), 'Reset', () => { if (state.current) { state.editor.setValue(state.current.starter); saveCode(); state.editor.focus(); } });
    initSplitter();
    $('#exam-toggle').onclick = toggleExam;
    $('#exam-minutes').onchange = () => { state.settings.examMinutes = Number($('#exam-minutes').value); saveJSON(LS.settings, state.settings); renderExam(); };
    $$('.tab').forEach(t => t.onclick = () => switchView(t.dataset.view));
    $('#ex-list').onclick = ev => { const li = ev.target.closest('li[data-i]'); if (li) showExercise(Number(li.dataset.i)); };
    ['#f-theme', '#f-difficulty', '#f-language'].forEach(s => $(s).onchange = () => { restoreOrCreateOrder(true); showExercise(state.order.length ? 0 : -1); });
    $('#reshuffle').onclick = () => { restoreOrCreateOrder(true); showExercise(state.order.length ? 0 : -1); };
    $('#btn-export').onclick = () => {
      const blob = new Blob([JSON.stringify({ exportedAt: new Date().toISOString(), progress: state.progress }, null, 2)], { type: 'application/json' });
      const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = 'progress.json'; a.click();
    };
    twoClick($('#btn-reset-progress'), 'Reset progress', () => { state.progress = {}; saveProgress(); restoreOrCreateOrder(true); renderRecap(); showExercise(state.order.length ? 0 : -1); });
    window.addEventListener('beforeunload', () => { saveCode(); saveProgress(); });
    setInterval(tick, 1000);
    renderExam();

    try { await loadBank(); } catch (e) { $('#statement').innerHTML = `<h2>Bank unreachable</h2><p>${escapeHtml(e.message)}. Run <code>python server.py</code> and open the printed URL.</p>`; }
    restoreOrCreateOrder();
    // Resume where we left off: the last exercise seen, otherwise the first one.
    const lastId = loadJSON(LS.lastId, null, sessionStorage);
    const startIdx = lastId && state.order.includes(lastId) ? state.order.indexOf(lastId) : 0;
    showExercise(state.order.length ? startIdx : -1);
    await initPython();
  }

  document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'hidden') { saveCode(); saveProgress(); } });
  main();
})();
