// Browser tests (Phase 12C, extended in Phases 14, 14c and 14d): the landing page at phone and desktop width in both themes; keyboard
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
const TRUST = "Demonstration data. A flag is a prompt for a human to look, not a verdict.";

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
      await expect(page.getByRole("heading", { level: 1 })).toHaveText("Fair lending needs the whole picture.");
      await expect(page.getByText("Lending conduct monitor · prototype")).toBeVisible();
      await expect(page.getByRole("link", { name: /Explore the demo/ }).first()).toHaveAttribute("href", "/overview");
      await expect(page.getByRole("link", { name: "Request access" }).first()).toHaveAttribute("href", "/request-access");
      for (const point of ["No names stored", "Every flag explained", "A human decides"]) {
        await expect(page.getByText(point, { exact: true }).first()).toBeVisible();
      }
      for (const heading of ["Each lender sees only its own loans.", "Four steps, and a person at the end.",
                             "Built for the people who look after fair lending.", "Privacy and fairness are part of the design."]) {
        await expect(page.getByRole("heading", { name: heading })).toBeAttached();
      }
      for (const title of ["Several loans at once", "Borrowing to repay", "Harsh collection"]) {
        await expect(page.getByRole("heading", { name: title })).toBeAttached();
      }
      // The product preview reads its numbers from the API: the full frame on a desktop, a simpler card on a phone.
      const preview = page.getByTestId(size.name === "phone" ? "hero-preview-compact" : "hero-preview");
      await expect(preview).toBeVisible();
      await expect(preview.locator("[data-tile]").filter({ hasText: "Borrowers" })).toBeVisible();
      await expect(preview.getByText("5,000").first()).toBeVisible();
      if (size.name === "desktop") await expect(preview.getByText("Highest-scoring borrowers")).toBeVisible();
      // The stats band: the first two figures come from the API.
      await expect(page.getByRole("term").filter({ hasText: "demonstration lenders compared" })).toBeAttached();
      await expect(page.getByRole("term").filter({ hasText: "signals behind every score" })).toBeAttached();
      // Phase 14d: no sticky strip; the message sits quietly in the footer.
      await expect(page.getByRole("note", { name: "About this data" })).toHaveCount(0);
      await expect(page.locator("footer").getByText(TRUST)).toBeVisible();
      await page.waitForLoadState("networkidle");
      const wide = await page.evaluate(() => document.documentElement.scrollWidth);
      expect(wide, "the landing page is wider than the window").toBeLessThanOrEqual(size.width);
      expect(await page.evaluate(() => document.documentElement.classList.contains("dark"))).toBe(theme === "dark");
      await expectAccessible(page, `landing page (${size.name}, ${theme})`);
    });
  }
}

// --- The landing page's product preview never clips (Phase 14c) -------------------------------------------------------
// Real screens at common widths, plus a 1920 px screen at 125% and 150% browser zoom (the window is then 1536 and
// 1280 CSS pixels wide, drawn at 1.25 and 1.5 device pixels per CSS pixel). In every one, nothing inside the preview may
// overflow its own box, leave the frame or the window, end in an ellipsis or wrap onto a second line, and the page may
// not scroll sideways. Set E2E_SHOTS to a folder to save a screenshot of each case.

/** Everything wrong with the preview's layout: clipping, overflow, ellipses, wrapped short text, sideways scroll.
 *  Runs inside the page (Playwright sends its source), so it must not use anything from this file. */
function previewProblems(id: string): string[] {
  const root = document.querySelector(`[data-testid="${id}"]`)!;
  const frame = root.getBoundingClientRect();
  const found: string[] = [];
  const name = (el: Element) => `${el.tagName.toLowerCase()} "${(el.textContent ?? "").trim().slice(0, 30)}"`;
  if (frame.left < 0 || frame.right > window.innerWidth) found.push(`frame ${frame.left}-${frame.right} leaves the window`);
  if (document.documentElement.scrollWidth > window.innerWidth) found.push("the page scrolls sideways");
  for (const el of Array.from(root.querySelectorAll("*"))) {
    const style = getComputedStyle(el);
    if (style.display === "none" || el.closest(".sr-only")) continue;
    const box = el.getBoundingClientRect();
    if (box.width === 0 && box.height === 0) continue;
    if (box.left < frame.left - 0.5 || box.right > frame.right + 0.5) found.push(`${name(el)} leaves the frame`);
    if (el instanceof HTMLElement && el.clientWidth > 0 && el.scrollWidth > el.clientWidth + 1) {
      found.push(`${name(el)} overflows its box (${el.scrollWidth} > ${el.clientWidth})`);
    }
    if (style.textOverflow === "ellipsis") found.push(`${name(el)} uses an ellipsis`);
    // Short text (every child inline) must stay on one line.
    const inline = Array.from(el.children).every((c) => getComputedStyle(c).display.startsWith("inline"));
    if (inline && (el.textContent ?? "").trim() && !style.display.includes("flex") && !style.display.includes("grid")) {
      const range = document.createRange();
      range.selectNodeContents(el);
      const tops = Array.from(range.getClientRects()).map((r) => r.top).sort((a, b) => a - b);
      const lines = tops.filter((t, i) => i === 0 || t - tops[i - 1] > 6).length;
      if (lines > 1 && el.tagName !== "UL") found.push(`${name(el)} wraps onto ${lines} lines`);
    }
  }
  return found;
}

