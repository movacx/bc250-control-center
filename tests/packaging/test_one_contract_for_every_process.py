"""Three processes, one set of numbers — and no way to disagree quietly.

The desktop, the privileged helpers and the Decky backend cannot import each
other. The helpers run under ``python3 -I``, which drops their own directory
from ``sys.path`` and ignores ``PYTHONPATH``; the Decky backend receives only
the handful of files its installer stages. So each had written the same rules
down for itself, and four of those copies had drifted:

* ``cu_repository`` expected runtime protocol 9 while the helper published 13.
  Every Compute Units change made in Game Mode was discarded without a log
  line, and the desktop showed a stale cache instead — since protocol 10.
* The Decky backend capped CPU frequency at 3500 MHz against a canonical 3100,
  so a profile saved at 3200 on the desktop was rounded *up* before being
  re-applied.
* The plugin's copy of the GPU profile table grew an Oberon profile canon did
  not have, in a shape the desktop's validator rejected.
* A helper printed ``CPU_BACKEND_UNTRUSTED`` and the catalogue had never heard
  of it, so the exit number decided and said "a required program is missing".

Every one of those passed its own tests, because each side was tested against
its own copy. What is checked here is agreement between the copies.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from bc250cc.shared import contract  # noqa: E402

GENERATOR = ROOT / "scripts" / "development" / "generate_contract.py"
PYTHON_ARTEFACT = ROOT / "privileged" / "lib" / "bc250_contract.py"
PANEL_ARTEFACT = (
    ROOT / "integrations" / "decky" / "bc250-quick-access"
    / "src" / "generated" / "error_catalog.json"
)
HELPERS = ROOT / "privileged" / "helpers"
DECKY_BACKEND = ROOT / "integrations" / "decky" / "bc250-quick-access" / "main.py"


def _generated() -> dict[Path, str]:
    spec = importlib.util.spec_from_file_location("generate_contract", GENERATOR)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module.artefacts()


def consumers() -> list[Path]:
    """Found by content, so a fourth consumer inherits every check below."""
    found = [
        path
        for path in sorted(HELPERS.iterdir())
        if path.is_file() and not path.is_symlink() and path.name != "README.md"
        and "bc250_contract" in path.read_text(encoding="utf-8", errors="ignore")
    ]
    if DECKY_BACKEND.is_file() and "bc250_contract" in DECKY_BACKEND.read_text(encoding="utf-8"):
        found.append(DECKY_BACKEND)
    return found


def consumer_names() -> list[str]:
    return [str(path.relative_to(ROOT)) for path in consumers()]


# ------------------------------------------------------------ the generation


def test_the_generated_artefacts_match_their_source():
    stale = [
        str(path.relative_to(ROOT))
        for path, text in _generated().items()
        if not path.is_file() or path.read_text(encoding="utf-8") != text
    ]
    assert stale == [], (
        "these are out of date — run scripts/development/generate_contract.py: "
        + ", ".join(stale)
    )


def test_the_generator_says_so_itself():
    result = subprocess.run(
        [sys.executable, str(GENERATOR), "--check"],
        capture_output=True,
        text=True,
        cwd=ROOT,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, result.stderr


# ------------------------------------------------- what the artefact may hold


def test_the_contract_imports_nothing_outside_the_standard_library():
    """It is ``exec``'d as root by a helper whose import path was emptied."""
    tree = ast.parse(PYTHON_ARTEFACT.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            imported.add(node.module.split(".")[0])
    outside = sorted(
        name for name in imported
        if name not in sys.stdlib_module_names and name != "__future__"
    )
    assert outside == [], outside


def test_the_contract_declares_only_data_and_pure_functions():
    """Nothing at module scope may run. This executes with uid 0."""
    tree = ast.parse(PYTHON_ARTEFACT.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.ImportFrom, ast.Import, ast.Expr)):
            continue
        assert isinstance(node, (ast.Assign, ast.AnnAssign)), ast.dump(node)[:120]
        value = node.value
        assert not isinstance(value, ast.Call), f"module-level call: {ast.unparse(node)[:80]}"


# --------------------------------------------------------- the consumers


def test_there_is_more_than_one_consumer():
    """A guard that silently covers nothing is worse than none."""
    assert len(consumers()) >= 2, consumer_names()


@pytest.mark.parametrize("name", consumer_names())
def test_every_consumer_stamps_the_revision_it_was_built_against(name):
    source = (ROOT / name).read_text(encoding="utf-8")
    tree = ast.parse(source)
    stamps = [
        node.value.value
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "REQUIRED_CONTRACT_REVISION"
            for target in node.targets
        )
        and isinstance(node.value, ast.Constant)
    ]
    assert stamps == [contract.CONTRACT_REVISION], f"{name} stamps {stamps}"


@pytest.mark.parametrize("name", consumer_names())
def test_every_consumer_verifies_root_ownership_before_loading(name):
    source = (ROOT / name).read_text(encoding="utf-8")
    assert "st_uid != 0" in source or "st_uid == 0" in source, name


