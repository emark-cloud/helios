import { test, expect } from "@playwright/test";

/**
 * WS-FE-2 smoke for `/`. Asserts headline + four-stat band + CTAs +
 * secondary links land. Mocks subgraph so the band always returns
 * deterministic numbers.
 */

const STATS = {
  data: {
    strategies: [
      { id: "0x1111111111111111111111111111111111111111", totalAttestedTrades: 12 },
      { id: "0x2222222222222222222222222222222222222222", totalAttestedTrades: 7 },
      { id: "0x3333333333333333333333333333333333333333", totalAttestedTrades: 5 },
    ],
    allocators: [
      { id: "0xa1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1" },
      { id: "0xa2a2a2a2a2a2a2a2a2a2a2a2a2a2a2a2a2a2a2a2" },
    ],
    allocations: [
      { capitalDeployed: "1500000000" },
      { capitalDeployed: "500000000" },
      { capitalDeployed: "1000000000" },
    ],
    trades: [],
  },
};

function fulfill(body: unknown) {
  return {
    status: 200,
    contentType: "application/json",
    body: JSON.stringify(body),
  };
}

test.describe("/ landing", () => {
  test("renders headline, stats band, and primary CTAs", async ({ page }) => {
    await page.route("**/subgraphs/**", async (route) => {
      const req = route.request().postData() ?? "";
      if (req.includes("query LandingStats")) {
        await route.fulfill(fulfill(STATS));
        return;
      }
      await route.fulfill(fulfill({ data: {} }));
    });

    await page.goto("/");

    // Visible mark is the "Helios." masthead (sr-only h1 carries the name);
    // the thesis deck below it carries the discoverable headline copy.
    await expect(
      page.getByText(/A capital market for AI strategies/i),
    ).toBeVisible();

    const enter = page.getByRole("link", { name: /enter app/i });
    await expect(enter).toBeVisible();
    await expect(enter).toHaveAttribute("href", "/onboard");

    const spec = page.getByRole("link", { name: /read the spec/i });
    await expect(spec).toBeVisible();
    await expect(spec).toHaveAttribute("href", /github\.com\/.+Helios\.md$/);

    // Stats band — three of the four cells render finite numbers from
    // the deterministic fixture.
    const band = page.getByLabel("Live network statistics");
    await expect(band).toBeVisible();
    await expect(band.getByText("Active strategies")).toBeVisible();
    await expect(band.getByText("3", { exact: true }).first()).toBeVisible();
    await expect(band.getByText("Active allocators")).toBeVisible();
    await expect(band.getByText("Attested trades")).toBeVisible();
    // 12 + 7 + 5 = 24
    await expect(band.getByText("24", { exact: true }).first()).toBeVisible();
  });
});
