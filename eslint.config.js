/* ESLint flat config for the web page. The scripts in app/js are classic scripts loaded in the order set by
   app/index.html: theme-init.js, then the CodeMirror and Pyodide CDN bundles, then common.js (defines window.TT),
   app.js, qcm.js and theory.js. They share globals through window (TT, TTQCM, TTTHEORY, tt), so the only names
   declared here are the ones the CDN bundles put in scope. Rule set: recommended, plus eqeqeq, no-var and
   prefer-const; no-empty keeps its recommended level but allows an empty catch, the pattern used for storage access
   that is expected to fail in private windows. */
const js = require('@eslint/js');
const globals = require('globals');

module.exports = [
  js.configs.recommended,
  {
    files: ['app/js/**/*.js'],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: 'script',
      globals: {
        ...globals.browser,
        CodeMirror: 'readonly',
        loadPyodide: 'readonly',
      },
    },
    rules: {
      eqeqeq: 'error',
      'no-var': 'error',
      'prefer-const': 'error',
      'no-empty': ['error', { allowEmptyCatch: true }],
    },
  },
];
