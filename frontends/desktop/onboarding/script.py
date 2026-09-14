"""What the tour says, what each sentence is attached to, and in what order.

Written as data rather than as code so the route can be read in one screen and
argued with. Three rules hold throughout:

*Point at something real.* Every stop resolves to a widget that exists on the
page, so the sentence is read next to the control it describes rather than
next to a picture of it. Where the control lives on a tab, the stop opens that
tab first: a tour that says "and over here you can…" about something the user
cannot see has explained nothing.

*Follow the shape of the application.* The dashboard first, because it is the
page everything starts from, and split into the parts it is actually made of —
the readings at the top, then the four halves of preparing the board. Then the
modules in the order someone would use them.

*Say it plainly.* Not "configure the SMU parameters" but what the control does
and what happens to the machine when it is pressed. Somebody meeting a BC250
for the first time has enough to take in without the interface showing off.
"""

from __future__ import annotations

from ..i18n import tr
from .tour import TourStop


def _rail(key: str):
    """The sidebar entry for a module, which is where every module starts."""

    def resolve(window):
        sidebar = getattr(window, "sidebar", None)
        buttons = getattr(sidebar, "buttons", {}) if sidebar is not None else {}
        return buttons.get(key)

    return resolve


def _attribute(*path: str):
    """A widget named by a chain of attributes, or None if any link is missing.

    Pages differ between boards and between backends — the Cyan panels are not
    built for an Oberon governor — so a missing link is an ordinary answer
    here, not an error. The tour skips the stop.
    """

    def resolve(window):
        node = window
        for name in path:
            node = getattr(node, name, None)
            if node is None:
                return None
        return node

    return resolve


def _together(*resolvers):
    """Highlight several widgets as one. Missing ones are simply left out."""

    def resolve(window):
        found = []
        for resolver in resolvers:
            widget = resolver(window)
            if widget is not None:
                found.append(widget)
        return found

    return resolve


def _preparation_tab(index: int):
    """A tab of *Prepare BC250 system*, with what is on it.

    The button alone would highlight a word and leave the user to guess what
    pressing it shows; the contents alone would not say which of the four tabs
    they are looking at. Both together is the whole answer.
    """

    def resolve(window):
        readiness = _attribute("dashboard", "readiness")(window)
        buttons = getattr(readiness, "tab_buttons", None) if readiness else None
        if not buttons or index >= len(buttons):
            return None
        found = [buttons[index]]
        for name in ("stack", "prepare_footer"):
            part = getattr(readiness, name, None)
            if part is not None:
                found.append(part)
        return found

    return resolve


def _open_preparation_tab(index: int):
    """Select that tab, and bring the whole panel into view while at it.

    The panel sits at the foot of a page taller than the window, so without
    this the stop would highlight whatever strip of it happened to be on
    screen. The guide scrolls the anchor into view on its own; selecting the
    tab here is what makes the anchor the right one.
    """

    def arrange(window):
        readiness = _attribute("dashboard", "readiness")(window)
        select = getattr(readiness, "select_tab", None) if readiness else None
        if callable(select):
            select(index)

    return arrange


def _open_cpu_workspace(name: str):
    def arrange(window):
        page = getattr(window, "cpu_page", None)
        select = getattr(page, "_select_workspace", None) if page else None
        if callable(select):
            select(name)

    return arrange


def _cpu_workspace_tab(key: str):
    def resolve(window):
        page = getattr(window, "cpu_page", None)
        buttons = getattr(page, "workspace_tab_buttons", None) if page else None
        return buttons.get(key) if buttons else None

    return resolve


def _open_fan_mode(curve: bool):
    def arrange(window):
        page = getattr(window, "fans_page", None)
        button = getattr(page, "curve_mode_button" if curve else "manual_mode_button", None)
        if button is not None and not button.isChecked():
            button.click()

    return arrange


