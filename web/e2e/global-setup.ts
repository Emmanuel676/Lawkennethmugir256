// Creates the three test accounts in this run's throwaway data folder, with the run's random password.
// The password reaches the seed script through its environment only (never a command argument or a file).
import { execFileSync } from "node:child_process";
import path from "node:path";

export default function globalSetup() {
  const root = path.resolve(__dirname, "..", "..");
  execFileSync(path.join(root, ".venv", "Scripts", "python.exe"), [path.join(__dirname, "seed_users.py")], {
    cwd: root,
    env: { ...process.env, FAIRLEND_WEB_DATA: process.env.E2E_DATA, FAIRLEND_SESSION_SECRET: process.env.E2E_SECRET },
    stdio: "inherit",
  });
}