const PREVIEW_SIZES = [
  { label: "1280", width: 1280, height: 800, scale: 1 },
  { label: "1366", width: 1366, height: 768, scale: 1 },
  { label: "1440", width: 1440, height: 900, scale: 1 },
  { label: "1536", width: 1536, height: 864, scale: 1 },
  { label: "1920", width: 1920, height: 1080, scale: 1 },
  { label: "1920_zoom125", width: 1536, height: 864, scale: 1.25 },
  { label: "1920_zoom150", width: 1280, height: 720, scale: 1.5 },
  { label: "phone", width: 390, height: 844, scale: 3 },
];

for (const theme of ["light", "dark"] as const) {
  test(`the landing preview fits at every width, ${theme} theme`, async ({ browser, baseURL }) => {
    test.setTimeout(240_000);
    for (const size of PREVIEW_SIZES) {
      const context = await browser.newContext({ baseURL, viewport: { width: size.width, height: size.height }, deviceScaleFactor: size.scale });
      const page = await context.newPage();
      await page.goto(`/?theme=${theme}`);
      const testId = size.width < 1024 ? "hero-preview-compact" : "hero-preview";
      const preview = page.getByTestId(testId);
      await expect(preview.getByText("5,000", { exact: true }).first()).toBeVisible();
      await page.waitForLoadState("networkidle");
      await page.waitForTimeout(1500);   // let the count-up tiles reach their final values

      const problems = await page.evaluate(previewProblems, testId);
      // The check itself can fail: a clipped label and a wrapped label, put in for a moment, must both be reported.
      if (size.label === "1440") {
        // (Separate steps, not eval inside the page, so the site's content security policy is never in the way.)
        await page.evaluate((id) => {
          const probe = document.createElement("div");
          probe.id = "e2e-probe";
          probe.innerHTML = '<p style="width:40px;overflow:hidden;white-space:nowrap">Owed by high band</p>' +
                            '<p style="width:40px">Owed by high band</p>';
          document.querySelector(`[data-testid="${id}"]`)!.appendChild(probe);
        }, testId);
        const caught = await page.evaluate(previewProblems, testId);
        await page.evaluate(() => document.getElementById("e2e-probe")!.remove());
        expect(caught.some((p) => p.includes("overflows its box")), "the overflow check can fail").toBe(true);
        expect(caught.some((p) => p.includes("wraps onto")), "the wrap check can fail").toBe(true);
      }
      expect(problems, `the preview at ${size.label} (${theme})`).toEqual([]);

      if (process.env.E2E_SHOTS) {
        const file = path.join(process.env.E2E_SHOTS, `14c_landing_${size.label}_${theme}.png`);
        if (size.width < 1024) await page.screenshot({ path: file, fullPage: true, clip: { x: 0, y: 0, width: size.width, height: 1450 } });
        else await page.screenshot({ path: file });
      }
      await context.close();
    }
  });
}

// --- The trust message, kept quiet (Phase 14d) ---------------------------------------------------------------------------

test("the trust message is a small footer line on every page, not a sticky strip", async ({ page }) => {
  for (const url of ["/overview", "/borrowers", "/lenders", "/repayments", "/about", "/signin", "/request-access"]) {
    await page.goto(url);
    await expect(page.getByRole("note", { name: "About this data" }), url).toHaveCount(0);
    const line = page.getByRole("contentinfo").getByText(TRUST);
    await expect(line, url).toBeAttached();
    expect(await line.evaluate((el) => getComputedStyle(el).position), url).toBe("static");
  }
});

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
