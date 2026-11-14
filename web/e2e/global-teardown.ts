// Deletes this run's throwaway data folder (users, sessions, imported test datasets).
import { rmSync } from "node:fs";

export default function globalTeardown() {
  const folder = process.env.E2E_DATA;
  if (folder && folder.includes("fairlend-e2e-")) {
    try {
      rmSync(folder, { recursive: true, force: true });
    } catch {
      /* the API may still hold a file for a moment on Windows; the OS temp folder is cleaned later */
    }
  }
}
