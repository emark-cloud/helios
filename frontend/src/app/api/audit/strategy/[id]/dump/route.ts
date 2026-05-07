/**
 * `/api/audit/strategy/[id]/dump` — JSON download for the forensic
 * audit page (`DESIGN.md §9.7`). One request: pull every trade,
 * NAV report, and paramsHash rotation for the strategy from
 * Goldsky and serve it as a single attachment.
 *
 * Caps `trades` at 1000 to keep one payload reasonable; consumers
 * that need full history paginate via the subgraph directly.
 */

import { NextResponse } from "next/server";

import { fetchStrategyDetail, fetchStrategyAudit } from "@/lib/goldsky";

const TRADE_DUMP_CAP = 1000;

export async function GET(
  _request: Request,
  context: { params: { id: string } },
): Promise<NextResponse> {
  const id = decodeURIComponent(context.params.id);

  try {
    const [detail, audit] = await Promise.all([
      fetchStrategyDetail(id, { tradeFirst: 0, allocFirst: 50, navFirst: 1000 }),
      fetchStrategyAudit(id, { first: TRADE_DUMP_CAP, skip: 0 }),
    ]);

    if (!detail || !audit) {
      return NextResponse.json({ error: "Strategy not indexed", id }, { status: 404 });
    }

    const payload = {
      generatedAt: new Date().toISOString(),
      strategyId: detail.id,
      manifest: {
        declaredClass: detail.declaredClass,
        chainId: detail.chainId,
        operator: detail.operator,
        feeRateBps: detail.feeRateBps,
        stakeAmount: detail.stakeAmount,
        maxCapacity: detail.maxCapacity,
        active: detail.active,
        registeredAt: detail.registeredAt,
        currentReputation: detail.currentReputation,
        totalRealizedPnL: detail.totalRealizedPnL,
        totalAttestedTrades: detail.totalAttestedTrades,
        maxDrawdownBps: detail.maxDrawdownBps,
      },
      trades: audit.trades,
      tradesTruncatedAt: TRADE_DUMP_CAP,
      navSnapshots: detail.navSnapshots,
      paramsRotations: audit.paramsRotations,
      allocations: detail.allocations,
    };

    return new NextResponse(JSON.stringify(payload, null, 2), {
      status: 200,
      headers: {
        "Content-Type": "application/json",
        "Content-Disposition": `attachment; filename="audit-${id}.json"`,
      },
    });
  } catch (err) {
    return NextResponse.json(
      { error: "Subgraph unreachable", message: (err as Error).message },
      { status: 502 },
    );
  }
}
