import { createContext, useContext, useEffect, useState } from "react";
import { t } from "./lib.jsx";
import { Btn } from "./ui.jsx";

const Installation = createContext(null);
const standalone = () => matchMedia("(display-mode: standalone)").matches || navigator.standalone === true;

export function PwaProvider({ children }) {
  const [installed, setInstalled] = useState(standalone);
  const [offer, setOffer] = useState(null);
  useEffect(() => {
    const display = matchMedia("(display-mode: standalone)");
    const changed = () => setInstalled(standalone());
    const ready = (event) => { event.preventDefault(); setOffer(event); };
    const done = () => { setInstalled(true); setOffer(null); };
    addEventListener("beforeinstallprompt", ready);
    addEventListener("appinstalled", done);
    display.addEventListener("change", changed);
    // Never cache hardware state or API responses. The worker only provides
    // installation compatibility and an honest navigation failure screen.
    if (window.isSecureContext && "serviceWorker" in navigator) {
      navigator.serviceWorker.register("/sw.js", { scope: "/", updateViaCache: "none" }).catch(() => {});
    }
    return () => { removeEventListener("beforeinstallprompt", ready); removeEventListener("appinstalled", done); display.removeEventListener("change", changed); };
  }, []);
  const install = async () => {
    if (!offer) return false;
    try { await offer.prompt(); await offer.userChoice; } finally { setOffer(null); }
    return true;
  };
  return <Installation.Provider value={{ installed, available: !!offer, install }}>{children}</Installation.Provider>;
}

export function InstallApp() {
  const { installed, available, install } = useContext(Installation);
  const [help, setHelp] = useState(false);
  if (installed) return null;
  const apple = /iPad|iPhone|iPod/.test(navigator.userAgent) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
  return <div className="install-app">
    <div className="install-app-action"><span>{t("Keep BC250 on your home screen")}</span><Btn small onClick={async () => {
      if (!available) { setHelp(!help); return; }
      try { await install(); } catch { setHelp(true); }
    }} aria-expanded={available ? undefined : help}>{t("Install app")}</Btn></div>
    <p className="note">{t("Open the installed app to use BC250 without the browser address bar.")}</p>
    {help && <p className="note" role="status">{!window.isSecureContext ? t("HTTPS required") : apple ? t("In Safari, open Share, then Add to Home Screen and Open as Web App.") : t("Open your browser menu and choose Install app or Add to Home screen. If it is unavailable, trust this board's HTTPS certificate first.")}</p>}
  </div>;
}
