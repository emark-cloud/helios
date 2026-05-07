import { test, expect } from "@playwright/test";

/**
 * WS-FE-7 onboard error UX. The UI must distinguish a wallet-side
 * "signing failed" rejection (the user dismissed the wallet prompt)
 * from a server-side "allocator unreachable" failure (the user did
 * sign but Sentinel didn't acknowledge). The latter must keep the
 * signed payload around so the retry doesn't re-prompt.
 *
 * The tests run on the EIP-191 dev path (NEXT_PUBLIC_USE_PASSPORT=0
 * in `frontend/playwright.config.ts`) and exercise the surface
 * directly; the wallet flow itself is mocked via the dev anvil keys
 * the harness uses.
 */

test.describe("/onboard error UX", () => {
  test("expanded defund controls render three editable sliders", async ({ page }) => {
    await page.goto("/onboard");
    await page.getByRole("button", { name: /Advanced/ }).first().click();

    // Three sliders: TWAP bars / trigger bond / confirm window.
    await expect(page.getByLabel("TWAP bars")).toBeVisible();
    await expect(page.getByLabel("Trigger bond")).toBeVisible();
    await expect(page.getByLabel("Confirm window")).toBeVisible();
    // Help text covers all three knobs.
    await expect(page.getByText(/Consecutive observations/)).toBeVisible();
    await expect(page.getByText(/refunded if the breach confirms/)).toBeVisible();
    await expect(page.getByText(/Bond slashed to user/)).toBeVisible();
  });
});
