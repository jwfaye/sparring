/* Theme bootstrap: apply the remembered choice (tt.theme = light | dark) before the stylesheet loads, to avoid a flash. */
(function () {
  try {
    const t = localStorage.getItem('tt.theme');
    if (t === 'light' || t === 'dark') document.documentElement.dataset.theme = t;
  } catch {}
})();
