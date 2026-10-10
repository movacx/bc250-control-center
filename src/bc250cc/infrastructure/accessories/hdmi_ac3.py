"""Dolby Digital 5.1 over HDMI/DisplayPort: AC-3 encoded in real time.

HDMI audio carries 5.1 as plain PCM only when the receiver accepts
multichannel PCM; many soundbars and older receivers only take a compressed
stream. ALSA's ``a52`` plugin (alsa-plugins, encoding with FFmpeg's
libavcodec) turns six channels into an AC-3 stream, and PipeWire ships the
profile set that routes the HDMI ports through it (``hdmi-ac3.conf``, from
PulseAudio). What no system does on its own is pick that profile set for the
BC-250's audio function (PCI 1002:13ff).

This follows keyboardspecialist/bc250-steamos's hdmi-ac3 (public domain),
itself based on rpf16rj/bc250-steamos-real-toolkit's guide: a udev property
and a WirePlumber rule select the profile set, the HDMI sink stays open
between sounds (a receiver relocks on every new stream) and the encoder
buffers one 1536-sample AC-3 frame before playback starts. On top of it:
its own file names, every distribution with PipeWire and WirePlumber 0.5,
the distribution's packages for the encoder, and the encoder's ALSA
definition switched on where a distribution ships it switched off (the Arch
family leaves 60-a52-encoder.conf out of /etc/alsa/conf.d).
"""

from __future__ import annotations

import os
import re
import shlex
import shutil
from pathlib import Path

from ..steamos_readonly import STEAMOS_PASSWORD_GUARD
from ._shared import command_output, shell_header

REFERENCE = "https://github.com/keyboardspecialist/bc250-steamos/tree/main/hdmi-ac3"
MARKER = "# Managed by BC250 Control Center: HDMI AC-3 audio"
UDEV_RULE = Path("/etc/udev/rules.d/91-bc250-control-center-hdmi-ac3.rules")
WIREPLUMBER_NAME = "90-bc250-control-center-hdmi-ac3.conf"
KEEP_FILE = Path("/etc/atomic-update.conf.d/bc250-control-center-ac3.conf")
PROFILE_SET = Path("/usr/share/alsa-card-profile/mixer/profile-sets/hdmi-ac3.conf")
A52_SOURCE = Path("/usr/share/alsa/alsa.conf.d/60-a52-encoder.conf")
A52_LINK = Path("/etc/alsa/conf.d/60-a52-encoder.conf")
#: Written next to the link Control Center made, so removing takes back only
#: what it added (a distribution package may own the same path).
A52_LINK_RECORD = Path("/etc/bc250-control-center/hdmi-ac3-a52-link")
A52_PLUGIN_DIRS = ("/usr/lib/alsa-lib", "/usr/lib64/alsa-lib", "/usr/lib/x86_64-linux-gnu/alsa-lib")
A52_PLUGIN = "libasound_module_pcm_a52.so"
AUDIO_VENDOR, AUDIO_DEVICE = "0x1002", "0x13ff"
#: keyboardspecialist's toolkit switches the same profile on; never both.
FOREIGN_SYSTEM = (Path("/etc/udev/rules.d/91-bc250-hdmi-ac3.rules"),)
FOREIGN_USER_NAME = "90-bc250-hdmi-ac3.conf"
#: The encoder and the FFmpeg library it encodes with, per distribution.
#: Fedora ships the plugin on its own; Debian folds it into the plugins
#: package and older Ubuntu releases kept it apart as -extra.
PACKAGES = {
    "arch": ("alsa-plugins", "ffmpeg"),
    "manjaro": ("alsa-plugins", "ffmpeg"),
    "cachyos": ("alsa-plugins", "ffmpeg"),
    "fedora": ("alsa-plugins-a52",),
    "bazzite": ("alsa-plugins-a52",),
    "debian": ("libasound2-plugins",),
    "ubuntu": ("libasound2-plugins", "libasound2-plugins-extra"),
}
#: SteamOS ships the encoder, FFmpeg and the profile set in its image.
FAMILIES = frozenset(PACKAGES) | {"steamos"}
MIN_WIREPLUMBER = (0, 5)

