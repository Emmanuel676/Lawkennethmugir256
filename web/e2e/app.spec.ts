// Browser tests (Phase 12C, extended in Phase 14): the landing page at phone and desktop width in both themes; keyboard
// paths through sign-in, Request access with Admin approval, import and delete; phone width; both themes; and an
// automated accessibility check (axe-core, WCAG 2 A and AA rules) that fails on any serious or critical problem.
import { existsSync } from "node:fs";
import path from "node:path";

import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

const PASSWORD = process.env.E2E_PASSWORD!;
const PACK = path.resolve(__dirname, "..", "..", "sample_pack", "baseline", "lender_D");
const TABLES = ["lenders", "borrowers", "loans", "transactions", "messages"];
const DATASET = "E2E lender D";
const REQUESTER = "e2e.requester@example.org";
const REQUESTER_PASSWORD = "a requester password";

async function expectAccessible(page: Page, label: string) {
  const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
  const serious = results.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
  const report = serious.map((v) => `${v.id} (${v.impact}): ${v.help} -> ${v.nodes.slice(0, 3).map((n) => n.target.join(" ")).join(" | ")}`);
  expect(report, `accessibility problems on ${label}`).toEqual([]);
}

/** Press Tab until the element is focused, proving it can be reached with the keyboard alone. */
async function tabTo(page: Page, selector: string, max = 80) {
  for (let i = 0; i < max; i++) {
    if (await page.locator(selector).first().evaluate((el) => el === document.activeElement).catch(() => false)) return;
    await page.keyboard.press("Tab");
  }
  throw new Error(`Could not reach ${selector} with the Tab key`);
}

async function signInWithKeyboard(page: Page, email: string, password: string) {
  await page.goto("/signin");
  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
  await tabTo(page, "#email");
  await page.keyboard.type(email);
  await page.keyboard.press("Tab");
  await page.keyboard.type(password);
  await page.keyboard.press("Enter");
}

async function signInAs(page: Page, role: string) {
  await signInWithKeyboard(page, `${role}@example.org`, PASSWORD);
  await expect(page).toHaveURL(/\/datasets$/);
}

// --- The landing page --------------------------------------------------------------------------------------------------

for (const theme of ["light", "dark"] as const) {
  for (const size of [{ name: "phone", width: 390, height: 844 }, { name: "desktop", width: 1440, height: 900 }]) {
    test(`landing page, ${size.name}, ${theme} theme`, async ({ page }) => {
      await page.setViewportSize({ width: size.width, height: size.height });
      await page.goto(`/?theme=${theme}`);
      await expect(page.getByRole("heading", { level: 1 })).toContainText("One view across lenders");
      await expect(page.getByRole("link", { name: /Explore the demo/ }).first()).toHaveAttribute("href", "/overview");
      await expect(page.getByRole("link", { name: "Request access" }).first()).toHaveAttribute("href", "/request-access");
      for (const heading of ["Each lender sees only its own loans.", "Four steps, and a person at the end.",
                             "What the demo shows right now.", "Built for the people who look after fair lending.",
                             "Privacy and fairness are part of the design."]) {
        await expect(page.getByRole("heading", { name: heading })).toBeAttached();
      }
      await page.getByRole("heading", { name: "What the demo shows right now." }).scrollIntoViewIfNeeded();
      await expect(page.locator("#preview").getByText("Borrowers scored")).toBeVisible();
      await expect(page.getByText("Demonstration data. A flag is a prompt for a human to look, not a verdict.").first()).toBeVisible();
      await page.waitForLoadState("networkidle");
      const wide = await page.evaluate(() => document.documentElement.scrollWidth);
      expect(wide, "the landing page is wider than the window").toBeLessThanOrEqual(size.width);
      expect(await page.evaluate(() => document.documentElement.classList.contains("dark"))).toBe(theme === "dark");
      await expectAccessible(page, `landing page (${size.name}, ${theme})`);
    });
  }
}

