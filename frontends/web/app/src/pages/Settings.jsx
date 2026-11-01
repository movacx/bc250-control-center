import { useState } from "react";
import { languages, loadStrings, t, useApp } from "../lib.jsx";
import { ACCENTS, THEMES, savedAccent, savedTheme, saveAppearance } from "../appearance.js";
import { InstallApp } from "../Pwa.jsx";
import { Btn, Card } from "../ui.jsx";

export default function Settings({ onLogout }) {
  const { session } = useApp();
  const [theme, setTheme] = useState(savedTheme);
  const [accent, setAccent] = useState(savedAccent);
  const [language, setLanguage] = useState(document.documentElement.lang);
  const pick = (value) => {
    setTheme(value);
    saveAppearance(value, accent);
  };
  return (
    <div className="cols two">
      <Card title={t("Language")}><select className="input" aria-label={t("Language")} value={language} onChange={async (e) => {
        const next = e.target.value; localStorage.setItem("language", next); await loadStrings(next); setLanguage(next); dispatchEvent(new Event("languagechanged"));
      }}>{languages.map((item) => <option key={item.key} value={item.key}>{item.title}</option>)}</select></Card>
      <Card title={t("Theme")} className="appearance-settings"><div className="theme-choices">{THEMES.map(([key, label]) => (
        <button type="button" key={key} className={theme === key ? "on" : ""} aria-pressed={theme === key} onClick={() => pick(key)}><span className={`theme-preview ${key}`} aria-hidden="true"><i /><b /></span><span>{t(label)}</span></button>))}</div>
        <section className="accent-settings"><h3>{t("Accent color")}</h3><div className="accent-choices">{ACCENTS.map(([key, label]) => <button type="button" key={key} className={accent === key ? "on" : ""} aria-pressed={accent === key} onClick={() => { setAccent(key); saveAppearance(theme, key); }}><i aria-hidden="true" style={{ background: `var(--c-accent-${key})` }} /><span>{t(label)}</span></button>)}</div></section>
      </Card>
      <Card title={t("Remote access")} sub={t("The access key is shown in Remote access on the desktop application.")}>{session.named_url && <a className="btn local-address" href={session.named_url + "/#/settings"}>{new URL(session.named_url).host}</a>}<InstallApp /><Btn onClick={onLogout}>{t("Sign out")}</Btn></Card>
    </div>
  );
}
