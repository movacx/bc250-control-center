"""One row per game, with what HelixSR and FSR 4 each do in it and offer. Qt-free."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from ..i18n import tr, tr_format


def _mapping(value) -> Mapping:
    return value if isinstance(value, Mapping) else {}


_FSR4_GAME_COPY = {
    "ready": ("Ready", "green",
              "In the game choose DLSS, FSR or XeSS, then press Insert to open OptiScaler."),
    "needs-launch-option": ("Launch option missing", "orange",
                            "OptiScaler is installed, but Steam does not load it yet. Close Steam, then add the launch option."),
    "not-installed": ("Not installed", "gray",
                      "In the client, select this game and press Install / update selected."),
    "other-launcher": ("Launcher setting needed", "blue",
                       "Add WINEDLLOVERRIDES with {dll}=n,b in the launcher that runs this game; the guide shows where."),
    "unknown-adapter": ("Check the adapter", "orange",
                        "OptiScaler is in this game under a file name this panel does not recognise; see the guide."),
    "linked-folder": ("Linked folder", "orange",
                      "OptiScaler Client refuses folders reached through a link ({link}). Add this library again in its launcher from the real folder: {path}"),
}
_HELIXSR_GAME_COPY = {
    "installed": "In the game, choose AMD FSR as the upscaler. Remove puts the game's own file back.",
    "restored": "A game update or Steam's file check put the game's own FSR file back. Remove cleans up; add HelixSR again if you want it.",
    "available": "Add HelixSR to replace this game's FSR 3.1 upscaler. The original file is kept as a backup.",
    "missing": "The game's folder is gone: it was uninstalled or moved. Remove HelixSR forgets it here.",
}
_HELIXSR_SCALER_COPY = {
    "installed": "In the game choose DLSS; Insert opens HelixSR Scaler's menu. Frame generation runs in games with DLSS Frame Generation: turn it on here, then in the game. Remove puts every file it replaced back.",
    "restored": "A game update or Steam's file check changed HelixSR Scaler's files. Remove cleans up; add it again if you want it.",
    "available": "HelixSR Scaler is HelixSR inside its own OptiScaler: the game's DLSS option runs HelixSR, with DLSS frame generation if you turn it on. Not for online games or games with anti-cheat.",
    "missing": "The game's folder is gone: it was uninstalled or moved. Remove forgets it here.",
    "outdated": "This game has HelixSR Scaler {version}. Update HelixSR gives it the installed release and keeps {version} to go back to.",
}
_HELIXSR_NETWORK_MISSING_COPY = (
    "HelixSR is in this game but its network files are not, so it only does a simple upscale. Update HelixSR copies them back."
)
_HELIXSR_OPTISCALER_COPY = {
    "installed": "In the game choose DLSS, FSR or XeSS, press Insert and pick FSR HelixSR in OptiScaler's upscaler menu. Remove puts OptiScaler's settings back.",
    "restored": "OptiScaler's settings no longer point to HelixSR, usually after OptiScaler Client updated or restored this game. Remove cleans up HelixSR's folder.",
    "available": "OptiScaler is in this game, so HelixSR can upscale through it, even when the game only offers DLSS or XeSS.",
    "missing": "The game's folder is gone: it was uninstalled or moved. Remove HelixSR forgets it here.",
}
_FSR4_UNDO_COPY = {
    "intact": "OptiScaler Client installed these files. Remove OptiScaler, keep a backup moves them into a backup folder and puts back any game file they replaced; Put OptiScaler back returns them.",
    "partial": "Some of OptiScaler's files were deleted by hand. Remove OptiScaler, keep a backup moves the rest into a backup folder and clears the client's record.",
    "removed": "OptiScaler's files are gone, but OptiScaler Client still records them, so it refuses to install, update or restore this game. Clear the client's record to start again; the record is kept in a backup folder.",
    "changed": "Some of OptiScaler's files changed after the client installed them (a game update or a hand edit). Nothing was touched.",
    "helixsr": "HelixSR uses this game's OptiScaler. Remove HelixSR from it first.",
    "pending": "OptiScaler Client was interrupted in this game. Open the client and use Restore / recover selected first.",
    "backup-broken": "OptiScaler Client's copy of a game file changed, so the game's own file could not come back. Nothing was touched.",
    "unsupported": "This installation record is not one Control Center can read. Nothing was touched.",
    "interrupted": "Control Center was interrupted while taking OptiScaler out of this game. Put OptiScaler back returns the files it had already moved; then try again.",
    "linked": "OptiScaler Client recorded this game through a linked folder ({link}), so its own Restore cannot undo it. This panel can.",
    "backup": "Control Center took OptiScaler out of this game on {date}. Put OptiScaler back returns it as it was. The backup is in {path}.",
}
_FSR4_MATRIX_COPY = {
    "ready": ("Active", "green"),
    "needs-launch-option": ("Steam option missing", "orange"),
    "not-installed": ("Not installed", ""),
    "other-launcher": ("Set up in launcher", ""),
    "unknown-adapter": ("Check the adapter", "orange"),
    "linked-folder": ("Linked folder", "orange"),
}


#: FSR4 states in which OptiScaler (OptiScaler Client's) is in the game.
_OPTISCALER_IN_GAME = frozenset({"needs-launch-option", "ready", "other-launcher", "unknown-adapter"})


#: OptiScaler Client's record per state, when the game table has no FSR4
#: reading of its own (the client is not installed): (text, tone).
_FSR4_RECORD_CELL = {
    "intact": ("OptiScaler installed", ""),
    "partial": ("OptiScaler installed", ""),
    "removed": ("Record left", "orange"),
    "changed": ("Check the files", "orange"),
    "helixsr": ("OptiScaler installed", ""),
    "pending": ("Interrupted", "orange"),
    "interrupted": ("Interrupted", "orange"),
    "backup-broken": ("Check the files", "orange"),
    "unsupported": ("Check the files", "orange"),
}


def _undo_rows(row_for, installations: Iterable[Mapping], backups: Iterable[Mapping]) -> None:
    """What OptiScaler Client recorded per game, and Control Center's backups.

    Any game the client recorded gets "Remove OptiScaler, keep a backup",
    whichever way it was added; a game whose files are already gone gets
    "Clear the client's record", which is what keeps the client from
    installing it again. The newest backup of a game the client no longer
    records gets "Put OptiScaler back".
    """
    copy = _FSR4_UNDO_COPY
    recorded: set[str] = set()
    for record in installations:
        state = str(record.get("state") or "unsupported")
        key = str(record.get("key") or "")
        if state == "missing" or not key:
            continue  # the game is gone; nothing in the table to act on
        appid = str(record.get("appid") or "")
        row = row_for(appid, str(record.get("name") or appid))
        recorded.add(appid or row["name"])
        row["fsr4_recorded"] = state != "removed"
        if state == "interrupted":
            # Control Center's own removal was cut short: its backup goes back first.
            action = ("Put OptiScaler back", f"fsr4_backup_restore:{record.get('backup')}", True)
        else:
            label = "Clear the client's record" if state == "removed" else "Remove OptiScaler, keep a backup"
            action = (label, f"fsr4_undo:{key}", bool(record.get("removable")))
        note = tr(copy.get(state, copy["unsupported"]))
        linked = str(record.get("linked_path") or "")
        if linked and record.get("removable"):
            note = f"{tr_format(copy['linked'], link=linked)} {note}"
        cell = row["fsr4"]
        if cell is None or state in {"removed", "interrupted"}:
            text, tone = _FSR4_RECORD_CELL.get(state, _FSR4_RECORD_CELL["unsupported"])
            row["fsr4"] = (text, tone, note, (*(cell[3] if cell else ()), action))
        else:
            row["fsr4"] = (cell[0], cell[1], f"{cell[2]} {note}", (*cell[3], action))
    for backup in backups:
        appid = str(backup.get("appid") or "")
        name = str(backup.get("name") or appid)
        # An interrupted one too: cut short at the very end, it holds the record.
        if (appid or name) in recorded or backup.get("state") not in {"ready", "interrupted"}:
            continue
        recorded.add(appid or name)
        row = row_for(appid, name)
        note = tr_format(copy["backup"], date=str(backup.get("created") or "")[:10],
                         path=str(backup.get("path") or ""))
        action = ("Put OptiScaler back", f"fsr4_backup_restore:{backup.get('id')}", True)
        cell = row["fsr4"]
        if cell is None:
            row["fsr4"] = ("In a backup", "", note, (action,))
        else:
            row["fsr4"] = (cell[0], cell[1], f"{cell[2]} {note}", (*cell[3], action))


#: HelixSR 3's two ways into a game, as the game matrix names them.
_HELIXSR3_WAYS = {"scaler": "HelixSR Scaler (DLSS)", "fsr": "HLX FSR 4"}
_HELIXSR3_ADD = {"scaler": "Add HelixSR Scaler", "fsr": "Add HLX FSR 4"}
_HELIXSR3_SWITCH = {"scaler": "Switch to HelixSR Scaler", "fsr": "Switch to HLX FSR 4"}
_HELIXSR3_COPY = {
    "scaler": "In the game choose DLSS; Insert opens HelixSR Scaler's menu, where HLX FSR 4, AMD FSR and XeSS can be picked too. Remove puts every file it replaced back.",
    "fsr": "In the game choose AMD FSR: HLX FSR 4 takes the place of the game's FSR 3.1. Remove puts the game's own file back.",
    "available": "Add HelixSR Scaler puts OptiScaler with HelixSR next to the game: its DLSS option runs HelixSR's DLSS network, and DLSS Frame Generation can run HelixSR's frame generation. Add HLX FSR 4 replaces the game's FSR 3.1 with HelixSR's FSR 4. Not for online games.",
    "anticheat": "This game has anti-cheat ({names}). Changing its files can get an online account banned: use it offline only.",
    "fg_on": "HelixSR's frame generation is on: turn on DLSS Frame Generation in the game; its multiplier and pacing are in HelixSR settings.",
    "fg_off": "This game has DLSS Frame Generation: Turn on frame generation lets HelixSR generate the frames (2x to 6x).",
    "fg_other": "This game's OptiScaler.ini picks another frame generation; HelixSR's is left alone.",
    "network": "Build the DLSS network first (on the HelixSR card). HLX FSR 4 needs no build.",
    "legacy": "This game has HelixSR {version}, put in by an earlier release. Update gives it HelixSR 3: the old files are removed and the game's own ones put back first.",
    "outdated": "This game has HelixSR {version}. Update gives it the installed release and keeps {version} to go back to.",
    "switch": "Switching to the other way removes this one first; the version kept to go back to is dropped.",
    "other": "HelixSR's own setup or HelixSR Desktop put it in this game: update it there. Remove works from here too.",
}


def _bridge_cells(row_for, bridge_games: Iterable[Mapping]) -> None:
    """HelixSR 3's cell of each game, from the bridge's view of it."""
    for game in bridge_games:
        appid = str(game.get("appid") or "")
        name = str(game.get("name") or appid)
        if not appid and not name:
            continue
        row = row_for(appid, name)
        if game.get("folder") and not appid.isdigit():
            # Added by hand (a Folder_ key), or a Steam shortcut: where it is.
            row["folder"] = str(game["folder"])
            row["folder_detail"] = "Outside Steam"
        ways = [way for way in (game.get("ways") or ()) if way in _HELIXSR3_WAYS]
        recommended = str(game.get("recommended") or "")
        ways.sort(key=lambda way: way != recommended)
        ready = _mapping(game.get("way_ready"))
        installed = str(game.get("installed_way") or "")
        version = str(game.get("version") or "")
        key = appid or name
        if game.get("missing"):
            # The folder is gone: there is nothing to add or put back, only a
            # row to take off the list (R-2e7f6048).
            row["helixsr"] = (
                "Not on disk", "gray",
                tr("The game's folder is gone. Removing it from the list changes nothing on disk."),
                (("Remove from list", f"helixsr_bridge_remove:{key}", True),),
            )
            continue
        remove = ("Remove HelixSR", f"helixsr_bridge_remove:{key}", True)
        if game.get("managed_by") == "app-2x":
            # The same way HelixSR 2 gave it (Update all does the same).
            way = str(game.get("legacy_way") or recommended or (ways[0] if ways else ""))
            actions = [("Update HelixSR", f"helixsr_bridge_install:{key}:{way}", bool(way and ready.get(way)))] if way else []
            row["helixsr"] = (
                "Update available", "orange",
                tr_format(_HELIXSR3_COPY["legacy"], version=version or "2"),
                (*actions, remove),
            )
            continue
        if installed in _HELIXSR3_WAYS and game.get("managed_by") == "other":
            # HelixSR's own setup or HelixSR Desktop put it in: shown, and
            # removable through the bridge, but managed where it came from.
            row["helixsr"] = (
                _HELIXSR3_WAYS[installed], "green",
                f"{tr(_HELIXSR3_COPY[installed])} {tr(_HELIXSR3_COPY['other'])}", (remove,),
            )
            continue
        anticheat = [str(item) for item in game.get("anticheat") or () if item]
        warning = f" {tr_format(_HELIXSR3_COPY['anticheat'], names=', '.join(anticheat))}" if anticheat else ""
        if installed in _HELIXSR3_WAYS:
            actions: list[tuple[str, str, bool]] = []
            text, tone = _HELIXSR3_WAYS[installed], "green"
            copy = tr(_HELIXSR3_COPY[installed]) + warning
            if installed == "scaler" and game.get("frame_generation"):
                text = f"{_HELIXSR3_WAYS['scaler']} · FG"
                copy = f"{copy} {tr(_HELIXSR3_COPY['fg_on'])}"
                actions.append(("Turn off frame generation", f"helixsr_bridge_fg_off:{key}", True))
            elif installed == "scaler" and game.get("fg_other"):
                copy = f"{copy} {tr(_HELIXSR3_COPY['fg_other'])}"
            elif installed == "scaler" and game.get("fg_possible"):
                copy = f"{copy} {tr(_HELIXSR3_COPY['fg_off'])}"
                actions.append(("Turn on frame generation", f"helixsr_bridge_fg_on:{key}", True))
            if game.get("outdated"):
                text, tone = "Update available", "orange"
                copy = tr_format(_HELIXSR3_COPY["outdated"], version=version or "?")
                actions.append(("Update HelixSR", f"helixsr_bridge_install:{key}:{installed}", bool(ready.get(installed))))
            for other in ways:
                if other != installed:
                    actions.append((_HELIXSR3_SWITCH[other], f"helixsr_bridge_install:{key}:{other}", bool(ready.get(other))))
            if game.get("previous_version"):
                actions.append(("Go back to the previous version", f"helixsr_bridge_rollback:{key}", True))
            row["helixsr"] = (text, tone, copy, (*actions, remove))
            continue
        if not ways:
            continue
        actions = [(_HELIXSR3_ADD[way], f"helixsr_bridge_install:{key}:{way}", bool(ready.get(way))) for way in ways]
        copy = tr(_HELIXSR3_COPY["available"]) + warning
        text = ""
        if "scaler" in ways and not ready.get("scaler"):
            copy = f"{copy} {tr(_HELIXSR3_COPY['network'])}"
            # Said on the row, not only on hover: why HelixSR Scaler is greyed.
            text = "Needs the DLSS network"
        row["helixsr"] = (text, "gray" if text else "", copy, tuple(actions))


def game_matrix_rows(
    helixsr_games: list[Mapping],
    fsr4_games: list[Mapping],
    *,
    helixsr_ready: bool,
    scaler_games: Iterable[Mapping] = (),
    scaler_ready: bool = False,
    fg_ready: bool = False,
    fsr4_installations: Iterable[Mapping] = (),
    fsr4_backups: Iterable[Mapping] = (),
    bridge_games: Iterable[Mapping] | None = None,
) -> list[dict]:
    """One row per Steam game, with what HelixSR and FSR4 each do in it.

    A cell is ``(text, tone, tooltip, actions)``; ``actions`` holds
    ``(label, action, enabled)``. Rows that need the reader come first, then
    working ones, then the rest, each by name.
    """
    rows: dict[str, dict] = {}

    def row_for(appid: str, name: str) -> dict:
        key = appid or name
        row = rows.setdefault(key, {"appid": appid, "name": name, "helixsr": None, "fsr4": None})
        row["name"] = row["name"] or name
        return row

    if bridge_games is not None:
        # HelixSR 3 and newer: every game goes through upstream's bridge, one
        # entry per game; the 2.x lists below do not apply.
        _bridge_cells(row_for, bridge_games)
        # HelixSR added through an OptiScaler put in by hand is HelixSR 2's
        # own route: it keeps its row and its Remove until it is taken out.
        helixsr_games = [game for game in helixsr_games
                         if game.get("kind") == "optiscaler" and game.get("state") != "available"]
        scaler_games = ()
    by_game: dict[str, list[Mapping]] = {}
    for game in helixsr_games:
        appid = str(game.get("appid") or "")
        row = row_for(appid, str(game.get("name") or appid))
        if game.get("folder"):
            # Added by hand from outside Steam: the folder it came from.
            row["folder"] = str(game["folder"])
            row["folder_detail"] = (
                "OptiScaler added by hand" if game.get("kind") == "optiscaler" else "Outside Steam"
            )
        by_game.setdefault(appid or str(game.get("name")), []).append(game)
    for key, entries in by_game.items():
        def first(state: str, entries=entries):
            return next((g for g in entries if g.get("state") == state), None)

        appid = rows[key]["appid"]
        chosen = first("installed") or first("restored") or first("missing")
        if chosen is not None:
            optiscaler = chosen.get("kind") == "optiscaler"
            state = chosen.get("state")
            copy = (_HELIXSR_OPTISCALER_COPY if optiscaler
                    else _HELIXSR_GAME_COPY)[state]
            if state == "installed":
                text, tone = ("Active via OptiScaler" if optiscaler else "Active"), "green"
            elif state == "missing":
                text, tone = "Game not found", "orange"
            else:
                text, tone = ("OptiScaler changed" if optiscaler else "Original file back"), "orange"
            route = "opti" if optiscaler else "game"
            actions = (("Remove HelixSR", f"helixsr_{route}_remove:{appid}", True),)
            if state == "installed" and chosen.get("network_missing"):
                # Without them HelixSR only does its simple upscale; the
                # update copies the installed release's files back.
                text, tone = "Network files missing", "orange"
                copy = _HELIXSR_NETWORK_MISSING_COPY
                actions = (("Update HelixSR", f"helixsr_game_update:{appid}", helixsr_ready), *actions)
            elif state == "installed" and chosen.get("outdated"):
                # Still working with the release it was given; one click
                # brings it the one installed here, newer or picked older.
                text = "Update available" if chosen.get("older", True) else "Other version"
                tone = "orange"
                actions = (("Update HelixSR", f"helixsr_game_update:{appid}", helixsr_ready), *actions)
            rows[key]["helixsr"] = (text, tone, copy, actions)
            continue
        # Where OptiScaler is in the game, HelixSR goes through it: OptiScaler
        # loads the FidelityFX DLLs of its own folder, so a replaced game DLL
        # would never run.
        chosen = next((g for g in entries if g.get("kind") == "optiscaler"), entries[0])
        optiscaler = chosen.get("kind") == "optiscaler"
        copy = (_HELIXSR_OPTISCALER_COPY if optiscaler
                else _HELIXSR_GAME_COPY)["available"]
        route = "opti" if optiscaler else "game"
        rows[key]["helixsr"] = (
            "Via OptiScaler" if optiscaler else "", "", copy,
            (("Add HelixSR", f"helixsr_{route}_install:{appid}", helixsr_ready),),
        )
    fsr4_copy = _FSR4_MATRIX_COPY
    for game in fsr4_games:
        appid = str(game.get("appid") or "")
        row = row_for(appid, str(game.get("name") or appid))
        state = str(game.get("state") or "not-installed")
        text, tone = fsr4_copy.get(state, fsr4_copy["not-installed"])
        detail = _FSR4_GAME_COPY.get(
            state, _FSR4_GAME_COPY["not-installed"]
        )[2]
        tooltip = tr_format(
            detail,
            dll=str(game.get("adapter") or "dxgi.dll").removesuffix(".dll"),
            link=str(game.get("linked_path") or ""),
            path=str(game.get("real_path") or ""),
        )
        executable = str(game.get("suggested_executable") or "")
        if state == "not-installed" and executable:
            tooltip = f"{tooltip} {tr_format('If it asks for the executable, choose {path}.', path=executable)}"
        actions = ()
        if state == "needs-launch-option" and game.get("steam"):
            actions = (("Add FSR4 to Steam", f"fsr4_steam_option:{appid}", True),)
        row["fsr4"] = (text, tone, tooltip, actions)
        row["fsr4_state"] = state
    _undo_rows(row_for, fsr4_installations, fsr4_backups)
    scaler_copy = _HELIXSR_SCALER_COPY
    for game in scaler_games:
        appid = str(game.get("appid") or "")
        state = str(game.get("state") or "available")
        if not appid or (state == "available" and not scaler_ready):
            continue
        row = row_for(appid, str(game.get("name") or appid))
        remove = ("Remove HelixSR Scaler", f"helixsr_scaler_remove:{appid}", True)
        if state == "installed":
            actions: list[tuple[str, str, bool]] = []
            text, tone, copy = "Active via HelixSR Scaler", "green", scaler_copy["installed"]
            if game.get("outdated"):
                # Still working with the release it was given; one click
                # brings it the installed one, keeping this one to go back to.
                text, tone = ("Update available" if game.get("older", True) else "Other version"), "orange"
                copy = tr_format(scaler_copy["outdated"], version=str(game.get("version") or "?"))
                actions.append(("Update HelixSR", f"helixsr_scaler_update:{appid}", scaler_ready))
            if game.get("frame_generation"):
                actions.append(("Turn off frame generation", f"helixsr_scaler_fg_off:{appid}", True))
            elif game.get("fg_possible") is not False:
                # False: HelixSR's bridge found no DLSS Frame Generation in the
                # game, nothing to switch on. None: it could not tell, and
                # refuses on its own if not.
                actions.append(("Turn on frame generation", f"helixsr_scaler_fg_on:{appid}", fg_ready))
            if game.get("previous"):
                actions.append(("Go back to the previous version", f"helixsr_scaler_rollback:{appid}", True))
            row["helixsr"] = (text, tone, copy, (*actions, remove))
            continue
        if state in {"restored", "missing"}:
            text = "HelixSR Scaler changed" if state == "restored" else "Game not found"
            row["helixsr"] = (text, "orange", scaler_copy[state], (remove,))
            continue
        cell = row["helixsr"]
        # HelixSR is in the game another way, or OptiScaler Client's
        # OptiScaler is: a game has one of each.
        if cell and any(label.startswith("Remove") for label, _action, _enabled in cell[3]):
            continue
        if (row.get("fsr4_state") in _OPTISCALER_IN_GAME or row.get("fsr4_recorded")
                or (cell and cell[0] == "Via OptiScaler")):
            continue
        add = ("Add HelixSR Scaler", f"helixsr_scaler_install:{appid}", True)
        row["helixsr"] = (*cell[:3], (*cell[3], add)) if cell else ("", "", scaler_copy["available"], (add,))

    def rank(row: dict) -> tuple:
        tones = {cell[1] for cell in (row["helixsr"], row["fsr4"]) if cell}
        order = 0 if "orange" in tones else 1 if "green" in tones else 2
        return order, row["name"].lower()

    return sorted(rows.values(), key=rank)
