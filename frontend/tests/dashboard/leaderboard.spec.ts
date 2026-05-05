import { test, expect } from "@playwright/test";

/// WS6.C smoke test for the `/dashboard` allocator leaderboard.
/// Asserts the panel renders with Sentinel + Helix pinned to the top
/// regardless of the underlying reputation order, and that the table
/// surfaces the 24h delta column for both rows.

const SENTINEL = {
  id: "0xf3e4452fe17edbfa6833022b9c186aa14b98955d",
  name: "Helios Sentinel-shadow",
  operator: "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  feeRateBps: 500,
  stakeAmount: "5000000000",
  isReferenceBrand: true,
  active: true,
  registeredAt: "1777000000",
  totalUsers: 12,
  totalCapitalManaged: "150000000000",
  currentReputation: "78",
  reputationUpdates: [{ delta: "3" }, { delta: "1" }],
};

const HELIX = {
  id: "0xfcc3a7e57e6841055ca6bc7b75b404576bf88f04",
  name: "Helios Helix-shadow",
  operator: "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
  feeRateBps: 600,
  stakeAmount: "5000000000",
  isReferenceBrand: true,
  active: true,
  registeredAt: "1777200000",
  totalUsers: 8,
  totalCapitalManaged: "92000000000",
  currentReputation: "64",
  reputationUpdates: [{ delta: "-2" }],
};

function fulfillGoldsky(body: unknown) {
  return {
    status: 200,
    contentType: "application/json",
    body: JSON.stringify(body),
  };
}

test.describe("/dashboard allocator leaderboard", () => {
  test("renders Sentinel + Helix pinned with reference badges", async ({ page }) => {
    await page.route("**/subgraphs/**", async (route) => {
      const req = route.request().postData() ?? "";
      if (req.includes("query AllocatorsLeaderboard")) {
        // Return Helix first to prove the pin step lifts Sentinel above it.
        await route.fulfill(fulfillGoldsky({ data: { allocators: [HELIX, SENTINEL] } }));
        return;
      }
      await route.fulfill(fulfillGoldsky({ data: {} }));
    });

    await page.goto("/dashboard");

    const panel = page.getByTestId("allocator-leaderboard");
    await expect(panel).toBeVisible();
    await expect(panel.getByRole("heading", { name: /Allocator leaderboard/ })).toBeVisible();

    // Both rows render with the Reference badge.
    const sentinelRow = panel.locator('tr[data-allocator-name="Helios Sentinel"]');
    const helixRow = panel.locator('tr[data-allocator-name="Helios Helix"]');
    await expect(sentinelRow).toHaveCount(1);
    await expect(helixRow).toHaveCount(1);

    // Sentinel pinned first.
    const rows = panel.locator("tbody tr");
    await expect(rows.first()).toHaveAttribute("data-allocator-name", "Helios Sentinel");

    const badges = panel.getByText("Reference");
    await expect(badges).toHaveCount(2);

    // 24h delta column reflects the summed updates: Sentinel +4, Helix -2.
    await expect(sentinelRow).toContainText("+4");
    await expect(helixRow).toContainText("-2");
  });
});
