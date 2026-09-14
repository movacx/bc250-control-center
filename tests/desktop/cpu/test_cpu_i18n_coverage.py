import ast
from pathlib import Path

from frontends.desktop.i18n import translation_coverage

CPU_PAGE = Path("frontends/desktop/pages/cpu_smu.py")

# These are hardware identifiers, units, numeric-only render formats or words
# that are legitimately identical in some supported languages.  Everything
# else visible in the CPU page must resolve through the translation system.
TECHNICAL_EXEMPT = {
    "MHz", "mV", "°C", "scale", "--", "-- °C | -- MHz",
    # The Game Mode floor moved 3500 -> 3100; the old value was exempt and the
    # new one was not, which only stayed invisible because translation_coverage
    # checked a single string per call before that was fixed.
    "3100–4200 MHz", "950–1325 mV · up to 90 °C", "3550 MHz / 1050 mV",
    # Pure format, no prose: both placeholders are filled with already
    # translated text by the caller.
    "{url}: {error}",
    "k10temp Tctl", "CPU / SMU",
    "{frequency} MHz | scale {scale} | {temperature} °C",
    "{frequency} MHz · scale {scale} · {temperature} °C",
    "{temperature} °C | {frequency} MHz",
    "{frequency} · {usage:.0f}%",
    "Visible", "Live", "VID",
}

VISIBLE_CALL_ARGS = {
    "tr": (0,),
    "tr_format": (0,),
    "SectionCard": (0, 1),
    "RuntimeStat": (0, 1, 2),
    "CpuValueField": (0, 1),
    "MetricTile": (0, 1, 2),
    "StatusLine": (0, 1, 2),
    "CpuSummaryItem": (0, 1, 2),
    "QLabel": (0,),
    "QPushButton": (0,),
    "ConfirmDialog": (0, 1),
    "InfoDialog": (0, 1),
    "_show_info": (0, 1),
    "add_header_button": (0,),
    "set_values": (0, 1),
    "setText": (0,),
    "setToolTip": (0,),
    "setPlainText": (0,),
    "_append_console": (0,),
    "_build_and_start_process": (1, 2),
}


def _literal_string(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        value = node.value.strip()
        return value or None
    return None


def cpu_visible_strings():
    tree = ast.parse(CPU_PAGE.read_text(encoding="utf-8"))
    values = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name):
            name = node.func.id
        elif isinstance(node.func, ast.Attribute):
            name = node.func.attr
        else:
            continue
        for index in VISIBLE_CALL_ARGS.get(name, ()):
            if index < len(node.args):
                value = _literal_string(node.args[index])
                if value:
                    values.add(value)
        if name == "SectionCard":
            for kw in node.keywords:
                if kw.arg == "status" and isinstance(kw.value, ast.Tuple) and kw.value.elts:
                    value = _literal_string(kw.value.elts[0])
                    if value:
                        values.add(value)
        if name == "CpuValueField":
            for kw in node.keywords:
                if kw.arg in {"info_title", "info_message"}:
                    value = _literal_string(kw.value)
                    if value:
                        values.add(value)
        if name in {"ConfirmDialog", "InfoDialog"}:
            for kw in node.keywords:
                if kw.arg in {"confirm_text", "eyebrow", "button_text", "notice"}:
                    value = _literal_string(kw.value)
                    if value:
                        values.add(value)
                if name == "ConfirmDialog" and kw.arg == "summary" and isinstance(kw.value, (ast.Tuple, ast.List)):
                    for pair in kw.value.elts:
                        if not isinstance(pair, (ast.Tuple, ast.List)):
                            continue
                        for element in pair.elts:
                            value = _literal_string(element)
                            if value:
                                values.add(value)
    return {
        value for value in values
        if value not in TECHNICAL_EXEMPT
        and not value.startswith("/")
        and not value.startswith("bc250-")
    }


def test_cpu_module_has_no_language_fallback_for_visible_copy():
    missing = translation_coverage(cpu_visible_strings())
    assert missing == {}, "CPU UI translation fallback detected: " + repr(missing)
