"""The command palette: every section, tab and action, found by typing part of its name."""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from typing import Any

from .content import Buttons, Panel, Tiles, cell_width, clip, pad
from .i18n import tr

#: Parts of a block that hold other blocks.
_NESTED = ("blocks", "left", "right", "cards", "choices")


def plain(text: str) -> str:
    """Lower case without accents, so "desinstalacion" finds "Desinstalación"."""
    return "".join(char for char in unicodedata.normalize("NFKD", text.casefold()) if not unicodedata.combining(char))


@dataclass
class Entry:
    label: str
    where: str
    page: str
    tab: str = ""
    choice: Any = None
    haystack: str = field(init=False)

    def __post_init__(self) -> None:
        self.haystack = plain(f"{self.label} {self.where}")


def matches(entries: list[Entry], query: str) -> list[Entry]:
    words = plain(query).split()
    found = [entry for entry in entries if all(word in entry.haystack for word in words)]
    return sorted(found, key=lambda entry: (entry.choice is not None and not words,
                                            not all(word in plain(entry.label) for word in words)))


def choices_of(blocks, group: str = ""):
    """(choice, the group it is in) for every action in ``blocks``."""
    for block in blocks:
        title = block.title if isinstance(block, Panel) else getattr(block, "text", group) if type(block).__name__ == "Heading" else group
        if type(block).__name__ == "Heading":
            group = title
        if getattr(block, "handler", None) is not None and getattr(block, "label", ""):
            yield block, group
        if isinstance(block, Panel) and block.action is not None:
            yield block.action, title
        if isinstance(block, Tiles):
            continue  # profiles: picked on their page, next to their values
        for name in _NESTED:
            nested = getattr(block, name, None)
            if nested:
                yield from choices_of(nested, title if not isinstance(block, Buttons) else group)


class PaletteSupport:
    """Mixin: the screen supplies pages, navigation and dialogs."""

    def command_entries(self) -> list[Entry]:
        entries = []
        for key in self.order:
            page, title = self.pages[key], tr(self.pages[key].title)
            entries.append(Entry(title, "", key))
            tabs = page.tabs(self.ctx)
            entries += [Entry(label, title, key, tab) for tab, label in tabs]
            # Remote access shows credentials of the session: never in a list of everything.
            if key == "remote" or (page.loads and key not in self.ctx.page_data):
                continue
            for tab, label in tabs or [("", "")]:
                try:
                    with self.ctx.lock:
                        blocks = page.build(self.ctx, self.ctx.page_data.get(key), tab, self)
                except Exception:  # noqa: BLE001 - one page's problem must not hide the others' actions
                    continue
                for choice, group in choices_of(blocks):
                    name = choice.label.strip(" ›")
                    if name.startswith(("[", "(", "<")) or not name:
                        continue
                    where = " / ".join(dict.fromkeys(part for part in (title, label, group) if part and part != name))
                    entries.append(Entry(name, where, key, tab, choice))
        return entries

    def command_palette(self) -> None:
        if self.poller:
            self.poller.prefetch()
        query, index, loaded, entries = "", 0, None, []
        caret = "▏" if self.unicode else "_"
        while True:
            if loaded != len(self.ctx.page_data):
                loaded, entries = len(self.ctx.page_data), self.command_entries()
            found = matches(entries, query)
            index = max(0, min(index, len(found) - 1))
            height, width = self.size()
            box = min(width - 4, 92)
            view = max(1, min(14, height - 8))
            offset = max(0, min(index - view // 2, len(found) - view))
            lines = [f"{query}{caret}"]
            for entry in found[offset:offset + view]:
                name = entry.label if entry.choice is None or entry.choice.enabled else f"{entry.label} · {tr('Unavailable')}"
                name = clip(name, box - 8)
                room = box - 4 - cell_width(name) - 2
                lines.append(name + ("  " + pad("", room - cell_width(clip(entry.where, room))) + clip(entry.where, room)
                                     if entry.where and room > 8 else ""))
            lines += [tr("No results")] if not found else []
            lines += [""] * (view + 1 - len(lines))  # the box keeps its height while typing
            self.draw()
            top, left, _h, box_w = self._box(tr("Commands"), lines, width=box, selected=index - offset + 1 if found else None,
                                             footer="↑↓  Enter  Esc")
            self._dialog_hits += [(top + 2 + line, left + 1, left + box_w - 1, f"pick:{offset + line}")
                                  for line in range(min(view, len(found) - offset))]
            self._present()
            key = self._modal_key()
            if key in ("esc", "f2"):
                return
            if key.startswith("pick:") or (key == "enter" and found):
                self._open_entry(found[int(key[5:])] if key.startswith("pick:") else found[index])
                return
            moves = {"up": -1, "down": 1, "pgup": -view, "pgdn": view, "wheelup": -3, "wheeldown": 3}
            if key in moves:
                index += moves[key]
            elif key == "backspace":
                query, index = query[:-1], 0
            elif key == "space" or (len(key) == 1 and key.isprintable()):
                query, index = query + (" " if key == "space" else key), 0

    def _open_entry(self, entry: Entry) -> None:
        """Go there; an action is then opened exactly as from its own row."""
        self.goto(entry.page)
        if entry.tab:
            self.show_tab(entry.tab)
        self._focus("content")
        if entry.choice is None:
            return
        layout, slot = self.build(), self._slot()
        at = next((i for i, choice in enumerate(layout.choices) if choice.label == entry.choice.label
                   and choice.detail == entry.choice.detail), None)
        if at is None:
            self.notify(tr("Unavailable"), "warn")
            return
        self.cursor[slot] = at
        self._reveal(slot, layout.choice_rows[at])
        self._activate(layout.choices[at])
