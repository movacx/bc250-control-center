import ast
import json
import subprocess
import sys
from pathlib import Path

from frontends.desktop.i18n.locale_catalog import COMPLETE_LOCALES, LOCALE_DIRECTORY

ROOT = Path(__file__).resolve().parents[2]


def _literals() -> set[str]:
    found: set[str] = set()
    for path in (ROOT / "frontends" / "tui").rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call):
                func = node.func
                name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
                if name in ("tr", "tr_format") and node.args and isinstance(node.args[0], ast.Constant) \
                        and isinstance(node.args[0].value, str):
                    found.add(node.args[0].value)
    return found


def _table_labels() -> set[str]:
    from frontends.tui.pages import build_pages, extras, settings
    from frontends.tui.pages.monitoring import SERIES

    labels = {title for _key, title in extras.TAB_TITLES} | {label for _k, label in extras.MEMORY_POLICIES}
    labels |= {label for _k, label in extras.DRIVER_COMPONENTS} | {label for _k, label in extras.STATUS_INSTALL}
    for entries in extras.TABS.values():
        for entry in entries:
            labels.add(entry.label)
            labels |= {label for key, label in entry.actions if label != key}  # raw ids are shown untranslated
    labels |= {label for _k, label in settings.THEMES} | {label for _k, label in settings.TABS}
    labels |= {label for _k, label, _lo, _hi in settings.ALERT_FIELDS}
    for group, rows in SERIES:
        labels.add(group)
        labels |= {label for _n, label, _u in rows}
    labels |= {page.title for page in build_pages().values()}
    return labels


def test_every_visible_terminal_string_is_in_the_english_catalog_and_all_thirty_locales():
    visible = _literals() | _table_labels()
    assert visible
    for code in COMPLETE_LOCALES:
        catalog = json.loads((LOCALE_DIRECTORY / f"{code}.json").read_text(encoding="utf-8"))
        missing = sorted(text for text in visible if text not in catalog)
        assert not missing, (code, missing)


def test_new_terminal_strings_are_really_translated_not_copied_from_english():
    english = json.loads((LOCALE_DIRECTORY / "en.json").read_text(encoding="utf-8"))
    sentence = "The value must be between {low} and {high}."
    for code in COMPLETE_LOCALES:
        if code == "en":
            continue
        catalog = json.loads((LOCALE_DIRECTORY / f"{code}.json").read_text(encoding="utf-8"))
        assert catalog[sentence] != english[sentence], code
        assert "{low}" in catalog[sentence] and "{high}" in catalog[sentence], code


def test_the_terminal_interface_imports_without_qt():
    code = (
        "import sys; sys.modules['PyQt6'] = None\n"
        "import frontends.tui.app, frontends.tui.pages, frontends.tui.screen\n"
        "from frontends.tui.pages import build_pages; build_pages()\n"
    )
    result = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True,
                            env={"PYTHONPATH": f"{ROOT}/src:{ROOT}", "PATH": "/usr/bin"}, check=False)
    assert result.returncode == 0, result.stderr


def test_the_cli_exposes_the_terminal_interface_as_a_subcommand():
    from frontends import cli

    args = cli._parser().parse_args(["tui", "--theme", "mono", "--page", "gpu"])
    assert (args.command, args.theme, args.page) == ("tui", "mono", "gpu")


def test_the_tui_entrypoint_and_main_launcher_dispatch_to_the_same_module():
    tui = (ROOT / "scripts/entrypoints/bc250-control-center-tui").read_text(encoding="utf-8")
    main = (ROOT / "scripts/entrypoints/bc250-control-center").read_text(encoding="utf-8")
    assert "python3 -m frontends.tui" in tui
    assert '"${1:-}" = "tui"' in main and 'APP_MODULE="frontends.tui"' in main
    assert (ROOT / "scripts/entrypoints/bc250-control-center-tui").stat().st_mode & 0o111


def test_a_non_interactive_start_explains_itself_instead_of_crashing(tmp_path):
    result = subprocess.run([sys.executable, "-m", "frontends.tui"], cwd=ROOT, capture_output=True, text=True,
                            stdin=subprocess.DEVNULL, env={"PYTHONPATH": f"{ROOT}/src:{ROOT}", "PATH": "/usr/bin",
                                                          "HOME": str(tmp_path)}, check=False)
    assert result.returncode == 2 and "interactive terminal" in result.stderr
