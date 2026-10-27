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
const MAX_ATTACHMENTS = 60;

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
  const system = report.system || {};
  const owner = report.owner || {};
  const error = report.error || {};
  const metadata = {
    id: report.id,
    received,
    schema: Number(report.schema || 1),
    kind: report.kind,
    code: clip(error.code || report.code, 40),
    summary: clip(report.summary, 160),
    distribution: clip(system["Operating system"] || owner.distribution || report.distribution, 60),
    version: clip((report.app || {}).version || report.version, 20),
    source: clip((report.app || {}).opened_from, 60),
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
  for (const part of ["app", "problem", "error", "workflow", "system", "os_release", "firmware", "owner", "fields"]) {
    if (report[part] !== undefined && (typeof report[part] !== "object" || Array.isArray(report[part]))) return `${part} must be an object`;
  }
  if (report.history !== undefined && (!Array.isArray(report.history) || report.history.length > 50)) return "invalid history";
  if (report.attachments !== undefined) {
    if (!Array.isArray(report.attachments) || report.attachments.length > MAX_ATTACHMENTS) return "invalid attachments";
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
  // ADMIN_PASSWORD is an optional second key the maintainer can type on a phone.
  return [env.ADMIN_TOKEN, env.ADMIN_PASSWORD].some(
    (key) => typeof key === "string" && key.length >= 12 && token.length > 0 && timingSafeEqual(token, key),
  );
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
    const text = [`New BC250 report ${meta.id}`, line, meta.source ? `From: ${meta.source}` : "", meta.summary || "", link].filter(Boolean).join("\n");
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
:root{color-scheme:light dark;--bg:#f4f5f7;--card:#fff;--soft:#eef0f4;--text:#15171c;--muted:#5d6472;--line:#dde1e8;--accent:#2f5bd3;--red:#c0392b;--amber:#b7791f;--green:#2f855a}
@media (prefers-color-scheme:dark){:root{--bg:#0f1115;--card:#171a20;--soft:#1e222a;--text:#e6e8ec;--muted:#98a0ad;--line:#2a2f39;--accent:#7d9cff;--red:#ff7b6b;--amber:#f2b552;--green:#68d391}}
*{box-sizing:border-box}body{margin:0;font:14px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif;background:var(--bg);color:var(--text)}
header{position:sticky;top:0;z-index:2;display:flex;gap:8px;align-items:center;padding:10px 16px;background:var(--card);border-bottom:1px solid var(--line);flex-wrap:wrap}
h1{font-size:15px;margin:0 10px 0 0;letter-spacing:.2px}input,button{font:inherit;padding:6px 10px;border:1px solid var(--line);border-radius:7px;background:var(--card);color:var(--text)}
button{cursor:pointer}button:hover{border-color:var(--accent)}button.danger{color:var(--red)}
main{display:grid;grid-template-columns:minmax(260px,400px) 1fr;height:calc(100vh - 53px)}
#list{border-right:1px solid var(--line);overflow:auto}
.row{padding:10px 14px;border-bottom:1px solid var(--line);cursor:pointer}.row:hover{background:var(--soft)}.row.on{background:var(--soft);box-shadow:inset 3px 0 var(--accent)}
.row .t{font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.meta{color:var(--muted);font-size:12px}#view{overflow:auto;padding:18px 22px}
.chip{display:inline-block;padding:1px 8px;margin:2px 4px 2px 0;border-radius:999px;background:var(--soft);border:1px solid var(--line);font-size:12px}
.chip.code{font-family:ui-monospace,monospace;color:var(--red)}.chip.idea{color:var(--green)}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px;margin:0 0 14px}
.card h3{margin:0 0 10px;font-size:13px;text-transform:uppercase;letter-spacing:.6px;color:var(--muted)}
h2{margin:0 0 6px;font-size:19px}
dl{display:grid;grid-template-columns:minmax(120px,190px) 1fr;gap:6px 14px;margin:0}dt{color:var(--muted)}dd{margin:0;white-space:pre-wrap;word-break:break-word}
pre{white-space:pre-wrap;word-break:break-word;background:var(--soft);border:1px solid var(--line);border-radius:8px;padding:10px;margin:6px 0 0;font:12px/1.45 ui-monospace,monospace;max-height:520px;overflow:auto}
details{border-top:1px solid var(--line);padding:6px 0}details:first-of-type{border-top:0}summary{cursor:pointer;font-weight:600}summary .meta{font-weight:400}
table{width:100%;border-collapse:collapse;font-size:13px}td,th{text-align:left;padding:5px 8px;border-bottom:1px solid var(--line);vertical-align:top}th{color:var(--muted);font-weight:500}
.fix{border-left:3px solid var(--green);padding-left:10px}
.actions{display:flex;gap:6px;flex-wrap:wrap;margin-top:10px}
@media (max-width:820px){main{grid-template-columns:1fr;height:auto}#list{max-height:38vh;border-right:0;border-bottom:1px solid var(--line)}#view{padding:14px}dl{grid-template-columns:1fr}dt{font-size:12px}}
</style></head><body>
<header><h1>BC250 reports</h1><input id="filter" placeholder="Filter: code, distro, text" style="flex:1;min-width:160px"><span id="count" class="meta"></span>
<input id="token" type="password" placeholder="Admin token or password" style="width:200px"><button id="save">Open</button></header>
<main><div id="list"></div><div id="view"><p class="meta">Choose a report.</p></div></main>
<script>
const $=s=>document.querySelector(s);let reports=[],current=null,loaded=null;
const tokenKey="bc250-admin-token";
function token(){try{return localStorage.getItem(tokenKey)||""}catch{return ""}}
async function api(path,options={}){const r=await fetch(path,{...options,headers:{authorization:"Bearer "+token()}});if(r.status===401)throw new Error("Wrong admin token or password");return r.json()}
function el(tag,text,cls){const e=document.createElement(tag);if(text!==undefined&&text!==null)e.textContent=String(text);if(cls)e.className=cls;return e}
function when(iso){return (iso||"").replace("T"," ").slice(0,16)}
async function load(){reports=[];let cursor=null;do{const d=await api("/v1/admin/reports"+(cursor?"?cursor="+encodeURIComponent(cursor):""));reports.push(...d.reports);cursor=d.cursor}while(cursor);draw()}
function draw(){const q=$("#filter").value.toLowerCase();const list=$("#list");list.replaceChildren();
const shown=reports.filter(r=>JSON.stringify(r).toLowerCase().includes(q));$("#count").textContent=shown.length+" of "+reports.length;
for(const r of shown){const row=el("div",undefined,"row"+(r.id===current?" on":""));
const top=el("div");if(r.code)top.append(el("span",r.code,"chip code"));else top.append(el("span",r.kind,"chip"+(r.kind==="idea"?" idea":"")));row.append(top);
row.append(el("div",r.summary||"(no summary)","t"));
row.append(el("div",[r.distribution,r.version&&("v"+r.version),when(r.received),r.source].filter(Boolean).join(" · "),"meta"));
row.onclick=()=>{location.hash=r.id;open(r.id)};list.append(row)}}
function card(title){const c=el("section",undefined,"card");c.append(el("h3",title));return c}
function pairs(obj,labels){const dl=el("dl");let any=false;for(const [k,label] of labels){const v=obj&&obj[k];if(v===undefined||v===null||v===""||(Array.isArray(v)&&!v.length))continue;any=true;dl.append(el("dt",label));dl.append(el("dd",Array.isArray(v)?v.join("\\n"):v))}return any?dl:null}
function table(obj){const t=el("table");let any=false;for(const [k,v] of Object.entries(obj||{})){if(v===""||v==null)continue;any=true;const tr=el("tr");tr.append(el("th",k));tr.append(el("td",v));t.append(tr)}return any?t:null}
function block(title,text,open){const d=el("details");d.open=!!open;const s=el("summary",title+" ");s.append(el("span","("+Math.max(1,Math.round(String(text).length/1024))+" KB)","meta"));d.append(s);d.append(el("pre",text));return d}
async function open(id){current=id;draw();const v=$("#view");v.replaceChildren(el("p","Loading…","meta"));
const d=await api("/v1/admin/reports/"+id);if(!d.ok){v.replaceChildren(el("p",d.error||"Not found","meta"));return}loaded=d.report;const rep=d.report,m=d.metadata||{};v.replaceChildren();
const head=card(rep.kind==="idea"?"Idea":"Problem report");head.append(el("h2",rep.summary||"(no summary)"));
const chips=el("div");const err=rep.error||{};
for(const [text,cls] of [[err.code||rep.code,"chip code"],[m.distribution,"chip"],[(rep.app||{}).version&&("v"+(rep.app||{}).version),"chip"],[when(rep.sent_at||m.received),"chip"],[(rep.app||{}).opened_from,"chip"],[(rep.app||{}).language,"chip"],[rep.id,"chip"]])if(text)chips.append(el("span",text,cls));
head.append(chips);if(rep.contact)head.append(el("p","Contact: "+rep.contact,"meta"));
const actions=el("div",undefined,"actions");const dl=el("button","Download JSON");dl.onclick=()=>{const a=document.createElement("a");a.href=URL.createObjectURL(new Blob([JSON.stringify(rep,null,2)],{type:"application/json"}));a.download=id+".json";a.click()};
const cp=el("button","Copy JSON");cp.onclick=async()=>{await navigator.clipboard.writeText(JSON.stringify(rep,null,2));cp.textContent="Copied"};
const del=el("button","Delete","danger");del.onclick=async()=>{if(!confirm("Delete "+id+"?"))return;await api("/v1/admin/reports/"+id,{method:"DELETE"});reports=reports.filter(r=>r.id!==id);current=null;v.replaceChildren();draw()};
actions.append(dl,cp,del);head.append(actions);v.append(head);
if(rep.idea){const c=card("Idea");c.append(el("dd",rep.idea));v.append(c)}
const p=pairs(rep.problem,[["area","Area"],["seen","What they saw"],["frequency","How often"],["worked_before","Worked before"],["steps","Steps"],["expected","Expected"],["media","Media"],["notes","Notes"]]);if(p){const c=card("What the user reports");c.append(p);v.append(c)}
if(rep.error){const c=card("Error");const e=pairs(err,[["code","Code"],["title","Window"],["what","What happened"],["cause","Likely cause"]]);if(e)c.append(e);if(err.fix)c.append(el("p",err.fix,"fix"));const w=pairs(err,[["reference","Reference"],["where","Where"]]);if(w)c.append(w);if(err.raw)c.append(block("Raw error",err.raw,true));v.append(c)}
const wf=rep.workflow||{};if(wf.log||wf.title){const c=card("Failed workflow");if(wf.title)c.append(el("p",wf.title));if(wf.log)c.append(block("Log",wf.log,true));v.append(c)}
const sysT=table(rep.system);const fw=table(rep.firmware);const os=table(rep.os_release);
if(sysT||fw||os){const c=card("System (detected)");if(sysT)c.append(sysT);if(fw){c.append(el("h3","BIOS"));c.append(fw)}if(os){c.append(el("h3","os-release"));c.append(os)}v.append(c)}
const ow=pairs(rep.owner,[["distribution","Distribution"],["install","Installed with"],["bios","BIOS"],["cores","CPU cores"],["cus","GPU CUs"],["other_tools","Other tools"]]);if(ow){const c=card("User answers");c.append(ow);v.append(c)}
if((rep.history||[]).length){const c=card("Earlier errors ("+rep.history.length+")");const t=el("table");const h=el("tr");for(const x of ["When","Code","Where","Title","Detail"])h.append(el("th",x));t.append(h);
for(const e of rep.history){const tr=el("tr");for(const x of [when(e.at),e.code,e.source,e.title,e.detail])tr.append(el("td",x||""));t.append(tr)}c.append(t);v.append(c)}
if((rep.attachments||[]).length){const total=rep.attachments.reduce((n,a)=>n+a.text.length,0);const c=card("Diagnosis · "+rep.attachments.length+" sections · "+Math.round(total/1024)+" KB");for(const a of rep.attachments)c.append(block(a.name,a.text,false));v.append(c)}
if(rep.fields){const c=card("Form answers (old format)");for(const [name,value] of Object.entries(rep.fields)){if(!value||(Array.isArray(value)&&!value.length))continue;c.append(block(name,Array.isArray(value)?value.join(", "):String(value),String(value).length<3000))}v.append(c)}
v.scrollTop=0}
$("#save").onclick=()=>{try{localStorage.setItem(tokenKey,$("#token").value)}catch{};load().then(()=>{if(current)open(current)}).catch(e=>alert(e.message))};
$("#filter").oninput=draw;const wanted=location.hash.slice(1);
if(!token())$("#view").replaceChildren(el("p","Type the admin token or password above and press Open.","meta"));
if(token())load().then(()=>{if(/^R-[0-9a-f]{8}$/.test(wanted))open(wanted)}).catch(e=>{$("#view").replaceChildren(el("p",e.message,"meta"))});
</script></body></html>`;
