import { test, expect } from "@playwright/test";

import momentumFixture from "./fixtures/momentum.json";
import meanReversionFixture from "./fixtures/mean_reversion.json";
import yieldRotationFixture from "./fixtures/yield_rotation.json";

type AuditFixture = typeof momentumFixture;

const cases: Array<{ slug: string; fixture: AuditFixture }> = [
  { slug: "momentum", fixture: momentumFixture },
  { slug: "mean_reversion", fixture: meanReversionFixture },
  { slug: "yield_rotation", fixture: yieldRotationFixture },
];

test.describe("/audit/<actor>", () => {
  for (const { slug, fixture } of cases) {
    test(`${slug} — page snapshot`, async ({ page }) => {
      await page.route("**/v1/audit/*", (route) =>
        route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(fixture),
        }),
      );

      await page.goto(`/audit/${fixture.actor}`);

      // Wait for the data-driven body to replace the loading skeleton:
      // the components_hash hex is unique per fixture, so its presence
      // proves the page rendered the response (not the skeleton).
      await expect(page.getByText(fixture.components_hash)).toBeVisible();

      await expect(page).toHaveScreenshot(`${slug}.png`, { fullPage: true });
    });
  }
});
