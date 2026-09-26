"""Interface code the application can never reach.

The desktop frontend has been redesigned several times, and each pass left the
previous one behind: whole card builders that nothing calls, a ``_reflow`` the
class defined twice so the first copy could never run, and widget classes no
page instantiates any more.  None of it failed a test, because unreachable code
does not fail — it just costs review time, translation work and honest answers
to "where is this drawn?".

This file measures that residue and pins it at the current count, so the next
redesign has to take its predecessor with it.  Adding a new entry to an
allowlist below is allowed, but it has to be deliberate.
"""

from __future__ import annotations

import ast
import collections
import io
import re
import tokenize
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
FRONTEND = ROOT / "frontends"

# Qt calls these; nothing in our own code has to.
QT_OVERRIDES = frozenset({
    "paintEvent", "resizeEvent", "showEvent", "hideEvent", "keyPressEvent",
    "keyReleaseEvent", "mousePressEvent", "mouseMoveEvent", "mouseReleaseEvent",
    "mouseDoubleClickEvent", "wheelEvent", "enterEvent", "leaveEvent",
    "closeEvent", "eventFilter", "event", "sizeHint", "minimumSizeHint",
    "focusInEvent", "focusOutEvent", "changeEvent", "inputMethodEvent",
    "contextMenuEvent", "moveEvent", "dragEnterEvent", "dragMoveEvent",
    "dragLeaveEvent", "dropEvent", "timerEvent", "heightForWidth",
    "hasHeightForWidth", "setVisible", "actionEvent", "tabletEvent",
    "hitButton",
})

# Features that are fully written but have no control that invokes them.  Each
# one is a decision waiting to be made — wire it up or delete it — not an
# accident, so they are listed by name rather than tolerated by pattern.
UNWIRED_FEATURES = frozenset({
    "SettingsPage._build_health_page",
    "SettingsPage._build_notifications_page",
    "SettingsPage._import_profile_bundle",
    "SettingsPage._export_profile_bundle",
    "SettingsPage._evaluate_memory_pressure",
    "SettingsPage._show_local_paths",
    "SettingsPage._banner",
    "CpuSmuPage.test_scale_live",
    "CpuSmuPage._build_command_context_card",
    "DependencyPreparationDialog._ttm_memory_card",
    "DependencyPreparationDialog._show_memory_policy_preview",
})


def _identifiers(paths) -> collections.Counter:
    """Every identifier in the tree, including ones inside string literals.

    Strings matter: ``getattr(host, "gamepad_go_dashboard", None)`` is a real
    call site, and a stylesheet selector is a real reference to a class name.
    """
    names: collections.Counter = collections.Counter()
    for path in paths:
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):  # pragma: no cover - binary assets
            continue
        if path.suffix != ".py":
            names.update(re.findall(r"[A-Za-z_]\w*", text))
            continue
        try:
            for token in tokenize.generate_tokens(io.StringIO(text).readline):
                if token.type == tokenize.NAME:
                    names[token.string] += 1
                elif token.type == tokenize.STRING:
                    names.update(re.findall(r"[A-Za-z_]\w*", token.string))
        except (tokenize.TokenError, IndentationError, SyntaxError):  # pragma: no cover
            pass
    return names


def _everything_that_can_refer_to_the_frontend():
    for folder in ("frontends", "src", "tests", "packaging", "privileged", "docs"):
        for path in (ROOT / folder).rglob("*"):
            if path.is_file() and path.suffix not in {".zip", ".png", ".svg", ".map"}:
                yield path


def _frontend_modules() -> list[tuple[Path, ast.Module]]:
    return [(path, ast.parse(path.read_text(encoding="utf-8")))
            for path in sorted(FRONTEND.rglob("*.py"))]


def _named(path: Path) -> str:
    return str(path.relative_to(ROOT))


# A name that appears exactly once in the whole project is its own definition
# and nothing else.
_names = _identifiers(_everything_that_can_refer_to_the_frontend())
_modules = _frontend_modules()


def test_no_widget_class_is_defined_without_ever_being_built():
    orphans = [
        f"{_named(path)}: class {node.name}"
        for path, module in _modules
        for node in module.body
        if isinstance(node, ast.ClassDef) and _names[node.name] == 1
    ]
    assert orphans == [], (
        "these classes are never instantiated anywhere, not even in a test:\n  "
        + "\n  ".join(orphans)
    )


def test_no_method_is_written_without_a_caller():
    orphans = []
    for path, module in _modules:
        for cls in [n for n in ast.walk(module) if isinstance(n, ast.ClassDef)]:
            for fn in cls.body:
                if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                if fn.name.startswith("__") or fn.name in QT_OVERRIDES:
                    continue
                if _names[fn.name] != 1:
                    continue
                qualified = f"{cls.name}.{fn.name}"
                if qualified in UNWIRED_FEATURES:
                    continue
                orphans.append(f"{_named(path)}:{fn.lineno}: {qualified}")
    assert orphans == [], (
        "nothing calls these, and no test does either — wire them up, delete "
        "them, or add them to UNWIRED_FEATURES with a reason:\n  "
        + "\n  ".join(orphans)
    )


def test_the_unwired_feature_list_has_not_gone_stale():
    """An allowlist that outlives its entries hides the next regression."""
    defined = {
        f"{cls.name}.{fn.name}"
        for _path, module in _modules
        for cls in [n for n in ast.walk(module) if isinstance(n, ast.ClassDef)]
        for fn in cls.body
        if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert UNWIRED_FEATURES <= defined, sorted(UNWIRED_FEATURES - defined)


def test_no_class_defines_the_same_method_twice():
    """Python keeps the last definition and discards the first silently.

    ``FansPage`` carried two ``_reflow`` methods.  The dead one laid out the
    pre-redesign cards and reached for ``self.workspace``, an attribute no
    longer assigned anywhere — so had it ever run, the page would have raised
    on its first resize.
    """
    shadowed = []
    for path, module in _modules:
        for cls in [n for n in ast.walk(module) if isinstance(n, ast.ClassDef)]:
            seen: dict[str, int] = {}
            for fn in cls.body:
                if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                if fn.name in seen:
                    shadowed.append(
                        f"{_named(path)}: {cls.name}.{fn.name} at line {seen[fn.name]} "
                        f"is replaced by the one at line {fn.lineno}"
                    )
                seen[fn.name] = fn.lineno
    assert shadowed == [], "\n  ".join(shadowed)


def test_no_module_level_function_is_written_without_a_caller():
    """The checks above only walk class bodies.

    That is why ``frontends/quick_access/backend/mapper.py`` survived: a
    22-line package from before the real Decky plugin existed, whose README
    stated an intention ("must not maintain duplicate hardware policy tables")
    that the shared contract now implements, imported by nothing but its own
    test.
    """
    orphans = []
    for path, module in _modules:
        for node in module.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if node.name.startswith("_") and _names[node.name] == 1:
                # A private module-level helper with no caller is dead; a
                # public one may be an intentional export.
                orphans.append(f"{_named(path)}:{node.lineno}: {node.name}")
    assert orphans == [], (
        "nothing calls these module-level functions:\n  " + "\n  ".join(orphans)
    )
