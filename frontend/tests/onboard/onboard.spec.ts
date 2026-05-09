import { test, expect } from "@playwright/test";

/// WS6.B smoke for the `/onboard` allocator-picker step. Helix was a
/// Phase-3 scope cut (project_phase3_scope_cuts), so the picker now
/// renders Sentinel only. Asserts:
///   1. The single Sentinel card renders with the reference badge and
///      is selected by default.
///   2. A stale `"helix"` value in localStorage is coerced back to
///      `"sentinel"` on read (the AllocatorPicker only ever surfaces
///      Sentinel, so the round-trip lands on Sentinel either way).

test.describe("/onboard allocator picker", () => {
  test("renders the Sentinel card with the reference badge and is selected", async ({ page }) => {
    await page.goto("/onboard");

    const cards = page.locator("[data-allocator-choice]");
    await expect(cards).toHaveCount(1);

    const badges = page.getByText("Official Reference");
    await expect(badges).toHaveCount(1);

    const sentinel = page.locator('[data-allocator-choice="sentinel"]');
    await expect(sentinel).toHaveAttribute("aria-checked", "true");
  });

  test("stale helix in localStorage falls back to sentinel on reload", async ({ page }) => {
    await page.goto("/onboard");
    await page.evaluate(() =>
      window.localStorage.setItem("helios.onboard.allocator", "helix"),
    );
    await page.reload();

    const sentinel = page.locator('[data-allocator-choice="sentinel"]');
    await expect(sentinel).toHaveAttribute("aria-checked", "true");
    await expect(page.locator('[data-allocator-choice="helix"]')).toHaveCount(0);
  });
});
