"""Compatibility as rows: one line per component, what it is in Details, what it offers under Enter.

Every row reads the tools snapshot the desktop's cards read and calls the
service method the desktop's buttons call. Texts are the desktop's own.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from bc250cc.application.preparation import toolkit_rows
from bc250cc.application.preparation.steamos_providers import ALTERNATIVE_ACTIONS
from bc250cc.application.system import accessory_rows, kernel_option_rows

from ..content import Choice, Info, Panel
from ..i18n import tr, tr_format
from .base import guarded

TONES = {"green": "ok", "orange": "warn", "red": "bad", "blue": "accent", "gray": "dim"}
#: (key, title, what it is) of each accessory; the sleep row has its own function.
SENSORS = (
    ("apu_telemetry", "Power delivery readings (I2C mod)",
     "Author: onlinermm, BC250-Telemetry. A service that reads the voltage regulators over the I2C wires soldered to "
     "the board: input voltage, rails and VRM temperatures. Needs the physical modification."),
    ("vrm_sensor", "Power delivery readings (kernel driver)",
     "Author: Liam McLoughlin (Hexxeh), bc250-vrm-dkms. Reads the voltage regulator through the fan chip, without the "
     "I2C wires: input voltage, CPU and GPU rails and VRM temperatures. Builds with DKMS on Arch, CachyOS and Manjaro."),
    ("vram_sensor", "VRAM temperature (kernel driver)",
     "Author: Liam McLoughlin (Hexxeh), bc250-memory-dkms. Reads the eight GDDR6 chips through the SMU and shows them "
     "as a normal sensor in Control Center, sensors and MangoHud. Builds with DKMS on Arch, CachyOS and Manjaro, and "
     "follows kernel updates."),
)
ACCESSORIES = (
    ("hdmi_ac3", "HDMI audio · Dolby Digital 5.1",
     "Encodes 5.1 sound to AC-3 in real time for receivers and soundbars that only take Dolby Digital over HDMI, with "
     "PipeWire's own AC-3 profile and ALSA's a52 encoder."),
    ("hdmi_cec", "TV control · HDMI-CEC",
     "Valve's cecd, the CEC daemon SteamOS uses: the TV turns on when the BC-250 wakes and sleeps when it suspends, and "
     "its remote works as input. Needs a DisplayPort-to-HDMI adapter that passes CEC."),
    ("thermalright", "Thermalright cooler display",
     "TRCC Linux drives the LCD on Thermalright coolers. After you save a theme once, it plays in Desktop and Game Mode "
     "without any window open."),
    ("corsair", "Corsair fans and RGB",
     "OpenLinkHub replaces iCUE on Linux for Corsair hubs, AIOs, fans and lighting, with its own control panel. The "
     "NexGen3D Steam Machine PRO case uses it for its Commander Duo."),
)
SLEEP_DETAIL = ("Author: superkeka. Makes the system's own Suspend work, in memory (S3) or on disk (hibernation). "
                "Experimental: its author has only tested it on SteamOS.")
LOCK_DETAIL = ("pacman keeps a lock file while it changes packages. An update that was cut off (power loss, a closed "
               "terminal) leaves it behind, and every later install fails with \"unable to lock database\".")
LOCK_QUESTION = ("No package manager is running, so the lock was left behind by an interrupted update. This removes it "
                 "with your password in the terminal. It checks again first and stops, removing nothing, if a package "
                 "manager has started meanwhile.")
HEADERS_DETAIL = ("Drivers built with DKMS (fans, power and memory sensors) need the headers of the running kernel. A "
                  "partial update can leave them for another version, and those drivers stop loading at the next restart.")
HEADERS_QUESTION = ("The running kernel and its headers do not match, so drivers built with DKMS (fans, sensors) stop "
                    "loading after the next restart. This installs the right headers with your password in the "
                    "terminal; when your distribution no longer has them, it updates the kernel and its headers "
                    "together. Then it rebuilds the DKMS drivers. If the kernel was updated, restart the computer "
                    "afterwards.")
DIRECTMESH_DETAIL = ("Mesh shaders for DX12 Ultimate games on the BC-250. Development build: a game can hang the GPU.")
#: VA-API states as the desktop's card words them: (status, tone, sentence).
VAAPI = {
    "active": ("Active", "ok", "Programs that use VA-API encode and decode with it. For streaming while you play, "
               "choose H.264."),
    "relogin-required": ("Log out to apply", "warn",
                         "Installed. Log out and back in (or restart) so programs pick it up."),
    "outdated": ("Update available", "warn",
                 "A newer reviewed version is available. Install builds and switches to it."),
    "invalid": ("Incomplete", "warn", "The files that switch it on are there but the driver is missing. Install it "
                "again or remove it."),
    "managed-elsewhere": ("Managed externally", "accent", "Another installer already switches this driver on (its own "
                          "scripts or the SteamOS toolkit). Remove that one first to manage it here."),
    "hardware-vcn": ("Not needed", "dim", "The kernel's experimental hardware video block is on (amdgpu.bc250_vcn=1), "
                     "and radeonsi drives it."),
}
VAAPI_DETAIL = ("The BC-250 has no working video block, so programs fall back to software video. This driver encodes "
                "H.264 on the GPU and HEVC mostly on the CPU, and decodes both, for Sunshine, OBS, Steam Remote Play, "
                "ffmpeg and browsers.")


@dataclass
class Action:
    """One thing a row can do. ``question`` "" runs at once: it only reads, or only shows something."""

    label: str
    work: Callable[[], Any] | None = None
    question: str = ""
    danger: bool = False
    show: Callable[[Any], None] | None = None  # instead of running: a text, a picker
    confirm: bool = True


def component(title: str, status: str, tone: str, detail: str, actions: list[Action], *, risk: str = "", undo: str = "",
              blocked: str = "") -> Choice:
    """A component's row. Enter offers its actions; with none, Details says why."""
    def perform(ui, action: Action) -> None:
        if action.show is not None:
            action.show(ui)
        elif not action.confirm or ui.confirm(f"{title} · {action.label}" + (f": {action.question}" if action.question else ""),
                                              danger=action.danger):
            guarded(ui, f"{title} · {action.label}", action.work)

    def open_row(ui) -> None:
        if not actions:
            ui.notify(blocked or status, "warn" if blocked else "")
            return
        picked = 0 if len(actions) == 1 else ui.choose(title, [(i, action.label) for i, action in enumerate(actions)])
        if picked is not None:
            perform(ui, actions[picked])

    return Choice(f"{title} ›" if actions else title, open_row, badge=status, badge_tone=tone,
                  tone="" if actions else "dim", info=Info(detail, risk, undo, blocked))


