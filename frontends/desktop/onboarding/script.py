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
the readings at the top, then each tab of preparing the board. Then the
modules in the order someone would use them, and inside each module the
controls a first-time user has to understand: the profile cards and their
pencil, the export to Decky, the voltage laboratory, the first button of the
compute-unit editor.

*Say it plainly.* Not "configure the SMU parameters" but what the control does
and what happens to the machine when it is pressed. Somebody meeting a BC250
for the first time has enough to take in without the interface showing off.
"""

from __future__ import annotations

from ..i18n import tr
from ..pages.firmware import AFTER_FLASH_WARNING
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


def _readiness(window):
    return _attribute("dashboard", "readiness")(window)


def _preparation_tab(key: str):
    """A tab of *Prepare BC250 system*, with what is on it.

    The button alone would highlight a word and leave the user to guess what
    pressing it shows; the contents alone would not say which of the tabs
    they are looking at. Both together is the whole answer. Tabs are named,
    not numbered: counting positions pointed every stop after "Memory & Swap"
    at the tab before the one it described.
    """

    def resolve(window):
        readiness = _readiness(window)
        buttons = getattr(readiness, "tab_buttons", None) if readiness else None
        index = readiness.tab_index(key) if readiness is not None else -1
        if not buttons or not 0 <= index < len(buttons):
            return None
        found = [buttons[index]]
        for name in ("stack", "prepare_footer"):
            part = getattr(readiness, name, None)
            if part is not None:
                found.append(part)
        return found

    return resolve


def _open_preparation_tab(key: str):
    """Select that tab, and bring the whole panel into view while at it.

    The panel sits at the foot of a page taller than the window, so without
    this the stop would highlight whatever strip of it happened to be on
    screen. The guide scrolls the anchor into view on its own; selecting the
    tab here is what makes the anchor the right one.
    """

    def arrange(window):
        readiness = _readiness(window)
        if readiness is None:
            return
        index = readiness.tab_index(key)
        if index >= 0:
            readiness.select_tab(index)

    return arrange


def _memory_card(name: str):
    """One card of the Memory & Swap tab."""

    def resolve(window):
        readiness = _readiness(window)
        return getattr(readiness, name, None) if readiness else None

    return resolve


def _cpu_view(*path: str):
    return _attribute("cpu_page", "_unified_cpu_control", *path)


def _gpu_view(*path: str):
    return _attribute("gpu_page", "_redesigned_gpu_view", *path)


def _first_card_pencil(view_resolver):
    def resolve(window):
        view = view_resolver(window)
        cards = getattr(view, "_profile_cards", None) if view is not None else None
        return getattr(cards[0], "_edit_button", None) if cards else None

    return resolve


def _open_voltage_lab(window):
    page = getattr(window, "gpu_page", None)
    opener = getattr(page, "open_voltage_lab", None) if page else None
    drawer = getattr(page, "voltage_lab_drawer", None) if page else None
    if callable(opener) and drawer is not None and not drawer.is_open():
        opener()


def _close_voltage_lab(window):
    page = getattr(window, "gpu_page", None)
    drawer = getattr(page, "voltage_lab_drawer", None) if page else None
    if drawer is not None and drawer.is_open():
        drawer.close_animated()


def _open_cpu_workspace(name: str):
    def arrange(window):
        page = getattr(window, "cpu_page", None)
        select = getattr(page, "_select_workspace", None) if page else None
        if callable(select):
            select(name)

    return arrange


#: The per-part views and the sensor list of the Performance page.
PERFORMANCE_VIEWS_FEATURE = "performance-views"


def _performance_views_menu(window):
    """The three tiles that open a views menu, and the menu under CPU."""
    page = getattr(window, "performance_page", None)
    if page is None:
        return None
    tiles = [page.tiles.get(key) for key in ("cpu", "gpu", "vram")]
    return [widget for widget in (*tiles, page.flyout) if widget is not None]


def _pin_views_menu(window):
    page = getattr(window, "performance_page", None)
    if page is not None:
        page.pin_views_menu("cpu")


def _unpin_views_menu(window):
    page = getattr(window, "performance_page", None)
    if page is not None:
        page.unpin_views_menu()


def _open_sensor_list(window):
    page = getattr(window, "performance_page", None)
    if page is not None:
        page.show_sensors()


def _close_sensor_list(window):
    page = getattr(window, "performance_page", None)
    if page is not None:
        page.show_chart()


def _open_fan_mode(curve: bool):
    def arrange(window):
        page = getattr(window, "fans_page", None)
        button = getattr(page, "curve_mode_button" if curve else "manual_mode_button", None)
        if button is not None and not button.isChecked():
            button.click()

    return arrange


def feature_stops(feature: str) -> tuple[TourStop, ...]:
    """Only the stops that introduce ``feature``, in tour order."""
    return tuple(stop for stop in tour_stops() if stop.feature == feature)


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
            anchor=_preparation_tab("components"),
            arrange=_open_preparation_tab("components"),
            title=tr("Components: install what is missing"),
            body=tr(
                "This tab installs the system tools the other modules need. "
                "Tick the ones you want, press Prepare selected, and the "
                "application downloads and installs them for you. A green "
                "tick means that one is already installed."
            ),
        ),
        TourStop(
            page="dashboard",
            anchor=_preparation_tab("compatibility"),
            arrange=_open_preparation_tab("compatibility"),
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
            anchor=_preparation_tab("memory"),
            arrange=_open_preparation_tab("memory"),
            title=tr("Memory & Swap: when the RAM runs out"),
            body=tr(
                "The BC250 shares its memory between the processor and the "
                "graphics. When games fill it, the system needs somewhere to "
                "put the overflow, or the game closes. This tab decides where "
                "that goes, how much the graphics may borrow, and how much is "
                "set aside for video memory."
            ),
        ),
        TourStop(
            page="dashboard",
            anchor=_memory_card("memory_swap_card"),
            arrange=_open_preparation_tab("memory"),
            title=tr("Swap and compression: pick one"),
            body=tr(
                "Disk swap is a file on the SSD that catches the overflow: "
                "slow but roomy. ZRAM squeezes the overflow and keeps it in "
                "RAM: fast but smaller. ZSWAP does both — compresses first, "
                "sends the rest to disk. Not sure? Disk swap of 16 GiB is the "
                "safe choice. Restore puts everything back as it was."
            ),
        ),
        TourStop(
            page="dashboard",
            anchor=_memory_card("memory_ttm_card"),
            arrange=_open_preparation_tab("memory"),
            title=tr("TTM limit: how much the graphics may borrow"),
            body=tr(
                "Besides its own video memory, the GPU borrows normal RAM for "
                "textures. TTM is the ceiling on that loan. Higher helps big "
                "games; too high leaves the system without room. Move along "
                "the line to choose, then press Apply TTM. It needs a restart."
            ),
        ),
        TourStop(
            page="dashboard",
            anchor=_memory_card("memory_vram_card"),
            arrange=_open_preparation_tab("memory"),
            title=tr("VRAM size: memory reserved for video"),
            body=tr(
                "This is the part of the RAM set aside only for the GPU when "
                "the board starts. More VRAM helps games that check for it; "
                "the rest stays for the system. The change is written to the "
                "board's firmware settings and takes effect after a restart."
            ),
        ),
        TourStop(
            page="dashboard",
            anchor=_preparation_tab("decky"),
            arrange=_open_preparation_tab("decky"),
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
            anchor=_preparation_tab("drivers"),
            arrange=_open_preparation_tab("drivers"),
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
            anchor=_cpu_view("profiles_panel"),
            arrange=_open_cpu_workspace("configuration"),
            title=tr("CPU: operating profiles"),
            body=tr(
                "Three ready-made speeds for the processor. One click on a "
                "card selects it; nothing changes on the board until you press "
                "Apply below. Start with the first one and move up only if "
                "the machine stays stable."
            ),
        ),
        TourStop(
            page="cpu",
            anchor=_first_card_pencil(_cpu_view()),
            arrange=_open_cpu_workspace("configuration"),
            title=tr("The pencil: make a profile yours"),
            body=tr(
                "The pencil on each card opens its settings: name, speed, "
                "voltage and temperature limit. Save keeps the change on that "
                "card; Reset brings back the original values. With a "
                "controller, A selects a card and X edits it."
            ),
        ),
        TourStop(
            page="cpu",
            anchor=_cpu_view("_export_decky_button"),
            arrange=_open_cpu_workspace("configuration"),
            title=tr("Export to Decky: the same profiles in Game Mode"),
            body=tr(
                "Sends these three cards to the Decky Quick Access panel, so "
                "in Game Mode you pick the same profiles with the controller. "
                "Edit here, export, and Decky shows your names and values."
            ),
        ),
        TourStop(
            page="cpu",
            anchor=_cpu_view("cores_panel"),
            arrange=_open_cpu_workspace("configuration"),
            title=tr("CPU cores: what each one is doing"),
            body=tr(
                "One row per core: its speed and how busy it is, live. A core "
                "shown as Hidden is switched off by the factory firmware — the "
                "BC250 comes with some cores locked."
            ),
        ),
        TourStop(
            page="cpu",
            anchor=_cpu_view("_risk_panel"),
            arrange=_open_cpu_workspace("overview"),
            title=tr("Hidden cores: unlocking them"),
            body=tr(
                "This button turns the hidden cores on. It restarts the "
                "machine and it is experimental, so every step is explained "
                "and confirmed before anything is written. Leave it for when "
                "the rest is working."
            ),
        ),
        # ------------------------------------------------------------- gpu
        TourStop(
            page="gpu",
            anchor=_gpu_view("service_toggle"),
            title=tr("GPU: turn the service on first"),
            body=tr(
                "The governor is what actually moves the graphics clock, so "
                "start it here: the rest of this page only takes effect while "
                "it is running. After that, pick a profile or set the range by "
                "hand — every change is checked before it runs."
            ),
        ),
        TourStop(
            page="gpu",
            anchor=_together(_gpu_view("profiles_panel"), _first_card_pencil(_gpu_view())),
            title=tr("GPU profiles and the pencil"),
            body=tr(
                "The same idea as the CPU: three frequency ranges, one click "
                "to choose, the pencil to rename a card or change its minimum "
                "and maximum. A card with a red edge needs the extra points "
                "above 2000 MHz switched on first."
            ),
        ),
        TourStop(
            page="gpu",
            anchor=_gpu_view("_export_decky_button"),
            title=tr("Export the GPU profiles to Decky"),
            body=tr(
                "Sends these three GPU cards to Decky, so Game Mode offers the "
                "same ranges. Export again whenever you edit one here."
            ),
        ),
        TourStop(
            page="gpu",
            anchor=_gpu_view("_range_panel"),
            title=tr("Frequency range by hand"),
            body=tr(
                "The lowest and highest speed the graphics may use. Drag the "
                "two handles, or use the arrows. Red marks are points above "
                "the safe ceiling. Review and apply shows exactly what will "
                "change before it runs."
            ),
        ),
        TourStop(
            page="gpu",
            anchor=_gpu_view("lab_panel"),
            title=tr("Voltage laboratory"),
            body=tr(
                "Each speed of the GPU runs at a voltage. More voltage makes a "
                "high speed stable, and also makes more heat. The laboratory "
                "is where those voltages are adjusted, in small steps. Next, "
                "it opens."
            ),
        ),
        TourStop(
            page="gpu",
            anchor=_attribute("gpu_page", "voltage_lab_drawer", "drawer"),
            arrange=_open_voltage_lab,
            leave=_close_voltage_lab,
            title=tr("Inside the laboratory"),
            body=tr(
                "At the top, what would change. Then the boost: +10, +20 or "
                "+30 mV added only to the fast points, or Custom to edit each "
                "point yourself. The table lists every speed with its voltage "
                "now and after. Start with +10 mV; Restore goes back to the "
                "governor's values."
            ),
        ),
        # -------------------------------------------------------------- cu
        TourStop(
            page="cu",
            anchor=_attribute("cu_page", "live_refresh_button"),
            title=tr("Compute units: step one is this button"),
            body=tr(
                "Before anything else, press Unlock / Sync (it later reads "
                "Refresh live topology). It reads the chip's live table and "
                "unlocks the editor; until then every switch stays greyed "
                "out. Press it again whenever you want the page to match the "
                "chip."
            ),
        ),
        TourStop(
            page="cu",
            anchor=_together(
                _attribute("cu_page", "topology_scroll"),
                _attribute("cu_page", "selection_panel"),
            ),
            title=tr("Compute units: switch pairs on, keep the engines even"),
            body=tr(
                "Each button is a pair of compute units. The top two rows are "
                "shader engine 0, the bottom two engine 1. Performance follows "
                "the weaker engine, so 20 + 18 works like 18 + 18: keep both "
                "equal. Apply now tests it live; a restart undoes it until you "
                "save it."
            ),
        ),
        # ----------------------------------------------------- performance
        TourStop(
            page="performance",
            anchor=_rail("performance"),
            title=tr("Performance: the history"),
            body=tr(
                "Graphs of the last two minutes of processor, graphics, "
                "memory, disk and network. Auto zooms in so small loads are "
                "readable; 0–100 % shows the whole scale. Point at the graph "
                "to read an exact value."
            ),
        ),
        TourStop(
            page="performance",
            anchor=_performance_views_menu,
            arrange=_pin_views_menu,
            leave=_unpin_views_menu,
            feature=PERFORMANCE_VIEWS_FEATURE,
            title=tr("Every part has more views"),
            body=tr(
                "Point at CPU, GPU or VRAM and this menu opens under it: the "
                "clock and load of each core, the threads as a heat map, the "
                "temperatures, and the graphics clock, fabric, power and "
                "voltage. Pick one and the graph below switches to it. On a "
                "controller, X opens the same menu."
            ),
        ),
        TourStop(
            page="performance",
            anchor=_attribute("performance_page", "sensor_board"),
            arrange=_open_sensor_list,
            leave=_close_sensor_list,
            feature=PERFORMANCE_VIEWS_FEATURE,
            title=tr("Every sensor in one list"),
            body=tr(
                "Sensors, beside Auto, puts every reading of the board here in "
                "place of the graph: its current, lowest, average and highest "
                "value since the list opened. Tick a sensor to draw it; the "
                "buttons at the top show the list, the list with graphs, or "
                "graphs only."
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
            page="fans",
            anchor=_attribute("fans_page", "system_control_panel"),
            title=tr("Fans from the moment it boots"),
            body=tr(
                "Turn this on and a system service applies your curve from "
                "boot, before anyone logs in, without asking for a password "
                "again. It asks once when you turn it on."
            ),
        ),
        # -------------------------------------------------------- firmware
        # The page is for doing it; how to boot the stick and flash is said
        # here, once, next to the controls, instead of as a column of steps
        # every visit has to scroll past.
        TourStop(
            page="firmware",
            anchor=_attribute("firmware_page", "firmware_panel"),
            title=tr("Firmware (BIOS): choose what goes on the USB"),
            body=tr(
                "Two groups. The modded images open what ASRock left locked; "
                "the stock ones are ASRock's own builds, untouched. Every card "
                "shows the same four facts, so you choose by reading down them."
            ),
            points=(
                tr(
                    "P3.00 Chipset Menu: ASRock's P3.00 with the Chipset menu "
                    "opened, so the VRAM size is set in the BIOS. The usual "
                    "choice, and the one selected for you."
                ),
                tr(
                    "MeiMeiDXE v3: the same menu, plus the two CPU cores the "
                    "factory switched off and 16 boot logos. Some boards are not "
                    "stable with eight cores."
                ),
                tr("P5.00: ASRock's newest official firmware, with nothing unlocked."),
                tr(
                    "P3.00 and P2.00: ASRock's earlier official images, to go back "
                    "to factory behaviour or to troubleshoot."
                ),
            ),
            footnote=tr(
                "Then, in the BIOS setup, Chipset › GFX Configuration › UMA Frame "
                "Buffer Size sets how much memory the GPU gets."
            ),
        ),
        TourStop(
            page="firmware",
            anchor=_attribute("firmware_page", "logo_panel"),
            title=tr("Your own boot logo, if you want one"),
            body=tr(
                "Choose a picture and it replaces the logo the board shows while "
                "it starts, whichever firmware you picked. The preview shows "
                "exactly what the board will show."
            ),
            points=(
                tr(
                    "PNG, JPEG or any other picture this system opens. It is fitted "
                    "onto the board's black 672 × 378 screen and turned into the "
                    "JPEG the BIOS reads."
                ),
                tr("Size sets how much of the screen it fills. Remove goes back to the firmware's own logo."),
                tr(
                    "Nothing changes until the USB is prepared. Then the logo goes "
                    "into the chosen firmware, which is read back and compared with "
                    "the published one: only the logo may differ."
                ),
                tr("Tested on real boards with P2.00, P3.00, P5.00 and MeiMeiDXE v3."),
            ),
        ),
        TourStop(
            page="firmware",
            anchor=_attribute("firmware_page", "usb_panel"),
            title=tr("The USB drive finds itself"),
            body=tr(
                "Plug a USB drive of 1 GB or more into any port and it appears "
                "here within a couple of seconds; pull it out and it goes. With "
                "a single usable drive, it is chosen for you."
            ),
            points=(
                tr(
                    "Drives that hold part of this system, are write-protected or "
                    "are smaller than 1 GB are listed greyed out, with the reason."
                ),
                tr(
                    "Everything on the chosen drive is erased. The name, size and "
                    "volumes shown are what will be lost."
                ),
                tr(
                    "Right before erasing, the drive is checked again: if another "
                    "one was plugged in its place, nothing is touched."
                ),
            ),
        ),
        TourStop(
            page="firmware",
            anchor=_attribute("firmware_page", "prepare_panel"),
            title=tr("Prepare USB, then flash on the board"),
            body=tr(
                "Prepare USB downloads the files, checks each one, erases and "
                "formats the drive, copies the kit and reads it all back. Then, "
                "on the BC-250:"
            ),
            points=(
                tr(
                    "Switch the BC-250 off and unplug its SSD and any other drive, "
                    "so the only thing it can start from is the USB."
                ),
                tr(
                    "Plug the USB in and switch the board on. It starts the UEFI "
                    "shell and shows the kit's menu by itself."
                ),
                tr(
                    "Type flash and press Enter. The BIOS the board runs now is "
                    "saved to the USB first, and nothing is flashed without that "
                    "backup."
                ),
                tr(
                    "Leave it alone until it says it has finished. Switching off "
                    "while the flash tool runs can leave the board unable to start."
                ),
                tr(AFTER_FLASH_WARNING),
                tr(
                    "Plug your drives back in and start as usual. Keep the USB: "
                    "your previous BIOS is saved on it, and restore puts it back."
                ),
            ),
            ordered=True,
            footnote=tr(
                "If the menu does not appear, type fs0: and press Enter, then cd "
                "BC250 and then menu."
            ),
        ),
        # -------------------------------------------------------- settings
        TourStop(
            page="dashboard",
            anchor=_rail("settings"),
            title=tr("Settings, and that is everything"),
            body=tr(
                "Settings holds the rest: language, light or dark theme and "
                "accent colour, compact or comfortable density, the terminal, "
                "the background daemon that keeps fans and alerts running, "
                "the controller options, and the button that plays this tour "
                "again. Anything that needs a password runs in the terminal "
                "inside this window."
            ),
        ),
    )