UDEV_TEXT = f"""{MARKER}
# The BC-250's HDMI/DisplayPort audio function; card numbers change between boots.
SUBSYSTEM=="sound", KERNEL=="card*", ATTRS{{vendor}}=="{AUDIO_VENDOR}", ATTRS{{device}}=="{AUDIO_DEVICE}", ENV{{ACP_PROFILE_SET}}="hdmi-ac3.conf"
"""

WIREPLUMBER_TEXT = f"""{MARKER}
monitor.alsa.rules = [
  {{
    matches = [
      {{
        device.name = "~alsa_card.pci-.*"
        device.vendor.id = "{AUDIO_VENDOR}"
        device.product.id = "{AUDIO_DEVICE}"
      }}
    ]
    actions = {{
      update-props = {{
        device.description = "HDMI / DisplayPort"
        api.acp.disable-pro-audio = true
        device.profile-set = "hdmi-ac3.conf"
      }}
    }}
  }}
  {{
    # A receiver relocks on every new stream; keep the HDMI sink open for an hour.
    matches = [ {{ node.name = "~alsa_output.pci-.*hdmi.*" }} ]
    actions = {{ update-props = {{ session.suspend-timeout-seconds = 3600 }} }}
  }}
  {{
    # One AC-3 frame (1536 samples) buffered before playback starts.
    matches = [ {{ node.name = "~alsa_output.pci-.*hdmi.*", alsa.name = "~a52.*" }} ]
    actions = {{ update-props = {{ api.alsa.start-delay = 1536 }} }}
  }}
]
"""

#: Finds the BC-250's card and switches it between its stereo and AC-3
#: profiles. ``bc250_select <ac3|stereo>``: the AC-3 profile of the port the
#: stereo profile was on (hdmi-stereo-extra1 -> hdmi-ac3-surround-extra1), so
#: the sound stays on the same output.
_SELECT = r"""bc250_card() {
  pactl list cards 2>/dev/null | awk '
    /^Card #/ { name = "" }
    /^[[:space:]]+Name:/ { name = $2 }
    /device.product.id = "0x13ff"/ && name != "" { print name; exit }'
}
bc250_active_profile() {
  pactl list cards 2>/dev/null | awk -v target="$1" '
    /^Card #/ { selected = 0 }
    /^[[:space:]]+Name:/ { selected = ($2 == target) }
    selected && /^[[:space:]]+Active Profile:/ { sub(/^[^:]+:[[:space:]]*/, ""); print; exit }'
}
bc250_available_profiles() {
  pactl list cards 2>/dev/null | awk -v target="$1" -v kind="$2" '
    /^Card #/ { selected = 0 }
    /^[[:space:]]+Name:/ { selected = ($2 == target) }
    selected && $1 ~ ("^output:" kind) && /available: yes/ { sub(/:$/, "", $1); print $1 }'
}
bc250_select() {
  local want="$1" card="" active suffix target sink _
  for _ in $(seq 1 15); do card="$(bc250_card)"; [ -n "$card" ] && break; sleep 1; done
  [ -n "$card" ] || { echo "ERROR: the BC-250 HDMI/DisplayPort audio card was not found."; return 1; }
  active="$(bc250_active_profile "$card")"
  suffix="$(printf '%s\n' "$active" | sed -n 's/^output:hdmi-[a-z0-9-]*\(-extra[0-9]\+\)$/\1/p')"
  if [ "$want" = ac3 ]; then target="output:hdmi-ac3-surround$suffix"; kind="hdmi-ac3-surround"
  else target="output:hdmi-stereo$suffix"; kind="hdmi-stereo"; fi
  if ! bc250_available_profiles "$card" "$kind" | grep -qxF "$target"; then
    target="$(bc250_available_profiles "$card" "$kind" | head -n 1)"
  fi
  if [ -z "$target" ]; then
    echo "ERROR: no connected HDMI/DisplayPort output offers this profile. Is the display or receiver on?"
    return 1
  fi
  pactl set-card-profile "$card" "$target"
  sleep 1
  sink="$(pactl list sinks short | awk -v card="${card#alsa_card.}" 'index($2, card) { print $2; exit }')"
  if [ -n "$sink" ]; then pactl set-default-sink "$sink"; echo "[INFO] Default output: $sink"; fi
  echo "[INFO] Profile: $target"
}"""


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def wireplumber_path() -> Path:
    config = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(config) / "wireplumber" / "wireplumber.conf.d" / WIREPLUMBER_NAME


