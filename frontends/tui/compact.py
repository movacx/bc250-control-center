"""Responsive hardware workspaces with visible groups, profiles and actions."""
from __future__ import annotations

from dataclasses import replace

from .content import Gap, Panel, Split


def terminal_form(blocks):
    """Keep the interaction hierarchy; the layout engine stacks narrow cards.

    Flattening profiles and button groups made actions indistinguishable from
    readings. Panels now retain their borders, badges and keyboard targets.
    """
    out = []
    for block in blocks:
        if isinstance(block, Panel):
            block = replace(block, blocks=terminal_form(block.blocks))
        elif isinstance(block, Split):
            block = replace(block, left=terminal_form(block.left), right=terminal_form(block.right))
        if out and isinstance(block, Panel) and not isinstance(out[-1], Gap):
            out.append(Gap())
        out.append(block)
    return out
