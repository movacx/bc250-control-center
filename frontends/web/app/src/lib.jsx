import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";

// -- talking to the server --------------------------------------------------------------------------
let csrf = "";
let onLost = () => {};
export const setCsrf = (value) => { csrf = value || ""; };
export const onSessionLost = (fn) => { onLost = fn; };

export async function api(path, body) {
  const options = body === undefined ? { credentials: "same-origin" }
    : { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf }, body: JSON.stringify(body) };
  try {
    const response = await fetch(`/api/${path}`, options);
    const data = await response.json();
    if (response.status === 401 && path !== "login") onLost();
    return { ...data, status: response.status };
  } catch {
    return { ok: false, status: 0, error: t("Not detected") };
  }
}

// -- translation: the desktop's catalogues, only the strings this page uses -------------------------
let strings = {};
export const loadStrings = async (lang) => {
  const response = await fetch(`/api/i18n${lang ? `?lang=${lang}` : ""}`);
  const data = await response.json();
  strings = data.strings || {};
  document.documentElement.lang = data.language || "en";
};
export function t(source, values) {
  const text = strings[source] || source;
  return values ? text.replace(/\{(\w+)\}/g, (m, key) => (key in values ? values[key] : m)) : text;
}

// -- shared state -------------------------------------------------------------------------------------
export const App = createContext(null);
export const useApp = () => useContext(App);

/** Polls ``path`` every ``ms`` while the tab is visible; ``again`` changes to ask right away. */
export function usePoll(path, ms, again) {
  const [data, setData] = useState(null);
  const alive = useRef(true);
  const load = useCallback(async () => {
    if (document.hidden) return;
    const result = await api(path);
    if (alive.current) setData(result);
  }, [path]);
  useEffect(() => {
    alive.current = true;
    load();
    const timer = setInterval(load, ms);
    return () => { alive.current = false; clearInterval(timer); };
  }, [load, ms, again]);
  return data;
}

export const num = (value, digits = 0) => (typeof value === "number" && isFinite(value) ? value.toFixed(digits) : "--");
export const pick = (...values) => values.find((value) => value !== undefined && value !== null);

export function usePage(name) {
  const { again } = useApp();
  const result = usePoll(`page?name=${name}`, 3000, again);
  return result?.ok ? result.data : null;
}

/** Bytes as the desktop shows memory: MB below 1 GB, else GB. */
export function memory(bytes) {
  if (typeof bytes !== "number" || !isFinite(bytes)) return { value: "--", unit: "" };
  return bytes >= 2 ** 30 ? { value: (bytes / 2 ** 30).toFixed(1), unit: "GB" } : { value: Math.round(bytes / 2 ** 20), unit: "MB" };
}
export const heat = (celsius) => (celsius >= 95 ? "danger" : celsius >= 85 ? "warning" : undefined);

/** Marks a catalogue key that is looked up later by name, so the build still collects it. */
export const keep = (source) => source;
