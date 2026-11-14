"use client";

import { useEffect, useState } from "react";

export const THEME_KEY = "fairlend-theme";

/** Runs before the first paint (in <head>) so a saved dark choice never flashes light. Light is the default. */
/** "?theme=dark" or "?theme=light" in the address also sets it (handy for demos and screenshots). */
export const THEME_SCRIPT = `try{var q=new URLSearchParams(location.search).get("theme");if(q==="dark"||q==="light")localStorage.setItem("${THEME_KEY}",q);if(localStorage.getItem("${THEME_KEY}")==="dark")document.documentElement.classList.add("dark")}catch(e){}`;

export function ThemeToggle({ compact = false }: { compact?: boolean }) {
  const [dark, setDark] = useState(false);

  useEffect(() => {
    setDark(document.documentElement.classList.contains("dark"));
  }, []);

  function toggle() {
    const next = !dark;
    setDark(next);
    document.documentElement.classList.toggle("dark", next);
    try {
      localStorage.setItem(THEME_KEY, next ? "dark" : "light");
    } catch {
      /* private mode: the choice simply is not remembered */
    }
  }

  return (
    <button
      type="button"
      onClick={toggle}
      aria-pressed={dark}
      aria-label={dark ? "Switch to the light theme" : "Switch to the dark theme"}
      className="inline-flex items-center gap-2 rounded-lg border border-line px-3 py-2 text-sm text-ink-2 hover:bg-surface-2"
    >
      <svg aria-hidden="true" viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2">
        {dark ? (
          <path d="M12 3v2m0 14v2m9-9h-2M5 12H3m15.4-6.4-1.4 1.4M7 17l-1.4 1.4m12.8 0L17 17M7 7 5.6 5.6M16 12a4 4 0 1 1-8 0 4 4 0 0 1 8 0Z" />
        ) : (
          <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8Z" />
        )}
      </svg>
      {!compact && <span>{dark ? "Light theme" : "Dark theme"}</span>}
    </button>
  );
}
