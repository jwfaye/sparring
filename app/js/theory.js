/* Interview mode: parameters on the setup screen, theory question, free-text answer, grading through the API (or offline recording), history by theme. */
(() => {
  'use strict';
  const { $, $$, PROFILE, loadJSON, saveJSON, escapeHtml, fmtTime, fmtDate, shuffle, renderMd, NS } = window.TT;
  const KEY = { prefs: NS + 'theory.prefs' };
  const api = path => '/api/theory/' + path + (PROFILE ? (path.includes('?') ? '&' : '?') + 'profile=' + encodeURIComponent(PROFILE) : '');
  const st = { questions: [], byId: {}, sections: [], history: [], status: { available: false, reason: '' }, current: null, fromHistory: false, timer: null, timerLeft: 0, started: 0, loaded: false };
  const SRC_LABEL = q => q.id.startsWith('fg-') ? 'AI engineering field guide' : 'data-science-interviews';

  async function load() {
    const [q, h, s] = await Promise.all([fetch(api('questions'), { cache: 'no-store' }), fetch(api('history'), { cache: 'no-store' }), fetch(api('status'), { cache: 'no-store' })]);
    if (!q.ok) throw new Error('HTTP ' + q.status);
    const qd = await q.json();
    st.questions = qd.items.filter(x => x && x.id && x.question);
    st.byId = Object.fromEntries(st.questions.map(x => [x.id, x]));
    const order = [];
    st.questions.forEach(x => { if (!order.includes(x.section)) order.push(x.section); });
    st.sections = order;
    st.history = (await h.json()).items || [];
    st.status = await s.json();
    st.loaded = true;
  }
  async function refreshHistory() { st.history = (await (await fetch(api('history'), { cache: 'no-store' })).json()).items || []; }
  function show(part) { ['home', 'question'].forEach(p => $('#th-' + p).classList.toggle('hidden', p !== part)); }
  const hasGrid = q => Array.isArray(q.key_points) && q.key_points.length > 0;
  const scoreOf = a => a.grade ? a.grade.score : null;

  // ------------------------------------------------------------ setup panel (#setup-theory) and history page (#th-home)
  function renderSetup() {
    if (!st.loaded) return;
    const prefs = loadJSON(KEY.prefs, { sections: [], onlyNew: true, timer: '180' });
    const counts = {};
    st.questions.forEach(q => counts[q.section] = (counts[q.section] || 0) + 1);
    const bySrc = { fg: [], ds: [] };
    st.sections.forEach(s => bySrc[st.questions.find(q => q.section === s).id.startsWith('fg-') ? 'fg' : 'ds'].push(s));
    const chip = s => `<label class="chip"><input type="checkbox" value="${escapeHtml(s)}" ${!prefs.sections.length || prefs.sections.includes(s) ? 'checked' : ''}> ${escapeHtml(s)} <span class="muted">${counts[s]}</span></label>`;
    $('#th-sections').innerHTML = `<div class="muted small">AI engineering field guide</div><div class="chips">${bySrc.fg.map(chip).join('')}</div>
      <div class="muted small">data-science-interviews (ML fundamentals)</div><div class="chips">${bySrc.ds.map(chip).join('')}</div>`;
    $('#th-only-new').checked = prefs.onlyNew !== false;
    $('#th-timer').value = String(prefs.timer ?? '180');
    const stb = $('#th-status');
    stb.className = 'status-line ' + (st.status.available ? 'ok' : 'off');
    stb.innerHTML = st.status.available
      ? `Online grading: ${escapeHtml(st.status.model)}`
      : `Offline mode: ${escapeHtml(st.status.reason)}`;
    $('#th-msg').textContent = '';
  }
  function renderHistory() {
    if (!st.loaded) return;
    const graded = st.history.filter(a => a.grade), pending = st.history.filter(a => !a.grade);
    const avg = graded.length ? (graded.reduce((s, a) => s + a.grade.score, 0) / graded.length).toFixed(1) : '–';
    const nGrid = st.questions.filter(hasGrid).length;
    $('#th-cards').innerHTML = [
      [st.questions.length, 'questions'], [nGrid, 'with a grid'], [new Set(st.history.map(a => a.qid)).size, 'questions answered'],
      [graded.length, 'graded'], [avg, 'average /10'], [pending.length, 'waiting for grading'],
    ].map(([v, l]) => `<div class="card"><div class="v">${v}</div><div class="l">${l}</div></div>`).join('');
    $('#th-pending-help').classList.toggle('hidden', !pending.length);

    const rows = st.sections.map(s => {
      const qs = st.questions.filter(q => q.section === s), ids = new Set(qs.map(q => q.id));
      const g = graded.filter(a => ids.has(a.qid)), done = new Set(st.history.filter(a => ids.has(a.qid)).map(a => a.qid)).size;
      const mean = g.length ? g.reduce((x, a) => x + a.grade.score, 0) / g.length : null;
      return { s, n: qs.length, done, graded: g.length, mean };
    });
    $('#th-themes').innerHTML = `<tr><th>Section</th><th>Questions</th><th>Answered</th><th>Graded</th><th>Average</th><th><span class="visually-hidden">Progress</span></th></tr>` +
      rows.map(r => `<tr><td>${escapeHtml(r.s)}</td><td>${r.n}</td><td>${r.done}</td><td>${r.graded}</td><td>${r.mean === null ? '–' : r.mean.toFixed(1)}</td>
        <td><div class="bar ${r.mean !== null && r.mean < 5 ? 'rate' : ''}"><span style="width:${r.mean === null ? 0 : r.mean * 10}%"></span></div></td></tr>`).join('');
    const weak = rows.filter(r => r.mean !== null).sort((a, b) => a.mean - b.mean).slice(0, 3);
    $('#th-weak').innerHTML = weak.length ? 'Weak spots: ' + weak.map(r => `<strong>${escapeHtml(r.s)}</strong> (${r.mean.toFixed(1)})`).join(', ') : '';

    $('#th-history').innerHTML = [...st.history].reverse().slice(0, 30).map(a => {
      const q = st.byId[a.qid] || {}, sc = scoreOf(a);
      return `<li data-id="${escapeHtml(a.id)}"><button type="button" class="th-item"><span class="muted">${fmtDate(a.at)}</span><span class="score-pill ${sc === null ? 'pending' : sc >= 7 ? 'good' : sc >= 4 ? 'mid' : 'bad'}">${sc === null ? 'pending' : sc + '/10'}</span><span class="t">${escapeHtml(q.question || a.qid)}</span><span class="muted small">${escapeHtml(q.section || '')}</span></button></li>`;
    }).join('') || '<li class="muted">No answer yet.</li>';
    $$('#th-history li[data-id]').forEach(li => $('.th-item', li).onclick = () => openAnswer(li.dataset.id));
  }
  const selectedSections = () => $$('#th-sections input:checked').map(i => i.value);

  // ------------------------------------------------------------ picking and showing a question
  function pickQuestion() {
    const secs = selectedSections(), onlyNew = $('#th-only-new').checked, timer = $('#th-timer').value;
    saveJSON(KEY.prefs, { sections: secs.length === st.sections.length ? [] : secs, onlyNew, timer });
    let pool = st.questions.filter(q => secs.includes(q.section));
    const answered = new Set(st.history.map(a => a.qid));
    if (onlyNew) { const fresh = pool.filter(q => !answered.has(q.id)); if (fresh.length) pool = fresh; }
    // prefer questions that have a grid (gradable)
    const withGrid = pool.filter(hasGrid);
    if (withGrid.length) pool = withGrid;
    if (!pool.length) { $('#th-msg').textContent = 'No question for this selection.'; return false; }
    showQuestion(shuffle(pool)[0].id);
    return true;
  }
  function showQuestion(qid) {
    const q = st.byId[qid]; st.current = { q, answerId: null }; st.fromHistory = false;
    show('question');
    $('#th-q-section').textContent = q.section;
    $('#th-q-source').textContent = SRC_LABEL(q) + (q.difficulty ? ' · ' + q.difficulty : '');
    $('#th-q-fr').textContent = q.question;
    $('#th-q-note').innerHTML = (q.uncertain ? `<div class="notice warn">Uncertain grid: ${escapeHtml(q.note || '')}</div>` : '') +
      (!hasGrid(q) ? `<div class="notice">No grid for this question yet: the answer will be saved without automatic grading.</div>` : '');
    $('#th-answer').value = ''; $('#th-answer').disabled = false;
    $('#th-result').classList.add('hidden'); $('#th-result').innerHTML = '';
    $('#th-actions').classList.remove('hidden'); $('#th-after').classList.add('hidden');
    $('#th-submit').textContent = st.status.available && hasGrid(q) ? 'Grade my answer' : 'Save (deferred grading)';
    $('#th-submit').disabled = false;
    startTimer(Number($('#th-timer').value || 0));
    $('#th-answer').focus();
    $('#th-question').scrollIntoView({ block: 'start' });
  }
  function startTimer(seconds) {
    stopTimer(); st.started = Date.now();
    const el = $('#th-clock'); el.className = 'clock';
    if (!seconds) { el.textContent = ''; return; }
    st.timerLeft = seconds; el.textContent = fmtTime(seconds);
    st.timer = setInterval(() => {
      st.timerLeft--; el.textContent = st.timerLeft >= 0 ? fmtTime(st.timerLeft) : '-' + fmtTime(-st.timerLeft);
      el.className = 'clock ' + (st.timerLeft < 0 ? 'over' : st.timerLeft <= 30 ? 'warning' : 'running');
    }, 1000);
  }
  function stopTimer() { if (st.timer) clearInterval(st.timer); st.timer = null; }

  async function submit() {
    const { q } = st.current; const answer = $('#th-answer').value;
    stopTimer();
    const btn = $('#th-submit'); btn.disabled = true; btn.textContent = 'Grading…';
    $('#th-answer').disabled = true;
    try {
      const r = await fetch(api('answer'), { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ qid: q.id, answer, duration: Math.round((Date.now() - st.started) / 1000), profile: PROFILE }) });
      const d = await r.json();
      await refreshHistory();
      if (d.record) st.current.answerId = d.record.id;
      renderResult(d.record, d.error);
    } catch (e) { renderResult(null, 'Server unreachable: ' + e.message); }
    $('#th-actions').classList.add('hidden'); $('#th-after').classList.remove('hidden');
  }
  function renderResult(rec, error) {
    const q = st.current.q, box = $('#th-result'); box.classList.remove('hidden');
    let html = '';
    if (error) html += `<div class="notice warn">${escapeHtml(error)}${rec ? ' Your answer is saved and can be graded later.' : ''}</div>`;
    if (rec && rec.grade) html += gradeHtml(rec.grade);
    else if (rec) html += `<div class="notice">Answer saved (offline mode). To have it graded with the same grid, ask me: <code>grade my pending interview answers</code>.</div>`;
    html += gridHtml(q);
    box.innerHTML = html;
    $('#th-toggle-grid')?.addEventListener('click', e => { const open = $('#th-grid').classList.toggle('hidden') === false; e.currentTarget.setAttribute('aria-expanded', String(open)); });
  }
  const list = (items, cls) => (items && items.length) ? `<ul class="pts ${cls}">${items.map(x => `<li>${escapeHtml(x)}</li>`).join('')}</ul>` : '';
  function gradeHtml(g) {
    const cls = g.score >= 7 ? 'good' : g.score >= 4 ? 'mid' : 'bad';
    return `<div class="grade">
      <div class="grade-head"><span class="score-big ${cls}">${g.score} / 10</span><span class="muted small">${escapeHtml(g.model || '')}</span></div>
      <div class="md">${renderMd(g.feedback || '')}</div>
      ${g.covered?.length ? '<h4>Covered points</h4>' + list(g.covered, 'ok') : ''}
      ${g.missing?.length ? '<h4>Missing points</h4>' + list(g.missing, 'miss') : ''}
      ${g.wrong?.length ? '<h4>Errors or imprecisions</h4>' + list(g.wrong, 'wrong') : ''}
      ${g.improved_answer ? `<h4>Improved version of your answer</h4><div class="improved md">${renderMd(g.improved_answer)}</div>` : ''}
    </div>`;
  }
  function gridHtml(q) {
    if (!hasGrid(q)) return '';
    return `<button class="btn small" id="th-toggle-grid" aria-expanded="false" aria-controls="th-grid">Reference answer and grid</button>
      <div id="th-grid" class="grid-box hidden">
        <h4>Reference answer</h4><div class="md">${renderMd(q.reference || '')}</div>
        <h4>Expected key points</h4>${list(q.key_points, 'plain')}
        <h4>Common mistakes</h4>${list(q.common_mistakes, 'plain')}
        <div class="muted small">Source: ${escapeHtml(q.source || '')}</div>
      </div>`;
  }
  function openAnswer(id) {
    const rec = st.history.find(a => a.id === id); if (!rec) return;
    const q = st.byId[rec.qid]; if (!q) return;
    st.current = { q, answerId: id }; st.fromHistory = true;
    show('question'); stopTimer();
    $('#th-q-section').textContent = q.section; $('#th-q-source').textContent = SRC_LABEL(q);
    $('#th-q-fr').textContent = q.question;
    $('#th-q-note').innerHTML = `<div class="muted small">Answered on ${fmtDate(rec.at)}${rec.duration ? ' · ' + fmtTime(rec.duration) : ''}</div>`;
    $('#th-answer').value = rec.answer; $('#th-answer').disabled = true; $('#th-clock').textContent = '';
    $('#th-actions').classList.add('hidden'); $('#th-after').classList.remove('hidden');
    renderResult(rec, null);
    $('#th-regrade').classList.toggle('hidden', !(st.status.available && !rec.grade && hasGrid(q)));
  }
  async function regrade() {
    const id = st.current?.answerId; if (!id) return;
    const b = $('#th-regrade'); b.disabled = true; b.textContent = 'Grading…';
    const r = await fetch(api('grade'), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ id, profile: PROFILE }) });
    const d = await r.json(); await refreshHistory();
    b.disabled = false; b.textContent = 'Grade now';
    renderResult(d.record || st.history.find(a => a.id === id), d.error);
    if (d.record) b.classList.add('hidden');
  }

  // ------------------------------------------------------------ init
  // Next or Skip: another question of the same selection; back to the setup screen when it has none left to give.
  const nextQuestion = () => { stopTimer(); if (!pickQuestion()) window.TTAPP.openSetup(); };
  $('#th-next2').onclick = nextQuestion;
  $('#th-submit').onclick = submit;
  $('#th-skip').onclick = nextQuestion;
  // Back: to the history page when the answer was reopened from it, else to the setup screen.
  $('#th-back').onclick = () => { if (st.fromHistory) { leave(); openHistory(); } else window.TTAPP.openSetup(); };
  $('#th-regrade').onclick = regrade;
  $('#th-all').onclick = () => { const boxes = $$('#th-sections input'); const all = boxes.every(b => b.checked); boxes.forEach(b => b.checked = !all); };
  $('#th-answer').addEventListener('keydown', e => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey) && !$('#th-actions').classList.contains('hidden')) { e.preventDefault(); submit(); } });
  function leave() { stopTimer(); st.current = null; }
  async function openHistory() {
    renderHistory(); show('home');
    try { await refreshHistory(); } catch (e) { console.warn(e); }
    renderHistory();
  }
  // start: a question from the setup panel (false when the selection is empty); openHistory: the history page; leave: stop the timer.
  window.TTTHEORY = {
    start: () => { stopTimer(); return pickQuestion(); },
    openHistory,
    leave,
    state: st,
  };
  load().then(() => { renderSetup(); renderHistory(); show('home'); }).catch(e => { $('#th-msg').textContent = 'Interview unavailable: ' + e.message; $('#th-home').innerHTML = `<h2>Interview unavailable</h2><p>${escapeHtml(e.message)}</p>`; });
})();
