# Security

## Threat model

Sparring is a local, single-user tool. The server (`server.py`, Python standard library `http.server`) has no
authentication, no sessions and no rate limiting. It is meant to listen on a loopback address only
(`server.host` = `127.0.0.1`, the default) and to be used from a browser on the same machine.

Exposing the server on a network (for example `server.host` = `0.0.0.0`, a port forward, or a reverse proxy without
authentication) exposes:

- every saved interview answer and grade (`data/theory/`), readable, gradable and deletable by anyone who can reach
  the port, including the `?profile=` namespaces;
- the grading backend: each `POST /api/theory/answer` or `/api/theory/grade` consumes your Anthropic API credits or
  your Claude Code subscription quota.

Do not expose it as is. If you need remote access, put it behind an authenticating reverse proxy or a VPN.

Built-in guards (`server.py`): API requests are refused when the `Host` header is not a loopback address (or the
configured bind host), when an `Origin` header does not match the page's origin, and when a POST is not
`application/json`; POST bodies are capped at 1 MB; `qid`, `id` and `profile` must match `[A-Za-z0-9_.-]{1,80}`;
an already graded answer is not re-graded unless `force: true` is sent. Every response carries
`X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, a `Content-Security-Policy` restricted to the
pinned CDNs (Pyodide needs `'unsafe-eval'` and `'wasm-unsafe-eval'`; the worker file gets the same policy),
`Cross-Origin-Opener-Policy: same-origin` and `Cross-Origin-Embedder-Policy: require-corp`. The last two make the
page cross-origin isolated, which enables `SharedArrayBuffer` for Pyodide's interrupt buffer (Stop button, run
timeout) and, as a side effect, isolates the page from cross-origin windows and from any cross-origin resource that
does not opt in with CORP or CORS. The server logs a warning when bound to a non-loopback address.

## What runs where

- **Exercise code** (yours, the setup, the tests, the solutions) runs in the browser, inside Pyodide (WebAssembly
  Python) and an in-memory SQLite, in a dedicated Web Worker (`app/js/py-worker.js`). Nothing you type in the editor
  is executed on the server. The Pyodide sandbox is the browser's sandbox: the code can use CPU and memory of the
  worker, nothing else, and a run is interrupted by the Stop button or after 20 s.
- **Bank checkers** (`python -m tools.check_bank`, `check_qcm`, `add_exercises`, `add_qcm`, `add_theory_grids`)
  execute the code of the bank files and of draft modules **on your machine, with your privileges**. They are meant
  for banks shipped in this repository and for drafts you wrote or reviewed yourself. Do not run them on a bank or a
  draft from an untrusted source.
- **Grading** sends the question, its grading grid and your answer to the model, either through the Anthropic API or
  through the local Claude Code CLI in non-interactive mode with no tool enabled and the project's settings disabled.
  The model's output is structured JSON (score, lists of points, feedback, improved answer) that is stored and
  displayed; it is never executed. A prompt injection in an answer can at most produce a wrong grade.

## Secrets

- The Anthropic API key is read by the SDK from the environment (`ANTHROPIC_API_KEY`). It is never written to a
  file of the repository, never sent to the page, and never logged.
- The Claude Code backend relies on the CLI's own login; the server never reads its token.
- `.gitignore` excludes `data/`, `.env`, `.venv/`, `.venv-check/` and IDE files. Check `git status --ignored` before
  publishing.

## Data stored locally

- Browser `localStorage`: exercise progress and code, quiz history, theme and preferences. Separate namespaces per
  `?profile=`.
- `data/theory[/<profile>]/answers.sqlite3`: interview answers and grades, a SQLite database written in one
  transaction per call (with its `-wal` and `-shm` side files while open). An `answers.json` from an earlier
  version is imported once and renamed `answers.json.migrated`, never deleted. The profile name is reduced to
  `[a-zA-Z0-9_-]` before being used as a directory name.

## Network calls made by the page

On load, the page fetches from pinned third-party origins: CodeMirror 5.65.16 from cdnjs.cloudflare.com, Pyodide
0.27.7 (and the pandas/numpy/sqlite3 packages) from cdn.jsdelivr.net, and the Inter / JetBrains Mono fonts from
fonts.googleapis.com and fonts.gstatic.com. The browser caches them afterwards. No telemetry is sent anywhere.

The cdnjs assets are integrity-checked: each CodeMirror tag in `app/index.html` carries a Subresource Integrity
hash (`integrity="sha384-..."`, `crossorigin="anonymous"`), so the browser refuses a file that does not match the
reviewed version. Pyodide is pinned to a version but not integrity-checked: the worker loads `pyodide.js` with
`importScripts`, which takes no integrity attribute, and `pyodide.js` fetches `pyodide.asm.js`, the WebAssembly
binary and the packages itself at runtime, so a hash on the loader alone would leave those unverified while
suggesting otherwise. Vendoring Pyodide under `app/` (about 15 MB) would remove that trust in
cdn.jsdelivr.net; it is a possible future change. The Google Fonts stylesheet is generated per browser and cannot
carry a hash; the fonts are cosmetic and fall back to system fonts when unreachable.

To work fully offline, vendor those assets under `app/` and point `app/index.html` and `PYODIDE_URL` in
`app/js/py-worker.js` at the local copies; the fonts fall back to system fonts when unreachable.

## Reporting an issue

Open a private security advisory on the GitHub repository, or an issue if the problem is not exploitable. Include the
version (commit), your `config.json` (without secrets) and the steps to reproduce.
