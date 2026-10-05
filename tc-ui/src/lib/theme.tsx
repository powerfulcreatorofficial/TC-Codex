"use client";

import * as React from "react";

type Theme = "light" | "dark" | "system";
interface ThemeContextValue {
  theme: Theme;
  setTheme: (theme: Theme) => void;
  resolved: "light" | "dark";
}

const ThemeContext = React.createContext<ThemeContextValue | null>(null);

function systemTheme(): "light" | "dark" {
  return typeof window !== "undefined" && window.matchMedia("(prefers-color-scheme: dark)").matches
    ? "dark"
    : "light";
}

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setThemeState] = React.useState<Theme>("system");
  const [resolved, setResolved] = React.useState<"light" | "dark">("light");

  React.useEffect(() => {
    const stored = window.localStorage.getItem("tc-theme") as Theme | null;
    const initial = stored === "light" || stored === "dark" || stored === "system" ? stored : "system";
    setThemeState(initial);
    const apply = (value: Theme) => {
      const next = value === "system" ? systemTheme() : value;
      setResolved(next);
      document.documentElement.dataset.theme = next;
    };
    apply(initial);
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const listener = () => {
      if (initial === "system") apply("system");
    };
    media.addEventListener?.("change", listener);
    return () => media.removeEventListener?.("change", listener);
  }, []);

  const setTheme = React.useCallback((next: Theme) => {
    setThemeState(next);
    try {
      window.localStorage.setItem("tc-theme", next);
    } catch {
      // Ignore storage failures; the in-memory preference remains valid.
    }
    const resolvedTheme = next === "system" ? systemTheme() : next;
    setResolved(resolvedTheme);
    document.documentElement.dataset.theme = resolvedTheme;
  }, []);

  return <ThemeContext.Provider value={{ theme, setTheme, resolved }}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeContextValue {
  const value = React.useContext(ThemeContext);
  if (!value) throw new Error("useTheme must be used within ThemeProvider");
  return value;
}
