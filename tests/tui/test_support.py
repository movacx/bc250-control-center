"""New versions and problem reports in the terminal interface."""

from types import SimpleNamespace

from bc250cc.domain.updates import UpdateStatus
from frontends.tui import support
from frontends.tui.pages import build_pages
from frontends.tui.screen import Screen

from .fakes import FakeUI, make_context
from .test_pages import render


ASKS_TO_REPORT = Screen._asks_to_report  # as written, before the fixtures answer it


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
    layout = render(build_pages()["about"], screen.ctx, FakeUI(), "about")
    update = next(c for c in layout.choices if c.label == "Update now")
    assert update.enabled
    installed = []
    monkeypatch.setattr(support, "install_update", lambda ctx, family: installed.append(family) or "ok")
    monkeypatch.setattr("frontends.tui.pages.about.install_update", support.install_update)
    ui = FakeUI()
    update.handler(ui)
    assert installed and ui.ran == ["Update now"]


def test_up_to_date_and_unreachable_read_differently():
    ctx = make_context()
    ctx.state("ui")["update"] = UpdateStatus(installed="9.9.9", published="9.9.9", reachable=True)
    assert support.available_version(ctx) == ""
    text = " ".join(t for row in render(build_pages()["about"], ctx, FakeUI(), "about").rows for t, _ in row.spans)
    assert "You have the latest version." in text
    assert not any(c.label == "Update now" for c in render(build_pages()["about"], ctx, FakeUI(), "about").choices)


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


def report_page(monkeypatch, facts=None):
    from bc250cc.application.system.feedback import reports as form

    sent = []
    monkeypatch.setattr(form, "submit", lambda report: sent.append(report) or report.id)
    monkeypatch.setattr("frontends.desktop.core.report_facts.read_report_facts",
                        lambda attachments=True: dict(facts or {}, **({"attachments": [("kernel", "log")]} if attachments else {})))
    monkeypatch.setattr("frontends.tui.report_form.read_light_facts", lambda draft: None)
    return build_pages()["report"], sent


def row(page, ui, label, ctx):
    return next(c for c in render(page, ctx, ui).choices if c.label == label)


def test_the_report_form_sends_the_answers_with_the_system_facts(monkeypatch):
    page, sent = report_page(monkeypatch, {"version": "1.2.3", "distribution": "Bazzite", "system": {"OS": "x"}})
    ctx, ui = make_context(), Asking(["The fan stops", "It keeps spinning", "@me"])
    row(page, ui, "Send", ctx).handler(ui)
    assert not sent and ui.notes[-1][1] == "warn"  # the one required answer comes first
    for label in ("What went wrong?", "What did you expect to happen?", "Telegram or Discord username"):
        row(page, ui, label, ctx).handler(ui)
    row(page, ui, "Send", ctx).handler(ui)
    assert sent[0].summary == "The fan stops" and sent[0].contact == "@me" and sent[0].expected == "It keeps spinning"
    assert sent[0].distribution == "Bazzite" and sent[0].opened_from == "tui" and sent[0].attachments == [("kernel", "log")]
    assert ui.notes[-1][1] == "ok"
    assert row(page, ui, "Report a problem", ctx)


def test_the_automatic_report_can_be_left_out_and_an_idea_never_carries_it(monkeypatch):
    page, sent = report_page(monkeypatch, {"system": {"OS": "x"}})
    ctx, ui = make_context(), Asking(["The fan stops"])
    row(page, ui, "What went wrong?", ctx).handler(ui)
    row(page, ui, "Send the automatic report", ctx).handler(ui)
    row(page, ui, "Send", ctx).handler(ui)
    assert sent[0].attachments == [] and sent[0].system == {} and sent[0].history == []
    page.open(__import__("frontends.tui.report_form", fromlist=["x"]).new_draft())
    row(page, ui, "Type", ctx).handler(ui)
    ui.answers = ["A darker theme"]
    row(page, ui, "Suggestions and ideas", ctx).handler(ui)
    row(page, ui, "Send", ctx).handler(ui)
    assert sent[1].notes == "A darker theme" and not sent[1].is_problem and sent[1].attachments == []


def test_a_report_that_cannot_be_sent_keeps_what_was_written(monkeypatch):
    from bc250cc.application.system.feedback import reports as form

    page, _sent = report_page(monkeypatch)

    def refuse(_report):
        raise form.ReportError("no network")

    monkeypatch.setattr(form, "submit", refuse)
    ctx, ui = make_context(), Asking(["The fan stops"])
    row(page, ui, "What went wrong?", ctx).handler(ui)
    row(page, ui, "Send", ctx).handler(ui)
    assert "still here" in ui.notes[-1][0] and page.draft().get("summary") == "The fan stops"


def test_a_failed_action_asks_first_and_opens_the_form_with_its_log(monkeypatch):
    from .test_screen import make_screen

    monkeypatch.setattr(Screen, "_asks_to_report", ASKS_TO_REPORT)
    for answer, opens in (("esc", False), ("r", True)):
        _window, screen = make_screen()
        screen._foreground = None
        monkeypatch.setattr("frontends.tui.report_form.read_light_facts", lambda draft: None)
        monkeypatch.setattr(screen, "_getch", lambda: 27)
        monkeypatch.setattr(screen, "_modal_key", lambda answer=answer: answer)

        def work():
            print("E: broken package")
            raise RuntimeError("the package manager failed")

        # Esc while it runs would cancel it: the key only arrives once it has ended.
        def key(screen=screen):
            screen.active_console.done.wait(5)
            return 27

        monkeypatch.setattr(screen, "_getch", key)
        ok, _error = screen.run("Prepare dependencies", work)
        assert not ok and (screen.page_key == "report") is opens
        if opens:
            draft = screen.pages["report"].draft()
            assert draft.title == "Prepare dependencies" and "broken package" in draft.get("terminal")
            assert "the package manager failed" in draft.raw and draft.details["page"] == "dashboard"
            assert any(c.label == "Send" for c in screen.build().choices)


def test_a_refusal_never_asks_to_report(monkeypatch):
    from bc250cc.shared.operation_contract import OperationCancelled

    from .test_screen import make_screen

    _window, screen = make_screen()
    screen._foreground = None
    monkeypatch.setattr(screen, "_asks_to_report", lambda *a: (_ for _ in ()).throw(AssertionError("asked")))

    def key():
        screen.active_console.done.wait(5)
        return 27

    monkeypatch.setattr(screen, "_getch", key)

    def work():
        raise OperationCancelled

    screen.run("Anything", work)
    assert screen.page_key == "dashboard"
