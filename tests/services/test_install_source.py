"""Where an update should come from depends on how this copy was installed.

"There is a newer version" is half an answer. Telling someone who installed
from the AUR to download a release tarball would walk around their package
manager's records, and telling someone on a source checkout to run an AUR
helper names a package they do not have.

The question is answered by asking the package manager which package owns a
file belonging to this installation — not by guessing from a prefix, because
every installer in this project can be pointed somewhere else. Every unknown
answer resolves to the releases page, which is the harmless way to be wrong.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from bc250cc.infrastructure import install_source as module
from bc250cc.infrastructure.install_source import (
    AUR_PACKAGE,
    InstallSource,
    UpdateChannel,
    detect_install_source,
)


@pytest.fixture
def owned_file(tmp_path):
    target = tmp_path / "release_check.py"
    target.write_text("# a file this installation owns\n", encoding="utf-8")
    return target


def _answers(monkeypatch, *, which=(), pacman="", pacman_code=0, rpm="", rpm_code=1,
             dpkg="", dpkg_code=1):
    available = set(which)
    monkeypatch.setattr(
        module.shutil, "which", lambda name: f"/usr/bin/{name}" if name in available else None
    )

    def run(argv):
        if argv[0] == "pacman":
            return pacman_code, pacman
        if argv[0] == "rpm":
            return rpm_code, rpm
        if argv[0] == "dpkg-query":
            return dpkg_code, dpkg
        raise AssertionError(f"unexpected query: {argv}")

    monkeypatch.setattr(module, "_run", run)


# ------------------------------------------------------------------------ AUR


def test_the_aur_package_is_recognised(monkeypatch, owned_file):
    _answers(monkeypatch, which={"pacman", "paru"}, pacman=AUR_PACKAGE)
    source = detect_install_source(path=owned_file)
    assert source.channel is UpdateChannel.AUR
    assert source.package == AUR_PACKAGE
    assert source.manager == "pacman"


def test_any_git_package_is_treated_as_an_aur_build(monkeypatch, owned_file):
    """A ``-git`` package is built from source by a helper, whatever its name."""
    _answers(monkeypatch, which={"pacman", "yay"}, pacman="bc250-control-center-git")
    assert detect_install_source(path=owned_file).channel is UpdateChannel.AUR


def test_the_command_names_the_helper_that_is_installed(monkeypatch, owned_file):
    _answers(monkeypatch, which={"pacman", "yay"}, pacman=AUR_PACKAGE)
    assert detect_install_source(path=owned_file).command == f"yay -Syu {AUR_PACKAGE}"


def test_paru_is_preferred_when_several_are_present(monkeypatch, owned_file):
    _answers(monkeypatch, which={"pacman", "paru", "yay", "trizen"}, pacman=AUR_PACKAGE)
    assert detect_install_source(path=owned_file).helper == "paru"


def test_no_helper_installed_still_yields_a_usable_command(monkeypatch, owned_file):
    """Naming one is more useful than naming none; the user installs it or not."""
    _answers(monkeypatch, which={"pacman"}, pacman=AUR_PACKAGE)
    command = detect_install_source(path=owned_file).command
    assert command.endswith(AUR_PACKAGE)
    assert command.split()[0] in module.AUR_HELPERS


# ------------------------------------------------------------------- packages


def test_a_repository_pacman_package_is_not_aur(monkeypatch, owned_file):
    """``build-local-pkg.sh`` produces the plain name: rebuilt, not helper-updated."""
    _answers(monkeypatch, which={"pacman"}, pacman="bc250-control-center")
    source = detect_install_source(path=owned_file)
    assert source.channel is UpdateChannel.PACKAGE
    assert source.command == ""


def test_an_rpm_is_recognised(monkeypatch, owned_file):
    _answers(
        monkeypatch,
        which={"rpm"},
        rpm="bc250-control-center",
        rpm_code=0,
    )
    source = detect_install_source(path=owned_file)
    assert source.channel is UpdateChannel.PACKAGE
    assert source.manager == "rpm"


def test_a_deb_is_recognised(monkeypatch, owned_file):
    _answers(
        monkeypatch,
        which={"dpkg-query"},
        dpkg="bc250-control-center: /usr/share/bc250-control-center/x.py",
        dpkg_code=0,
    )
    source = detect_install_source(path=owned_file)
    assert source.channel is UpdateChannel.PACKAGE
    assert source.manager == "dpkg"


def test_an_rpm_answer_that_is_a_sentence_is_not_a_package_name(monkeypatch, owned_file):
    """``rpm -qf`` prints "file ... is not owned by any package" on stdout."""
    _answers(
        monkeypatch,
        which={"rpm"},
        rpm="file /x is not owned by any package",
        rpm_code=0,
    )
    assert detect_install_source(path=owned_file).channel is UpdateChannel.RELEASE


# --------------------------------------------------------- falling back safely


def test_a_source_checkout_is_sent_to_the_releases_page(monkeypatch, owned_file):
    _answers(monkeypatch, which=set())
    source = detect_install_source(path=owned_file)
    assert source.channel is UpdateChannel.RELEASE
    assert source.package == ""
    assert source.command == ""


def test_a_package_manager_that_owns_nothing_falls_back(monkeypatch, owned_file):
    _answers(monkeypatch, which={"pacman", "rpm", "dpkg-query"}, pacman_code=1)
    assert detect_install_source(path=owned_file).channel is UpdateChannel.RELEASE


def test_an_ambiguous_answer_is_refused(monkeypatch, owned_file):
    """A directory is owned by every package that puts a file in it.

    ``pacman -Qoq /usr/bin`` reports hundreds of names, and taking the first
    would confidently attribute this application to whatever sorted first.
    """
    _answers(monkeypatch, which={"pacman"}, pacman="7zip\npacman\nvim")
    assert detect_install_source(path=owned_file).channel is UpdateChannel.RELEASE


def test_a_directory_is_never_asked_about(monkeypatch, tmp_path):
    def explode(_argv):  # pragma: no cover - must not be reached
        raise AssertionError("a directory cannot identify one package")

    monkeypatch.setattr(module.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(module, "_run", explode)
    assert detect_install_source(path=tmp_path).channel is UpdateChannel.RELEASE


def test_a_missing_file_is_survived(monkeypatch, tmp_path):
    monkeypatch.setattr(module.shutil, "which", lambda name: None)
    assert detect_install_source(path=tmp_path / "gone").channel is UpdateChannel.RELEASE


# ------------------------------------------------------------ the queries used


def test_every_query_is_read_only_and_bounded():
    """None of these may change anything, and none may hang the interface.

    Read from the argument lists themselves rather than by searching the text:
    an earlier version of this test grepped for "install" and matched the word
    in a docstring, which is how a guard ends up asserting about prose.
    """
    import ast

    source = Path(module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    detection = {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name != "command"
    }

    queried: list[list[str]] = []
    for name, function in detection.items():
        for node in ast.walk(function):
            if not (isinstance(node, ast.Call) and getattr(node.func, "id", "") == "_run"):
                continue
            argv = node.args[0]
            assert isinstance(argv, ast.List), f"{name} builds its argv dynamically"
            words = [
                element.value
                for element in argv.elts
                if isinstance(element, ast.Constant) and isinstance(element.value, str)
            ]
            queried.append(words)

    assert queried, "no query was found to check"
    # Named exactly, per tool, rather than matched by shape. A flag letter
    # means different things to each: ``-S`` is a sync for pacman and a search
    # for dpkg-query, which cannot modify anything whatever it is passed. An
    # addition here is a deliberate decision, which is the point.
    allowed = {
        "pacman": {"-Qoq"},
        "rpm": {"-qf", "--queryformat"},
        "dpkg-query": {"-S"},
    }
    for words in queried:
        tool = words[0]
        assert tool in allowed, f"{tool!r} is not a read-only query tool"
        flags = {word for word in words[1:] if word.startswith("-")}
        unexpected = flags - allowed[tool]
        assert unexpected == set(), f"{tool} was passed {sorted(unexpected)}: {words}"
    assert module.QUERY_TIMEOUT_SECONDS <= 10


def test_a_query_that_explodes_does_not_escape(monkeypatch, owned_file):
    monkeypatch.setattr(module.shutil, "which", lambda name: f"/usr/bin/{name}")

    def boom(_argv):
        raise OSError("no such executable")

    monkeypatch.setattr(module.subprocess, "run", lambda *a, **k: boom(a))
    assert detect_install_source(path=owned_file).channel is UpdateChannel.RELEASE


def test_the_command_is_empty_for_everything_but_aur():
    for channel in (UpdateChannel.PACKAGE, UpdateChannel.RELEASE):
        assert InstallSource(channel, package="x", manager="y").command == ""