def more(title: str, detail: str, actions: list[Action]) -> Choice:
    return component(title, "", "dim", detail, actions)


# -- System -----------------------------------------------------------------------------------------


def pacman_lock(service, state: dict) -> Choice | None:
    kind = state.get("state")
    words = {"stale": ("Stuck", "warn"), "in-use": ("In use", "dim"), "free": ("Not locked", "dim")}
    if kind not in words:
        return None
    holders = ", ".join(state.get("holders") or ())
    detail = tr(LOCK_DETAIL) + (" " + tr_format("Running now: {names}", names=holders) if holders else "")
    actions = [Action(tr("Release lock"), service.liberar_bloqueo_pacman, tr(LOCK_QUESTION))] if kind == "stale" else []
    status, tone = words[kind]
    return component(tr("Package manager lock · pacman"), tr(status), tone, detail, actions)


def kernel_headers(service, state: dict) -> Choice | None:
    kind = state.get("state")
    words = {"mismatch": ("Mismatched", "warn"), "missing": ("Missing", "warn"),
             "modules-missing": ("Drivers not built", "warn"), "reboot-pending": ("Restart needed", "warn"),
             "ok": ("Ready", "ok")}
    if kind not in words:
        return None
    said = {
        "mismatch": lambda: tr_format("Running kernel: {kernel}. Installed headers: {headers}.",
                                      kernel=state.get("kernel_package") or state.get("kernel"), headers=state.get("headers")),
        "missing": lambda: tr_format("No headers for the running kernel {kernel}.", kernel=state.get("kernel")),
        "modules-missing": lambda: tr_format("Not built for this kernel: {names}.", names=", ".join(state.get("modules") or ())),
        "reboot-pending": lambda: tr("The kernel was updated. Restart the computer to use it."),
    }.get(kind, str)()
    actions = [Action(tr("Repair"), service.reparar_cabeceras_kernel, tr(HEADERS_QUESTION))] \
        if kind in ("mismatch", "missing", "modules-missing") else []
    status, tone = words[kind]
    return component(tr("Kernel headers · DKMS"), tr(status), tone, " ".join(filter(None, (tr(HEADERS_DETAIL), said))), actions)


