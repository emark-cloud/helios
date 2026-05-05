import { test, expect } from "@playwright/test";

/// Smoke test for the WS6.A `/allocators` directory + detail. Mocks
/// the Goldsky GraphQL endpoint with deterministic Sentinel + Helix
/// rows so the assertion never depends on live subgraph state.

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
};

function fulfillGoldsky(body: unknown) {
  return {
    status: 200,
    contentType: "application/json",
    body: JSON.stringify(body),
  };
}

test.describe("/allocators", () => {
  test("directory pins Sentinel + Helix with the reference badge", async ({ page }) => {
    await page.route("**/subgraphs/**", async (route) => {
      const req = route.request().postData() ?? "";
      if (req.includes("query Allocators")) {
        await route.fulfill(fulfillGoldsky({ data: { allocators: [HELIX, SENTINEL] } }));
        return;
      }
      await route.fulfill(fulfillGoldsky({ data: {} }));
    });

    await page.goto("/allocators");

    // Both cards render with the reference badge. Sentinel is pinned
    // first per `pinReferenceBrandsFirst`; Helix follows.
    const cards = page.getByRole("link", { name: /Open Helios (Sentinel|Helix) detail/ });
    await expect(cards).toHaveCount(2);

    const badges = page.getByText("Official Reference");
    await expect(badges).toHaveCount(2);

    // Order: Sentinel first.
    const firstCard = cards.first();
    await expect(firstCard).toContainText("Helios Sentinel");
  });

  test("/allocators/Helios%20Helix shows reputation breakdown", async ({ page }) => {
    await page.route("**/subgraphs/**", async (route) => {
      const req = route.request().postData() ?? "";
      if (req.includes("query AllocatorByName")) {
        await route.fulfill(
          fulfillGoldsky({
            data: {
              allocators: [
                {
                  ...HELIX,
                  decisions: [],
                  delegations: [],
                  reputationUpdates: [],
                },
              ],
            },
          }),
        );
        return;
      }
      await route.fulfill(fulfillGoldsky({ data: {} }));
    });

    await page.goto("/allocators/Helios%20Helix");

    // Header surfaces the brand display name (resolved from the
    // shadow form via `referenceBrandFor`).
    await expect(page.getByRole("heading", { name: "Helios Helix" })).toBeVisible();

    // Reputation breakdown panel renders the v1 weights verbatim.
    await expect(page.getByRole("heading", { name: /Reputation v1 breakdown/ })).toBeVisible();
    await expect(page.getByText("User net P&L above HWM")).toBeVisible();
    await expect(page.getByText("Drawdown discipline")).toBeVisible();
    await expect(page.getByText("User retention")).toBeVisible();
    await expect(page.getByText("Stake size")).toBeVisible();

    // Decisions table empty-state copy when no on-chain decisions yet.
    await expect(page.getByText("No decisions on chain yet")).toBeVisible();
  });
});
