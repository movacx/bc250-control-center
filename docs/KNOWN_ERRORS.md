# Support handbook

Settings → About → Support → Known errors contains 76 entries in the 15 modules
of the November 2026 support inventory. The third support card opens the index;
error dialogs can link to a matching entry or to multiple candidates.

The index follows the Official repositories layout: full-width, spaced rows,
search and a module selector. It uses the settings page's single scrollbar.
The index contains only search, the module selector and the complete guide list.
Articles detect the current distribution automatically. The manual selector is
hidden and reserves no layout space. The title and entry ID share one row.

Articles open on Solution, a continuous column of prose and command boxes,
without numbered steps or separate cards. Developer notes contains status and
engineering work. There is no diagnostic tab: unverified causes and historical
report metadata are not presented as a current diagnosis. A distribution with a null fix gets
an applicability explanation instead of another system's commands.

The public data is `src/bc250cc/shared/known_errors.json`. It contains no report
IDs, personal report titles or user-specific attachments. Keep report-to-entry
research outside the packaged tree. Runtime code never reads a developer's
Documents directory or contacts the report service.

## Adding or correcting an entry

Keep the existing entry ID stable. Add new entries to the appropriate module;
several entries may share a diagnostic code. In particular, missing UMR and a
broken UMR runtime both use BC250-UMR-001 and need different advice.

- `title`, `symptom`, `cause`, `developer` and `fix.*.steps` have Spanish and
  English text. Other UI languages display English long-form content.
- `guide.title` is the article title and `guide.summary` explains its context.
  Each applicable `fix.*.article` contains bilingual `text` and literal
  `commands` lists. Render them in one column, without generic check/apply/verify
  headings or numbering. State the condition for a modifying command next to
  it and explain the expected output.
- `codes` includes current identities and historical aliases for searching.
  An incorrect historical code must not become a message-recognition rule.
- `match` contains reviewed regular expressions over the actual error message.
  Reuse existing window rules or terminal markers when they identify this
  particular entry. Do not copy a broad generic rule into every matching code.
- `keywords` accepts language-keyed lists, including `und` for mixed-language
  source keywords. Existing translated diagnostic vocabulary is also indexed.
- `distros.reported` is evidence from actual reports. `distros.possible` lists
  families where the entry or a documented equivalent can apply; it does not
  claim that all those systems have been tested.
- `fix` explicitly covers `arch`, `steamos`, `bazzite`, `fedora`, `ubuntu`,
  `debian` and `other`. A null value means this backend does not apply. Never
  replace it with another family's instructions. `scope` distinguishes
  `applicable`, `equivalent` and `conditional` advice.
- `fix.*.command` remains available for catalog clients; the article uses its
  `fix.*.article[].commands`. Both are reviewed clipboard text. Avoid commands
  with unresolved placeholders, broad cache deletion or automatic execution.
  SteamOS and Bazzite retain their own package/deployment workflows.
- `owner` is `user`, `developer`, `both` or `expected`. Preserve protective
  refusals and user cancellations; do not offer a bypass as a repair.
- `status_flags` preserves mixed states, such as a published diagnostic with a
  remaining developer task. `fixed_in` is null unless a precise published
  version is documented. Development-only fixes do not trigger an update to
  an imaginary release.

The application reads this declarative catalog locally and caches it for the
process. Restart after editing it. Increment `catalog_version` for content
changes, and `schema_version` if the schema changes. Remote catalog updates are
not implemented; they need a defined publication source and validation before
they can replace the bundled offline catalog.

UI text uses the normal 30 locale catalogs. Preserve their key order when
editing them. The support pages reuse the settings table/card styles and the
error dialog's shared copy-only command widget.

## Verification

The offline vocabulary in `src/bc250cc/shared/known_errors_search.json` contains
the supplied 8,116 terms in 15 modules, including the app's 30 languages. It is
module vocabulary, not evidence that every guide shares a particular error.
Keep titles, diagnostic patterns, commands and published fix versions with
their individual entries. Add entry-specific spelling/technical aliases in
`known_errors_search.py` only when a module alias would hide that distinction.

Search normalizes accents, punctuation and underscores. An exact entry ID ranks
before a diagnostic code; codes accept omitted padding and separators. `PKG-06`
is the entry ID, while `pkg 6` and `PKG-006` mean diagnostic BC250-PKG-006.
Shared codes retain all their candidates. Long pasted error messages prioritize
the actual regex match over historical codes. Full words, module synonyms,
word-start prefixes (at least three characters), and bounded spelling edits
follow. Common boilerplate is excluded from prefix expansion. Multiword queries
prefer all useful words, then a majority; stopwords alone return no results.
Version searches use only documented `fixed_in` releases. Distribution names
include aliases and explicit applicability; search never changes the selected
distribution or borrows another distribution's commands.

The index and bounded query caches are built in memory. Typing waits 150 ms;
Enter searches immediately. Each result has a short match reason. Empty results
offer applicable spelling/module suggestions and a prefilled report form;
opening that form never submits it. Private report IDs are deliberately absent
from this public vocabulary and cannot be resolved through this search.

The vocabulary regression checks every supplied term against its module;
terms containing only stopwords are excluded. Re-run it when editing the data.

Run the handbook tests and relevant desktop/i18n tests, not the full repository
suite:

```bash
QT_QPA_PLATFORM=offscreen python -m pytest --no-cov \
  tests/services/test_known_errors.py \
  tests/services/test_known_errors_search.py \
  tests/desktop/settings/test_known_errors_section.py \
  tests/desktop/settings/test_support_section.py \
  tests/desktop/i18n/test_complete_locale_catalogs.py \
  tests/desktop/i18n/test_i18n_dialog_coverage.py
PYTHONPATH=src python -m bc250cc.shared.error_origins
```

The rpm-ostree guide distinguishes status inspection from package removal and
the subsequent reboot. Its behavior follows the [rpm-ostree administration
handbook](https://coreos.github.io/rpm-ostree/administrator-handbook/). Log commands
are limited to relevant units/lines using [journalctl's documented
options](https://www.freedesktop.org/software/systemd/man/latest/journalctl).

The Cyan TOML articles include a dated backup, editing with sudoedit, and a
validation command that gates the service restart with `&&`. The validator uses
[Python 3.11's tomllib](https://docs.python.org/3.11/library/tomllib.html);
[sudoedit](https://manpages.debian.org/bookworm/sudo/sudoedit.8.en.html) edits a
temporary copy rather than running the editor as root. Tests exercise the
read-only validator against temporary valid/invalid TOML and syntax-check the
shell blocks, without editing system files or restarting a service.

Review light/dark captures at the real settings window size, switch distributions
and article tabs, and check long translated titles and narrow layouts. The
handbook is explanatory: implementing its listed infrastructure fixes remains
separate work and may require a matching installed privileged helper.
