// Browser tests for the web interface (Phase 12C). Separate from the Python suite and light on memory:
// ONE worker, the Chrome already installed on this computer (no browser download), and
// a throwaway data folder, so they never touch data\web. The web app runs on port 3100; the API on its default
// port 8000, because Next.js fixes where /api/* is forwarded when the web app is BUILT (FAIRLEND_API_URL).
// Playwright refuses to start if something already answers on either port, so stop your dev servers first.
//
// Run from the project folder, with no other API or web server running:
//   npm --prefix web run build
//   npm --prefix web run test:e2e
import { randomBytes } from "node:crypto";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

import { defineConfig } from "@playwright/test";

const ROOT = path.resolve(__dirname, "..", "..");
const WEB = path.resolve(__dirname, "..");
const PYTHON = path.join(ROOT, ".venv", "Scripts", "python.exe");

// Shared with global-setup.ts and the tests through the environment of this one test run only.
process.env.E2E_DATA ??= mkdtempSync(path.join(tmpdir(), "fairlend-e2e-"));
process.env.E2E_PASSWORD ??= randomBytes(18).toString("base64url");   // random per run, never written to disk
process.env.E2E_SECRET ??= randomBytes(32).toString("hex");

export default defineConfig({
  testDir: ".",
  testMatch: "*.spec.ts",
  workers: 1,
  fullyParallel: false,
  retries: 0,
  timeout: 120_000,
  expect: { timeout: 30_000 },
  reporter: [["list"]],
  globalSetup: "./global-setup.ts",
  globalTeardown: "./global-teardown.ts",
  use: {
    baseURL: "http://localhost:3100",
    channel: "chrome",
    headless: true,
    trace: "off",
    video: "off",
    screenshot: "only-on-failure",
  },
  webServer: [
    {
      command: `"${PYTHON}" -m api`,
      cwd: ROOT,
      url: "http://127.0.0.1:8000/api/health",
      timeout: 180_000,
      reuseExistingServer: false,
      env: {
        FAIRLEND_WEB_ORIGINS: "http://localhost:3100",
        FAIRLEND_WEB_DATA: process.env.E2E_DATA!,
        FAIRLEND_SESSION_SECRET: process.env.E2E_SECRET!,
        FAIRLEND_PRESENT: "1",
      },
    },
    {
      command: "npx next start --port 3100 --hostname localhost",
      cwd: WEB,
      url: "http://localhost:3100/",
      timeout: 120_000,
      reuseExistingServer: false,
      env: {},
    },
  ],
});