// --- Keyboard paths ----------------------------------------------------------------------------------------------------

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
    await signInAs(page, "viewer");
    await expect(page.getByRole("heading", { name: "Datasets" })).toBeVisible();
    await expectAccessible(page, "datasets page");
  });

  test("request access with the keyboard; the account waits for approval", async ({ page }) => {
    await page.goto("/request-access");
    await expect(page.getByRole("heading", { name: "Request access" })).toBeVisible();
    await expect(page.getByText("No email is sent at any point")).toBeVisible();
    await expectAccessible(page, "request access page");
    await tabTo(page, "#full_name");
    await page.keyboard.type("Ada Example");
    await page.keyboard.press("Tab");
    await page.keyboard.type(REQUESTER);
    await page.keyboard.press("Tab");
    await page.keyboard.type("Consumer Body Demo");
    await page.keyboard.press("Tab");                       // the type-of-user select (Radix, shadcn/ui)
    await expect(page.locator("#user_type")).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(page.getByRole("listbox")).toBeVisible();
    await page.keyboard.press("ArrowDown");
    await page.keyboard.press("Enter");
    await expect(page.locator("#user_type")).not.toContainText("Choose one");
    await tabTo(page, "#reason");
    await page.keyboard.type("To review lending conduct for a demonstration.");
    await tabTo(page, "#password");
    await page.keyboard.type(REQUESTER_PASSWORD);
    await tabTo(page, "#password_again");
    await page.keyboard.type(REQUESTER_PASSWORD);
    await page.keyboard.press("Enter");
    await expect(page.getByRole("heading", { name: "Request received" })).toBeVisible();
    await expect(page.getByText("no email is sent")).toBeVisible();
    // The right password tells the person their account is waiting; it does not sign them in.
    await signInWithKeyboard(page, REQUESTER, REQUESTER_PASSWORD);
    await expect(page.locator("form").getByRole("alert")).toContainText("waiting for approval");
    await expect(page).toHaveURL(/\/signin$/);
  });

  test("an Admin approves the request with the keyboard, and the person can sign in", async ({ page }) => {
    await signInAs(page, "admin");
    await page.goto("/users");
    await expect(page.getByRole("tab", { name: /Pending requests \(1\)/ })).toHaveAttribute("data-state", "active");
    await expect(page.getByText("Consumer Body Demo")).toBeVisible();
    await expectAccessible(page, "users page with a pending request");
    await tabTo(page, `button:has-text("Approve as Viewer: ${REQUESTER}")`);
    await page.keyboard.press("Enter");
    await expect(page.getByText(`${REQUESTER} approved as Viewer.`)).toBeVisible();
    await expect(page.getByRole("tab", { name: /Pending requests \(0\)/ })).toBeVisible();
    await page.context().clearCookies();
    await signInWithKeyboard(page, REQUESTER, REQUESTER_PASSWORD);
    await expect(page).toHaveURL(/\/datasets$/);
  });

  test("import the lender D sample pack with the keyboard", async ({ page }) => {
    test.skip(!existsSync(path.join(PACK, "lenders.csv")), "Build the sample packs first: .\\dev.ps1 -SamplePack");
    await signInAs(page, "importer");
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
    await signInAs(page, "admin");
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
    await expect(page.locator("p[role=status]")).toContainText("were deleted");
    await expect(page.locator("section", { hasText: DATASET })).toHaveCount(0);
  });
});

// --- Phone width and themes ---------------------------------------------------------------------------------------------

const PAGES = ["/", "/overview", "/borrowers", "/borrowers/B01767", "/lenders", "/repayments", "/guided-demo", "/export",
               "/about", "/signin", "/request-access"];

test("phone width: no page scrolls sideways, and the More menu works", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  for (const url of PAGES) {
    await page.goto(url);
    await page.waitForLoadState("networkidle");
    const wide = await page.evaluate(() => document.documentElement.scrollWidth);
    expect(wide, `${url} is wider than the phone`).toBeLessThanOrEqual(390);
  }
  await page.goto("/overview");
  await page.getByRole("button", { name: "More" }).click();
  await expect(page.locator("#more-menu").getByRole("link", { name: "Guided demo" })).toBeVisible();
  await expect(page.locator("#more-menu").getByRole("link", { name: "About" })).toBeVisible();
});

test("the first-visit guide on /overview can be dismissed and stays dismissed", async ({ page }) => {
  await page.goto("/overview");
  const guide = page.getByRole("heading", { name: "Four things to look at on this page" });
  await expect(guide).toBeVisible();
  await page.getByRole("button", { name: "Dismiss the guide" }).click();
  await expect(guide).toHaveCount(0);
  await page.reload();
  await expect(page.getByRole("heading", { name: "Overview", level: 1 })).toBeVisible();
  await expect(guide).toHaveCount(0);
});

for (const theme of ["light", "dark"] as const) {
  test(`${theme} theme passes the accessibility check`, async ({ page }) => {
    for (const url of ["/overview", "/repayments", "/guided-demo", "/about", "/export", "/request-access"]) {
      await page.goto(`${url}?theme=${theme}`);
      await expect(page.locator("main h1")).toBeVisible();
      await page.waitForLoadState("networkidle");
      expect(await page.evaluate(() => document.documentElement.classList.contains("dark"))).toBe(theme === "dark");
      await expectAccessible(page, `${url} (${theme})`);
    }
  });
}
