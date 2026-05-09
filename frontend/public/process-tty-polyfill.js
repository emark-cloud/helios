// Particle Network's bundled pino logger reads
// `process.stdout.isTTY` / `process.stderr.isTTY` while the passkey
// modal builds its userOp signer. Webpack 5's browser shim only
// exposes `process.env`, so the SDK throws
// "Cannot read properties of undefined (reading 'isTTY')" mid-flow.
//
// Loading this file synchronously from <head> guarantees the polyfill
// is in place before any webpack chunk — including Particle's
// lazy-imported bundle — first reads the global. A polyfill embedded
// in a client component runs too late in some build outputs because
// Particle's logger initializes during its own dynamic import.
(function () {
  if (typeof window === "undefined") return;
  var p = window.process || (window.process = { env: {} });
  if (!p.env) p.env = {};
  if (!p.stdout) p.stdout = { isTTY: false };
  if (!p.stderr) p.stderr = { isTTY: false };
})();
