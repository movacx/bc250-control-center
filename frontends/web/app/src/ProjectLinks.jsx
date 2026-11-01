import { t } from "./lib.jsx";

export default function ProjectLinks() {
  return <div className="project-links" aria-label={t("Project links")}>
    <a href="https://ko-fi.com/movacx" target="_blank" rel="noopener noreferrer" title={t("Support on Ko-fi")} aria-label={t("Support on Ko-fi")}><img src="/project-kofi.png" alt=""/><span>Ko-fi</span></a>
    <a href="https://t.me/+LJAp9e4cpPs3Mzky" target="_blank" rel="noopener noreferrer" title={t("BC250 community on Telegram")} aria-label={t("BC250 community on Telegram")}><img src="/project-telegram.svg" alt=""/><span>Telegram</span></a>
    <a href="https://github.com/movacx/bc250-control-center" target="_blank" rel="noopener noreferrer" title={t("Project on GitHub")} aria-label={t("Project on GitHub")}><img src="/project-github.svg" alt=""/><span>GitHub</span></a>
  </div>;
}