def real_sleep(service, info: dict) -> Choice | None:
    state = info.get("state")
    words = {"installed": ("Installed", "accent"), "broken": ("Incomplete", "warn"), "not-installed": ("Not installed", "dim")}
    if state not in words:
        return None
    reason = str(info.get("reason") or "") if state == "not-installed" else ""
    hibernate = info.get("mode") == "hibernate"
    note = ("Hibernation needs a swap file or partition on the disk; there is only compressed memory now."
            if info.get("needs_swap") and (hibernate or not info.get("s3_supported")) else
            "Only S3 (memory) here: this system's initramfs does not bring a hibernated session back."
            if info.get("hibernate_ready") is False else "")

    def manage(action):
        return lambda: service.manage_accessory("real_sleep", action)

    actions = []
    if state != "installed" and not reason:
        actions.append(Action(tr("Install"), manage("install"), "\n\n".join(
            (tr(accessory_rows.REAL_SLEEP_INSTALL), tr(accessory_rows.REAL_SLEEP_POWER_OFF))), True))
    if state == "installed":
        if info.get("s3_supported") if hibernate else info.get("hibernate_ready") is not False:
            actions.append(Action(tr("Use S3 (memory)" if hibernate else "Use hibernation"),
                                  manage("mode-s3" if hibernate else "mode-hibernate")))
        wake = info.get("power_off") == "wake"
        actions.append(Action(tr("Normal power off" if wake else "Turn on with a gamepad"),
                              manage("poweroff-default" if wake else "poweroff-wake")))
    if state in ("installed", "broken"):
        actions.append(Action(tr("Remove"), manage("remove"), tr(accessory_rows.REAL_SLEEP_REMOVE), True))
    status, tone = words[state]
    return component("Sleep · bc250-sleep", tr(status), tone, " ".join(filter(None, (tr(SLEEP_DETAIL), tr(note)))),
                     actions, risk=tr(accessory_rows.REAL_SLEEP_INSTALL), undo=tr(accessory_rows.REAL_SLEEP_REMOVE),
                     blocked=tr(reason))


def accessory(service, key: str, title: str, detail: str, info: dict) -> Choice | None:
    state = str(info.get("state") or "")
    if state not in accessory_rows.STATES:
        return None
    status, tone, install = accessory_rows.STATES[state]
    note = accessory_rows.NOTES.get((key, state), "")
    blocked = tr(str(info.get("blocked_reason") or note)) if state == "unsupported" else ""
    if state == "error":
        note = tr_format("Control Center could not check this on your system ({error}). Send a report from "
                         "Settings › Support so it can be fixed.", error=str(info.get("error") or "unknown error"))
    installed = state in ("update-available", "relogin-required", "installed", "active")
    actions = []
    if install:
        work = (lambda: service.gestionar_apu_telemetry("install")) if key == "apu_telemetry" else \
            (lambda: service.manage_accessory(key, "install"))
        actions.append(Action(tr(install), work, ""))
    if key == "hdmi_cec" and (installed or state == "managed-elsewhere"):
        actions.append(Action(tr("Open TV control"), show=lambda ui: tv_control(ui, service)))
    if installed:
        work = (lambda: service.gestionar_apu_telemetry("uninstall")) if key == "apu_telemetry" else \
            (lambda: service.manage_accessory(key, "remove"))
        actions.append(Action(tr("Remove"), work, tr(accessory_rows.removal_text(key)), True))
    return component(tr(title), tr(status), TONES.get(tone, "dim"),
                     " ".join(filter(None, (tr(detail), "" if blocked else tr(note)))), actions, blocked=blocked)