def tour_stops() -> tuple[TourStop, ...]:
    """The route, built fresh so every sentence is in the current language."""
    return (
        # ------------------------------------------------------- dashboard
        TourStop(
            page="dashboard",
            # The readings and the memory strip are one subject sitting in
            # two blocks; one box round both says so, and saves a stop.
            anchor=_together(
                _attribute("dashboard", "gpu_card"),
                _attribute("dashboard", "memory_summary"),
            ),
            title=tr("First: what the board is doing"),
            body=tr(
                "This top strip only reads. Temperature, speed, memory, how "
                "busy each CPU core is. Nothing up here changes anything on "
                "the machine, so look all you like — it is the page to come "
                "back to when you want to know how things are going."
            ),
        ),
        TourStop(
            page="dashboard",
            anchor=_preparation_tab(0),
            arrange=_open_preparation_tab(0),
            title=tr("Components: install what is missing"),
            body=tr(
                "A BC250 needs a few tools before the rest of this application "
                "can do anything. Tick the ones you want, press Prepare "
                "selected, and they are downloaded and installed for you. A "
                "green tick means it is already there."
            ),
        ),
        TourStop(
            page="dashboard",
            anchor=_preparation_tab(1),
            arrange=_open_preparation_tab(1),
            title=tr("Compatibility: make it run better"),
            body=tr(
                "Fixes and extras that improve how the board performs: the GPU "
                "governor, the graphics stack, the power-management "
                "correction. Some of them replace the kernel or Mesa — the one "
                "you have now always stays as a fallback you can boot into."
            ),
        ),
        TourStop(
            page="dashboard",
            anchor=_preparation_tab(2),
            arrange=_open_preparation_tab(2),
            title=tr("Decky: controls from the couch"),
            body=tr(
                "Decky is a plugin for the console-style interface — Game Mode "
                "or Steam Big Picture. Install it and you can change fan speed "
                "and clocks from the Steam overlay, with a controller, without "
                "coming back to this window."
            ),
        ),
        TourStop(
            page="dashboard",
            anchor=_preparation_tab(3),
            arrange=_open_preparation_tab(3),
            title=tr("Drivers: get the rest of the hardware working"),
            body=tr(
                "The things around the board rather than the board itself: "
                "Wi-Fi adapters and printers. If something is plugged in and "
                "the system cannot see it, this is the tab to try."
            ),
        ),
        # ------------------------------------------------------------- cpu
        TourStop(
            page="cpu",
            anchor=_cpu_workspace_tab("configuration"),
            arrange=_open_cpu_workspace("configuration"),
            title=tr("CPU: making it faster"),
            body=tr(
                "Pick one of the presets or type your own speed, voltage and "
                "temperature cap. Start with a preset. What you apply lasts "
                "until you reboot, unless you ask for it to be saved for boot "
                "— so if something goes wrong, restarting undoes it."
            ),
        ),
        TourStop(
            page="cpu",
            anchor=_cpu_workspace_tab("overview"),
            arrange=_open_cpu_workspace("overview"),
            title=tr("CPU: watching it, and the hidden cores"),
            body=tr(
                "The other tab: what every core is doing right now, and the "
                "cores the factory firmware left switched off. Unlocking them "
                "gives you more processor; it is reversible and it is all "
                "explained before anything is applied."
            ),
        ),
        # ------------------------------------------------------------- gpu
        TourStop(
            page="gpu",
            anchor=_attribute("gpu_page", "_redesigned_gpu_view", "service_toggle"),
            title=tr("GPU: turn the service on first"),
            body=tr(
                "The governor is what actually moves the graphics clock. "
                "Nothing else on this page does anything until it is running, "
                "so this button is step one. After that, pick a profile or set "
                "the range by hand — every change is checked before it runs."
            ),
        ),
        # ------------------------------------------------------------- rest
        TourStop(
            page="cu",
            anchor=_rail("cu"),
            title=tr("Compute units: more graphics power"),
            body=tr(
                "The BC250 ships with part of its graphics chip switched off. "
                "Here you turn those pieces back on. They come in pairs, the "
                "change is undone by a reboot unless you save it, and the page "
                "tells you which ones the driver has actually accepted."
            ),
        ),
        TourStop(
            page="performance",
            anchor=_rail("performance"),
            title=tr("Performance: the history"),
            body=tr(
                "Graphs of what the board has been doing, and a record of "
                "everything this application has changed on it. If something "
                "started behaving differently, this is where you find out when "
                "and what did it."
            ),
        ),
        # ------------------------------------------------------------ fans
        TourStop(
            page="fans",
            anchor=_attribute("fans_page", "manual_mode_button"),
            arrange=_open_fan_mode(curve=False),
            title=tr("Fans, by hand"),
            body=tr(
                "Set a fixed speed and leave it there. Good for testing, or "
                "when you simply want the machine quiet. There is a floor that "
                "cannot be switched off: a setting that would let the board "
                "overheat is refused instead of applied."
            ),
        ),
        TourStop(
            page="fans",
            anchor=_attribute("fans_page", "curve_mode_button"),
            arrange=_open_fan_mode(curve=True),
            title=tr("Fans, on their own"),
            body=tr(
                "The other way: you say how fast the fan should spin at each "
                "temperature, and the board follows that by itself from then "
                "on. Quiet when it is cool, loud when it is working. This is "
                "the one to leave running day to day."
            ),
        ),
        TourStop(
            page="dashboard",
            anchor=_rail("settings"),
            title=tr("And that is everything"),
            body=tr(
                "Language, appearance, the sidebar, and the button that plays "
                "this tour again all live in Settings. Anything that needs an "
                "administrator password runs in a terminal inside this window, "
                "so you never have to leave it."
            ),
        ),
    )
