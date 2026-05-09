// Replacement for `process/browser` used by webpack's ProvidePlugin
// in client bundles. Aliased in next.config.mjs.
//
// Why we replace it: the npm `process` package returns a fresh,
// empty object on `module.exports = {}`, so mutations on
// `globalThis.process` cannot reach modules that do `require("process")`.
// Particle Network's bundled pino logger reads `process.stdout.isTTY`
// while building the userOp signer — without `stdout` defined that
// throws "Cannot read properties of undefined (reading 'isTTY')" mid
// passkey prompt. Aliasing every chunk's `process/browser` to this
// file gives them all a single object pre-populated with the surfaces
// the SDK touches.

const proc = (typeof globalThis !== "undefined" && globalThis.process) || {};

if (!proc.env) proc.env = {};
if (!proc.stdout) proc.stdout = { isTTY: false, write: () => true };
if (!proc.stderr) proc.stderr = { isTTY: false, write: () => true };
if (!proc.argv) proc.argv = [];
if (!proc.versions) proc.versions = {};

if (typeof proc.nextTick !== "function") {
  proc.nextTick = function nextTick(cb) {
    const args = Array.prototype.slice.call(arguments, 1);
    setTimeout(function run() {
      cb.apply(null, args);
    }, 0);
  };
}

if (typeof proc.cwd !== "function") proc.cwd = () => "/";
if (typeof proc.chdir !== "function") proc.chdir = () => undefined;
if (typeof proc.umask !== "function") proc.umask = () => 0;

if (typeof globalThis !== "undefined" && !globalThis.process) {
  globalThis.process = proc;
}

module.exports = proc;
