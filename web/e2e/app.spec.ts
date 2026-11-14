// Browser tests (Phase 12C): keyboard paths through sign-in, import and delete; phone width; both themes; and an
// automated accessibility check (axe-core, WCAG 2 A and AA rules) that fails on any serious or critical problem.
import { existsSync } from "node:fs";
import path from "node:path";

import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

const PASSWORD = process.env.E2E_PASSWORD!;
const PACK = path.resolve(__dirname, "..", "..", "sample_pack", "baseline", "lender_D");
const TABLES = ["lenders", "borrowers", "loans", "transactions", "messages"];
const DATASET = "E2E lender D";

async function expectAccessible(page: Page, label: string) {
  const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
  const serious = results.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
  const report = serious.map((v) => `${v.id} (${v.impact}): ${v.help} -> ${v.nodes.slice(0, 3).map((n) => n.target.join(" ")).join(" | ")}`);
  expect(report, `accessibility problems on ${label}`).toEqual([]);
}

/** Press Tab until the element is focused, proving it can be reached with the keyboard alone. */
async function tabTo(page: Page, selector: string, max = 60) {
  for (let i = 0; i < max; i++) {
    if (await page.locator(selector).evaluate((el) => el === document.activeElement).catch(() => false)) return;
    await page.keyboard.press("Tab");
  }
  throw new Error(`Could not reach ${selector} with the Tab key`);
}

async function signInWithKeyboard(page: Page, role: string) {
  await page.goto("/signin");
  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
  await tabTo(page, "#email");
  await page.keyboard.type(`${role}@example.org`);
  await page.keyboard.press("Tab");
  await page.keyboard.type(PASSWORD);
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/\/datasets$/);
}

test.describe.serial("keyboard paths", () => {
  test("sign in with the keyboard, and a wrong password shows the neutral message", async ({ page }) => {
    await page.goto("/signin");
    await expectAccessible(page, "sign-in page");
    await tabTo(page, "#email");
    await page.keyboard.type("importer@example.org");
    await page.keyboard.press("Tab");
    await page.keyboard.type("not the password");
    await page.keyboard.press("Enter");
    await expect(page.locator("form").getByRole("alert")).toHaveText("Email or password not recognised.");
    await signInWithKeyboard(page, "viewer");
    await expect(page.getByRole("heading", { name: "Datasets" })).toBeVisible();
    await expectAccessible(page, "datasets page");
  });

  test("import the lender D sample pack with the keyboard", async ({ page }) => {
    test.skip(!existsSync(path.join(PACK, "lenders.csv")), "Build the sample packs first: .\\dev.ps1 -SamplePack");
    await signInWithKeyboard(page, "importer");
    await page.goto("/import");
    await expect(page.getByRole("heading", { name: "Import data" })).toBeVisible();
    await tabTo(page, "#ds-name");
    await page.keyboard.type(DATASET);
    // A file chooser is the browser's own dialog; picking the files is the one step done without the keyboard.
    await page.locator("#files").setInputFiles(TABLES.map((t) => path.join(PACK, `${t}.csv`)));
    await tabTo(page, "button:has-text('Check the files')");
    await page.keyboard.press("Enter");
    await expect(page.getByText("No errors found.")).toBeVisible();
    await tabTo(page, "input[type=checkbox] >> nth=-1");
    await page.keyboard.press("Space");
    await tabTo(page, "button:text-is('Import')");
    await page.keyboard.press("Enter");
    await expect(page.getByText("Imported. Shown as demonstration data.").first()).toBeVisible({ timeout: 90_000 });
    await expect(page.getByText("Review labels page")).toBeVisible();
    await expectAccessible(page, "import page after an import");
  });

  test("delete that dataset with the keyboard (Admin)", async ({ page }) => {
    test.skip(!existsSync(path.join(PACK, "lenders.csv")), "Build the sample packs first: .\\dev.ps1 -SamplePack");
    await signInWithKeyboard(page, "admin");
    const card = page.locator("section", { hasText: DATASET });
    await expect(card).toBeVisible();
    await tabTo(page, `section:has-text("${DATASET}") button:has-text("Delete")`);
    await page.keyboard.press("Enter");
    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();
    await expectAccessible(page, "delete dialog");
    await expect(page.locator("#confirm-name")).toBeFocused();
    await page.keyboard.type(DATASET);
    await tabTo(page, "button:has-text('Delete dataset')");
    await page.keyboard.press("Enter");
    await expect(page.getByRole("status")).toContainText("were deleted");
    await expect(page.locator("section", { hasText: DATASET })).toHaveCount(0);
  });
});

const PAGES = ["/", "/borrowers", "/borrowers/B01767", "/lenders", "/repayments", "/guided-demo", "/export", "/about", "/signin"];

test("phone width: no page scrolls sideways, and the More menu works", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  for (const url of PAGES) {
    await page.goto(url);
    await page.waitForLoadState("networkidle");
    const wide = await page.evaluate(() => document.documentElement.scrollWidth);
    expect(wide, `${url} is wider than the phone`).toBeLessThanOrEqual(390);
  }
  await page.goto("/");
  await page.getByRole("button", { name: "More" }).click();
  await expect(page.locator("#more-menu").getByRole("link", { name: "Guided demo" })).toBeVisible();
  await expect(page.locator("#more-menu").getByRole("link", { name: "About" })).toBeVisible();
});

for (const theme of ["light", "dark"] as const) {
  test(`${theme} theme passes the accessibility check`, async ({ page }) => {
    for (const url of ["/", "/repayments", "/guided-demo", "/about", "/export"]) {
      await page.goto(`${url}?theme=${theme}`);
      await expect(page.locator("main h1")).toBeVisible();
      await page.waitForLoadState("networkidle");
      expect(await page.evaluate(() => document.documentElement.classList.contains("dark"))).toBe(theme === "dark");
      await expectAccessible(page, `${url} (${theme})`);
    }
  });
}
