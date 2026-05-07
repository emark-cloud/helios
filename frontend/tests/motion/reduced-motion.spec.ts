import { test, expect } from "@playwright/test";

/**
 * WS-FE-7 reduced-motion audit. With `prefers-reduced-motion: reduce`
 * on, the three motion tokens collapse to 0ms and the inline-styled
 * keyframes (`helios-sunburst-grow`, `helios-cascade-row-in`,
 * `helios-rail-in`, `helios-chain-pulse`) are zero-duration. The
 * specific reduced-motion CSS lives in `globals.css` and `tokens.css`.
 */

test.describe("reduced motion", () => {
  test.use({ colorScheme: "dark" });

  test("token vars collapse to 0ms under prefers-reduced-motion", async ({ browser }) => {
    const context = await browser.newContext({ reducedMotion: "reduce" });
    const page = await context.newPage();
    await page.route("**/subgraphs/**", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ data: { strategies: [] } }),
      }),
    );
    await page.goto("/strategies");
    const tickStep = await page.evaluate(
      () => getComputedStyle(document.documentElement).getPropertyValue("--tick-step").trim(),
    );
    const tickSegment = await page.evaluate(
      () => getComputedStyle(document.documentElement).getPropertyValue("--tick-segment").trim(),
    );
    const tickCascade = await page.evaluate(
      () => getComputedStyle(document.documentElement).getPropertyValue("--tick-cascade").trim(),
    );
    expect(tickStep).toBe("0ms");
    expect(tickSegment).toBe("0ms");
    expect(tickCascade).toBe("0ms");
    await context.close();
  });
});
