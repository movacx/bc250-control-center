// BC250 Control Center problem reports.
//
// POST /v1/reports   the app sends one report, gzip-compressed JSON, with its
//                    attachments. Stored compressed in KV; a short summary is
//                    kept in the key's metadata so the list needs no reads.
// GET  /admin        the maintainer's page (asks for the admin token).
// GET  /v1/admin/reports[?cursor=]      list (Bearer ADMIN_TOKEN)
// GET  /v1/admin/reports/<id>           one report, as JSON
// DELETE /v1/admin/reports/<id>         remove it
// GET  /v1/admin/telegram-chats         chats that wrote to the bot (to find TELEGRAM_CHAT_ID)
// POST /v1/admin/notify-test            send a test message to Telegram and Discord
//
// Nothing here runs code from a report or shows it as HTML: the page renders
// every field as text.

const MAX_COMPRESSED = 1 << 20; // 1 MiB on the wire
const MAX_EXPANDED = 6 << 20; // 6 MiB once decompressed
const KEEP_SECONDS = 180 * 24 * 3600; // reports expire after ~6 months
const ID = /^R-[0-9a-f]{8}$/;
const KINDS = new Set(["problem", "idea"]);

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    try {
      if (url.pathname === "/v1/reports" && request.method === "POST") {
        return await receive(request, env, ctx);
      }
      if (url.pathname === "/admin" && request.method === "GET") {
        return new Response(ADMIN_PAGE, {
          headers: { "content-type": "text/html; charset=utf-8", "cache-control": "no-store" },
        });
      }
      if (url.pathname.startsWith("/v1/admin/")) {
        if (!authorized(request, env)) return json({ ok: false, error: "unauthorized" }, 401);
        return await admin(request, env, url);
      }
      if (url.pathname === "/" || url.pathname === "/health") {
        return json({ ok: true, service: "bc250-reports" });
      }
      return json({ ok: false, error: "not found" }, 404);
    } catch (error) {
      return json({ ok: false, error: "server error" }, 500);
    }
  },
};

async function receive(request, env, ctx) {
  const address = request.headers.get("cf-connecting-ip") || "unknown";
  if (env.LIMITER) {
    const { success } = await env.LIMITER.limit({ key: address });
    if (!success) return json({ ok: false, error: "too many reports, wait a minute" }, 429);
  }
  const length = Number(request.headers.get("content-length") || 0);
  if (length > MAX_COMPRESSED) return json({ ok: false, error: "report too large" }, 413);
  const compressed = new Uint8Array(await request.arrayBuffer());
  if (compressed.byteLength > MAX_COMPRESSED) return json({ ok: false, error: "report too large" }, 413);

  let report;
  try {
    report = JSON.parse(await gunzipText(compressed));
  } catch (error) {
    return json({ ok: false, error: String(error.message || "unreadable report") }, 400);
  }
  const problem = validate(report);
  if (problem) return json({ ok: false, error: problem }, 400);

  const key = `report:${report.id}`;
  if (await env.REPORTS.get(key, { type: "stream" })) {
    return json({ ok: true, id: report.id, duplicate: true });
  }
  const received = new Date().toISOString();
  const metadata = {
    id: report.id,
    received,
    kind: report.kind,
    code: clip(report.code, 40),
    summary: clip(report.summary, 160),
    distribution: clip(report.distribution, 40),
    version: clip(report.version, 20),
    attachments: (report.attachments || []).length,
    bytes: compressed.byteLength,
  };
  await env.REPORTS.put(key, compressed, { metadata, expirationTtl: KEEP_SECONDS });
  ctx.waitUntil(notify(env, metadata, new URL(request.url).origin));
  return json({ ok: true, id: report.id });
}

function validate(report) {
  if (!report || typeof report !== "object") return "report must be an object";
  if (!ID.test(String(report.id || ""))) return "invalid report id";
  if (!KINDS.has(report.kind)) return "invalid kind";
  if (report.fields && typeof report.fields !== "object") return "fields must be an object";
  if (report.attachments !== undefined) {
    if (!Array.isArray(report.attachments) || report.attachments.length > 20) return "invalid attachments";
    for (const item of report.attachments) {
      if (!item || typeof item.name !== "string" || typeof item.text !== "string") return "invalid attachment";
    }
  }
  return "";
}

async function gunzipText(bytes) {
  const stream = new Blob([bytes]).stream().pipeThrough(new DecompressionStream("gzip"));
  const reader = stream.getReader();
  const chunks = [];
  let total = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    total += value.byteLength;
    if (total > MAX_EXPANDED) throw new Error("report too large once expanded");
    chunks.push(value);
  }
  return new TextDecoder().decode(concat(chunks, total));
}

