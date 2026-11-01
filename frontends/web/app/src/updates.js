/** Ignore failed probes and compare only web build identities, never package versions. */
export function hasWebUpdate(loaded, release) {
  const valid = value => typeof value === "string" && /^[a-f0-9]{16}$/.test(value);
  return !!release && !release._disconnected && release.status === 200
    && valid(loaded) && valid(release.version) && loaded !== release.version;
}

/** A new navigation URL on every attempt also bypasses a previously cached reload. */
export function refreshUrl(href, version, nonce = Date.now()) {
  const url = new URL(href);
  url.searchParams.set("v", version);
  url.searchParams.set("_refresh", String(nonce));
  return url.href;
}
