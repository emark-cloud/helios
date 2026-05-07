import { test, expect } from "@playwright/test";

/**
 * WS-FE-2 smoke for `/judge`. Asserts the surface a hackathon judge
 * lands on is self-sufficient: addresses table populated from the
 * checked-in deployments JSON, verify-yourself command block visible,
 * 5-step eval checklist linked, recent-trades panel renders.
 */

const STATS = {
  data: {
    strategies: [
      { id: "0x1111111111111111111111111111111111111111", totalAttestedTrades: 4 },
    ],
    allocators: [
      { id: "0xa1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1" },
    ],
    allocations: [{ capitalDeployed: "1000000000" }],
    trades: [
      {
        id: "0xtrade-judge-1",
        txHash: "0xabcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
        timestamp: "1788000000",
        proofValid: true,
        strategy: {
          id: "0x1111111111111111111111111111111111111111",
          declaredClass:
            "0x2a9aa442064b635baec37a7a259282faa5563a653a8325378d5676c6f04bc9dd",
          chainId: 2368,
        },
      },
    ],
  },
};

function fulfill(body: unknown) {
  return {
    status: 200,
    contentType: "application/json",
    body: JSON.stringify(body),
  };
}

test.describe("/judge", () => {
  test("renders eval checklist, addresses, verify command, and recent trades", async ({ page }) => {
    await page.route("**/subgraphs/**", async (route) => {
      const req = route.request().postData() ?? "";
      if (req.includes("query LandingStats")) {
        await route.fulfill(fulfill(STATS));
        return;
      }
      await route.fulfill(fulfill({ data: {} }));
    });

    await page.goto("/judge");

    // Eval checklist: 5 numbered steps, each linking to an in-app surface.
    await expect(page.getByText("5-step eval checklist")).toBeVisible();
    await expect(page.getByText("Sign a meta-strategy")).toBeVisible();
    await expect(page.getByText("Watch the cascade")).toBeVisible();
    await expect(page.getByText("Inspect a strategy")).toBeVisible();
    await expect(page.getByText("Audit a proof")).toBeVisible();
    await expect(page.getByText("Compare allocators")).toBeVisible();

    // Addresses table — pulled from contracts/deployments/kite-testnet.json.
    await expect(page.getByText("Deployed addresses")).toBeVisible();
    await expect(page.getByText("User vault")).toBeVisible();
    await expect(page.getByText("Allocator vault")).toBeVisible();
    await expect(page.getByText("Reputation anchor (V1)")).toBeVisible();

    // Verify-yourself command block
    await expect(page.getByText("Verify a trade yourself")).toBeVisible();
    await expect(page.locator("pre").filter({ hasText: /verify-trade\.js/ })).toBeVisible();

    // Recent trades — surfaced from subgraph mock
    const recent = page.getByTestId("judge-recent-trades");
    await expect(recent).toBeVisible();
    await expect(recent.getByText("Momentum")).toBeVisible();
    await expect(recent.getByText(/0xabcdef12/)).toBeVisible();
  });
});
