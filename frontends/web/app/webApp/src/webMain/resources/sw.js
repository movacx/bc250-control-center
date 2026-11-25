/* Installation support with an explicitly-offline navigation fallback.
 * Online navigation belongs to the browser so TLS errors remain visible. */
self.addEventListener("install", (event) => event.waitUntil(self.skipWaiting()));
self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()));
self.addEventListener("fetch", (event) => {
  const request = event.request;
  const url = new URL(request.url);
  // API traffic and mutations always go directly to the server, untouched.
  if (request.method !== "GET" || request.mode !== "navigate" || url.origin !== self.location.origin || url.pathname.startsWith("/api/")) return;
  // Do not wrap network failures: fetch cannot distinguish a TLS trust error
  // from a disconnected server. Let the browser handle online navigation.
  if (self.navigator.onLine !== false) return;
  event.respondWith(Promise.resolve(new Response(`<!doctype html>
<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>BC250 · Offline</title>
<style>html{color-scheme:dark;font:16px/1.6 system-ui;background:#111;color:#eee}body{max-width:32rem;margin:18vh auto;padding:24px}h1{font-size:24px}p{color:#bbb}a{display:inline-block;margin-top:12px;padding:10px 22px;border-radius:6px;background:#b39dff;color:#111;text-decoration:none;font-weight:600}</style>
<h1>BC250 · Offline</h1><p>No se pudo conectar con la placa. Comprueba que esté encendida y que tengas conexión a su red.</p><p>Cannot connect to the board. Check its power and your network connection.</p><a href="/">Reintentar / Retry</a></html>`, {
    status: 503,
    headers: { "Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store",
      "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'" },
  })));
});