#: The CEC actions of the TV remote that make sense without its picture.
TV_ACTIONS = (("tv-on", "Turn the TV on"), ("tv-off", "Turn the TV off"), ("switch", "Use this input"),
              ("amp-on", "Wake the receiver"), ("volume-up", "Volume up"), ("volume-down", "Volume down"), ("mute", "Mute"))


def tv_control(ui, service) -> None:
    ok, status = ui.run(tr("TV control · HDMI-CEC"), service.tv_control_status)
    if not ok or not isinstance(status, dict):
        return
    picked = ui.choose(tr("TV control · HDMI-CEC"), [(key, tr(label)) for key, label in TV_ACTIONS])
    if picked is not None:
        guarded(ui, tr("TV control · HDMI-CEC"), lambda: service.tv_control_action(picked))


# -- Kernel boot options ----------------------------------------------------------------------------


def kernel_options(service, setup: dict) -> Panel | None:
    state = setup.get("kernel_options") or {}
    if not (setup.get("helper_available") and state.get("available")):
        return None
    arguments = state.get("arguments") or {}
    allowed = set(state.get("allowed") or (row[0] for row in kernel_option_rows.ROWS))
    managed = {key for key, value in arguments.items() if (value or {}).get("managed")}
    rows, missing = [], []
    for option, title, add, restore in kernel_option_rows.ROWS:
        item = arguments.get(option) or {}
        parameter = option in kernel_option_rows.PARAMETER_OPTIONS
        supported = ((state.get("parameters") or {}).get(option) or {}).get("supported") if parameter else \
            (state.get("cu_unlock") or {}).get("supported") if option == kernel_option_rows.CU_UNLOCK_OPTION else True
        if option not in allowed:
            continue  # another boot loader's or another distribution's option
        offered = bool(supported or item.get("managed") or item.get("configured") or item.get("external"))
        status, tone = (("Set outside Control Center", "accent") if item.get("external") else
                        ("Reboot required", "warn") if bool(item.get("configured")) != bool(item.get("active")) else
                        ("Enabled", "ok") if item.get("active") else ("Disabled", "dim") if offered else ("Not available here", "dim"))
        on = option in managed
        wanted = tuple(sorted(managed - {option} if on else managed | {option}))
        name, text, button, weight = kernel_option_rows.CONFIRMATIONS.get(option, kernel_option_rows.CONFIRMATIONS["nosmt"])
        question = "" if on else tr(text)
        actions = [] if item.get("external") or not offered else [Action(tr(restore if on else add), lambda w=wanted: service.gestionar_opciones_kernel(w),
                                                          question, not on and weight == "red", confirm=not on)]
        row = component(tr(title), tr(status), tone, f"{tr('Kernel argument')}: {option}\n\n{tr(text)}", actions, undo=tr(restore),
                        blocked=tr("Set outside Control Center") if item.get("external") else
                        "" if offered else tr("Not available here"))
        (rows if offered else missing).append(row)
    smt = state.get("smt") or {}
    if smt.get("supported") and "nosmt" in allowed:
        now = str(smt.get("control") or "") == "on"
        rows.append(component(tr("SMT right now"), tr("Enabled" if now else "Disabled"), "ok" if now else "warn",
                              tr("The CPU runs one thread per core until you turn it back on or restart: some games run "
                                 "smoother, others slower. Nothing is saved: the next boot starts as the kernel boot "
                                 "options say."),
                              [Action(tr("Turn SMT off now" if now else "Turn SMT on now"),
                                      lambda: service.gestionar_smt_vivo("off" if now else "on"))]))
    return Panel(tr("Kernel boot options"), rows + missing, badge=str(state.get("backend") or "")) if rows or missing else None


