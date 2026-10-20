"""How the preparation sidebar paints a system state: set_state and the per-card renderers."""

from __future__ import annotations

from collections.abc import Mapping

from PyQt6.QtCore import (
    Qt,
)
from PyQt6.QtWidgets import (
    QBoxLayout,
)
from PyQt6.QtWidgets import QPushButton as IconButton

from ..core.feature_visibility import (
    FSR4_UI_ENABLED,
    GFX1013_FSR4_UI_ENABLED,
    HELIXSR_UI_ENABLED,
)
from ..core.gfx1013_presenter import present_gfx1013, present_radv_route
from ..i18n import tr, tr_format
from .buttons import WrappingButton as QPushButton
from .dashboard_widgets import (  # noqa: E402
    _mapping,
    game_matrix_rows,
)
from .responsive import clear_grid


class PreparationRenderMixin:
    """Methods of ``PreparationSidebar`` split out of ``dashboard_widgets``."""

    def _render_mesa(self, tools: Mapping[str, object]) -> None:
        if not hasattr(self, "mesa_card"):
            return
        mesa = _mapping(tools.get("mesa_desktop"))
        route = str(mesa.get("route") or "")
        self.mesa_card.setVisible(bool(mesa.get("offered")))
        self.mesa_card.set_status("Mesa too old for the desktop", "orange")
        if route == "release":
            self.mesa_card.detail.setText(tr(
                "The Mesa of this system does not draw the desktop on the BC-250 GPU, so windows are drawn by the CPU and feel slow, although games using Vulkan already run on the GPU. Fedora 44 ships Mesa 26.1 or newer: upgrade to it with GNOME Software, KDE Discover or dnf system-upgrade."
            ))
        elif route == "backports":
            self.mesa_card.detail.setText(tr(
                "Optional. The Mesa that Debian 13 ships does not recognize the BC-250 GPU, so the desktop is drawn by the CPU and feels slow. This installs the newer Mesa from Debian backports."
            ))
        else:
            self.mesa_card.detail.setText(tr(
                "The Mesa of this system does not draw the desktop on the BC-250 GPU, so windows are drawn by the CPU and feel slow, although games using Vulkan already run on the GPU. Mesa 26.1 or newer fixes it. This adds the kisak-mesa PPA, a third-party source, and updates Mesa from it."
            ))
        self.mesa_card.update_action(
            self.mesa_button,
            text="Install from backports" if route == "backports" else "Update Mesa",
            payload={"action": str(mesa.get("action") or "mesa_ppa_install"), "governor": ""},
            visible=route in {"ppa", "backports"},
        )

    def _render_vaapi(self, tools: Mapping[str, object]) -> None:
        if not hasattr(self, "vaapi_card"):
            return
        vaapi = _mapping(tools.get("vaapi_video"))
        state = str(vaapi.get("state") or "not-installed")
        supported = bool(vaapi.get("supported"))
        status, tone, detail = {
            "active": ("Active", "green",
                       "Programs that use VA-API encode and decode with it. For streaming while you play, choose H.264."),
            "relogin-required": ("Log out to apply", "orange",
                                 "Installed. Log out and back in (or restart) so programs pick it up."),
            "outdated": ("Update available", "orange",
                         "A newer reviewed version is available. Install builds and switches to it."),
            "invalid": ("Incomplete", "orange",
                        "The files that switch it on are there but the driver is missing. Install it again or remove it."),
            "managed-elsewhere": ("Managed externally", "blue",
                                  "Another installer already switches this driver on (its own scripts or the SteamOS toolkit). Remove that one first to manage it here."),
            "hardware-vcn": ("Not needed", "gray",
                             "The kernel's experimental hardware video block is on (amdgpu.bc250_vcn=1), and radeonsi drives it."),
        }.get(state, ("Not installed" if supported else "Not compatible", "gray", ""))
        installed = bool(vaapi.get("installed"))
        self.vaapi_card.set_status(status, tone)
        reason = str(vaapi.get("blocked_reason") or "")
        if detail:
            self.vaapi_card.detail.setText(tr(detail))
        elif not supported and reason:
            self.vaapi_card.detail.setText(tr(reason))
        else:
            self.vaapi_card.detail.setText(tr(
                "The BC-250 has no working video block, so programs fall back to software video. This driver encodes H.264 on the GPU and HEVC mostly on the CPU, and decodes both, for Sunshine, OBS, Steam Remote Play, ffmpeg and browsers."
            ))
        flatpak = _mapping(vaapi.get("flatpak"))
        flatpak_missing = (
            installed and state != "invalid" and bool(flatpak.get("available"))
            # Without the radeonsi alias, programs that clear LIBVA_DRIVER_NAME
            # (GPU Screen Recorder) cannot find the driver even when allowed.
            and (not flatpak.get("applied") or not vaapi.get("alias", True))
        )
        if flatpak_missing:
            self.vaapi_card.detail.setText(
                self.vaapi_card.detail.text() + "\n" + tr(
                    "Flatpak apps such as GPU Screen Recorder cannot see the driver yet, so they list H.264 as not available."
                )
            )
        driver32 = _mapping(vaapi.get("driver32"))
        state32 = str(driver32.get("state") or "unsupported")
        offer32 = installed and state != "invalid" and state32 in {"not-installed", "needs-libs"}
        if offer32:
            self.vaapi_card.detail.setText(
                self.vaapi_card.detail.text() + "\n" + tr(
                    "A SteamOS update removed the 32-bit libraries, so Steam Remote Play falls back to software video until they are back."
                    if state32 == "needs-libs" else
                    "Steam Remote Play and Steam Link encode with a 32-bit driver; without it they use software video."
                )
            )
        can_install = supported and state not in {"managed-elsewhere", "hardware-vcn", "active", "relogin-required"}
        self.vaapi_card.update_action(
            self.vaapi_install_button,
            text="Update" if state == "outdated" else "Reinstall" if state == "invalid" else "Install",
            enabled=can_install,
            visible=state not in {"active", "relogin-required", "managed-elsewhere", "hardware-vcn"},
            tooltip="" if supported else reason,
        )
        self.vaapi_card.update_action(
            self.vaapi_test_button, text="Test", visible=installed and state != "invalid",
        )
        self.vaapi_card.update_action(
            self.vaapi_flatpak_button, text="Allow Flatpak apps", visible=flatpak_missing,
        )
        self.vaapi_card.update_action(
            self.vaapi_32_button,
            text="Repair 32-bit driver" if state32 == "needs-libs" else "Add 32-bit driver",
            visible=offer32,
        )
        self.vaapi_card.update_action(
            self.vaapi_remove_button, text="Remove", visible=installed,
        )

    def _render_accessories(self, accessories: Mapping[str, object]) -> None:
        for key, card in self._accessory_cards.items():
            info = _mapping(accessories.get(key))
            state = str(info.get("state") or "")
            buttons = self.accessory_buttons[key]
            if state not in self._ACCESSORY_STATES:
                card.set_status("Checking", "gray")
                for name in ("install", "configure", "remove"):
                    buttons[name].hide()
                self._accessory_notes[key].hide()
                continue
            status, tone, install_text = self._ACCESSORY_STATES[state]
            installed = state in {"update-available", "relogin-required", "installed", "active"}
            if state == "not-installed" and info.get("device"):
                # The hardware is there and only the software is missing.
                status, tone = "Device detected", "blue"
            card.set_status(status, tone)
            note = self._ACCESSORY_NOTES.get((key, state), "")
            if key == "hdmi_ac3" and state == "installed":
                # Set up, but the owner picked another output since.
                install_text = "Use 5.1 output"
            if key == "hdmi_ac3" and state in {"installed", "active"} and not info.get("device"):
                note = "The connected display does not list Dolby Digital. Connect a receiver or soundbar that decodes AC-3."
            elif state in {"installed", "active"} and not info.get("device"):
                note = "Nothing is plugged in right now; it starts by itself when the device is connected."
            elif key == "hdmi_cec" and state == "not-installed" and not info.get("device"):
                note = "No CEC adapter is connected. CEC needs a DisplayPort-to-HDMI adapter that passes it, such as a Club3D CAC-1080 or CAC-1085."
            card.update_action(
                buttons["install"],
                text=install_text or "Install",
                payload={"accessory": key, "op": "install"},
                visible=bool(install_text),
            )
            configure_text = self._ACCESSORY_CONFIGURE.get(key, "")
            card.update_action(
                buttons["configure"],
                text=configure_text or "Open configuration",
                payload={"accessory": key, "op": "configure"},
                visible=bool(configure_text) and (installed or state == "managed-elsewhere"),
                enabled=state != "relogin-required",
            )
            card.update_action(
                buttons["remove"], text="Remove",
                payload={"accessory": key, "op": "remove"}, visible=installed,
            )
            self._accessory_notes[key].setText(tr(note))
            self._accessory_notes[key].setVisible(bool(note))

    def _reflow(self, width: int) -> None:
        tab_columns = (
            len(self.tab_buttons) - len(self._hidden_tabs)
            if width >= 620
            else 3 if width >= 420 else 2
        )
        self.system_layout.setDirection(
            QBoxLayout.Direction.TopToBottom
            if width < 480
            else QBoxLayout.Direction.LeftToRight
        )
        self.system_layout.setAlignment(self.status, Qt.AlignmentFlag.AlignLeft)
        # Content-sized actions must recover their single-line width after a
        # compact layout. WrappingButton's visible sizeHint follows its width.
        self.prepare_button.setMinimumWidth(
            min(max(0, width - 34), IconButton.sizeHint(self.prepare_button).width())
        )
        for button in (
            self.memory_swap_apply_button,
            self.memory_ttm_apply_button,
            self.mitigations_apply_button,
            self.readonly_button,
        ):
            button.setMinimumWidth(
                min(max(0, (width - 64) // 3), IconButton.sizeHint(button).width())
            )
        compact_mitigations = width < 660
        for panel_layout, panel_button in (
            (self.mitigations_layout, self.mitigations_apply_button),
            (self.readonly_layout, self.readonly_button),
        ):
            panel_layout.setDirection(
                QBoxLayout.Direction.TopToBottom
                if compact_mitigations
                else QBoxLayout.Direction.LeftToRight
            )
            panel_layout.setAlignment(
                panel_button,
                Qt.AlignmentFlag.AlignLeft
                if compact_mitigations
                else Qt.AlignmentFlag.AlignVCenter,
            )
        if hasattr(self, "upscaling_row"):
            # Side by side only while each card keeps its header on one row.
            self.upscaling_row.setDirection(
                QBoxLayout.Direction.LeftToRight
                if width >= 1180
                else QBoxLayout.Direction.TopToBottom
            )
            self._match_upscaler_headers()
        component_columns = (
            4 if width >= 1280 else 3 if width >= 980 else 2 if width >= 650 else 1
        )
        if tab_columns != self._tab_columns:
            self._tab_columns = tab_columns
            clear_grid(self.tabs_grid, reset_columns=6, reset_rows=3)
            shown = [
                self.tab_buttons[i] for i in self.TAB_ORDER if i not in self._hidden_tabs
            ]
            for index, button in enumerate(shown):
                self.tabs_grid.addWidget(
                    button, index // tab_columns, index % tab_columns
                )
            for column in range(tab_columns):
                self.tabs_grid.setColumnStretch(column, 1)
        if component_columns != self._component_columns:
            self._component_columns = component_columns
            clear_grid(self.components_grid, reset_columns=4, reset_rows=8)
            if component_columns == 1:
                row = 0
                for key, card in self.component_cards.items():
                    self.components_grid.addWidget(card, row, 0)
                    row += 1
                    if key == "core_unlock":
                        self.components_grid.addWidget(self.prepare_footer, row, 0)
                        row += 1
            else:
                last = component_columns - 1
                self.components_grid.addWidget(
                    self.component_cards["core_unlock"], 0, last
                )
                self.components_grid.addWidget(self.prepare_footer, 1, last)
                positions = (
                    (r, c)
                    for r in range(7)
                    for c in range(component_columns)
                    if (r, c) not in {(0, last), (1, last)}
                )
                for key, card in self.component_cards.items():
                    if key != "core_unlock":
                        row, column = next(positions)
                        self.components_grid.addWidget(card, row, column)
            for column in range(component_columns):
                self.components_grid.setColumnStretch(column, 1)

    def _render_gfx1013_source(self, source: Mapping[str, object], masta_supported: bool) -> None:
        """Status and actions of the independent GFX1013 source build."""
        state = str(source.get("state") or "not-installed")
        kernel = str(source.get("kernel") or "")
        installed = bool(source.get("installed"))
        enabled = bool(source.get("enabled"))
        self.gfx_card.set_scope("Built for this kernel · independent of MastaG", "blue")
        copy = {
            "not-installed": (
                "Source build available", "blue",
                tr_format(
                    "Builds DryhoppedIPA's V33 amdgpu patches for kernel {kernel} and RADV with the "
                    "compute-queue patch, and installs them beside the stock driver. If a boot with "
                    "the fix fails, the next boot uses the stock driver and switches the fix off by "
                    "itself. Building takes 15-30 minutes.",
                    kernel=kernel,
                ),
            ),
            "active": (
                "Active", "green",
                tr("The patched amdgpu and RADV are in use on this boot. Test stability game by game: async compute raises GPU load."),
            ),
            "reboot-required": (
                "Restart required", "blue",
                tr("Installed and switched on. Restart to load the patched driver."),
            ),
            "rebuild-needed": (
                "Rebuild needed", "orange",
                tr_format(
                    "Kernel {kernel} has no patched module yet, so the stock driver is in use. "
                    "Rebuilding only the module takes a few minutes.",
                    kernel=kernel,
                ),
            ),
            "switched-off": (
                "Switched off", "gray",
                tr("Installed but switched off: the stock amdgpu and system Mesa are in use."),
            ),
            "fell-back": (
                "Switched off after a failed boot", "orange",
                tr("A boot with the fix did not finish, so the stock driver took over and the fix was switched off. Switch it on again only after checking what failed."),
            ),
            "blocked-early-load": (
                "Loaded too early", "orange",
                tr("amdgpu was loaded from the initramfs before the boot service could choose it. Remove amdgpu from MODULES in the initramfs configuration and rebuild the initramfs."),
            ),
        }.get(state)
        if copy is None:
            copy = ("Checking", "gray", "")
        status, tone, detail = copy
        if masta_supported and state == "not-installed":
            detail = f"{detail} {tr('Use either this or the MastaG kernel below, not both.')}"
        self.gfx_card.set_status(status, tone)
        self.gfx_card.detail.setText(detail)
        if not installed:
            primary = ("Build and install the fix", "gfx1013_source_install")
        elif state == "rebuild-needed":
            primary = ("Rebuild for this kernel", "gfx1013_source_rebuild")
        elif enabled:
            primary = ("Switch off", "gfx1013_source_disable")
        else:
            primary = ("Switch on", "gfx1013_source_enable")
        self.gfx_card.update_action(
            self.gfx_primary_button,
            text=primary[0],
            payload={"action": primary[1], "governor": ""},
        )
        self.gfx_card.update_action(
            self.gfx_secondary_button,
            text="Remove the fix",
            payload={"action": "gfx1013_source_uninstall", "governor": ""},
            visible=installed,
        )
        self.gfx_card.update_action(
            self.gfx_tertiary_button if installed else self.gfx_secondary_button,
            text="Open upstream project",
            payload={"action": "gfx1013_upstream", "governor": ""},
        )

    def _render_debian_kernel(self, upgrade: Mapping[str, object]) -> None:
        """Debian 13: install a newer Mesa and kernel from backports, then the GFX1013 build."""
        pending_restart = str(upgrade.get("state") or "") == "reboot-required"
        with_kernel = bool(upgrade.get("install_kernel", True))
        self.gfx_card.set_scope("Debian · Kernel and Mesa too old for the GPU", "orange")
        self.gfx_card.set_status(
            "Restart required" if pending_restart else "Newer kernel and Mesa needed",
            "blue" if pending_restart else "orange",
        )
        self.gfx_card.detail.setText(
            tr("A newer kernel is already installed. Restart to use it, then build the GFX1013 fix.")
            if pending_restart
            else (
                tr(
                    "Optional. The Debian kernel and Mesa do not recognize the BC-250 GPU, so the desktop is drawn by the CPU and feels slow. This installs a newer Mesa and kernel from Debian backports; the current kernel stays in the boot menu."
                )
                if with_kernel
                else tr(
                    "Optional. The Mesa that Debian 13 ships does not recognize the BC-250 GPU, so the desktop is drawn by the CPU and feels slow. This installs the newer Mesa from Debian backports."
                )
            )
        )
        self.gfx_card.update_action(
            self.gfx_primary_button,
            text="Install from backports",
            payload={"action": "debian_kernel_install", "governor": ""},
            enabled=not pending_restart,
        )

    def _render_radv_async(
        self,
        radv: Mapping[str, object],
        source: Mapping[str, object],
        *,
        dryhopped_installed: bool = False,
        fedora: bool = False,
    ) -> None:
        """Async compute from the patched RADV alone, on a kernel 7.2+ (Arch family or Fedora)."""
        route = present_radv_route(
            radv,
            source_installed=bool(source.get("installed")),
            dryhopped_installed=dryhopped_installed,
            fedora=fedora,
        )
        self.gfx_card.set_scope(route.scope, "blue")
        self.gfx_card.set_status(route.status, route.tone)
        self.gfx_card.detail.setText(
            " ".join(tr_format(part, **route.values) for part in route.detail)
        )
        if route.build:
            self.gfx_card.update_action(
                self.gfx_primary_button,
                text="Build and install",
                payload={"action": "radv_async_install", "governor": ""},
            )
        else:
            self.gfx_card.update_action(
                self.gfx_primary_button,
                text="Switch off" if route.enabled else "Switch on",
                payload={"action": "radv_async_disable" if route.enabled else "radv_async_enable", "governor": ""},
            )
        self.gfx_card.update_action(
            self.gfx_secondary_button,
            text="Test async compute",
            payload={"action": "radv_async_test", "governor": ""},
            visible=route.testable,
        )
        self.gfx_card.update_action(
            self.gfx_tertiary_button,
            text="Remove",
            payload={"action": "radv_async_uninstall", "governor": ""},
            visible=route.installed,
        )
        self.gfx_card.update_action(
            self.gfx_quaternary_button,
            text="Remove the kernel-side fix",
            payload={"action": route.remove_fix_action, "governor": ""},
            visible=bool(route.remove_fix_action),
        )
        self.gfx_card.update_action(
            self.gfx_quinary_button,
            text="Open upstream project",
            payload={"action": "bazzite_async_upstream", "governor": ""},
        )

    def _render_helixsr(self, helixsr: Mapping) -> None:
        """HelixSR's datasheet and actions, from ``helixsr_state``."""
        available = bool(helixsr.get("installer_available"))
        installed = bool(helixsr.get("installed"))
        current = bool(helixsr.get("current"))
        ready = bool(helixsr.get("network_ready"))
        wine = bool(helixsr.get("wine_available", True))
        state = str(helixsr.get("state") or "not-installed")
        games = [dict(game) for game in helixsr.get("games") or () if isinstance(game, Mapping)]
        detail = "DLSS's neural network running on this GPU, in place of a game's FSR 3.1 upscaler."
        if ready:
            status, tone = "Ready", "green"
        elif not available:
            status, tone = "Unavailable", "gray"
            detail = "HelixSR's setup runs on x86_64 Linux only."
        elif not wine:
            status, tone = "Proton required", "orange"
            detail = "HelixSR's setup compiles its shaders through Proton. Install Proton from Steam first: setting any game to use Proton installs it."
        elif current:
            status, tone = "Network files missing", "orange"
            detail = (
                "HelixSR is installed, but its network files are not built yet. They are built from the copy of NVIDIA's DLSS DLL already on this PC."
                if helixsr.get("local_dlss") else
                "HelixSR is installed, but its network files are not built yet. The setup asks before it downloads NVIDIA's DLSS DLL."
            )
        elif state == "invalid":
            status, tone = "Repair required", "orange"
            detail = "The HelixSR folder is incomplete or was changed. Reinstall it."
        elif state == "update-available":
            status, tone = "Update available", "blue"
            detail = "A newer HelixSR release is available. Games that already use HelixSR keep working."
        elif state == "other-version":
            status, tone = "Other version selected", "blue"
            detail = "The selected HelixSR release is not installed yet. Install brings it in; games that already use HelixSR keep working."
        else:
            status, tone = "Not installed", "gray"
            detail = "Downloads the official release, checks it, and installs it in your user folder. Then build its network files and pick your games."
        self.helixsr_card.set_status(status, tone)
        self.helixsr_card.detail.setText(tr(detail))
        self._helixsr_view = {
            "state": helixsr, "status": status, "tone": tone, "detail": detail,
            "version": str(helixsr.get("version") or "") if current else "",
        }

        self.helixsr_card.update_action(
            self.helixsr_scan_button, text="Find FSR 3.1 games", visible=ready,
        )
        self.helixsr_card.update_action(
            self.helixsr_network_button,
            text="Build network files",
            enabled=wine,
            visible=current and not ready,
        )
        self.helixsr_card.update_action(
            self.helixsr_install_button,
            text="Repair HelixSR" if state == "invalid"
            else "Update HelixSR" if state == "update-available"
            else "Reinstall" if current
            else "Install HelixSR",
            enabled=available and (wine or current),
            visible=available,
        )
        self.helixsr_card.update_action(
            self.helixsr_remove_button, text="Remove", visible=installed,
        )
        self.helixsr_upstream_button.show()
        self.helixsr_card._refresh_action_styles()
        self._helixsr_games = (games if HELIXSR_UI_ENABLED else [], ready)
        self._helixsr_settings_state = (
            _mapping(helixsr.get("settings")), _mapping(helixsr.get("settings_defaults"))
        )
        self._helixsr_game_count = sum(
            1 for game in games if str(_mapping(game).get("state") or "") == "installed"
        )
        self._helixsr_int8 = bool(helixsr.get("int8_supported", True))
        if hasattr(self, "helixsr_settings"):
            self.helixsr_settings.set_int8_supported(self._helixsr_int8)
            self.helixsr_settings.set_settings(*self._helixsr_settings_state)
            self.helixsr_settings.set_game_count(self._helixsr_game_count)

    def _render_upscaling(self) -> None:
        """Both upscalers' cards, then the games table shared by both."""
        if not hasattr(self, "fsr4_section"):
            return
        helixsr_games, ready = getattr(self, "_helixsr_games", ([], False))
        rows = game_matrix_rows(
            helixsr_games, getattr(self, "_fsr4_games", []), helixsr_ready=ready
        )
        self._render_fsr4_section()
        self._render_helixsr_section()
        self._render_upscaling_games(rows, ready)
        self._match_upscaler_headers()

    def _render_fsr4_section(self) -> None:
        """FSR4 INT8: state, the Steam launch option, its games, next step."""
        view = getattr(self, "_fsr4_view", None) or {
            "state": {}, "status": "Checking", "tone": "", "detail": "", "version": "",
        }
        fsr4 = view["state"]
        current = bool(fsr4.get("current"))
        self._render_fsr4_versions(fsr4)
        games = list(getattr(self, "_fsr4_games", []))
        missing = [g for g in games if g.get("state") == "needs-launch-option" and g.get("steam")]
        patched = [g for g in games if g.get("state") not in {"not-installed", "linked-folder"}]
        active = [g for g in games if g.get("state") == "ready"]
        section = self.fsr4_section
        section.set_version(view["version"])
        section.set_fact("state", "State", view["status"], view["tone"])
        if not current or not patched:
            option, tone = "—", ""
        elif missing:
            option, tone = "Missing in some games", "orange"
        else:
            option, tone = "In every game", ""
        section.set_fact("prepare", "Steam launch option", option, tone)
        section.set_fact("games", "Active games", self._games_reading(len(active), len(games), current))
        section.set_notice("" if current else view["detail"])
        # The option is shown where it is missing, with a copy for by hand.
        self.fsr4_launch_panel.setVisible(current and bool(self._fsr4_launch_option))
        self.fsr4_launch_field.setText(self._fsr4_launch_option)
        self.fsr4_launch_field.setCursorPosition(0)
        self.fsr4_launch_field.updateGeometry()
        self.upscaling_games._layout_header(force=True)
        if not current:
            secondary = [self.fsr4_remove_button, self.fsr4_legacy_button]
            primary = self.fsr4_install_button
        elif missing:
            secondary = [self.fsr4_install_button, self.fsr4_remove_button,
                         self.fsr4_legacy_button, self.fsr4_launch_button]
            primary = self.fsr4_steam_all_button
        else:
            secondary = [self.fsr4_install_button, self.fsr4_remove_button, self.fsr4_legacy_button]
            primary = self.fsr4_launch_button
        self.fsr4_steam_all_button.setVisible(current and bool(missing))
        section.set_actions(secondary, primary)

    def _render_helixsr_versions(self, helixsr: Mapping) -> None:
        """The releases on offer, newest first, the picked one shown."""
        self._render_version_picker(self.helixsr_version_combo, self.helixsr_releases_button, helixsr)

    def _render_fsr4_versions(self, fsr4: Mapping) -> None:
        """The OptiScaler Client builds on offer, as for HelixSR."""
        if hasattr(self, "fsr4_version_combo"):
            self._render_version_picker(self.fsr4_version_combo, self.fsr4_releases_button, fsr4)

    @staticmethod
    def _render_version_picker(combo, button, state: Mapping) -> None:
        releases = [_mapping(item) for item in state.get("releases") or () if isinstance(item, Mapping)]
        combo.blockSignals(True)
        combo.clear()
        for release in releases:
            version = str(release.get("version") or "")
            if release.get("default"):
                text = tr_format("{version} (recommended)", version=version)
            elif release.get("prerelease"):
                text = tr_format("{version} (pre-release)", version=version)
            else:
                text = version
            combo.addItem(text, str(release.get("tag") or ""))
        combo.setCurrentIndex(max(combo.findData(str(state.get("tag") or "")), 0))
        combo.blockSignals(False)
        combo.setEnabled(bool(state.get("installer_available")) and combo.count() > 1)
        button.setEnabled(bool(state.get("installer_available")))

    def _render_helixsr_section(self) -> None:
        """HelixSR: state, its network files, its games, next step."""
        view = getattr(self, "_helixsr_view", None) or {
            "state": {}, "status": "Checking", "tone": "", "detail": "", "version": "",
        }
        helixsr = view["state"]
        current = bool(helixsr.get("current"))
        ready = bool(helixsr.get("network_ready"))
        games = game_matrix_rows(
            [dict(g) for g in helixsr.get("games") or () if isinstance(g, Mapping)], [],
            helixsr_ready=ready,
        )
        active = [row for row in games if row["helixsr"] and row["helixsr"][1] == "green"]
        section = self.helixsr_section
        section.set_version(view["version"])
        self._render_helixsr_versions(helixsr)
        section.set_fact("state", "State", view["status"], view["tone"])
        section.set_fact(
            "prepare", "Network files",
            "Built on this PC" if ready else "Not built yet" if current else "—",
            "" if ready or not current else "orange",
        )
        section.set_fact(
            "games", "Active games", self._games_reading(len(active), len(games), current and (ready or bool(games)))
        )
        section.set_notice("" if ready else view["detail"])
        if not current:
            secondary, primary = [self.helixsr_remove_button], self.helixsr_install_button
        elif not ready:
            secondary = [self.helixsr_install_button, self.helixsr_remove_button]
            primary = self.helixsr_network_button
        else:
            secondary = [self.helixsr_install_button, self.helixsr_remove_button]
            primary = self.helixsr_scan_button
        section.set_actions(secondary, primary)

    def _render_upscaling_games(self, rows: list[dict], ready: bool) -> None:
        """One column per upscaler that is set up, in the cards' order."""
        helixsr = _mapping(_mapping(getattr(self, "_helixsr_view", {})).get("state"))
        fsr4 = _mapping(_mapping(getattr(self, "_fsr4_view", {})).get("state"))
        helixsr_games, _ready = getattr(self, "_helixsr_games", ([], False))
        # HelixSR's column once it can go into games, or while a game still
        # has it (to update or remove it).
        helixsr_on = HELIXSR_UI_ENABLED and bool(helixsr.get("current")) and (ready or bool(helixsr_games))
        fsr4_on = FSR4_UI_ENABLED and bool(fsr4.get("current"))
        columns = tuple(key for key, on in (("fsr4", fsr4_on), ("helixsr", helixsr_on)) if on)
        table = []
        for row in rows:
            folder = row.get("folder") or ""
            helixsr_cell = None
            if helixsr_on and row["helixsr"] is not None:
                text, tone, tooltip, actions = row["helixsr"]
                # HelixSR is in the game whenever one of its actions removes it.
                on = any(label.startswith("Remove") for label, _action, _enabled in actions)
                helixsr_cell = {
                    "text": text or "Available", "tone": tone, "tooltip": tooltip,
                    "actions": (
                        *actions,
                        # A folder added by hand can leave the list while HelixSR is not in it.
                        *((("Remove from list", f"helixsr_forget_folder:{row['appid']}", True),)
                          if folder and not on else ()),
                    ),
                }
            fsr4_cell = None
            if fsr4_on and row["fsr4"] is not None:
                text, tone, tooltip, actions = row["fsr4"]
                fsr4_cell = {"text": text or "Available", "tone": tone, "tooltip": tooltip,
                             "actions": actions}
            if helixsr_cell is None and fsr4_cell is None:
                continue
            table.append({
                "key": row["appid"] or row["name"], "name": row["name"],
                "detail": (row.get("folder_detail") or "Outside Steam") if folder else "", "tooltip": folder,
                "helixsr": helixsr_cell, "fsr4": fsr4_cell,
            })
        self.upscaling_games.set_rows(
            table,
            "No games yet. Find FSR 3.1 games looks through your Steam library." if helixsr_on
            else "No games yet. Add OptiScaler to a game in OptiScaler Client.",
            columns,
        )
        self.upscaling_games.setVisible(bool(columns))
        for button in (self.helixsr_folder_button, self.helixsr_opti_folder_button):
            button.setVisible(helixsr_on and ready)
            # The header keeps each label on one line.
            button.setProperty("headerActionWidth", IconButton.sizeHint(button).width())
        self.upscaling_games._layout_header(force=True)
        self.helixsr_settings.setVisible(HELIXSR_UI_ENABLED and bool(helixsr.get("current")))

    def _render_fsr4_games(self, games: list[dict]) -> None:
        """FSR4's games are rows of its section on the Upscaling tab."""
        self._fsr4_games = list(games)

    def _apply_compatibility_filter(self) -> None:
        self._restore_compatibility_preview_actions()
        actual = self._distribution_group(str(self._tools.get("os_family") or ""))
        choice = str(self.compatibility_filter.currentData() or "detected")
        selected = actual if choice == "detected" else choice
        show_all = selected == "all"
        preview = choice not in {"detected", "all"} and selected != actual
        labels = {
            "steamos": "SteamOS",
            "bazzite": "Bazzite",
            "arch": "Arch / CachyOS / Manjaro",
            "fedora": "Fedora",
            "debian": "Ubuntu / Debian",
            "other": "Other distributions",
        }
        self.acpi_card.setVisible(show_all or selected in {"arch", "bazzite", "steamos"})
        # Bazzite takes the same tables through grubenv, SteamOS through GRUB's
        # early initrd list (both beta).
        self.acpi_card.set_scope(
            "Beta · Bazzite" if selected == "bazzite"
            else "Beta · SteamOS" if selected == "steamos"
            else "Validated · Arch / CachyOS / Manjaro"
        )
        self.cyan_card.setVisible(True)
        self.oberon_card.setVisible(True)
        self.gfx_card.setVisible(
            (
                show_all or selected != "arch"
                or (selected == actual and bool(getattr(self, "_gfx_source_offered", False)))
            )
            # Debian family on a kernel too old for any route: nothing to offer.
            and not (selected == actual and bool(getattr(self, "_gfx_hidden_old_kernel", False)))
        )
        self.cachyos_stack_card.setVisible(show_all or selected == "arch")
        self.fsr4_card.setVisible(FSR4_UI_ENABLED)
        self.helixsr_card.setVisible(HELIXSR_UI_ENABLED)
        self._refresh_compatibility_summary()

        if not preview:
            return

        self.gfx_card.set_scope(labels.get(selected, "Compatibility preview"), "blue")
        self.gfx_card.set_status("Preview only", "blue")
        preview_copy = {
            "steamos": "SteamOS 3.8/3.9 provides a reviewed two-stage path: install the matching AMDGPU module, reboot, then install the matched Mesa/RADV runtime.",
            "bazzite": "Bazzite is immutable. Direct kernel/Mesa patching is blocked; use a BC-250 image or a matching rpm-ostree package instead.",
            "arch": "Available only on plain Arch Linux or CachyOS",
            "fedora": "Fedora uses DryhoppedIPA's official current GFX1013 workflow. Control Center adds local safety gates, then leaves kernel and Mesa compatibility checks to upstream.",
            "debian": "Ubuntu and Debian can build the GFX1013 fix from source when the running kernel is 6.14 or newer (Ubuntu 25.04 and later, 24.04 with the HWE kernel, Debian with a backports kernel). Older kernels keep the manual upstream path.",
            "other": "This distribution can use common governors when its packages are available. Kernel/Mesa compatibility stays manual until a reviewed path exists.",
        }
        self.gfx_card.detail.setText(tr(preview_copy[selected]))
        self.steamos_graphics_state.setVisible(selected == "steamos")
        self.steamos_fsr4_launch_row.hide()
        if selected == "steamos":
            pills = [
                self.steamos_kernel_status,
                self.steamos_radv_status,
            ]
            if GFX1013_FSR4_UI_ENABLED:
                pills.append(self.steamos_fsr4_status)
            for pill in pills:
                pill.setText(tr("Available on SteamOS"))
                pill.set_tone("gray")
            self.gfx_card.update_action(
                self.gfx_primary_button,
                text="1 · Install kernel",
                payload={"action": "steamos_compat", "governor": ""},
                enabled=False,
            )
            self.gfx_card.update_action(
                self.gfx_secondary_button,
                text="2 · Install Mesa RADV",
                payload={"action": "steamos_graphics_install", "governor": ""},
                enabled=False,
            )
            if GFX1013_FSR4_UI_ENABLED:
                self.gfx_card.update_action(
                    self.gfx_tertiary_button,
                    text="3 · Install per-game FSR4",
                    payload={
                        "action": "steamos_graphics_fsr4_install",
                        "governor": "",
                    },
                    enabled=False,
                )
            self.gfx_card.update_action(
                self.gfx_quaternary_button,
                text="Open upstream project",
                payload={"action": "gfx1013_upstream", "governor": ""},
            )
            self.gfx_quinary_button.hide()
        else:
            self.gfx_card.update_action(
                self.gfx_primary_button,
                text="Open upstream project",
                payload={"action": "gfx1013_upstream", "governor": ""},
            )
            for button in (
                self.gfx_secondary_button,
                self.gfx_tertiary_button,
                self.gfx_quaternary_button,
                self.gfx_quinary_button,
            ):
                button.hide()
        if selected == "arch":
            self.cachyos_stack_card.set_status("Available on Arch family", "blue")
        # A filter is allowed to demonstrate coverage, never to run another
        # distribution's installer on the detected host. Keep documentation
        # links usable and disable every mutating preview action.
        for card in (
            self.acpi_card,
            self.cyan_card,
            self.oberon_card,
            self.gfx_card,
            self.cachyos_stack_card,
        ):
            for button in card.findChildren(QPushButton):
                action = str(getattr(button, "request_payload", {}).get("action") or "")
                if "upstream" not in action and "diagnostic" not in action:
                    self._preview_button_states[button] = button.isEnabled()
                    button.setEnabled(False)
                    button.setToolTip(
                        tr(
                            "Preview only: select the detected system to install or change components."
                        )
                    )

    def set_state(self, state) -> None:
        # Restore the last authoritative enabled states before new runtime
        # evidence updates the buttons. Otherwise leaving preview mode could
        # reapply an older disabled snapshot over freshly detected components.
        self._restore_compatibility_preview_actions()
        self._last_preparation_state = state
        tools = _mapping(getattr(state, "preparation_tools", {}))
        self._tools = tools
        setup = _mapping(tools.get("system_setup"))
        acpi = _mapping(setup.get("acpi"))
        status_text = {
            "active": "Active",
            "pending-reboot": "Reboot required",
            "not-active": "Not active",
            "incomplete": "Incomplete",
            "managed-elsewhere": "Managed externally",
            "needs-check": "Not verified",
            "outdated": "Update available",
            "needs-repair": "Repair required",
        }.get(acpi.get("status"), "Not installed")
        acpi_tone = (
            "green"
            if acpi.get("status") == "active"
            else "orange"
            if acpi.get("status") in {"pending-reboot", "incomplete", "not-active", "outdated", "needs-repair"}
            else "blue"
            if acpi.get("status") == "managed-elsewhere"
            else "gray"
        )
        self._render_vaapi(tools)
        self._render_mesa(tools)
        self.acpi_card.set_status(status_text, acpi_tone)
        reason = str(setup.get("reason") or acpi.get("reason") or "")
        self.acpi_install_button.setEnabled(
            bool(
                setup.get("helper_available")
                and acpi.get("available")
                and not acpi.get("installed")
            )
        )
        self.acpi_remove_button.setEnabled(
            bool(setup.get("helper_available") and acpi.get("installed"))
        )
        self.acpi_install_button.setVisible(not bool(acpi.get("installed")))
        # An earlier pinned release: v1.1.0's C3 idle state freezes the board.
        # On SteamOS the same action writes the tables back after an update.
        outdated = acpi.get("status") in {"outdated", "needs-repair"}
        self.acpi_update_button.setText(
            tr("Repair correction" if acpi.get("status") == "needs-repair" else "Update correction")
        )
        self.acpi_update_button.setEnabled(bool(setup.get("helper_available") and outdated))
        self.acpi_update_button.setVisible(outdated)
        self.acpi_remove_button.setVisible(bool(acpi.get("installed")))
        self.acpi_card.setToolTip(tr(reason))
        capabilities = _mapping(tools.get("prepare_components"))
        fallback = {
            "runtime": bool(getattr(state, "dependencies_ready", False)),
            "governor": bool(getattr(state, "governor_tool_ready", False)),
            "cpu_oc": bool(getattr(state, "cpu_tools_ready", False)),
            "core_unlock": bool(getattr(state, "core_unlock_ready", False)),
            "umr": bool(getattr(state, "umr_ready", False)),
            "cu_manager": bool(getattr(state, "cu_manager_ready", False)),
            "fan_pwm": bool(getattr(state, "nct_ready", False)),
        }
        installed_values = []
        for key, card in self.component_cards.items():
            capability = _mapping(capabilities.get(key))
            if not capability:
                capability = {"available": True, "installed": fallback[key]}
            card.set_capability(capability)
            installed_values.append(bool(capability.get("installed")))
        all_ready = bool(installed_values) and all(installed_values)
        known = (
            bool(tools)
            or bool(getattr(state, "tools_state_available", False))
            or any(installed_values)
        )
        self.status.setText(
            "Operational" if all_ready else "Attention" if known else "Not detected"
        )
        self.status.set_tone("green" if all_ready else "orange" if known else "gray")

        os_label = str(tools.get("os_label") or tr("Not detected"))
        family = str(tools.get("os_family") or "")
        system_identity = (
            os_label
            if family.lower() in os_label.lower()
            else (f"{os_label} · {family}" if family else os_label)
        )
        self.system_label.setText(
            tr_format("Detected system: {distribution}", distribution=system_identity)
        )
        detected = bool(tools.get("os_label") or family)
        self.system_status.setText("Detected" if detected else "Not detected")
        self.system_status.set_tone("green" if detected else "gray")
        self._update_memory_controls(tools)

        family = str(tools.get("os_family") or "").lower()
        detected_governors = _mapping(tools.get("supported_gpu_governors"))
        for identifier, card in (
            ("cyan-skillfish-governor-smu", self.cyan_card),
            ("oberon-governor", self.oberon_card),
        ):
            if card.secondary_button is None:
                continue
            evidence = _mapping(detected_governors.get(identifier))
            installed = bool(evidence.get("detected"))
            active = bool(evidence.get("active"))
            # Control Center's own copy of Cyan is an older release (or the
            # patched build of an earlier version): Update / repair moves it
            # to the reviewed upstream one.
            outdated = installed and identifier == "cyan-skillfish-governor-smu" and bool(
                tools.get("cyan_runtime_update_available")
            )
            card.set_status(
                "Update available" if outdated
                else "Active" if active else "Installed" if installed else "Not installed",
                "orange" if outdated else "green" if active else "blue" if installed else "gray",
            )
            if card.primary_button is not None:
                card.update_action(
                    card.primary_button,
                    text="Update / repair" if installed else "Install / update",
                    enabled=True,
                )
            card.secondary_button.setEnabled(installed)
            card.secondary_button.setVisible(installed)
            card.secondary_button.setToolTip("" if installed else tr("Not installed"))
        masta = _mapping(tools.get("masta_bc250_stack"))
        masta_supported = bool(
            masta.get("supported", tools.get("masta_bc250_stack_supported"))
        )
        kernel_installed = bool(masta.get("kernel_installed"))
        kernel_active = bool(masta.get("kernel_active"))
        mesa_installed = bool(masta.get("mesa_installed"))
        if not masta_supported:
            self.cachyos_stack_card.set_status("Not compatible", "gray")
        elif kernel_installed and mesa_installed and kernel_active:
            self.cachyos_stack_card.set_status("Full stack installed", "green")
        elif kernel_installed and mesa_installed:
            self.cachyos_stack_card.set_status("Installed · reboot required", "orange")
        elif kernel_installed or mesa_installed:
            self.cachyos_stack_card.set_status("Partially installed", "orange")
        else:
            self.cachyos_stack_card.set_status("Available", "blue")
        kernel_text = (
            tr("Active")
            if kernel_active
            else tr("Installed")
            if kernel_installed
            else tr("Not installed")
        )
        # RC and BORE are installed by hand beside the stable kernel; name the
        # one in use so "Active" is not read as the stable build.
        variant = {"rc": "RC", "bore": "BORE"}.get(str(masta.get("kernel_variant") or ""))
        if kernel_installed and variant:
            kernel_text = f"{kernel_text} · {variant}"
        self.cachyos_kernel_status.setText(kernel_text)
        self.cachyos_kernel_status.set_tone(
            "green" if kernel_active else "gray"
        )
        self.cachyos_mesa_status.setText(
            tr("Patched installed") if mesa_installed else tr("Not installed")
        )
        self.cachyos_mesa_status.set_tone("green" if mesa_installed else "gray")
        unsupported_tip = "Available only on plain Arch Linux or CachyOS"
        self.cachyos_stack_card.update_action(
            self.cachyos_kernel_button,
            text="Update / repair kernel" if kernel_installed else "Install kernel",
            enabled=masta_supported,
            tooltip="" if masta_supported else unsupported_tip,
        )
        self.cachyos_stack_card.update_action(
            self.cachyos_mesa_button,
            text="Update / repair Mesa" if mesa_installed else "Install Mesa",
            enabled=masta_supported,
            tooltip="" if masta_supported else unsupported_tip,
        )
        self.cachyos_stack_card.update_action(
            self.cachyos_full_button,
            text="Update / repair full stack"
            if kernel_installed and mesa_installed
            else "Install kernel + Mesa",
            enabled=masta_supported,
            tooltip="" if masta_supported else unsupported_tip,
        )

        gfx_state = _mapping(tools.get("gfx1013_compute"))
        # On the Arch family this card normally steps aside for MastaG's
        # stack card. The independent source build is rendered into it, so
        # the card has to stay visible whenever that build is on offer.
        self._gfx_source_offered = False
        kernel_upgrade = _mapping(gfx_state.get("kernel_upgrade"))
        self._gfx_hidden_old_kernel = (
            bool(_mapping(gfx_state.get("source")).get("hide_offer"))
            and not _mapping(gfx_state.get("radv_async")).get("supported")
            and not bool(gfx_state.get("masta_async_compute_ready"))
            # Debian 13 gets the backports kernel in this card instead.
            and not bool(kernel_upgrade.get("offered"))
        )
        gfx = present_gfx1013(gfx_state, include_fsr4=GFX1013_FSR4_UI_ENABLED)
        reason_key = str(gfx_state.get("reason_key") or "manual-patches-only")
        gfx_scope = {
            "steamos-dedicated-backend": "SteamOS · BC-250 toolkit",
            "fedora-upstream-managed": "Fedora · Official upstream main",
            "arch-family-manual-untested": (
                "Arch / CachyOS · Included in MastaG stack"
                if masta_supported
                else "Arch family · Manual only"
            ),
            "bazzite-release-managed": "Bazzite 44 · Reviewed v0.2.4 release",
            "bazzite-release-kernel-unsupported": "Bazzite 44 · Compatible kernel required",
            "bazzite-release-version-unsupported": "Bazzite · Version not supported",
        }.get(reason_key, "Ubuntu / Debian / other · Manual only")
        self.gfx_card.set_scope(
            gfx_scope,
            "blue"
            if reason_key in {"steamos-dedicated-backend", "fedora-upstream-managed", "bazzite-release-managed"}
            or masta_supported
            else "gray",
        )
        self.gfx_card.set_status(gfx.status, gfx.tone)
        self.gfx_card.detail.setText(
            " ".join(tr_format(part, **gfx.detail_values) for part in gfx.detail)
        )
        for button in (
            self.gfx_primary_button,
            self.gfx_secondary_button,
            self.gfx_tertiary_button,
            self.gfx_quaternary_button,
            self.gfx_quinary_button,
        ):
            button.hide()
        self.steamos_graphics_state.setVisible(
            reason_key == "steamos-dedicated-backend"
        )
        self._steamos_fsr4_launch_option = ""
        self.steamos_fsr4_launch_row.hide()
        self.bazzite_enable_row.hide()
        self.bazzite_launch_row.hide()
        if reason_key == "steamos-dedicated-backend":
            kernel_ready = bool(gfx_state.get("steamos_kernel_ready"))
            kernel_installed = bool(gfx_state.get("steamos_kernel_installed"))
            radv_state = str(
                gfx_state.get("steamos_external_radv_state") or "not-installed"
            )
            radv_current = bool(gfx_state.get("steamos_external_radv_current"))
            fsr4_state = str(
                gfx_state.get("steamos_external_fsr4_state") or "not-installed"
            )
            fsr4_current = bool(gfx_state.get("steamos_external_fsr4_current"))
            self._steamos_fsr4_launch_option = str(
                gfx_state.get("steamos_external_fsr4_launch_option") or ""
            )
            self.steamos_fsr4_launch_row.setVisible(
                GFX1013_FSR4_UI_ENABLED
                and fsr4_current
                and bool(self._steamos_fsr4_launch_option)
            )
            self.steamos_fsr4_copy_button.setText("⧉")
            self.steamos_fsr4_copy_button.setToolTip(
                tr("Copy Steam launch option")
            )
            self.steamos_kernel_status.setText(
                tr("Active")
                if kernel_ready
                else tr("Reboot required")
                if kernel_installed
                else tr("Not installed")
            )
            self.steamos_kernel_status.set_tone(
                "green" if kernel_ready else "orange" if kernel_installed else "gray"
            )
            self.steamos_radv_status.setText(
                tr("Ready")
                if radv_current
                else tr("Repair required")
                if radv_state == "invalid"
                else tr("Not installed")
            )
            self.steamos_radv_status.set_tone(
                "green"
                if radv_current
                else "orange"
                if radv_state == "invalid"
                else "gray"
            )
            self.steamos_fsr4_status.setText(
                tr("Ready")
                if fsr4_current
                else tr("Repair required")
                if fsr4_state == "invalid"
                else tr("Optional")
            )
            self.steamos_fsr4_status.set_tone(
                "green"
                if fsr4_current
                else "orange"
                if fsr4_state == "invalid"
                else "gray"
            )
            self.gfx_card.update_action(
                self.gfx_primary_button,
                text=gfx.compatibility_action,
                payload={"action": "steamos_compat", "governor": ""},
            )
            self.gfx_card.update_action(
                self.gfx_secondary_button,
                text="2 · Repair Mesa RADV"
                if radv_state != "not-installed"
                else "2 · Install Mesa RADV",
                payload={"action": "steamos_graphics_install", "governor": ""},
                enabled=kernel_ready,
                tooltip="Install the kernel and reboot first."
                if not kernel_ready
                else "",
            )
            if GFX1013_FSR4_UI_ENABLED:
                self.gfx_card.update_action(
                    self.gfx_tertiary_button,
                    text="Update per-game FSR4"
                    if fsr4_current
                    else "3 · Install per-game FSR4",
                    payload={
                        "action": "steamos_graphics_fsr4_install",
                        "governor": "",
                    },
                    enabled=kernel_ready and radv_current,
                    tooltip="Install and activate the matched Mesa/RADV stage first."
                    if not (kernel_ready and radv_current)
                    else "",
                )
            self.gfx_card.update_action(
                self.gfx_quaternary_button,
                text="Check full stack",
                payload={"action": "steamos_graphics_status", "governor": ""},
            )
            self.gfx_card.update_action(
                self.gfx_quinary_button,
                text=(
                    "Remove FSR4"
                    if GFX1013_FSR4_UI_ENABLED and fsr4_state != "not-installed"
                    else "Remove Mesa RADV"
                ),
                payload={
                    "action": "steamos_graphics_fsr4_uninstall"
                    if GFX1013_FSR4_UI_ENABLED and fsr4_state != "not-installed"
                    else "steamos_graphics_uninstall",
                    "governor": "",
                },
                visible=(
                    (GFX1013_FSR4_UI_ENABLED and fsr4_state != "not-installed")
                    or radv_state != "not-installed"
                ),
            )
        elif reason_key == "fedora-upstream-managed" and gfx.radv_route is None:
            # Fedora on a kernel older than 7.2: DryhoppedIPA's installer. On
            # 7.2 or newer the patched RADV alone takes over (below).
            installed = bool(gfx_state.get("dryhopped_installed"))
            patched_boot = installed and bool(gfx_state.get("dryhopped_boot_active"))
            buttons = iter((
                self.gfx_primary_button,
                self.gfx_secondary_button,
                self.gfx_tertiary_button,
                self.gfx_quaternary_button,
            ))
            if installed:
                # Upstream boots the patched entry once; these switch it on.
                self.gfx_card.update_action(
                    next(buttons),
                    text="Make the fix the default" if patched_boot else "Boot with the fix",
                    payload={
                        "action": "gfx1013_fedora_activate"
                        if patched_boot
                        else "gfx1013_fedora_boot_patched",
                        "governor": "",
                    },
                )
            self.gfx_card.update_action(
                next(buttons),
                text="Install / update",
                payload={"action": "gfx1013_fedora_install", "governor": ""},
            )
            if installed:
                self.gfx_card.update_action(
                    next(buttons),
                    text="Uninstall",
                    payload={"action": "gfx1013_fedora_uninstall", "governor": ""},
                )
            self.gfx_card.update_action(
                next(buttons),
                text="Open upstream project",
                payload={"action": "gfx1013_upstream", "governor": ""},
            )
        elif reason_key.startswith("bazzite-release-"):
            installed = bool(gfx_state.get("bazzite_async_installed"))
            installer_allowed = bool(gfx_state.get("direct_installer_allowed"))
            self.gfx_card.update_action(
                self.gfx_primary_button,
                text="Repair / update" if installed else "Install / update",
                payload={"action": "gfx1013_bazzite_install", "governor": ""},
                enabled=installer_allowed,
                tooltip="" if installer_allowed else "Requires Bazzite 44 with kernel 7.2.0-ogc4.1 or newer.",
            )
            self.gfx_card.update_action(
                self.gfx_secondary_button,
                text="Uninstall",
                payload={"action": "gfx1013_bazzite_uninstall", "governor": ""},
                visible=installed,
            )
            status_button = (
                self.gfx_tertiary_button if installed else self.gfx_secondary_button
            )
            self.gfx_card.update_action(
                status_button,
                text="Check status" if installed else "Open upstream project",
                payload={
                    "action": "gfx1013_bazzite_status"
                    if installed
                    else "bazzite_async_upstream",
                    "governor": "",
                },
            )
            self.gfx_card.update_action(
                self.gfx_quaternary_button,
                text="Open upstream project",
                payload={"action": "bazzite_async_upstream", "governor": ""},
                visible=installed,
            )
            # Only while the reviewed driver is in place but not always-on:
            # a damaged install needs Repair first, and an enabled one needs
            # neither the command nor a launch option.
            per_game = bool(gfx_state.get("bazzite_async_current")) and not bool(
                gfx_state.get("bazzite_async_enabled")
            )
            self.bazzite_enable_row.setVisible(per_game)
            self.bazzite_launch_row.setVisible(per_game)
        elif (
            _mapping(gfx_state.get("radv_async")).get("supported")
            and not bool(gfx_state.get("masta_async_compute_ready"))
        ):
            # Linux 7.2 or newer on the Arch family or Fedora: the patched RADV
            # alone, on the stock amdgpu that Bazzite's async-compute release uses.
            self._gfx_source_offered = True
            self._render_radv_async(
                _mapping(gfx_state.get("radv_async")),
                _mapping(gfx_state.get("source")),
                # Its uninstall runs DryhoppedIPA's Fedora-only installer.
                dryhopped_installed=reason_key == "fedora-upstream-managed"
                and bool(gfx_state.get("dryhopped_installed")),
                fedora=reason_key == "fedora-upstream-managed",
            )
        elif (
            _mapping(gfx_state.get("source")).get("supported")
            and not bool(gfx_state.get("masta_async_compute_ready"))
        ):
            # The independent source build: DryhoppedIPA's V33 patches for the
            # running kernel plus the patched RADV, beside the stock driver.
            self._gfx_source_offered = True
            self._render_gfx1013_source(_mapping(gfx_state.get("source")), masta_supported)
        elif (
            bool(kernel_upgrade.get("offered"))
            and bool(_mapping(gfx_state.get("source")).get("hide_offer"))
        ):
            # Debian 13: kernel 6.12 and Mesa 25.0 cannot drive the GPU, so the
            # desktop runs on the CPU. The backports kernel is the way out.
            self._render_debian_kernel(kernel_upgrade)
        else:
            if masta_supported:
                if not bool(gfx_state.get("masta_async_compute_ready")):
                    self.gfx_card.set_status("Available in stack below", "blue")
                    self.gfx_card.detail.setText(
                        tr(
                            "Use the matched MastaG kernel and Mesa buttons below. Installing only one half can hang the GPU."
                        )
                    )
            self.gfx_card.update_action(
                self.gfx_primary_button,
                text="View original GFX1013 project"
                if masta_supported
                else "Open upstream manual path",
                payload={"action": "gfx1013_upstream", "governor": ""},
            )

        fsr4 = _mapping(tools.get("fsr4"))
        fsr4_available = bool(fsr4.get("installer_available"))
        fsr4_installed = bool(fsr4.get("installed"))
        fsr4_current = bool(fsr4.get("current"))
        fsr4_state = str(fsr4.get("state") or "not-installed")
        self._fsr4_launch_option = str(fsr4.get("steam_launch_option") or "")
        self.fsr4_card.set_scope("All distributions · per game · no root", "purple")
        if fsr4_current:
            status, tone = ("Open" if fsr4.get("running") else "Ready"), "green"
            detail = tr(
                "Open the client, choose Scan Games, select games and press Install / update selected. "
                "Then add the launch option below to each game in Steam. Restore / recover selected undoes it."
            )
        elif fsr4_state == "invalid":
            status, tone = "Repair required", "orange"
            detail = tr("The client folder is incomplete or was changed. Reinstall it; your game backups are kept.")
        elif fsr4_state == "update-available":
            status, tone = "Update available", "blue"
            detail = tr("A newer BC250 build of the client is available. Updating keeps your games and backups.")
        elif fsr4_state == "other-version":
            status, tone = "Other version selected", "blue"
            detail = tr("The selected client build is not installed yet. Install brings it in; your games and backups are kept.")
        elif not fsr4_available:
            status, tone = "Unavailable", "gray"
            detail = tr("The client is built for x86_64 Linux only.")
        else:
            status, tone = "Not installed", "gray"
            detail = tr(
                "Downloads the pinned BC250 release, checks every file, and installs it in your user folder. "
                "Then open it and pick your games."
            )
        self.fsr4_card.set_status(status, tone)
        self.fsr4_card.detail.setText(detail)
        self._fsr4_view = {
            "state": fsr4, "status": status, "tone": tone, "detail": detail,
            # The build in use, not the one picked for the next install.
            "version": str(fsr4.get("version") or "") if fsr4_current else "",
        }
        self.fsr4_card.update_action(
            self.fsr4_install_button,
            text="Repair FSR4 client" if fsr4_state == "invalid"
            else "Update FSR4 client" if fsr4_state == "update-available"
            else "Reinstall" if fsr4_current
            else "Install FSR4",
            enabled=fsr4_available,
            visible=fsr4_available,
        )
        self.fsr4_card.update_action(
            self.fsr4_launch_button,
            text="Open OptiScaler Client",
            visible=fsr4_current,
            enabled=not fsr4.get("running"),
        )
        self.fsr4_card.update_action(
            self.fsr4_steam_all_button,
            text="Add to every Steam game",
            visible=fsr4_current,
        )
        self.fsr4_card.update_action(
            self.fsr4_remove_button, text="Remove", visible=fsr4_installed,
        )
        self.fsr4_card.update_action(
            self.fsr4_legacy_button,
            text="Remove old FSR4 V3 runtime",
            visible=bool(fsr4.get("legacy_v3_installed")),
        )
        self.fsr4_upstream_button.show()
        games = [dict(game) for game in fsr4.get("games") or () if isinstance(game, Mapping)]
        self._render_fsr4_games(games if FSR4_UI_ENABLED and fsr4_current else [])

        self._render_helixsr(_mapping(tools.get("helixsr")))
        self._render_upscaling()

        self._render_accessories(_mapping(tools.get("accessories")))

        quick = _mapping(tools.get("quick_access"))
        if quick:
            ready = bool(quick.get("ready"))
            decky_detected = bool(quick.get("decky_detected"))
            decky_frontend_compatible = bool(
                quick.get("decky_frontend_compatible", True)
            )
            self.decky_card.detail.setText(
                tr(
                    "Quick Access is ready. Restart Game Mode or reload Decky if the panel is not visible yet."
                    if ready
                    else "Decky must be updated because this Steam client uses the renamed initialization API."
                    if decky_detected and not decky_frontend_compatible
                    else "Decky is detected, but the BC250 Quick Access plugin or its protected helper needs installation or repair."
                    if decky_detected
                    else "Decky is optional. It is never installed by generic dependency preparation."
                )
            )
        self._apply_compatibility_filter()
