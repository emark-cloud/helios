import { test, expect } from "@playwright/test";

/**
 * WS-FE-7 — `/` focuses the strategies search box, `J` / `K` move the
 * row highlight, `Enter` activates the selected row by routing to
 * `/strategies/{id}`. Mocks the subgraph with two deterministic rows.
 */

const FIXTURE = {
  data: {
    strategies: [
      {
        id: "0x1111111111111111111111111111111111111111",
        operator: "0xa1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1",
        chainId: 2368,
        declaredClass:
          "0x2a9aa442064b635baec37a7a259282faa5563a653a8325378d5676c6f04bc9dd",
        feeRateBps: 200,
        stakeAmount: "1000000000",
        currentReputation: "5000000000000000000",
        totalRealizedPnL: "1000000",
        totalAttestedTrades: 10,
        maxDrawdownBps: 500,
      },
      {
        id: "0x2222222222222222222222222222222222222222",
        operator: "0xa2a2a2a2a2a2a2a2a2a2a2a2a2a2a2a2a2a2a2a2",
        chainId: 2368,
        declaredClass:
          "0x2a9aa442064b635baec37a7a259282faa5563a653a8325378d5676c6f04bc9dd",
        feeRateBps: 300,
        stakeAmount: "2000000000",
        currentReputation: "4000000000000000000",
        totalRealizedPnL: "500000",
        totalAttestedTrades: 5,
        maxDrawdownBps: 700,
      },
    ],
  },
};

test.describe("/strategies hotkeys", () => {
  test("/ focuses the search input; J then K cycles selection", async ({ page }) => {
    await page.route("**/subgraphs/**", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(FIXTURE),
      }),
    );
    await page.goto("/strategies");

    // Wait for table to render.
    const rows = page.locator("tbody tr");
    await expect(rows).toHaveCount(2);

    await page.locator("body").click();
    await page.keyboard.press("Slash");
    await expect(page.getByLabel("Search strategies")).toBeFocused();
    // `Esc` blurs and clears.
    await page.keyboard.press("Escape");
    await expect(page.getByLabel("Search strategies")).not.toBeFocused();

    // Default selection lands on the first row.
    await expect(rows.nth(0)).toHaveAttribute("aria-selected", "true");
    await page.keyboard.press("KeyJ");
    await expect(rows.nth(1)).toHaveAttribute("aria-selected", "true");
    await page.keyboard.press("KeyK");
    await expect(rows.nth(0)).toHaveAttribute("aria-selected", "true");
  });
});
