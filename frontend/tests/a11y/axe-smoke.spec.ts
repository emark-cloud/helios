import AxeBuilder from "@axe-core/playwright";
import { test, expect } from "@playwright/test";

/**
 * WS-ACC — WCAG AA smoke. axe-core runs across the static landing /
 * judge / strategies surfaces with the canonical fixture data plumbed
 * via subgraph mocks. Asserts zero `serious` or `critical` violations
 * — moderate / minor are tolerated and tracked as Phase-5+ polish.
 *
 * Subgraph is mocked with empty responses so the test doesn't depend
 * on a deployed Goldsky endpoint; the surfaces still render their
 * empty-state copy and chrome, which is what we want axe to evaluate.
 */

const SUBGRAPH_EMPTY = {
  data: {
    strategies: [],
    allocators: [],
    allocations: [],
    trades: [],
  },
};

async function mockSubgraph(page: import("@playwright/test").Page): Promise<void> {
  await page.route("**/subgraphs/**", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(SUBGRAPH_EMPTY),
    }),
  );
}

const ROUTES: Array<{ name: string; path: string }> = [
  { name: "landing", path: "/" },
  { name: "judge", path: "/judge" },
  { name: "strategies", path: "/strategies" },
  { name: "onboard", path: "/onboard" },
];

test.describe("WCAG AA axe-core smoke", () => {
  for (const route of ROUTES) {
    test(`${route.name} — no serious or critical violations`, async ({ page }) => {
      await mockSubgraph(page);
      await page.goto(route.path);

      // Wait for page chrome — `main` landmark is rendered by AppShell.
      await page.waitForSelector("main, [role='main']", { timeout: 5_000 });

      const results = await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa"])
        .analyze();

      const blocking = results.violations.filter(
        (v) => v.impact === "serious" || v.impact === "critical",
      );
      // Surface the failure list so the test report names the rule
      // and the offending node, not just a count.
      expect(
        blocking,
        `axe found ${blocking.length} blocking violation(s) on ${route.path}: ${blocking
          .map((v) => `${v.id} (${v.impact})`)
          .join(", ")}`,
      ).toEqual([]);
    });
  }
});
