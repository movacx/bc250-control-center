"""Linear terminal forms for hardware pages; dashboard and sensors keep their layout."""
from __future__ import annotations

from .content import Buttons, Choice, Field, Gap, Heading, Panel, Split, Tiles
from .i18n import tr


def terminal_form(blocks):
    """Flatten desktop cards into predictable, vertically ordered keyboard rows."""
    out = []
    for block in blocks:
        if isinstance(block, Panel):
            out.append(Heading(block.title + (f" · {block.badge}" if block.badge else "")))
            if block.subtitle:
                from .content import Note

                out.append(Note(block.subtitle, "dim"))
            out.extend(terminal_form(block.blocks))
            if block.action:
                out.append(block.action)
            out.append(Gap())
        elif isinstance(block, Split):
            out.extend(terminal_form([*block.left, *block.right]))
        elif isinstance(block, Buttons):
            out.extend(block.choices)
        elif isinstance(block, Tiles):
            for tile in block.tiles:
                detail = " · ".join(value for value in (tile.value, tile.hint) if value)
                if tile.handler:
                    out.append(Choice(f"({'x' if tile.active else ' '}) {tile.label}", tile.handler, detail))
                    if tile.edit:
                        out.append(Choice(f"  {tr('Edit')}: {tile.label}", tile.edit))
                else:
                    out.append(Field(tile.label, detail, tile.tone))
        else:
            out.append(block)
    return out