# -- Graphics ---------------------------------------------------------------------------------------


def directmesh(service, state: dict) -> Choice | None:
    if not state:
        return None
    supported, installed = bool(state.get("supported")), bool(state.get("installed"))
    newer = state.get("newer") or {}
    status, tone = (("Unsupported", "dim") if not supported else ("Update available", "warn") if newer and installed else
                    ("Installed", "ok") if installed else ("Not installed", "dim"))
    run = service.gestionar_directmesh
    tag = str(state.get("selected_tag") or "")

    def version(ui) -> None:
        names = [(r["tag"], r["version"] + ("  " + tr("Recommended") if r.get("default") else "")) for r in state.get("releases") or ()]
        picked = ui.choose(tr("Choose version"), names + [("", tr("Check for new DirectMesh releases"))])
        if picked == "":
            guarded(ui, "DirectMesh", lambda: run("releases"))
        elif picked:
            guarded(ui, "DirectMesh", lambda: run(f"select:{picked}"))

    actions = []
    if supported:
        label = tag.removeprefix("directmesh-v")
        actions.append(Action(tr("Reinstall") if installed else tr_format("Install {name}", name=label) if label else tr("Install"),
                              lambda: run(f"upgrade:{tag}" if tag else "install"), tr(DIRECTMESH_DETAIL), True))
        actions.append(Action(tr("Choose version"), show=version))
    if installed:
        actions.append(Action(tr("Steam launch option"), show=lambda ui: ui.show_text(
            tr("Steam launch option"), str(state.get("launch_option") or ""))))
        if supported:
            actions.append(Action(tr("Check mesh shaders"), lambda: run("check"), confirm=False))
        actions.append(Action(tr("Remove"), lambda: run("uninstall"), "", True))
    version_text = str(state.get("installed_version") or "")
    return component("DirectMesh" + (f" {version_text}" if version_text else ""), tr(status), tone, tr(DIRECTMESH_DETAIL),
                     actions, risk=tr("Bazzite · container · experimental") if state.get("experimental") else "",
                     blocked="" if supported else tr(str(state.get("reason") or "")))


def vaapi(service, state: dict) -> Choice:
    kind, supported = str(state.get("state") or "not-installed"), bool(state.get("supported", True))
    status, tone, sentence = VAAPI.get(kind, ("Not installed" if supported else "Not compatible", "dim", VAAPI_DETAIL))
    installed = bool(state.get("installed"))
    title = tr("Hardware video · VA-API")

    def manage(action):
        return lambda: service.gestionar_vaapi(action)

    actions = []
    if supported and kind not in ("managed-elsewhere", "hardware-vcn", "active", "relogin-required"):
        actions.append(Action(tr("Update" if kind == "outdated" else "Reinstall" if kind == "invalid" else "Install"), manage("install")))
    if installed and kind != "invalid":
        actions.append(Action(tr("Test"), manage("test"), confirm=False))
    flatpak = state.get("flatpak") or {}
    if installed and kind not in ("invalid", "managed-elsewhere") and flatpak.get("available") \
            and (not flatpak.get("applied") or not state.get("alias", True)):
        actions.append(Action(tr("Allow Flatpak apps"), manage("flatpak")))
    driver32 = str((state.get("driver32") or {}).get("state") or "unsupported")
    if installed and kind not in ("invalid", "managed-elsewhere") and driver32 in ("not-installed", "needs-libs"):
        actions.append(Action(tr("Repair 32-bit driver" if driver32 == "needs-libs" else "Add 32-bit driver"), manage("install32")))
    if installed:
        actions.append(Action(tr("Remove"), manage("uninstall"), "", True))
    return component(title, tr(status), tone, tr(sentence), actions,
                     blocked="" if supported else tr(str(state.get("blocked_reason") or "")))


