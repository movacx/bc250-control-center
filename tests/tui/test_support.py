"""New versions and problem reports in the terminal interface."""

from types import SimpleNamespace

from bc250cc.domain.updates import UpdateStatus
from frontends.tui import support
from frontends.tui.pages import build_pages

from .fakes import FakeUI, make_context
from .test_pages import render


class Asking(FakeUI):
    def __init__(self, texts, **kwargs):
        super().__init__(**kwargs)
        self.answers = list(texts)

    def ask_text(self, label, default=""):
        return self.answers.pop(0) if self.answers else default


def test_a_newer_release_shows_in_the_title_and_about_offers_the_update(monkeypatch):
    from .test_screen import make_screen

    window, screen = make_screen()
    screen.ctx.state("ui")["update"] = UpdateStatus(installed="1.0.0", published="9.9.9", reachable=True)
    screen.draw()
    assert "9.9.9" in window.line(0)
    layout = render(build_pages()["settings"], screen.ctx, FakeUI(), "about")
    update = next(c for c in layout.choices if c.label == "Update now")
    assert update.enabled
    installed = []
    monkeypatch.setattr(support, "install_update", lambda ctx, family: installed.append(family) or "ok")
    monkeypatch.setattr("frontends.tui.pages.settings.install_update", support.install_update)
    ui = FakeUI()
    update.handler(ui)
    assert installed and ui.ran == ["Update now"]


def test_up_to_date_and_unreachable_read_differently():
    ctx = make_context()
    ctx.state("ui")["update"] = UpdateStatus(installed="9.9.9", published="9.9.9", reachable=True)
    assert support.available_version(ctx) == ""
    text = " ".join(t for row in render(build_pages()["settings"], ctx, FakeUI(), "about").rows for t, _ in row.spans)
    assert "You have the latest version." in text
    assert not next(c for c in render(build_pages()["settings"], ctx, FakeUI(), "about").choices
                    if c.label == "Update now").enabled


def test_the_desktop_switch_turns_the_check_off(tmp_path, monkeypatch):
    (tmp_path / "bc250-control-center").mkdir()
    (tmp_path / "bc250-control-center" / "ui.conf").write_text("[settings]\nupdate_check=false\n")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert support.update_checks_enabled() is False


def test_a_manual_plan_is_explained_instead_of_run(monkeypatch):
    import bc250cc.application.system.updates as updates

    release = SimpleNamespace(version="9.9.9", page_url="https://example.invalid/r")
    monkeypatch.setattr(updates, "fetch_latest_release", lambda: release)
    monkeypatch.setattr(updates, "detect_install_source", lambda: None)
    monkeypatch.setattr(updates, "plan_update", lambda *a, **k: SimpleNamespace(kind="manual", reason="git pull."))
    ctx = make_context()
    try:
        support.install_update(ctx, "fedora")
    except updates.UpdateError as error:
        assert "git pull." in str(error)
    else:
        raise AssertionError("a manual plan must not install")


def test_a_report_sends_the_answers_with_the_system_facts(monkeypatch):
    from bc250cc.application.system.feedback import reports as form

    sent = []
    monkeypatch.setattr(form, "submit", lambda report: sent.append(report) or report.id)
    monkeypatch.setattr("frontends.desktop.core.report_facts.read_report_facts",
                        lambda: {"version": "1.2.3", "distribution": "Bazzite", "system": {"OS": "x"}})
    ui = Asking(["The fan stops", "@me"], choices=[form.KIND_PROBLEM])
    support.report(ui)
    assert sent and sent[0].summary == "The fan stops" and sent[0].contact == "@me"
    assert sent[0].distribution == "Bazzite" and sent[0].opened_from == "tui"
    assert ui.notes[-1][1] == "ok"


def test_a_failed_workflow_is_reported_with_its_log(monkeypatch):
    from bc250cc.application.system.feedback import reports as form

    sent = []
    monkeypatch.setattr(form, "submit", lambda report: sent.append(report) or report.id)
    monkeypatch.setattr("frontends.desktop.core.report_facts.read_report_facts", lambda: {})
    support.report(Asking([]), title="Prepare dependencies", log="E: broken package")
    assert sent[0].kind == form.KIND_PROBLEM and "broken package" in sent[0].workflow_log
