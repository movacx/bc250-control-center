"""Shared shell fragments that make generated workflows readable.

Every workflow used to invent its own ``== title ==`` line and then dump raw
tool output, so a user watching a long automated install could not tell what
was being installed, which step was running, or whether it was going well.
These helpers give every script the same visual language:

    ==========================================================================
      BC-250 · Prepare dependencies
      Step 2/5 · Installing packages
    ==========================================================================

Plain ASCII only: these strings are rendered by whatever terminal emulator the
user happens to have, including minimal consoles without box-drawing glyphs or
a Unicode-capable font.

Text is passed in already translated, because ``src`` cannot import the
frontend's catalogs.
"""

from __future__ import annotations

import shlex

RULE_WIDTH = 74
RULE = "=" * RULE_WIDTH
THIN_RULE = "-" * RULE_WIDTH


def banner(title: object, subtitle: object = "") -> str:
    """Frame the workflow's identity so it is obvious what is running."""
    lines = [f'echo; echo "{RULE}"; echo "  {title}";']
    if str(subtitle or "").strip():
        lines.append(f'echo "  {subtitle}";')
    lines.append(f'echo "{RULE}"; echo;')
    return " ".join(lines)


def step(number: object, total: object, title: object) -> str:
    """Announce one step, so progress is visible during a long install."""
    return (
        f'echo; echo "{THIN_RULE}"; '
        f'echo "  [{number}/{total}] {title}"; '
        f'echo "{THIN_RULE}";'
    )


def note(text: object) -> str:
    """A single indented line of context under the current step."""
    return f'echo "    {text}";'


def summary(title: object, rows: object = ()) -> str:
    """Close a workflow with what was actually done."""
    parts = [f'echo; echo "{RULE}"; echo "  {title}";']
    for row in rows or ():
        parts.append(f'echo "    {row}";')
    parts.append(f'echo "{RULE}"; echo;')
    return " ".join(parts)


def progress_note(text: object) -> str:
    """Reassure the user while a slow, quiet command runs.

    A build or download that prints nothing for minutes reads as a freeze;
    saying what is happening is the difference between waiting and worrying.
    """
    return f'echo "    ... {text}";'


def quoted_banner(title: object, subtitle: object = "") -> str:
    """``banner`` for titles that may contain shell metacharacters."""
    safe_title = shlex.quote(str(title))
    parts = [f'echo; echo "{RULE}"; echo "  "{safe_title};']
    if str(subtitle or "").strip():
        parts.append(f'echo "  "{shlex.quote(str(subtitle))};')
    parts.append(f'echo "{RULE}"; echo;')
    return " ".join(parts)