# -- SteamOS ----------------------------------------------------------------------------------------


def read_only_mode(service, state: dict) -> Choice | None:
    if not state.get("available"):
        return None
    mode, session = str(state.get("state") or "unknown"), state.get("toolkit_session") or {}
    running = bool(session.get("running"))
    status, tone = (("In use", "accent") if running else ("Interrupted", "warn") if session.get("restore_pending") else
                    {"enabled": ("Protected", "ok"), "disabled": ("Writable", "warn")}.get(mode, ("Unknown", "dim")))

    def manage(action):
        return lambda: service.gestionar_solo_lectura_steamos(action)

    actions = [Action(tr("Status"), manage("status"), confirm=False)]
    if not running:
        actions += [Action(tr("Disable"), manage("disable"), "", True), Action(tr("Enable"), manage("enable")),
                    Action(tr("Free /var space"), manage("free-var"))]
    return component(tr("SteamOS read-only mode"), tr(status), tone,
                     "", actions)


def real_toolkit(service, tools: dict, session: dict) -> list[Panel]:
    state = tools.get("steamos_real_toolkit") or {}
    presented = toolkit_rows.toolkit_presentation(state)
    running = str(session.get("action") or "toolkit") if session.get("running") else ""
    groups: dict[str, list[Choice]] = {}
    for category, names, descriptions, keys in toolkit_rows.TOOLS:
        note = presented.notes.get(keys[0])
        detail = " ".join(tr(part) for part in ((note,) if isinstance(note, str) else note or (descriptions[0],)))
        status = toolkit_rows.installed_status(keys[0], state)
        status = ("", "dim") if status is None else (tr(status[0]), TONES.get(status[1], "dim"))
        owned = any(key in presented.protected for key in keys)
        if owned:
            status = ("BC250 Control Center", "accent")
        if keys[0] == "verify" and state.get("lost_after_update"):
            status = (tr("Incomplete"), "warn")
        actions = []
        for index, key in enumerate(keys):
            if key in presented.blocked or (key == "put-back" and not state.get("lost_after_update")):
                continue
            label = tr(toolkit_rows.LABELS[key][0]) if index or len(keys) == 1 else tr(toolkit_rows.primary_label(key))
            actions.append(Action(label, lambda k=key: service.gestionar_real_toolkit_steamos(k), "",
                                  toolkit_rows.is_removal(key), confirm=not toolkit_rows.reads_only(key)))
        blocked = ""
        if running:
            shown = toolkit_rows.LABELS.get(running)
            blocked, actions = tr_format("Another toolkit action is running: {name}", name=tr(shown[0]) if shown else running), []
        elif not actions and owned:
            blocked = "BC250 Control Center"
        groups.setdefault(category, []).append(component(tr(names[0]), *status, detail, actions, blocked=blocked))
    titles = {"toolkit": "SteamOS toolkit", "system": "System", "graphics": "Kernel and graphics", "video": "Video",
              "audio": "Audio and TV", "drivers": "Controllers and wireless"}
    return [Panel(tr(titles[key]), rows, badge="rpf16rj") for key, rows in groups.items()]


def alternative(service, tools: dict) -> Panel:
    rows = []
    for _category, names, descriptions, keys in toolkit_rows.ALTERNATIVE_TOOLS:
        rows.append(component(tr(names[0]), "", "dim", tr(descriptions[0]), [
            Action(tr(ALTERNATIVE_ACTIONS[key][0]), lambda k=key: service.gestionar_alternativa_steamos(k), "",
                   toolkit_rows.is_removal(key), confirm=not toolkit_rows.reads_only(key)) for key in keys]))
    return Panel(tr("Kernel and graphics"), rows, badge="keyboardspecialist")
