import { keep } from "./lib.jsx";

// Keys mirror the desktop's theme/ACCENTS catalogue; all colours come from
// /theme.css, generated with theme_palette(..., "formal").
export const THEMES = [["auto", keep("Automatic")], ["light", keep("Light")], ["dark", keep("Dark")], ["midnight", keep("Night blue")]];
export const ACCENTS = [["blue", keep("Blue")], ["indigo", keep("Indigo")], ["violet", keep("Violet")], ["pink", keep("Pink")], ["orange", keep("Orange")], ["amber", keep("Amber")], ["green", keep("Green")], ["teal", keep("Teal")], ["cyan", keep("Cyan")], ["graphite", keep("Graphite")]];

const stored = (key) => { try { return localStorage.getItem(key); } catch { return null; } };
export const savedTheme = () => THEMES.some(([key]) => key === stored("theme")) ? stored("theme") : "auto";
export const savedAccent = () => ACCENTS.some(([key]) => key === stored("accent")) ? stored("accent") : "violet";

export function applyAppearance(theme = savedTheme(), accent = savedAccent()) {
  const root = document.documentElement;
  if (theme === "auto") delete root.dataset.theme;
  else root.dataset.theme = theme;
  root.dataset.accent = accent;
  const colour = getComputedStyle(root).getPropertyValue("--c-window").trim();
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta && colour) meta.content = colour;
}

export function saveAppearance(theme, accent) {
  try {
    if (theme === "auto") localStorage.removeItem("theme");
    else localStorage.setItem("theme", theme);
    localStorage.setItem("accent", accent);
  } catch { /* The current window can still use the selection with storage disabled. */ }
  applyAppearance(theme, accent);
}
