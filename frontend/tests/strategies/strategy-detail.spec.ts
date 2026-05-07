import { test, expect } from "@playwright/test";

/**
 * WS-FE-3 smoke tests for `/strategies/[id]`. Asserts:
 * - manifest header renders class + chain + operator from the
 *   subgraph payload
 * - reputation breakdown renders all five components
 *   (sourced from the reputation engine, not the subgraph)
 * - recent trades table renders the row
 * - allocators panel renders the mini-sunburst SVG
 * - paramsHash rotation table surfaces a row
 */

const STRATEGY_ID = "0x1111111111111111111111111111111111111111";
const ALLOCATOR_ID = "0x2222222222222222222222222222222222222222";
const ALLOCATOR_NAME = "Helios Sentinel-shadow";
const OPERATOR = "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";

const STRATEGY_DETAIL = {
  id: STRATEGY_ID,
  declaredClass: "0x2a9aa442064b635baec37a7a259282faa5563a653a8325378d5676c6f04bc9dd",
  chainId: 2368,
  operator: OPERATOR,
  feeRateBps: 200,
  stakeAmount: "50000000000",
  maxCapacity: "1000000000000",
  active: true,
  registeredAt: "1777000000",
  currentReputation: "78",
  totalRealizedPnL: "12500000",
  totalAttestedTrades: 372,
  maxDrawdownBps: 850,
  trades: [
    {
      id: "0xtrade1",
      timestamp: "1788000000",
      txHash: "0xttx1",
      proofValid: true,
      declaredClass: "0x2a9aa442064b635baec37a7a259282faa5563a653a8325378d5676c6f04bc9dd",
      assetIn: "0xc1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1",
      assetOut: "0xd2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2",
      amountIn: "1000000000",
      minAmountOut: "990000000",
      direction: 0,
      blockWindowStart: "100",
      blockWindowEnd: "120",
    },
  ],
  allocations: [
    {
      id: "0xalloc1",
      capitalDeployed: "10000000000",
      strategyHighWaterMark: "10000000000",
      lastRebalanceAt: "1788000000",
      defundedAt: null,
      defundReason: null,
      user: { id: "0xuser0001" },
      allocator: { id: ALLOCATOR_ID, name: ALLOCATOR_NAME },
    },
  ],
  paramsRotations: [
    {
      id: "0xrot1",
      oldHash: "0x" + "11".repeat(32),
      newHash: "0x" + "22".repeat(32),
      timestamp: "1788000000",
      txHash: "0xrottx1",
    },
  ],
  navSnapshots: [
    { id: "0xnav1", totalNAV: "10000000000", timestamp: String(1788000000 - 3600) },
    { id: "0xnav2", totalNAV: "10500000000", timestamp: String(1788000000) },
  ],
};

const REPUTATION_AUDIT = {
  actor: STRATEGY_ID,
  declaredClass: STRATEGY_DETAIL.declaredClass,
  score_e4: 7830,
  components: {
    performance: 0.85,
    risk: 0.72,
    proof: 0.98,
    stake: 0.55,
    age: 0.61,
  },
  components_hash: "0x6f1d8a3b12c4e76d0a4be9e8a17b2c5d4f3e8a91234567890abcdef0123456789",
  perf_breakdown: {
    sharpe_7d: 1.45,
    sharpe_30d: 1.62,
    sharpe_90d: 1.38,
    norm_7d: 0.82,
    norm_30d: 0.88,
    norm_90d: 0.84,
  },
  cohort: {
    win_7d: { size: 4, median: 0.95, iqr: 0.42, is_fallback: false },
    win_30d: { size: 4, median: 1.04, iqr: 0.38, is_fallback: false },
    win_90d: { size: 4, median: 0.91, iqr: 0.35, is_fallback: false },
  },
  weights: {
    performance: 0.4,
    risk: 0.25,
    proof: 0.15,
    stake: 0.1,
    age: 0.1,
  },
  inputs: {
    stake_e18: "50000000000000000000000",
    max_stake_in_class_e18: "100000000000000000000000",
    trades_attested: 372,
    max_drawdown_bps_90d: 850,
    valid_proofs: 365,
    total_proof_attempts: 372,
  },
  proof_score_is_binary: false,
};

function fulfill(body: unknown) {
  return {
    status: 200,
    contentType: "application/json",
    body: JSON.stringify(body),
  };
}

test.describe("/strategies/[id]", () => {
  test("renders the manifest, breakdown, trades, allocators, and rotations", async ({ page }) => {
    await page.route("**/subgraphs/**", async (route) => {
      const req = route.request().postData() ?? "";
      if (req.includes("query StrategyDetail")) {
        await route.fulfill(fulfill({ data: { strategy: STRATEGY_DETAIL } }));
        return;
      }
      await route.fulfill(fulfill({ data: {} }));
    });

    await page.route(`**/v1/audit/${STRATEGY_ID}`, (route) =>
      route.fulfill(fulfill(REPUTATION_AUDIT)),
    );

    await page.goto(`/strategies/${STRATEGY_ID}`);

    // Manifest renders class + operator
    await expect(page.getByText("Momentum").first()).toBeVisible();
    await expect(page.getByText(/0xaaaa…aaaa/i)).toBeVisible();

    // Reputation breakdown — five components. Manifest header also
    // surfaces some of the labels (Stake, etc.) so use .first() —
    // the assertion is "this label appears on the page", not which copy.
    await expect(page.getByText("Performance", { exact: true })).toBeVisible();
    await expect(page.getByText("Proof", { exact: true }).first()).toBeVisible();
    await expect(page.getByText("Risk", { exact: true })).toBeVisible();
    await expect(page.getByText("Stake", { exact: true }).first()).toBeVisible();
    await expect(page.getByText("Age", { exact: true })).toBeVisible();

    // Recent trades table populated
    await expect(page.getByTestId("recent-trades")).toBeVisible();
    await expect(page.getByTestId("recent-trades").getByText("Swap")).toBeVisible();

    // Allocators panel + mini-sunburst (svg with role=img)
    const allocators = page.getByTestId("strategy-allocators");
    await expect(allocators).toBeVisible();
    await expect(allocators.getByText(ALLOCATOR_NAME)).toBeVisible();
    await expect(allocators.locator("svg[role='img']")).toBeVisible();

    // ParamsHash rotation table — trimHash renders slice(0,10)…slice(-6).
    await expect(page.getByTestId("params-rotations")).toBeVisible();
    await expect(
      page.getByTestId("params-rotations").getByText("0x11111111…111111"),
    ).toBeVisible();

    // P&L curve renders an svg
    await expect(page.getByTestId("pnl-curve").locator("svg")).toBeVisible();
    // NAV timeline renders an svg
    await expect(page.getByTestId("nav-timeline").locator("svg")).toBeVisible();
  });

  test("Full audit CTA links to /audit/strategy/[id]", async ({ page }) => {
    await page.route("**/subgraphs/**", async (route) => {
      const req = route.request().postData() ?? "";
      if (req.includes("query StrategyDetail")) {
        await route.fulfill(fulfill({ data: { strategy: STRATEGY_DETAIL } }));
        return;
      }
      await route.fulfill(fulfill({ data: {} }));
    });
    await page.route(`**/v1/audit/${STRATEGY_ID}`, (route) =>
      route.fulfill(fulfill(REPUTATION_AUDIT)),
    );

    await page.goto(`/strategies/${STRATEGY_ID}`);

    const cta = page.getByRole("link", { name: /full audit/i }).first();
    await expect(cta).toHaveAttribute(
      "href",
      `/audit/strategy/${STRATEGY_ID.toLowerCase()}`,
    );
  });
});
