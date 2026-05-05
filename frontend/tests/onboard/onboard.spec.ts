import { test, expect } from "@playwright/test";

/// WS6.B smoke for the `/onboard` allocator-picker step. Asserts:
///   1. Both Sentinel + Helix cards render with the reference badge
///   2. Selecting Helix flips the radio state and writes
///      `helios.onboard.allocator` = "helix" to localStorage
///   3. The choice round-trips on reload (re-loading hydrates the
///      previously-selected card)

test.describe("/onboard allocator picker", () => {
  test("renders both reference allocators with badges and default Sentinel", async ({ page }) => {
    await page.goto("/onboard");

    const cards = page.locator('[data-allocator-choice]');
    await expect(cards).toHaveCount(2);

    const badges = page.getByText("Official Reference");
    await expect(badges).toHaveCount(2);

    const sentinel = page.locator('[data-allocator-choice="sentinel"]');
    const helix = page.locator('[data-allocator-choice="helix"]');
    await expect(sentinel).toHaveAttribute("aria-checked", "true");
    await expect(helix).toHaveAttribute("aria-checked", "false");
  });

  test("selecting Helix persists the choice in localStorage", async ({ page }) => {
    await page.goto("/onboard");

    const helix = page.locator('[data-allocator-choice="helix"]');
    await helix.click();
    await expect(helix).toHaveAttribute("aria-checked", "true");

    const stored = await page.evaluate(() =>
      window.localStorage.getItem("helios.onboard.allocator"),
    );
    expect(stored).toBe("helix");
  });

  test("choice round-trips on reload", async ({ page }) => {
    await page.goto("/onboard");
    await page.evaluate(() =>
      window.localStorage.setItem("helios.onboard.allocator", "helix"),
    );
    await page.reload();

    const helix = page.locator('[data-allocator-choice="helix"]');
    const sentinel = page.locator('[data-allocator-choice="sentinel"]');
    await expect(helix).toHaveAttribute("aria-checked", "true");
    await expect(sentinel).toHaveAttribute("aria-checked", "false");
  });
});
