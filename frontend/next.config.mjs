import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  experimental: {
    typedRoutes: true,
  },
  transpilePackages: ["@helios/contracts-abi"],
  webpack: (config, { isServer }) => {
    // Particle's bundled pino logger reads `process.stdout.isTTY` /
    // `process.stderr.isTTY` while building the userOp signer. The
    // default `process/browser` shim webpack injects via ProvidePlugin
    // is a fresh object with no stdout/stderr surface, so the read
    // throws "Cannot read properties of undefined (reading 'isTTY')"
    // mid passkey prompt. Re-pointing every `require('process/browser')`
    // at our shim patches the singleton every chunk gets — patching
    // `globalThis.process` from a <script> tag does NOT reach modules
    // that did `require('process')`, because that import returns its
    // own object.
    if (!isServer) {
      const shim = path.resolve(__dirname, "process-shim.cjs");
      config.resolve = config.resolve || {};
      config.resolve.alias = {
        ...(config.resolve.alias || {}),
        "process/browser": shim,
        "process/browser.js": shim,
        process: shim,
      };
    }
    return config;
  },
};

export default nextConfig;
