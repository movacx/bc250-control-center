# Privacy

Control Center sends nothing by itself. A problem report or idea leaves your
computer only when you press **Send** in the report dialog, and **See what is
sent** shows the exact text first.

## What a report contains

- What you typed: summary, steps, contact (optional).
- The app version, the distribution, BIOS, core and compute-unit answers.
- The error, its history, and a diagnosis of the system: kernel log, BC-250
  service journals, boot parameters, GPU listing and configuration files.

User name, computer name, IP addresses and MAC addresses are removed from the
text, and home folders become `~`. The contact field is sent as you typed it.
Logs can still hold something the filters do not know; read the preview, and
untick **Send the automatic report** to leave the diagnosis out.

## Where it goes

To a Cloudflare Worker run by the maintainer (`integrations/report-endpoint`).
Reports are kept in Workers KV for about six months and are read only by the
maintainer, to fix problems. They are not sold or shared.

Your IP address reaches Cloudflare like any web request. The service uses it
only to limit how many reports one address can send per minute and does not
store it in the report.
