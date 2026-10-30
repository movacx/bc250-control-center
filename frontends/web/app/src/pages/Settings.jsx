import { useState } from "react";
import { languages, loadStrings, t } from "../lib.jsx";
import { InstallApp } from "../Pwa.jsx";
import { Btn, Card } from "../ui.jsx";

export default function Settings({ onLogout }) {
  const [theme, setTheme] = useState(localStorage.getItem("theme") || "auto");
  const [language, setLanguage] = useState(document.documentElement.lang);
  const pick = (value) => {
    setTheme(value);
    if (value === "auto") { localStorage.removeItem("theme"); delete document.documentElement.dataset.theme; }
    else { localStorage.setItem("theme", value); document.documentElement.dataset.theme = value; }
  };
  return (
    <div className="cols two">
      <Card title={t("Language")}><select className="input" aria-label={t("Language")} value={language} onChange={async (e) => {
        const next = e.target.value; localStorage.setItem("language", next); await loadStrings(next); setLanguage(next); dispatchEvent(new Event("languagechanged"));
      }}>{languages.map((item) => <option key={item.key} value={item.key}>{item.title}</option>)}</select></Card>
      <Card title={t("Theme")}><div className="row">{[["auto", t("Automatic")], ["light", t("Light")], ["dark", t("Dark")]].map(([key, label]) => (
        <Btn key={key} wide kind={theme === key ? "soft" : ""} aria-pressed={theme === key} onClick={() => pick(key)}>{label}</Btn>))}</div></Card>
      <Card title={t("Remote access")} sub={t("The access key is shown in Remote access on the desktop application.")}><InstallApp /><Btn onClick={onLogout}>{t("Sign out")}</Btn></Card>
    </div>
  );
}
