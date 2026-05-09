/**
 * Same-origin proxy from the Vercel frontend to the VPS Sentinel
 * service.
 *
 * Why: Sentinel runs on `http://38.49.216.27:8001` (no TLS, no
 * domain). The browser sits on `https://*.vercel.app`, which blocks
 * mixed-content (`http://` from `https://`) and would also need CORS
 * if it could connect. Server-side fetch from a Next.js Route
 * Handler bypasses both — the browser sees a same-origin path; the
 * Vercel server talks plain HTTP to the VPS.
 *
 * Routes:
 *   /api/sentinel/users/{addr}/meta-strategy → POST  /v1/users/{addr}/meta-strategy
 *   /api/sentinel/users/{addr}/dashboard     → GET   /v1/users/{addr}/dashboard
 *   /api/sentinel/strategies                 → GET   /v1/strategies
 *
 * The `[...path]` segment captures everything after `/api/sentinel/`
 * and prepends `/v1/` when forwarding so the upstream URL matches
 * Sentinel's existing API.
 *
 * Configure with `SENTINEL_PROXY_TARGET` (server-side env, no
 * NEXT_PUBLIC_ prefix — must not leak to the bundle). Defaults to
 * the demo VPS so a forgotten env var still works.
 */

import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const TARGET = (process.env.SENTINEL_PROXY_TARGET ?? "http://38.49.216.27:8001").replace(/\/$/, "");

async function proxy(req: NextRequest, path: string[]): Promise<NextResponse> {
  const tail = path.join("/");
  const search = req.nextUrl.search; // includes leading "?" if any
  const upstream = `${TARGET}/v1/${tail}${search}`;

  // Forward method + body verbatim. Strip headers that would confuse
  // the upstream FastAPI server (`host`, `connection`, etc.) and only
  // pass content-type + content-length.
  const init: RequestInit = {
    method: req.method,
    headers: {
      "content-type": req.headers.get("content-type") ?? "application/json",
    },
    // GET / HEAD must not have a body.
    body: ["GET", "HEAD"].includes(req.method) ? undefined : await req.text(),
    cache: "no-store",
  };

  let upstreamRes: Response;
  try {
    upstreamRes = await fetch(upstream, init);
  } catch (err) {
    return NextResponse.json(
      {
        error: "sentinel_proxy_unreachable",
        target: upstream,
        detail: err instanceof Error ? err.message : String(err),
      },
      { status: 502 },
    );
  }

  // Stream the response body straight through; preserve status +
  // content-type so error JSON from FastAPI renders verbatim.
  const body = await upstreamRes.text();
  return new NextResponse(body, {
    status: upstreamRes.status,
    headers: {
      "content-type": upstreamRes.headers.get("content-type") ?? "application/json",
    },
  });
}

export async function GET(
  req: NextRequest,
  context: { params: Promise<{ path: string[] }> },
): Promise<NextResponse> {
  const { path } = await context.params;
  return proxy(req, path);
}

export async function POST(
  req: NextRequest,
  context: { params: Promise<{ path: string[] }> },
): Promise<NextResponse> {
  const { path } = await context.params;
  return proxy(req, path);
}

export async function PUT(
  req: NextRequest,
  context: { params: Promise<{ path: string[] }> },
): Promise<NextResponse> {
  const { path } = await context.params;
  return proxy(req, path);
}

export async function DELETE(
  req: NextRequest,
  context: { params: Promise<{ path: string[] }> },
): Promise<NextResponse> {
  const { path } = await context.params;
  return proxy(req, path);
}
