import de from "../locales/de.json";
import en from "../locales/en.json";
import es from "../locales/es.json";
import pl from "../locales/pl.json";
import pt from "../locales/pt.json";
import ru from "../locales/ru.json";
import uk from "../locales/uk.json";

export type QuickAccessLocale = "en" | "es" | "pt" | "ru" | "pl" | "de" | "uk";
export type QuickAccessTextKey = keyof typeof en;

const catalogs: Record<QuickAccessLocale, Record<QuickAccessTextKey, string>> = {
  en, es, pt, ru, pl, de, uk,
};

export function normalizeQuickAccessLanguage(value: unknown): QuickAccessLocale {
  const raw = String(value ?? "").trim().toLowerCase().replaceAll("_", "-").split(".", 1)[0];
  const aliases: Record<string, QuickAccessLocale> = {
    english: "en", spanish: "es", latam: "es", "spanish-latam": "es",
    portuguese: "pt", brazilian: "pt", "brazilian-portuguese": "pt",
    russian: "ru", polish: "pl", german: "de", ukrainian: "uk",
  };
  const exact = aliases[raw] ?? raw;
  const supported = new Set<QuickAccessLocale>(["en", "es", "pt", "ru", "pl", "de", "uk"]);
  if (supported.has(exact as QuickAccessLocale)) return exact as QuickAccessLocale;
  const base = String(exact).split("-", 1)[0];
  return base === "es" || base === "pt" || base === "ru" || base === "pl" || base === "de" || base === "uk" ? base : "en";
}

type SteamLanguageGlobals = typeof globalThis & {
  LocalizationManager?: { m_rgLocalesToUse?: unknown[] };
  SteamClient?: { Settings?: { GetCurrentLanguage?: () => unknown } };
};

function detectedLanguage(): unknown {
  const steam = globalThis as SteamLanguageGlobals;
  const localeList = steam.LocalizationManager?.m_rgLocalesToUse;
  if (Array.isArray(localeList) && localeList.length) return localeList[0];
  const steamLanguage = steam.SteamClient?.Settings?.GetCurrentLanguage?.();
  if (typeof steamLanguage === "string") return steamLanguage;
  return globalThis.navigator?.language ?? "en";
}

export const quickAccessLanguage = normalizeQuickAccessLanguage(detectedLanguage());
export const text = catalogs[quickAccessLanguage];
export const qa = (key: QuickAccessTextKey): string => text[key] ?? catalogs.en[key];