def _foreign_user_path() -> Path:
    return wireplumber_path().with_name(FOREIGN_USER_NAME)


def audio_function_present(root: Path = Path("/sys/bus/pci/devices")) -> bool:
    for device in root.glob("*"):
        if _read(device / "vendor").strip() == AUDIO_VENDOR and _read(device / "device").strip() == AUDIO_DEVICE:
            return True
    return False


def a52_plugin_present(dirs: tuple[str, ...] = A52_PLUGIN_DIRS) -> bool:
    return any((Path(directory) / A52_PLUGIN).is_file() for directory in dirs)


def receiver_takes_ac3(root: Path = Path("/proc/asound")) -> bool:
    """A connected sink whose EDID (ELD) lists AC-3 among its audio formats."""
    for eld in root.glob("card*/eld#*"):
        text = _read(eld)
        if re.search(r"^monitor_present\s+1", text, re.M) and re.search(r"coding_type\s+\S+\s+AC-3", text):
            return True
    return False


def wireplumber_version(output: str | None = None) -> tuple[int, int] | None:
    text = command_output(["wireplumber", "--version"]) if output is None else output
    match = re.search(r"libwireplumber (\d+)\.(\d+)", text)
    return (int(match[1]), int(match[2])) if match else None


def supported(family: str, *, version: tuple[int, int] | None = None,
              audio: bool | None = None) -> tuple[bool, str]:
    family = str(family or "").strip().lower()
    if not (audio if audio is not None else audio_function_present()):
        return False, "The BC-250 HDMI/DisplayPort audio function was not detected."
    if family not in FAMILIES:
        return False, "Offered on SteamOS, Bazzite, Arch, CachyOS, Manjaro, Fedora, Debian and Ubuntu."
    if version is None and not shutil.which("wireplumber"):
        return False, "PipeWire with WirePlumber is required; this system uses another sound server."
    version = version if version is not None else wireplumber_version()
    if version is not None and version < MIN_WIREPLUMBER:
        return False, "WirePlumber 0.5 or newer is required; this release ships an older one."
    if not PROFILE_SET.is_file():
        return False, "PipeWire's AC-3 profile set (hdmi-ac3.conf) is missing on this system."
    return True, ""


def inventory(family: str) -> dict:
    ok, reason = supported(family)
    base = {"supported": ok, "reason": reason, "device": receiver_takes_ac3(), "encoder": a52_plugin_present()}
    if not ok:
        return {**base, "state": "unsupported"}
    ours = UDEV_RULE.is_file() and MARKER in _read(UDEV_RULE) and wireplumber_path().is_file()
    foreign = any(path.exists() for path in FOREIGN_SYSTEM) or _foreign_user_path().is_file()
    if not ours:
        state = "managed-elsewhere" if foreign else "not-installed"
    elif not base["encoder"]:
        # Bazzite layered the encoder into the next deployment.
        state = "reboot-required"
    elif "hdmi-ac3" in command_output(["pactl", "get-default-sink"]):
        state = "active"
    else:
        state = "installed"
    return {**base, "state": state}


