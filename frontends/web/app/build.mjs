// Builds ../dist: the bundle, the desktop's own icons, and the list of strings to translate.
import { build } from "esbuild";
import { createHash } from "node:crypto";
import { copyFileSync, mkdirSync, readFileSync, readdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";

const here = import.meta.dirname, dist = join(here, "..", "dist"), root = join(here, "..", "..", "..");
const icons = join(root, "frontends", "desktop", "theme", "icons");
mkdirSync(dist, { recursive: true });

// The desktop's icons, recoloured by the text colour of whoever draws them.
const svg = {};
for (const file of readdirSync(icons).filter((f) => /^(nav_|collapse_gray|expand_gray|edit_gray|warning_orange|chevron_|check_|close_gray|copy_gray|refresh_gray|stop_red)/.test(f) && f.endsWith(".svg"))) {
  const text = readFileSync(join(icons, file), "utf8");
  const inner = text.replace(/^[\s\S]*?<svg[^>]*>/, "").replace(/<\/svg>\s*$/, "");
  svg[file.slice(0, -4)] = inner.replace(/(stroke|fill)="#[0-9a-fA-F]{3,8}"/g, '$1="currentColor"');
}
writeFileSync(join(here, "src", "icons.gen.js"), `export default ${JSON.stringify(svg)};\n`);

// Every t("...") literal is a catalogue key: the server translates exactly these.
const strings = new Set();
const walk = (dir) => readdirSync(dir, { withFileTypes: true }).forEach((e) => {
  const path = join(dir, e.name);
  if (e.isDirectory()) return walk(path);
  if (!/\.jsx?$/.test(e.name) || e.name.endsWith(".gen.js")) return;
  for (const m of readFileSync(path, "utf8").matchAll(/\b(?:t|keep)\(\s*"((?:[^"\\]|\\.)*)"/g)) strings.add(JSON.parse(`"${m[1]}"`));
});
walk(join(here, "src"));
writeFileSync(join(dist, "strings.json"), JSON.stringify([...strings].sort(), null, 1) + "\n");

await build({
  entryPoints: [join(here, "src", "main.jsx")], bundle: true, minify: true, target: "es2020", jsx: "automatic",
  outdir: dist, entryNames: "app", define: { "process.env.NODE_ENV": '"production"' }, legalComments: "none",
});
for (const [from, to] of [[join(icons, "bc250_board_light.png"), "board-light.png"], [join(icons, "bc250_board_dark.png"), "board-dark.png"],
  [join(root, "assets", "icons", "bc250-control-center-64.png"), "logo.png"]]) copyFileSync(from, join(dist, to));
// Installation metadata never includes a pairing key, device code or session.
const appIcons = [192, 256, 512].map((size) => {
  const name = `app-icon-${size}.png`;
  copyFileSync(join(root, "assets", "icons", `bc250-control-center-${size}.png`), join(dist, name));
  return { src: name, sizes: `${size}x${size}`, type: "image/png", purpose: "any" };
});
copyFileSync(join(here, "sw.js"), join(dist, "sw.js"));
writeFileSync(join(dist, "manifest.webmanifest"), JSON.stringify({
  id: "/", name: "BC250 Control Center", short_name: "BC250", scope: "/", start_url: "/#/dashboard",
  display: "standalone", background_color: "#111111", theme_color: "#171717",
  description: "BC250 hardware control and monitoring on your home network.",
  prefer_related_applications: false, icons: appIcons, categories: ["utilities"],
}, null, 2) + "\n");
// Content identity: an open tab can detect a new build without interrupting a job.
const version = createHash("sha256").update(readFileSync(join(dist, "app.js"))).update(readFileSync(join(dist, "app.css"))).update(readFileSync(join(dist, "sw.js"))).update(readFileSync(import.meta.filename)).digest("hex").slice(0, 16);
writeFileSync(join(dist, "version.json"), JSON.stringify({ version }) + "\n");
writeFileSync(join(dist, "index.html"), `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover,interactive-widget=resizes-content">
<meta name="bc250-build" content="${version}"><meta name="color-scheme" content="light dark"><title>BC250 Control Center</title>
<meta name="theme-color" content="#171717"><meta name="mobile-web-app-capable" content="yes"><meta name="apple-mobile-web-app-capable" content="yes"><meta name="apple-mobile-web-app-title" content="BC250"><meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<link rel="manifest" href="/manifest.webmanifest"><link rel="apple-touch-icon" href="/app-icon-256.png"><link rel="icon" href="logo.png"><link rel="stylesheet" href="/theme.css"><link rel="stylesheet" href="app.css?v=${version}"></head>
<body><div id="root"></div><script src="app.js?v=${version}"></script></body></html>
`);
console.log("dist ready");
