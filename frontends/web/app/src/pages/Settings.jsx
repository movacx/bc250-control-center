import { useState } from "react";
import { t } from "../lib.jsx";
import { Btn, Card } from "../ui.jsx";

export default function Settings({ onLogout }) {
  const [theme, setTheme] = useState(localStorage.getItem("theme") || "auto");
  const pick = (value) => {
    setTheme(value);
    if (value === "auto") { localStorage.removeItem("theme"); delete document.documentElement.dataset.theme; }
    else { localStorage.setItem("theme", value); document.documentElement.dataset.theme = value; }
  };
  return (
    <div className="cols two">
      <Card title={t("Theme")}><div className="row">{[["auto", t("Automatic")], ["light", t("Light")], ["dark", t("Dark")]].map(([key, label]) => (
        <Btn key={key} wide kind={theme === key ? "soft" : ""} aria-pressed={theme === key} onClick={() => pick(key)}>{label}</Btn>))}</div></Card>
      <Card title={t("Remote access")} sub={t("The access key is shown in Remote access on the desktop application.")}><Btn onClick={onLogout}>{t("Sign out")}</Btn></Card>
    </div>
  );
}