def _package_lines(family: str) -> list[str]:
    packages = " ".join(shlex.quote(item) for item in PACKAGES.get(family, ()))
    if family in {"arch", "manjaro", "cachyos"}:
        return [f"sudo pacman -S --needed --noconfirm {packages}"]
    if family == "fedora":
        return [f"sudo dnf install -y {packages}"]
    if family in {"debian", "ubuntu"}:
        # Install what this release offers: -extra only exists on older Ubuntu.
        return [
            "sudo apt-get update",
            f"for bc250_package in {packages}; do",
            '  if apt-cache policy "$bc250_package" 2>/dev/null | grep -q "Candidate: [^(]"; then',
            '    sudo apt-get install -y --no-install-recommends "$bc250_package"',
            "  fi",
            "done",
        ]
    if family == "bazzite":
        return [
            f"sudo rpm-ostree install --idempotent {packages}",
            "echo 'BC250_REBOOT_REQUIRED=1'",
        ]
    return ["echo 'ERROR: the AC-3 encoder is not part of this SteamOS image.'; exit 69"]


def _encoder_check() -> str:
    dirs = " ".join(shlex.quote(item) for item in A52_PLUGIN_DIRS)
    return (
        f"bc250_encoder=0; for bc250_dir in {dirs}; do "
        f'[ -f "$bc250_dir/{A52_PLUGIN}" ] && bc250_encoder=1; done'
    )


def _root_script(steamos: bool) -> str:
    """The system half, run once under sudo with the two texts as arguments."""
    record_dir = shlex.quote(str(A52_LINK_RECORD.parent))
    keep = shlex.quote(str(KEEP_FILE))
    rule = shlex.quote(str(UDEV_RULE))
    lines = [
        "set -eu",
        "umask 022",
        f"mkdir -p {shlex.quote(str(UDEV_RULE.parent))}",
        f"printf '%s' \"$1\" > {rule}",
        # The encoder's ALSA definition, only where nothing defines pcm.a52.
        f"if ! grep -qs '^pcm.a52' /etc/alsa/conf.d/*.conf && [ -f {shlex.quote(str(A52_SOURCE))} ]; then",
        f"  install -d -m 0755 /etc/alsa/conf.d {record_dir}",
        f"  ln -sfn {shlex.quote(str(A52_SOURCE))} {shlex.quote(str(A52_LINK))}",
        f"  printf '%s\\n' {shlex.quote(MARKER)} > {shlex.quote(str(A52_LINK_RECORD))}",
        "fi",
    ]
    if steamos:
        # SteamOS carries the listed /etc files over to the next image.
        lines += [
            f"mkdir -p {shlex.quote(str(KEEP_FILE.parent))}",
            f"printf '%s\\n' {shlex.quote(MARKER)} {shlex.quote(str(UDEV_RULE))} > {keep}",
            # The encoder link only when this application made it.
            f"if [ -f {shlex.quote(str(A52_LINK_RECORD))} ]; then printf '%s\\n' "
            f"{shlex.quote(str(A52_LINK))} {shlex.quote(str(A52_LINK_RECORD))} >> {keep}; fi",
        ]
    lines += [
        "udevadm control --reload-rules",
        "udevadm trigger --subsystem-match=sound || true",
    ]
    return "\n".join(lines)


def _foreign_guard() -> list[str]:
    system = " ".join(shlex.quote(str(path)) for path in FOREIGN_SYSTEM)
    rule = shlex.quote(str(UDEV_RULE))
    return [
        f'bc250_wp_dir="${{XDG_CONFIG_HOME:-$HOME/.config}}/wireplumber/wireplumber.conf.d"',
        f'for bc250_file in {system} "$bc250_wp_dir/{FOREIGN_USER_NAME}"; do',
        '  if [ -e "$bc250_file" ]; then',
        '    echo "ERROR: $bc250_file already switches the AC-3 profile on (another toolkit). Remove that installation first."',
        "    exit 65",
        "  fi",
        "done",
        f"if [ -e {rule} ] && ! grep -qxF {shlex.quote(MARKER)} {rule}; then",
        f"  echo 'ERROR: {UDEV_RULE} belongs to another tool; it was left untouched.'; exit 65",
        "fi",
    ]