@pytest.mark.parametrize("name", consumer_names())
def test_no_consumer_loads_the_contract_at_module_scope(name):
    """A module-scope failure is a plugin that never appears, with no message.

    Decky Loader imports ``main.py``; an exception there means the BC250 panel
    is simply absent, and nothing on screen says why. Inside a function, the
    same failure reaches the caller's error handler as one sentence.
    """
    tree = ast.parse((ROOT / name).read_text(encoding="utf-8"))
    inside: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for child in ast.walk(node):
                inside.add(id(child))
    offenders = [
        ast.unparse(node)[:70]
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and "spec_from_file_location" in ast.unparse(node.func)
        and id(node) not in inside
    ]
    assert offenders == [], f"{name} loads the contract at import time: {offenders}"


# ------------------------------------------- the numbers, agreed across copies


def test_the_desktop_expects_the_protocol_the_helper_publishes():
    from bc250cc.infrastructure.cu_repository import (
        QUICK_ACCESS_CU_RUNTIME_HELPER_PROTOCOL,
    )

    helper = (HELPERS / "bc250-quick-access-helper").read_text(encoding="utf-8")
    declared = [
        node.value.value
        for node in ast.parse(helper).body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "HELPER_PROTOCOL"
            for target in node.targets
        )
        and isinstance(node.value, ast.Constant)
    ]
    assert declared == [contract.QUICK_ACCESS_PROTOCOL]
    assert QUICK_ACCESS_CU_RUNTIME_HELPER_PROTOCOL == contract.QUICK_ACCESS_PROTOCOL


def test_every_interface_offers_the_same_cpu_frequencies():
    from bc250cc.domain.cpu.limits import FREQUENCY_RANGE

    assert FREQUENCY_RANGE is contract.CPU_FREQUENCY_RANGE
    backend = DECKY_BACKEND.read_text(encoding="utf-8")
    low, high = contract.CPU_FREQUENCY_RANGE
    assert f"range({low}, {high + 1}, {contract.CPU_FREQUENCY_STEP_MHZ})" in backend, (
        "the Game Mode CPU ladder is not the canonical one"
    )


def test_the_helper_and_the_contract_agree_about_oberon():
    helper = (HELPERS / "bc250-quick-access-helper").read_text(encoding="utf-8")
    block = helper[helper.index("OBERON_QAM_PROFILES = {"):]
    block = block[: block.index("}") + 1]
    offered = sorted(ast.literal_eval(block.split("=", 1)[1]).values())
    assert offered == sorted(contract.OBERON_DESKTOP_PROFILES)


def test_the_plugins_copy_of_the_profile_table_is_the_canonical_one():
    canonical = ROOT / "src" / "bc250cc" / "domain" / "gpu" / "profiles.py"
    vendored = (
        ROOT / "integrations" / "decky" / "bc250-quick-access"
        / "bc250cc" / "domain" / "gpu" / "profiles.py"
    )
    assert vendored.read_text(encoding="utf-8") == canonical.read_text(encoding="utf-8")


def test_the_profile_table_offers_exactly_the_contracted_oberon_profiles():
    """The copy above cannot import the contract, so this checks it instead."""
    from bc250cc.domain.gpu.profiles import profiles_for_allowed_range

    low = min(value for value, _high in contract.OBERON_DESKTOP_PROFILES)
    high = max(value for _low, value in contract.OBERON_DESKTOP_PROFILES)
    offered = profiles_for_allowed_range(low, high, governor="oberon")
    assert tuple((item.minimum_mhz, item.maximum_mhz) for item in offered) == (
        contract.OBERON_DESKTOP_PROFILES
    )


def test_the_panel_catalogue_carries_every_code_in_the_same_order():
    from bc250cc.shared.error_catalog import _CODES, _MARKERS_BY_LENGTH

    payload = json.loads(PANEL_ARTEFACT.read_text(encoding="utf-8"))
    assert payload["contract_revision"] == contract.CONTRACT_REVISION
    assert {entry["code"] for entry in payload["codes"]} == {e.code for e in _CODES}
    assert payload["markers_longest_first"] == [m for m, _e in _MARKERS_BY_LENGTH]


def test_the_panel_catalogue_carries_no_wording():
    """Sentences are translated on both sides already; a third copy would rot."""
    payload = json.loads(PANEL_ARTEFACT.read_text(encoding="utf-8"))
    for entry in payload["codes"]:
        assert set(entry) == {"code", "markers", "exit_statuses", "retryable"}


def test_the_plugin_reports_the_version_it_was_built_with():
    """It was pinned at 0.1.0 against a project at 1.19.0, with nothing
    comparing them — so Decky's plugin manager reported the same version
    forever and an upgrade that changed only the panel was undetectable."""
    import json as _json

    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    package = _json.loads(
        (ROOT / "integrations" / "decky" / "bc250-quick-access" / "package.json")
        .read_text(encoding="utf-8")
    )
    assert package["version"] == version
