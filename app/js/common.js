/* Helpers shared by the tabs (exercises, QCM, interview). */
window.TT = (() => {
  'use strict';
  const $ = (sel, el = document) => el.querySelector(sel);
  const $$ = (sel, el = document) => [...el.querySelectorAll(sel)];
  // Storage prefix: ?profile=xxx isolates a progress namespace (automated tests), never the user's own.
  const PROFILE = new URLSearchParams(location.search).get('profile');
  const NS = PROFILE ? `tt[${PROFILE}].` : 'tt.';
  const loadJSON = (key, def, store = localStorage) => { try { const v = store.getItem(key); return v ? JSON.parse(v) : def; } catch { return def; } };
  const saveJSON = (key, v, store = localStorage) => { try { store.setItem(key, JSON.stringify(v)); } catch (e) { console.warn('storage', e); } };
  const escapeHtml = s => String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const fmtTime = sec => { sec = Math.max(0, Math.round(sec)); const h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60), s = sec % 60; return (h ? h + ':' + String(m).padStart(2, '0') : m) + ':' + String(s).padStart(2, '0'); };
  const shuffle = a => { for (let i = a.length - 1; i > 0; i--) { const j = Math.floor(Math.random() * (i + 1)); [a[i], a[j]] = [a[j], a[i]]; } return a; };
  const fmtDate = ts => new Date(ts).toLocaleString('en-GB', { dateStyle: 'short', timeStyle: 'short' });

  // ---- light / dark theme (global key, independent of the profile)
  const systemDark = () => window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
  const currentTheme = () => document.documentElement.dataset.theme || (systemDark() ? 'dark' : 'light');
  function applyTheme(t) {
    if (t) document.documentElement.dataset.theme = t; else delete document.documentElement.dataset.theme;
    const b = $('#theme-toggle'); if (b) b.textContent = currentTheme() === 'dark' ? 'Light' : 'Dark';
    document.dispatchEvent(new CustomEvent('tt:theme', { detail: currentTheme() }));
  }
  document.addEventListener('DOMContentLoaded', () => {
    applyTheme(document.documentElement.dataset.theme || null);
    $('#theme-toggle')?.addEventListener('click', () => {
      const next = currentTheme() === 'dark' ? 'light' : 'dark';
      try { localStorage.setItem('tt.theme', next); } catch {}
      applyTheme(next);
    });
  });

  function inline(s) {
    s = escapeHtml(s);
    s = s.replace(/`([^`]+)`/g, '<code>$1</code>');
    s = s.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
    return s;
  }
  // Mini-markdown: paragraphs, lists, headings, **bold**, `code`, ``` blocks.
  function renderMd(src) {
    const lines = String(src || '').replace(/\r/g, '').split('\n');
    let html = '', i = 0;
    while (i < lines.length) {
      const l = lines[i];
      if (l.startsWith('```')) {
        const buf = []; i++;
        while (i < lines.length && !lines[i].startsWith('```')) buf.push(lines[i++]);
        i++;
        html += `<pre class="code"><code>${escapeHtml(buf.join('\n'))}</code></pre>`;
        continue;
      }
      if (/^\s*[-*] /.test(l)) {
        const items = [];
        while (i < lines.length && /^\s*[-*] /.test(lines[i])) items.push(`<li>${inline(lines[i].replace(/^\s*[-*] /, ''))}</li>`), i++;
        html += `<ul>${items.join('')}</ul>`;
        continue;
      }
      if (/^#{1,3} /.test(l)) { const lvl = l.match(/^#+/)[0].length + 2; html += `<h${lvl}>${inline(l.replace(/^#+ /, ''))}</h${lvl}>`; i++; continue; }
      if (l.trim() === '') { i++; continue; }
      const buf = [l]; i++;
      while (i < lines.length && lines[i].trim() !== '' && !/^(```|\s*[-*] |#{1,3} )/.test(lines[i])) buf.push(lines[i++]);
      html += `<p>${inline(buf.join(' '))}</p>`;
    }
    return html;
  }
  // Confirm-on-second-click buttons (two clicks within 3 s).
  function twoClick(btn, label, action, ms = 3000) {
    let armed = null;
    btn.addEventListener('click', () => {
      if (armed) { clearTimeout(armed); armed = null; btn.textContent = label; action(); return; }
      btn.textContent = 'Confirm?';
      armed = setTimeout(() => { armed = null; btn.textContent = label; }, ms);
    });
  }
  return { $, $$, PROFILE, NS, currentTheme, loadJSON, saveJSON, escapeHtml, fmtTime, fmtDate, shuffle, inline, renderMd, twoClick };
})();