def install_command(family: str) -> str:
    family = str(family or "").strip().lower()
    ok, reason = supported(family)
    if not ok:
        raise RuntimeError(reason)
    steamos = family == "steamos"
    commands = shell_header("HDMI audio · Dolby Digital 5.1 (AC-3)")
    if not receiver_takes_ac3():
        # Not a refusal: a receiver behind a TV or a switch may not report
        # its formats. But a display alone plays an AC-3 stream as silence.
        commands.append(
            "echo '[WARN] The connected display does not list Dolby Digital (AC-3). A monitor or TV "
            "without a decoder plays it as silence; Remove brings stereo back.'"
        )
    commands += [
        "for bc250_command in pactl systemctl sudo udevadm awk; do",
        '  command -v "$bc250_command" >/dev/null 2>&1 || { echo "ERROR: $bc250_command is required."; exit 69; }',
        "done",
        *_foreign_guard(),
        *((STEAMOS_PASSWORD_GUARD, "bc250_require_password") if steamos else ()),
        _encoder_check(),
        'if [ "$bc250_encoder" = 0 ]; then',
        "  echo '== Installing the AC-3 encoder (ALSA a52 plugin and FFmpeg) =='",
        *("  " + line for line in _package_lines(family)),
        "fi",
        _encoder_check(),
        'echo "== Selecting the AC-3 profile for the BC-250 audio function =="',
        (
            f"sudo sh -c {shlex.quote(_root_script(steamos))} bc250-hdmi-ac3 "
            f"{shlex.quote(UDEV_TEXT)}"
        ),
        'bc250_wp_dir="${XDG_CONFIG_HOME:-$HOME/.config}/wireplumber/wireplumber.conf.d"',
        'mkdir -p "$bc250_wp_dir"',
        f"printf '%s' {shlex.quote(WIREPLUMBER_TEXT)} > \"$bc250_wp_dir/{WIREPLUMBER_NAME}\"",
        'if [ "$bc250_encoder" = 0 ]; then',
        "  echo 'OK: the encoder is in the next deployment. Restart, then press Install again to switch the output to 5.1.'",
        "  exit 0",
        "fi",
        "systemctl --user restart wireplumber",
        _SELECT,
        "bc250_select ac3",
        "echo 'OK: Dolby Digital 5.1 (AC-3) is the HDMI output. Stereo sources still play as 5.1 from the front speakers.'",
    ]
    return "\n".join(commands)


def remove_command(family: str) -> str:
    family = str(family or "").strip().lower()
    rule = shlex.quote(str(UDEV_RULE))
    record = shlex.quote(str(A52_LINK_RECORD))
    link = shlex.quote(str(A52_LINK))
    root = "\n".join((
        "set -eu",
        f"if [ -e {rule} ] && grep -qxF {shlex.quote(MARKER)} {rule}; then rm -f {rule}; fi",
        # The encoder link only when this application made it.
        f"if [ -f {record} ] && [ -L {link} ]; then rm -f {link}; fi",
        f"rm -f {record}",
        f"if [ -e {shlex.quote(str(KEEP_FILE))} ] && grep -qxF {shlex.quote(MARKER)} {shlex.quote(str(KEEP_FILE))}; then rm -f {shlex.quote(str(KEEP_FILE))}; fi",
        "udevadm control --reload-rules",
        "udevadm trigger --subsystem-match=sound || true",
    ))
    commands = shell_header("HDMI audio · back to stereo")
    commands += [
        *((STEAMOS_PASSWORD_GUARD, "bc250_require_password") if family == "steamos" else ()),
        'bc250_wp="${XDG_CONFIG_HOME:-$HOME/.config}/wireplumber/wireplumber.conf.d/' + WIREPLUMBER_NAME + '"',
        f'if [ -e "$bc250_wp" ] && ! grep -qxF {shlex.quote(MARKER)} "$bc250_wp"; then',
        "  echo 'ERROR: the WirePlumber rule was changed by hand; it was left untouched.'; exit 65",
        "fi",
        'rm -f "$bc250_wp"',
        f"sudo sh -c {shlex.quote(root)}",
        "systemctl --user restart wireplumber",
        _SELECT,
        "bc250_select stereo || echo '[INFO] Stereo is chosen the next time the display is connected.'",
        # The encoder packages stay: other programs may use them.
        "echo 'OK: HDMI audio is back to stereo.'",
    ]
    return "\n".join(commands)
