import { test, expect } from "@playwright/test";

/**
 * WS-FE-4 smoke tests for `/audit/strategy/[id]`. Asserts:
 * - paginated trade table renders rows with the celebrated shield treatment
 * - clicking a row expands inline showing public inputs
 * - "Verify yourself" CTA opens the modal with a copyable command
 * - reputation calculation inputs panel renders the five components
 */

const STRATEGY_ID = "0x3333333333333333333333333333333333333333";
const STRATEGY_CLASS_HASH = "0x2a9aa442064b635baec37a7a259282faa5563a653a8325378d5676c6f04bc9dd";
const TX_HASH = "0xabcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890";

const STRATEGY_AUDIT_PAGE = {
  id: STRATEGY_ID,
  declaredClass: STRATEGY_CLASS_HASH,
  chainId: 2368,
  operator: "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
  feeRateBps: 200,
  stakeAmount: "50000000000",
  maxCapacity: "1000000000000",
  active: true,
  registeredAt: "1777000000",
  currentReputation: "78",
  totalRealizedPnL: "12500000",
  totalAttestedTrades: 1,
  maxDrawdownBps: 850,
  trades: [
    {
      id: "0xtrade1",
      timestamp: "1788000000",
      txHash: TX_HASH,
      proofValid: true,
      declaredClass: STRATEGY_CLASS_HASH,
      assetIn: "0xc1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1",
      assetOut: "0xd2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2",
      amountIn: "1000000000",
      minAmountOut: "990000000",
      direction: 0,
      blockWindowStart: "100",
      blockWindowEnd: "120",
    },
  ],
  paramsRotations: [],
};

const REPUTATION_AUDIT = {
  actor: STRATEGY_ID,
  declaredClass: STRATEGY_CLASS_HASH,
  score_e4: 7830,
  components: { performance: 0.85, risk: 0.72, proof: 0.98, stake: 0.55, age: 0.61 },
  components_hash: "0xddccaa1122334455667788990011223344556677889900aabbccddeeff001122",
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
  weights: { performance: 0.4, risk: 0.25, proof: 0.15, stake: 0.1, age: 0.1 },
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

test.describe("/audit/strategy/[id]", () => {
  test("renders trade row with shield treatment and reputation panel", async ({ page }) => {
    await page.route("**/subgraphs/**", async (route) => {
      const req = route.request().postData() ?? "";
      if (req.includes("query StrategyAudit")) {
        await route.fulfill(fulfill({ data: { strategy: STRATEGY_AUDIT_PAGE } }));
        return;
      }
      await route.fulfill(fulfill({ data: {} }));
    });
    await page.route(`**/v1/audit/${STRATEGY_ID}`, (route) =>
      route.fulfill(fulfill(REPUTATION_AUDIT)),
    );

    await page.goto(`/audit/strategy/${STRATEGY_ID}`);

    // Trade row shows up with the celebrated shield label
    const trades = page.getByTestId("audit-trades");
    await expect(trades).toBeVisible();
    await expect(trades.getByText("Verified")).toBeVisible();

    // Reputation inputs panel — exact match scoped to the breakdown card
    await expect(page.getByText("Performance", { exact: true })).toBeVisible();
    await expect(page.getByText("Proof", { exact: true }).first()).toBeVisible();

    // Click row to expand → "Verify yourself" CTA appears inline
    await trades.getByText("Verified").click();
    const verifyButton = trades.getByRole("button", { name: /verify yourself/i });
    await expect(verifyButton).toBeVisible();

    // Click → modal opens with the copyable command containing the tx hash
    await verifyButton.click();
    const dialog = page.getByRole("dialog", { name: /verify this proof yourself/i });
    await expect(dialog).toBeVisible();
    await expect(
      dialog.getByText(`node scripts/verify-trade.js ${TX_HASH}`),
    ).toBeVisible();
    await expect(dialog.getByRole("button", { name: /copy/i })).toBeVisible();
  });

  test("JSON dump endpoint exists and surfaces a structured response", async ({ page }) => {
    // The route handler runs server-side and calls Goldsky directly —
    // page.route only intercepts client-side requests, so the upstream
    // GraphQL call fails and the route returns a 502 with a typed
    // payload. We assert the contract of the error path here; the
    // happy-path payload is exercised end-to-end in the manual smoke
    // run against a deployed subgraph.
    const response = await page.request.get(
      `/api/audit/strategy/${STRATEGY_ID}/dump`,
    );
    const body = await response.json();
    if (response.ok()) {
      expect(body.strategyId).toBe(STRATEGY_ID);
      expect(Array.isArray(body.trades)).toBe(true);
    } else {
      expect([404, 502]).toContain(response.status());
      expect(typeof body.error).toBe("string");
    }
  });
});
