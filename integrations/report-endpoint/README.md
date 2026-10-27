# BC250 report service

Cloudflare Worker that receives problem reports from Control Center in one
request (gzip JSON, attachments included) and keeps them in Workers KV for
about six months. Google Forms stays the app's fallback.

- `POST /v1/reports`: used by the app (`REPORT_ENDPOINT` in
  `src/bc250cc/infrastructure/feedback_form.py`). 4 reports per minute per
  address, 1 MiB compressed, 6 MiB expanded.
- `/admin`: the maintainer's page to list, read and delete reports. It asks
  for the admin token (stored in `~/.config/bc250-reports-admin-token` on the
  maintainer's machine).

## Deploy

```bash
npx wrangler deploy
```

## Secrets

```bash
npx wrangler secret put ADMIN_TOKEN
```

Optional message per report on Telegram:

```bash
npx wrangler secret put TELEGRAM_BOT_TOKEN
npx wrangler secret put TELEGRAM_CHAT_ID
```