function concat(chunks, total) {
  const out = new Uint8Array(total);
  let offset = 0;
  for (const chunk of chunks) {
    out.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return out;
}

function authorized(request, env) {
  const header = request.headers.get("authorization") || "";
  const token = header.startsWith("Bearer ") ? header.slice(7) : "";
  return Boolean(env.ADMIN_TOKEN) && token.length > 0 && timingSafeEqual(token, env.ADMIN_TOKEN);
}

function timingSafeEqual(a, b) {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

async function admin(request, env, url) {
  const parts = url.pathname.split("/").filter(Boolean); // v1 admin reports [id]
  if (parts[2] === "telegram-chats") return await telegramChats(env);
  if (parts[2] === "notify-test" && request.method === "POST") {
    const sent = await notify(env, { id: "R-00000000", kind: "test", summary: "Test notification from the report service" }, url.origin);
    return json({ ok: true, sent });
  }
  if (parts[2] !== "reports") return json({ ok: false, error: "not found" }, 404);
  const id = parts[3];
  if (!id) {
    const listed = await env.REPORTS.list({ prefix: "report:", cursor: url.searchParams.get("cursor") || undefined, limit: 200 });
    const reports = listed.keys.map((key) => key.metadata || { id: key.name.slice(7) });
    reports.sort((a, b) => String(b.received || "").localeCompare(String(a.received || "")));
    return json({ ok: true, reports, cursor: listed.list_complete ? null : listed.cursor });
  }
  if (!ID.test(id)) return json({ ok: false, error: "invalid report id" }, 400);
  const key = `report:${id}`;
  if (request.method === "DELETE") {
    await env.REPORTS.delete(key);
    return json({ ok: true, deleted: id });
  }
  const stored = await env.REPORTS.getWithMetadata(key, { type: "arrayBuffer" });
  if (!stored.value) return json({ ok: false, error: "not found" }, 404);
  const report = JSON.parse(await gunzipText(new Uint8Array(stored.value)));
  return json({ ok: true, metadata: stored.metadata, report });
}

// Every channel is optional; a missed notification never loses the report.
async function notify(env, meta, origin) {
  const link = `${origin}/admin#${meta.id}`;
  const line = `${meta.kind} · ${meta.code || "no code"} · ${meta.distribution || "?"} · ${meta.version || "?"}`;
  const sent = {};
  if (env.TELEGRAM_BOT_TOKEN && env.TELEGRAM_CHAT_ID) {
    const text = [`New BC250 report ${meta.id}`, line, meta.summary || "", link].join("\n");
    sent.telegram = await post(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/sendMessage`, {
      chat_id: env.TELEGRAM_CHAT_ID,
      text,
      disable_web_page_preview: true,
    });
  }
  if (env.DISCORD_WEBHOOK_URL) {
    sent.discord = await post(env.DISCORD_WEBHOOK_URL, {
      username: "BC250 Control Center Reports",
      allowed_mentions: { parse: [] },
      embeds: [{
        title: `New report ${meta.id}`,
        url: link,
        description: clip(meta.summary || "(no summary)", 300),
        footer: { text: line },
        color: meta.kind === "idea" ? 0x2f9e5b : 0xd9822b,
      }],
    });
  }
  return sent;
}

async function post(target, body) {
  try {
    const response = await fetch(target, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
    });
    return response.status;
  } catch (error) {
    return 0;
  }
}

async function telegramChats(env) {
  if (!env.TELEGRAM_BOT_TOKEN) return json({ ok: false, error: "TELEGRAM_BOT_TOKEN is not set" }, 400);
  const response = await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/getUpdates`);
  const data = await response.json();
  const chats = new Map();
  for (const update of data.result || []) {
    const chat = (update.message || update.channel_post || update.my_chat_member || {}).chat;
    if (chat) chats.set(chat.id, { id: chat.id, type: chat.type, name: chat.title || chat.username || chat.first_name || "" });
  }
  return json({ ok: Boolean(data.ok), chats: [...chats.values()] });
}

function clip(value, limit) {
  const text = String(value || "");
  return text.length > limit ? text.slice(0, limit - 1) + "…" : text;
}

function json(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" },
  });
}

const ADMIN_PAGE = `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>BC250 reports</title>
<style>
:root{color-scheme:light dark;--bg:#f6f7f9;--card:#fff;--text:#16181d;--muted:#5b6170;--line:#d9dde4;--accent:#2f5bd3}
@media (prefers-color-scheme:dark){:root{--bg:#111318;--card:#1a1d24;--text:#e7e9ee;--muted:#9aa1ae;--line:#2b303b;--accent:#7d9cff}}
body{margin:0;font:14px/1.45 system-ui,sans-serif;background:var(--bg);color:var(--text)}
header{display:flex;gap:8px;align-items:center;padding:12px 16px;border-bottom:1px solid var(--line);flex-wrap:wrap}
h1{font-size:16px;margin:0 12px 0 0}input,button{font:inherit;padding:6px 10px;border:1px solid var(--line);border-radius:6px;background:var(--card);color:var(--text)}
button{cursor:pointer}main{display:grid;grid-template-columns:minmax(260px,420px) 1fr;min-height:calc(100vh - 58px)}
#list{border-right:1px solid var(--line);overflow:auto;max-height:calc(100vh - 58px)}
.row{padding:10px 16px;border-bottom:1px solid var(--line);cursor:pointer}.row:hover,.row.on{background:var(--card)}
.meta{color:var(--muted);font-size:12px}#view{padding:16px;overflow:auto;max-height:calc(100vh - 90px)}
pre{white-space:pre-wrap;word-break:break-word;background:var(--card);border:1px solid var(--line);border-radius:6px;padding:10px;font:12px/1.4 ui-monospace,monospace}
details{margin:8px 0}summary{cursor:pointer;font-weight:600}
@media (max-width:760px){main{grid-template-columns:1fr}#list{max-height:40vh;border-right:0}}
</style></head><body>
<header><h1>BC250 reports</h1><input id="filter" placeholder="Filter: code, distro, text"><span id="count" class="meta"></span>
<span style="flex:1"></span><input id="token" type="password" placeholder="Admin token"><button id="save">Open</button></header>
<main><div id="list"></div><div id="view"><p class="meta">Choose a report.</p></div></main>
<script>
const $=s=>document.querySelector(s);let reports=[],current=null;
const tokenKey="bc250-admin-token";
function token(){try{return localStorage.getItem(tokenKey)||""}catch{return ""}}
async function api(path,options={}){const r=await fetch(path,{...options,headers:{authorization:"Bearer "+token()}});if(r.status===401)throw new Error("Wrong admin token");return r.json()}
function el(tag,text,cls){const e=document.createElement(tag);if(text!==undefined)e.textContent=text;if(cls)e.className=cls;return e}
async function load(){reports=[];let cursor=null;do{const d=await api("/v1/admin/reports"+(cursor?"?cursor="+encodeURIComponent(cursor):""));reports.push(...d.reports);cursor=d.cursor}while(cursor);draw()}
function draw(){const q=$("#filter").value.toLowerCase();const list=$("#list");list.replaceChildren();
const shown=reports.filter(r=>JSON.stringify(r).toLowerCase().includes(q));$("#count").textContent=shown.length+" of "+reports.length;
for(const r of shown){const row=el("div",undefined,"row"+(r.id===current?" on":""));row.append(el("div",(r.code||r.kind||"")+" · "+(r.summary||"(no summary)")));
row.append(el("div",[r.id,r.distribution,r.version,(r.received||"").replace("T"," ").slice(0,16),r.attachments+" attachments"].filter(Boolean).join(" · "),"meta"));
row.onclick=()=>open(r.id);list.append(row)}}
async function open(id){current=id;draw();const v=$("#view");v.replaceChildren(el("p","Loading…","meta"));
const d=await api("/v1/admin/reports/"+id);const rep=d.report;v.replaceChildren();
const top=el("div");top.append(el("h2",(rep.code||rep.kind)+" · "+(rep.summary||"")));const del=el("button","Delete");
del.onclick=async()=>{if(!confirm("Delete "+id+"?"))return;await api("/v1/admin/reports/"+id,{method:"DELETE"});reports=reports.filter(r=>r.id!==id);current=null;v.replaceChildren();draw()};
top.append(del);v.append(top);
const fields=rep.fields||{};for(const [name,value] of Object.entries(fields)){if(!value||(Array.isArray(value)&&!value.length))continue;
const box=el("details");box.open=String(value).length<4000;box.append(el("summary",name));box.append(el("pre",Array.isArray(value)?value.join(", "):String(value)));v.append(box)}
for(const a of rep.attachments||[]){const box=el("details");box.append(el("summary",a.name+" ("+Math.round(a.text.length/1024)+" KB)"));box.append(el("pre",a.text));v.append(box)}}
$("#save").onclick=()=>{try{localStorage.setItem(tokenKey,$("#token").value)}catch{};load().catch(e=>alert(e.message))};
$("#filter").oninput=draw;const wanted=location.hash.slice(1);
if(token())load().then(()=>{if(/^R-[0-9a-f]{8}$/.test(wanted))open(wanted)}).catch(e=>{$("#view").replaceChildren(el("p",e.message,"meta"))});
</script></body></html>`;
