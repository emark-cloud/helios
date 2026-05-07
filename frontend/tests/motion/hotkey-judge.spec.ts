import { test, expect } from "@playwright/test";

/**
 * WS-FE-2 — `g j` hotkey chord lands on /judge. Mirrors the existing
 * `g d / g s / g a / g o` chords and is the only nav-level Phase 4
 * regression-prone surface (TopNav.tsx).
 */

test.describe("hotkey nav", () => {
  test("g j navigates to /judge", async ({ page }) => {
    // `/strategies` is a static route that doesn't require the Sentinel
    // WS subscription, so the chord can fire before any wallet flow.
    await page.route("**/subgraphs/**", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ data: { strategies: [] } }),
      }),
    );
    await page.goto("/strategies");
    // Bring focus to body so the keydown listener (which lives on
    // window) sees both keys; Playwright otherwise routes presses to
    // whatever element loaded first.
    await page.locator("body").click();
    await page.keyboard.press("KeyG");
    await page.keyboard.press("KeyJ");
    await expect(page).toHaveURL(/\/judge$/);
    await expect(page.getByRole("heading", { level: 1 })).toContainText(
      "Verify Helios end-to-end.",
    );
  });
});
