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

## Notifications

Each new report can post a short message with a link to `/admin#<id>`.
Both channels are optional.

Telegram: create a bot with @BotFather, send it any message, then:

```bash
npx wrangler secret put TELEGRAM_BOT_TOKEN
curl -H "authorization: Bearer $(cat ~/.config/bc250-reports-admin-token)" \
  https://bc250-reports.report-endpoint.workers.dev/v1/admin/telegram-chats
npx wrangler secret put TELEGRAM_CHAT_ID
```

Discord: Channel settings → Integrations → Webhooks → New webhook → Copy URL:

```bash
npx wrangler secret put DISCORD_WEBHOOK_URL
```

Test both:

```bash
curl -X POST -H "authorization: Bearer $(cat ~/.config/bc250-reports-admin-token)" \
  https://bc250-reports.report-endpoint.workers.dev/v1/admin/notify-test
```
