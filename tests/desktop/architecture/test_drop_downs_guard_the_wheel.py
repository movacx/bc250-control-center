"""Every drop-down list is a ``GuardedComboBox``.

A closed ``QComboBox`` changes its value when the wheel passes over it while the
page scrolls (a governor, a profile, a HelixSR setting, with no click at all).
``GuardedComboBox`` leaves that wheel to the page. A list built from the bare
class would bring the accident back, and nothing would say so, so the sources
are read here: a bare ``QComboBox()`` in the desktop frontend fails this test.

(The guard was an application-wide Python event filter once. That crashed the
interpreter while pages were being destroyed, see ``wheel_guard.py``.)
"""

from __future__ import annotations

import ast
from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[3] / "frontends"
#: The one place allowed to name the base class as a constructor: its own subclass.
GUARD = FRONTEND / "desktop" / "components" / "wheel_guard.py"


def _bare_constructions() -> list[str]:
    found = []
    for path in FRONTEND.rglob("*.py"):
        if path == GUARD:
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call):
                function = node.func
                name = function.id if isinstance(function, ast.Name) else function.attr if isinstance(function, ast.Attribute) else ""
                if name == "QComboBox":
                    found.append(f"{path.relative_to(FRONTEND.parent)}:{node.lineno}")
    return sorted(found)


def test_no_drop_down_is_built_from_the_bare_class():
    assert _bare_constructions() == [], "use GuardedComboBox (frontends/desktop/components/wheel_guard.py)"


def test_the_guard_is_a_method_of_the_list_and_not_an_event_filter():
    """An application-wide Python filter crashed the interpreter as pages were destroyed."""
    tree = ast.parse(GUARD.read_text(encoding="utf-8"))
    defined = {
        node.name for cls in ast.walk(tree) if isinstance(cls, ast.ClassDef)
        for node in cls.body if isinstance(node, ast.FunctionDef)
    }
    assert "wheelEvent" in defined and "eventFilter" not in defined
    assert "installEventFilter" not in GUARD.read_text(encoding="utf-8").replace("event filter", "")
