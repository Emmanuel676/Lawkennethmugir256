"use client";

import { Moon, Sun } from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "./ui/button";

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
    <Button type="button" variant="outline" size={compact ? "icon" : "sm"} onClick={toggle} aria-pressed={dark}
            aria-label={dark ? "Switch to the light theme" : "Switch to the dark theme"}>
      {dark ? <Sun aria-hidden="true" /> : <Moon aria-hidden="true" />}
      {!compact && <span>{dark ? "Light theme" : "Dark theme"}</span>}
    </Button>
  );
}
