/* Quiz tab: one question at a time, explanation, score, error history by theme. */
(() => {
  'use strict';
  const { $, $$, NS, loadJSON, saveJSON, escapeHtml, shuffle, renderMd, twoClick, fmtDate } = window.TT;
  const KEY = { history: NS + 'qcm.history', sessions: NS + 'qcm.sessions', prefs: NS + 'qcm.prefs' };
  const LABELS = {
    regression: 'Regression', validation: 'Validation', classification: 'Classification', regularization: 'Regularization',
    'trees-ensembles': 'Trees & ensembles', 'neural-networks': 'Neural networks', nlp: 'NLP', clustering: 'Clustering',
    'dimensionality-reduction': 'Dimensionality reduction', 'recommender-systems': 'Recommender systems & ranking', 'time-series': 'Time series',
    python: 'Python', pandas: 'pandas', sql: 'SQL', git: 'git',
  };
  const label = t => LABELS[t] || t;
  const st = { bank: [], byId: {}, themes: [], history: {}, sessions: [], session: null, loaded: false };

  async function load() {
    const r = await fetch('/api/qcm', { cache: 'no-store' });
    if (!r.ok) throw new Error('HTTP ' + r.status);
    const d = await r.json();
    if (d.errors?.length) console.warn('Ignored quiz files:', d.errors);
    st.bank = d.items.filter(q => q && q.id && Array.isArray(q.choices) && q.choices.length === 4);
    st.byId = Object.fromEntries(st.bank.map(q => [q.id, q]));
    st.themes = [...new Set(st.bank.map(q => q.theme))].sort((a, b) => label(a).localeCompare(label(b)));
    st.loaded = true;
  }
  const hist = id => (st.history[id] ||= { asked: 0, wrong: 0, lastWrong: false, lastAt: null });
  function save() { saveJSON(KEY.history, st.history); saveJSON(KEY.sessions, st.sessions.slice(-100)); }
  function show(part) { ['home', 'quiz', 'end'].forEach(p => $('#qcm-' + p).classList.toggle('hidden', p !== part)); }
  const plain = s => String(s).replace(/[`*]/g, '').replace(/\s+/g, ' ').trim();

  // ------------------------------------------------------------ home + history
  function renderHome() {
    if (!st.loaded) return;
    const counts = {};
    st.bank.forEach(q => counts[q.theme] = (counts[q.theme] || 0) + 1);
    const prefs = loadJSON(KEY.prefs, { themes: [], n: '10', prioritize: true });
    $('#qcm-themes').innerHTML = st.themes.map(t =>
      `<label class="chip"><input type="checkbox" value="${escapeHtml(t)}" ${!prefs.themes.length || prefs.themes.includes(t) ? 'checked' : ''}> ${escapeHtml(label(t))} <span class="muted">${counts[t]}</span></label>`).join('');
    $('#qcm-n').value = String(prefs.n); $('#qcm-prioritize').checked = prefs.prioritize !== false;
    $('#qcm-msg').textContent = '';

    const rows = st.themes.map(t => {
      const qs = st.bank.filter(q => q.theme === t);
      let asked = 0, wrong = 0, failing = 0, seen = 0;
      qs.forEach(q => { const h = st.history[q.id]; if (h) { asked += h.asked; wrong += h.wrong; seen++; if (h.lastWrong) failing++; } });
      return { t, n: qs.length, asked, wrong, failing, seen };
    });
    const tot = rows.reduce((a, r) => ({ asked: a.asked + r.asked, wrong: a.wrong + r.wrong, failing: a.failing + r.failing, seen: a.seen + r.seen }), { asked: 0, wrong: 0, failing: 0, seen: 0 });
    $('#qcm-stats-cards').innerHTML = [
      [st.bank.length, 'questions in the bank'], [tot.seen, 'questions seen'], [tot.asked, 'answers given'],
      [tot.wrong, 'mistakes'], [tot.asked ? Math.round(100 * tot.wrong / tot.asked) + ' %' : '–', 'error rate'], [tot.failing, 'to review (missed last time)'],
    ].map(([v, l]) => `<div class="card"><div class="v">${v}</div><div class="l">${l}</div></div>`).join('');
    $('#qcm-stats-themes').innerHTML = `<tr><th>Theme</th><th>Questions</th><th>Seen</th><th>Answers</th><th>Mistakes</th><th>Error rate</th><th>To review</th></tr>` +
      rows.map(r => `<tr><td>${escapeHtml(label(r.t))}</td><td>${r.n}</td><td>${r.seen}</td><td>${r.asked}</td><td>${r.wrong}</td>
        <td><div class="bar rate" title="${r.asked ? Math.round(100 * r.wrong / r.asked) + ' %' : ''}"><span style="width:${r.asked ? 100 * r.wrong / r.asked : 0}%"></span></div></td><td>${r.failing}</td></tr>`).join('');
    const rv = $('#qcm-review'); rv.disabled = tot.failing === 0; rv.textContent = `Review my mistakes (${tot.failing})`;
    $('#qcm-sessions').innerHTML = st.sessions.slice(-8).reverse().map(s =>
      `<li><span class="muted">${fmtDate(s.at)}</span><span><strong>${s.score} / ${s.n}</strong></span><span class="muted">${s.themes.map(label).join(', ')}</span></li>`).join('') || '<li class="muted">No session yet.</li>';
  }
  const selectedThemes = () => $$('#qcm-themes input:checked').map(i => i.value);

  // ------------------------------------------------------------ session
  function startSession(ids) {
    if (!ids.length) { $('#qcm-msg').textContent = 'No question for this selection.'; return; }
    st.session = { ids, idx: 0, answers: [], perms: Object.fromEntries(ids.map(id => [id, shuffle([0, 1, 2, 3])])) };
    show('quiz'); renderQuestion();
  }
  function newSession() {
    const themes = selectedThemes(), n = $('#qcm-n').value, prioritize = $('#qcm-prioritize').checked;
    saveJSON(KEY.prefs, { themes: themes.length === st.themes.length ? [] : themes, n, prioritize });
    const pool = st.bank.filter(q => themes.includes(q.theme));
    let ids;
    if (prioritize) {
      const g1 = pool.filter(q => st.history[q.id]?.lastWrong), g2 = pool.filter(q => !st.history[q.id]), g3 = pool.filter(q => st.history[q.id] && !st.history[q.id].lastWrong);
      ids = [...shuffle(g1), ...shuffle(g2), ...shuffle(g3)].map(q => q.id);
    } else ids = shuffle([...pool]).map(q => q.id);
    if (n !== 'all') ids = ids.slice(0, Number(n));
    startSession(ids);
  }
  function reviewErrors() { startSession(shuffle(st.bank.filter(q => st.history[q.id]?.lastWrong).map(q => q.id))); }

  function renderQuestion() {
    const s = st.session, q = st.byId[s.ids[s.idx]], perm = s.perms[q.id];
    $('#qcm-progress').textContent = `Question ${s.idx + 1} / ${s.ids.length}`;
    $('#qcm-theme').textContent = label(q.theme);
    $('#qcm-question').innerHTML = renderMd(q.question);
    const codeEl = $('#qcm-code');
    if (q.code) {
      codeEl.classList.remove('hidden'); codeEl.innerHTML = '';
      const mode = q.language === 'sql' ? 'text/x-sql' : q.language === 'python' || !q.language ? 'python' : q.language === 'bash' ? 'shell' : null;
      if (mode && window.CodeMirror?.runMode && (mode !== 'shell' || CodeMirror.modes.shell)) CodeMirror.runMode(q.code.replace(/\n$/, ''), mode, codeEl);
      else codeEl.textContent = q.code.replace(/\n$/, '');
    } else codeEl.classList.add('hidden');
    $('#qcm-choices').innerHTML = perm.map((orig, i) =>
      `<button class="choice" data-orig="${orig}"><span class="key">${i + 1}</span><span class="txt">${escapeHtml(q.choices[orig])}</span></button>`).join('');
    $$('#qcm-choices .choice').forEach(b => b.onclick = () => answer(Number(b.dataset.orig)));
    $('#qcm-feedback').classList.add('hidden'); $('#qcm-next').classList.add('hidden');
    $('#qcm-quiz').scrollIntoView({ block: 'start' });
  }
  function answer(orig) {
    const s = st.session; if (!s || s.answers.length > s.idx) return;
    const q = st.byId[s.ids[s.idx]], ok = orig === q.answer;
    s.answers.push({ id: q.id, picked: orig, ok });
    const h = hist(q.id); h.asked++; if (!ok) h.wrong++; h.lastWrong = !ok; h.lastAt = Date.now(); save();
    $$('#qcm-choices .choice').forEach(b => { const o = Number(b.dataset.orig); b.disabled = true; if (o === q.answer) b.classList.add('correct'); else if (o === orig) b.classList.add('wrong'); });
    const fb = $('#qcm-feedback');
    fb.className = 'feedback ' + (ok ? 'ok' : 'fail');
    fb.innerHTML = `<div class="verdict-line">${ok ? 'Correct' : 'Wrong. The right answer: ' + escapeHtml(q.choices[q.answer])}</div><div class="md">${renderMd(q.explanation)}</div><div class="muted small">Source: ${escapeHtml(q.source || '')}</div>`;
    const nx = $('#qcm-next'); nx.classList.remove('hidden');
    nx.textContent = s.idx + 1 < s.ids.length ? 'Next' : 'See the result';
    nx.focus();
  }
  function next() {
    const s = st.session; if (!s || s.answers.length <= s.idx) return;
    s.idx++;
    if (s.idx >= s.ids.length) finish(); else renderQuestion();
  }
  function finish() {
    const s = st.session, n = s.ids.length, ok = s.answers.filter(a => a.ok).length;
    st.sessions.push({ at: Date.now(), n, score: ok, themes: [...new Set(s.ids.map(id => st.byId[id].theme))] }); save();
    show('end');
    $('#qcm-score').innerHTML = `<div class="big">${ok} / ${n}</div><div class="muted">${Math.round(100 * ok / n)} % correct</div>`;
    const byT = {};
    s.answers.forEach(a => { const t = st.byId[a.id].theme; const o = byT[t] ||= { n: 0, ok: 0 }; o.n++; if (a.ok) o.ok++; });
    $('#qcm-end-themes').innerHTML = `<tr><th>Theme</th><th>Score</th><th></th></tr>` + Object.entries(byT).sort().map(([t, o]) =>
      `<tr><td>${escapeHtml(label(t))}</td><td>${o.ok} / ${o.n}</td><td><div class="bar"><span style="width:${100 * o.ok / o.n}%"></span></div></td></tr>`).join('');
    const failed = s.answers.filter(a => !a.ok);
    $('#qcm-failed').innerHTML = failed.length ? failed.map(a => {
      const q = st.byId[a.id];
      return `<details class="failed"><summary>${escapeHtml(label(q.theme))} — ${escapeHtml(plain(q.question).slice(0, 110))}</summary>
        <div class="md">${renderMd(q.question)}</div>${q.code ? `<pre class="code">${escapeHtml(q.code)}</pre>` : ''}
        <p><span class="wrong-txt">Your answer: ${escapeHtml(q.choices[a.picked])}</span><br><span class="ok-txt">Correct answer: ${escapeHtml(q.choices[q.answer])}</span></p>
        <div class="md">${renderMd(q.explanation)}</div></details>`;
    }).join('') : '<p>No mistake in this session.</p>';
    $('#qcm-replay').classList.toggle('hidden', !failed.length);
    $('#qcm-replay').onclick = () => startSession(shuffle(failed.map(a => a.id)));
    st.session = null;
  }
  function backHome() { st.session = null; renderHome(); show('home'); }

  // ------------------------------------------------------------ keyboard
  document.addEventListener('keydown', e => {
    if ($('#view-qcm').classList.contains('hidden') || $('#qcm-quiz').classList.contains('hidden')) return;
    if (e.target && e.target.matches && e.target.matches('input, textarea, select')) return;
    if (e.key >= '1' && e.key <= '4') { const b = $$('#qcm-choices .choice')[Number(e.key) - 1]; if (b && !b.disabled) { e.preventDefault(); b.click(); } }
    else if (e.key === 'Enter' && e.target?.tagName !== 'BUTTON') { e.preventDefault(); next(); }
  });

  // ------------------------------------------------------------ init
  $('#qcm-start').onclick = newSession;
  $('#qcm-review').onclick = reviewErrors;
  $('#qcm-next').onclick = next;
  $('#qcm-quit').onclick = backHome;
  $('#qcm-back').onclick = backHome;
  $('#qcm-all').onclick = () => { const boxes = $$('#qcm-themes input'); const all = boxes.every(b => b.checked); boxes.forEach(b => b.checked = !all); };
  twoClick($('#qcm-reset-history'), 'Clear quiz history', () => { st.history = {}; st.sessions = []; save(); renderHome(); });
  window.TTQCM = { open: () => { if (st.session) show('quiz'); else { renderHome(); show('home'); } }, state: st };
  st.history = loadJSON(KEY.history, {}); st.sessions = loadJSON(KEY.sessions, []);
  load().then(renderHome).catch(e => { $('#qcm-home').innerHTML = `<h2>Quiz bank unreachable</h2><p>${escapeHtml(e.message)}</p>`; });
})();
