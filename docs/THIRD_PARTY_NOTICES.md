# Third-party notices

BC250 Control Center is released under the [MIT License](../LICENSE). It builds on software, research and documentation published by other people. This document lists every third-party component the application ships, downloads, builds, installs or refers to, under which license, and how far the integration goes.

BC250 Control Center does not claim ownership of any project listed here, and a link does not mean that the project endorses this application or that its code is packaged with it. The list matches the **Official repositories** panel in the application. All links were last checked on 21 October 2026.

AMD, Radeon, NVIDIA, DLSS, Steam, SteamOS and the other names used here are trademarks of their respective owners. BC250 Control Center is not affiliated with any of them.

## Contents

1. [Distributed with BC250 Control Center](#1-distributed-with-bc250-control-center)
2. [Downloaded or built on the user's computer](#2-downloaded-or-built-on-the-users-computer)
3. [External installs](#3-external-installs)
4. [References](#4-references)
5. [License notes](#5-license-notes)

### Integration levels

- **Distributed**: included in the BC250 Control Center packages and source tree, with its license notice.
- **Downloaded at runtime**: fetched from its upstream location only after the user starts the workflow, pinned to a reviewed version and checked by SHA-256 where upstream publishes a fixed artifact. Not redistributed.
- **External install**: an upstream package, repository, kernel or module that the user opts into. It stays outside the BC250 Control Center package and is managed by its own project.
- **Reference**: listed for provenance, compatibility research or detection only. Never downloaded, built or run by the application.

## 1. Distributed with BC250 Control Center

| Component | Version | License | Location in this repository |
|---|---|---|---|
| [bc250_smu_oc](https://github.com/bc250-collective/bc250_smu_oc) | Commit `327014d`, with two audited local patches (see below) | MIT | `privileged/lib/bc250_smu_oc_vendor.zip` (contains `LICENSE`, `UPSTREAM_COMMIT` and `BC250CC_PATCHES`) |
| [bc250-acpi-fix](https://github.com/e-tho/bc250-acpi-fix) | Release `v1.1.1` early CPIO, SHA-256 checked | MIT | `privileged/lib/acpi_payload.py` (license in the file header) |
| [BC250-Telemetry](https://github.com/onlinermm/BC250-Telemetry) photos | The four photos of `hardware.md`, resized and without camera metadata | MIT | `assets/telemetry-i2c/` (license in `LICENSE`) |
| [@decky/api](https://github.com/SteamDeckHomebrew/loader-api) | 1.1.3 | LGPL-2.1 | Bundled in `integrations/decky/bc250-quick-access/dist/index.js` |
| [react-icons](https://github.com/react-icons/react-icons) | 5.7.0 | MIT; Font Awesome Free icons under CC BY 4.0, Lucide icons under ISC | Bundled in `integrations/decky/bc250-quick-access/dist/index.js` |
| [Nayuki QR Code generator](https://github.com/nayuki/QR-Code-generator) | Commit `bcfe1b0` | MIT | `src/bc250cc/_vendor/qrcodegen.py`, including its original license notice |

**bc250_smu_oc local patches.** (1)  The payload holds the PCI configuration lock across each complete `0xB8`/`0xBC` indirect SMU transaction, so that another SMU client such as the Cyan governor cannot move the shared address register between the address and data accesses. The patch follows [keyboardspecialist/bc250-steamos](https://github.com/keyboardspecialist/bc250-steamos/blob/master/smu-oc-patches/0001-transaction-level-flock.patch). The root helper refuses the payload unless its SHA-256 and upstream commit match the reviewed build. (2) The mailbox waits for the SMU's answer for up to five seconds, 1 ms apart, instead of reading the response register 100 times with no pause, which reported a valid command the firmware had not answered yet as status `0x00`; it raises a timeout error when nothing answers. It follows [keyboardspecialist/bc250-steamos](https://github.com/keyboardspecialist/bc250-steamos/blob/master/smu-oc-patches/0004-time-based-mailbox-timeout.patch) (Unlicense).

**Reimplemented, not copied.** The CMOS offsets used for the VRAM size come from the layout published by [bc250_memcfg](https://github.com/fanoush/bc250_memcfg) (MIT) and are reimplemented in Python; memory timing straps are read back unmodified and never exposed. The SteamOS ACPI and boot-option routes, the HDMI AC-3 profile selection and the two HDMI-CEC automations (wake the TV at session start, standby on power-off) follow or are ported from [bc250-steamos](https://github.com/keyboardspecialist/bc250-steamos), which is in the public domain (Unlicense).

## 2. Downloaded or built on the user's computer

None of these components is redistributed with BC250 Control Center. Each is fetched from its upstream location when the user starts the corresponding workflow.

### GPU

**[cyan-skillfish-governor](https://github.com/filippor/cyan-skillfish-governor/tree/smu)** (MIT). The GPU governor. Installed as upstream publishes it: the official `v0.4.14` release binary, checked by SHA-256, or the same commit (`7b08fdc`) built unmodified where the C library is older than glibc 2.39. Up to 1.21.1 Control Center built it with a patch of its own; Prepare BC250 system now replaces that build.

**[Oberon Governor](https://gitlab.com/mothenjoyer69/oberon-governor)** (MIT). Alternative GPU governor, installed when the user selects it.

**[bc250-steamos](https://github.com/keyboardspecialist/bc250-steamos)** (public domain, Unlicense). SteamOS AMDGPU and RADV compatibility, run through an explicit workflow.

**[bc250-async-compute-bazzite](https://github.com/tri3gubki-ops/bc250-async-compute-bazzite)** (MIT). Separate GFX1013 async-compute RADV for Bazzite 44. Release `v0.2.4` is pinned with its SHA-256; Bazzite, BC-250 and OGC-kernel checks are enforced and the system Mesa is not replaced. On Arch, CachyOS and Fedora with kernel 7.2 or newer, its two RADV patches (reviewed commit `56bf06b`) are built against Mesa 26.2.3 and installed beside the system Mesa.

### Upscaling

**[bc250-fsr4-fork](https://github.com/daniel-h-0/bc250-fsr4-fork)** (OptiScaler Client: GPL-3.0-or-later by Agustín Montaña and contributors; BC250 additions MIT). FSR4 INT8 per game through the BC250 build of OptiScaler Client. Release `opticlient-v1.0.7-bc250.5` is downloaded, verified against its published SHA-256 and its internal `SHA256SUMS`, installed under the user's data folder and opened from Control Center. The client downloads OptiScaler and OptiPatcher from their own pinned upstream locations.

**[HelixSR](https://github.com/lonewolf0622/HelixSR)** (HelixSR Freeware License for the DLL; the setup scripts are Apache-2.0 up to 1.8.1 and covered by the freeware license from 1.9, which allows running them unmodified). DLSS Model E reconstruction behind an FSR 3.1 DLL, per game. Not affiliated with NVIDIA or AMD.

- Release `v1.8.1` is the default. The user can pick an older reviewed release, `v2.0.0` (reviewed), or a newer release or pre-release from GitHub's release list; 1.9.x, listed on 19 October 2026, are offered as not reviewed.
- Archives and DLLs are verified against pinned SHA-256 values. For a release newer than the reviewed ones, the SHA-256 that GitHub publishes for the archive is used.
- The release is unpacked unmodified under the user's data folder. Its own setup builds the network on the user's computer from NVIDIA's DLSS DLL, after the user agrees in the terminal. These NVIDIA-derived files never leave the computer.
- In 2.0.0 the DLL is in `HelixSR-fsrfg`; the network is built with `--no-fg`, and DLSS frame generation separately with `--fg-only` (the setup asks before each download from NVIDIA).
- HelixSR Scaler, HelixSR's own OptiScaler build (GPL-3.0, shipped in the release), is installed per Steam game through the release's own bridge, never over another OptiScaler.
- Per game, the original FSR 3.1 DLL is kept as `*.original.dll` and restored on removal. In games where OptiScaler Client installed OptiScaler, HelixSR can instead go into a `HelixSR` folder beside it, with `OptiScaler.ini` pointed at it; the previous `OptiScaler.ini` is saved and restored byte for byte, so the client's own records stay valid.

**[bc250-fsr4](https://github.com/dmorazasanchez/bc250-fsr4)** (no license in the reviewed revision; upstream added the MIT License on 10 September 2026 in `fd4e9dc`, documentation only). FSR4 V3 per-game RADV runtime, superseded by OptiScaler Client; only its uninstaller is still offered. It used the official `v3` branch, built reproducibly in the upstream Fedora 44 container with rootless Podman on Fedora 44, Bazzite, Debian and Ubuntu; Fedora required the repaired GFX1013 boot, and Manjaro remained an ABI-gated experiment. As nothing of it is redistributed, the pin was left at the reviewed code.

### CPU and Compute Units

**[bc250-core-unlock](https://github.com/rw-r-r-0644/bc250-core-unlock)** (MIT). Experimental CPU core unlock, run through an explicit workflow.

**[bc250-cu-live-manager](https://github.com/WinnieLV/bc250-cu-live-manager)** and **[bc250-cu-live-manager-SteamOS](https://github.com/F5GO/bc250-cu-live-manager-SteamOS)** (no license grant recorded). Compute Unit topology workflows for standard distributions and for SteamOS, fetched at runtime.

### Sensors and telemetry

**[BC250-Telemetry](https://github.com/onlinermm/BC250-Telemetry)** (MIT). Source of the CPU and GPU VRM readings. Control Center reads its public `/run/apu_telemetry.json` snapshot and, from **Settings › Telemetry**, can install the daemon alone after confirmation: the pinned revision is built on the computer and installed as `apu-telemetry.service`. Its web server, fan module and GDDR6 collector are not installed, and a service installed by upstream's own installer is never replaced or removed. The daemon reads the PMIC over I2C and writes only the PMBus page selector. The photos in the I2C guide are listed in [section 1](#1-distributed-with-bc250-control-center).

**[bc250-memory-temperature](https://github.com/pan-Rijovich/bc250-memory-temperature)** (MIT). GDDR6 temperature per chip through the SMU and UMC. Reverse-engineered and not fully verified by its own author, as the in-app warning explains; installed only after an inspection window and a mandatory confirmation. Reviewed revision `4a2221d` (bounded UMC waits, chip-index validation, packed reads, SMU firmware check in `patch_smu.py`) is run unmodified. The first payload (`b7e6bff`) is replaced in place, unless BC250-Telemetry's collector, which bundles it, is installed.

**[nct6687d](https://github.com/Fred78290/nct6687d)** (GPL-2.0). NCT sensor and PWM kernel module, built and loaded through an explicit workflow.

### Video and HDMI

**[bc250-encoding-decoding-fix](https://github.com/simpmix/bc250-encoding-decoding-fix)** (GPL-3.0-only). VA-API driver for hardware video: H.264 and HEVC encoding on the GPU's compute units and decoding on the CPU, for Sunshine, OBS, Steam Remote Play, ffmpeg and browsers. From the Compatibility tab, the source at commit `b8de980` (v0.5.2) is fetched, checked by SHA-256 and built on the user's computer in a Fedora container without libx264, installed under `/var/lib/bc250-control-center/vaapi` and enabled through `environment.d` and `profile.d` files. An optional 32-bit companion (SteamOS, Arch, CachyOS, Manjaro) is built the same way, and a per-user Flatpak override lets sandboxed applications use it.

**[linux-cec](https://gitlab.steamos.cloud/holo/linux-cec)** (LGPL-2.1-or-later; linux-cec-sys: BSD-3-Clause). cecd, Valve's HDMI-CEC daemon: the TV turns on with the computer, sleeps on suspend and its remote works as input. The Drivers tab adds a remote window (TV and receiver power, input, volume) that talks to cecd over D-Bus. SteamOS ships cecd, so only a configuration fragment is written there. Elsewhere, commit `2b7a801` (cecd 0.3.0) is fetched and built on the user's computer, natively with Rust 1.87 or newer (Arch, CachyOS, Manjaro, Fedora) or in the official `rust:1.90-slim-bookworm` image (Bazzite, and Debian or Ubuntu releases with an older Rust), then run from the user's data folder as a user service with upstream's two uaccess udev rules.

### Firmware

All BIOS files are downloaded from one pinned commit per source, verified against pinned SHA-256 values and written only to the USB drive the user confirms. Control Center never flashes the board itself.

**[bc250-bios](https://gitlab.com/TuxThePenguin0/bc250-bios)**. Stock P3.00 and the P3.00 Chipset Menu BIOS, the community default.

**[AMD BC-250 UEFI Firmware Menu Script](https://github.com/Forbidden-Darkness/AMD-BC-250-UEFI-v2.2-Firmware-Menu-Script)**. The UEFI Shell 2.2 that the update USB boots, the MeiMeiDXE v3 images (P3.00 with eight cores unlocked, 16 boot logos) and the AFU build and flags used to flash them.

**[BC-250](https://github.com/kenavru/BC-250)**. Mirror of ASRock's 4U12G BIOS update kit (AFU flasher, the official P5.00 image and its flash command) and the P2.00 image.

## 3. External installs

**[bc250-gfx1013-fix](https://github.com/DryhoppedIPA/bc250-gfx1013-fix)**. GFX1013 compute queue, kernel and Mesa/RADV stack. External install; Control Center updates official `main`, applies only the reviewed Fedora 44 RPM 6 source-path compatibility repair when its exact upstream line is present, and runs the complete upstream lifecycle after local safety checks.

**[linux-cachyos-bc250](https://github.com/MastaG/linux-cachyos-bc250)** (GPL-2.0). Matched Arch and CachyOS kernel and Mesa/RADV with GFX1013 async-compute fixes, plus the Proton BC-250 builds (proton-cachyos-native-bc250, protonge-latest-bc250, proton-cachyos-slr-bc250), added as an opt-in unsigned package repository. The BC-250 toolkit by redbeard1083 (https://github.com/redbeard1083/bc250-toolkit) was the reference for the Proton packages. Not enabled on Manjaro.

**[kisak-mesa PPA](https://launchpad.net/~kisak/+archive/ubuntu/kisak-mesa)**. Mesa 26.1 or newer for Ubuntu and its derivatives, so that the desktop is drawn by the BC-250 GPU instead of the CPU. Offered on the Compatibility tab only where Mesa is older than 26.1, and after confirmation. The source and its signing key are added in separate files under `/etc/apt`; the key is refused unless its fingerprint is `EB8B81E14DA65431D7504EA8F63F0F2B90935439`, and only the Mesa packages (and their 32-bit counterparts when present) are installed from it.

## 4. References

Listed for provenance or compatibility research. None of these is downloaded, built or run by the application.

**BC-250 projects**
- [bc250-40cu-unlock](https://github.com/duggasco/bc250-40cu-unlock): 40 CU research (archived upstream)
- [bc250-efi-core-unlock](https://github.com/Hexxeh/bc250-efi-core-unlock): EFI core unlock; its installation is detected read-only to report whether a core unlock survives a power-off
- [bc250-acpi-fix-updated-8c](https://github.com/mendesrr/bc250-acpi-fix-updated-8c): 8-core ACPI research
- [bc250-steamos-real-toolkit](https://github.com/rpf16rj/bc250-steamos-real-toolkit): SteamOS ASIC fallback research
- [bc250-toolkit](https://github.com/redbeard1083/bc250-toolkit): community toolkit; its installed files are detected read-only so that overlapping ownership of shared services and configuration can be reported, and are never modified
- [Latest Bazzite AMD BC-250 Patched Images](https://github.com/62fixolab/Latest-Bazzite-AMD-BC-250-Patched-Images): Bazzite image reference
- [bc250-batocera-tools](https://github.com/tmghd272/bc250-batocera-tools): Batocera compatibility research
- [BC250-Native-Mesh-Shaders-](https://github.com/lonewolf0622/BC250-Native-Mesh-Shaders-): native mesh shader research
- [bc250-custom-bios-logo](https://github.com/tmghd272/bc250-custom-bios-logo): boot logo research; its ROM, made with AMI's ChangeLogo, was compared with the images Control Center builds, and its 672 × 378 recommendation matches the MeiMeiDXE logos. Its ROM and ChangeLogo.exe are never downloaded, run or redistributed
- [bc250-vrm-dkms](https://github.com/Hexxeh/bc250-vrm-dkms) (GPL-2.0 as reported by GitHub): VRM temperature as a kernel module; listed in the integration catalog without automation, pinned to upstream `main` when it was listed, not code-reviewed
- [bc250-memory-dkms](https://github.com/Hexxeh/bc250-memory-dkms) (GPL-2.0 as reported by GitHub): GDDR6 temperature as a kernel module; same terms as the VRM module

**Drivers and system components**
- [USB-WiFi](https://github.com/morrownr/USB-WiFi): USB Wi-Fi compatibility
- [BlueZ](https://github.com/bluez/bluez): Bluetooth
- [CUPS](https://github.com/OpenPrinting/cups), [ipp-usb](https://github.com/OpenPrinting/ipp-usb), [system-config-printer](https://github.com/OpenPrinting/system-config-printer), [foomatic-db](https://github.com/OpenPrinting/foomatic-db), [PAPPL](https://github.com/michaelrsweet/pappl) and [pappl-retrofit](https://github.com/OpenPrinting/pappl-retrofit): printing

## 5. License notes

- **MIT and public-domain components distributed with the application** carry their original notices in the locations listed in [section 1](#1-distributed-with-bc250-control-center).
- **@decky/api (LGPL-2.1)** is bundled unmodified in the Decky plugin. Its source is available from its upstream project, and the plugin's own source is in `integrations/decky/bc250-quick-access/src`, so the plugin can be rebuilt against a modified version of the library.
- **GPL and LGPL software other than @decky/api** (OptiScaler Client, HelixSR Scaler, bc250-encoding-decoding-fix, linux-cec, nct6687d, linux-cachyos-bc250) is never redistributed. It is downloaded from its upstream location and, where needed, built on the user's computer.
- **Projects without a license grant** (bc250-cu-live-manager and its SteamOS port, and the reviewed revision of bc250-fsr4) are only fetched from their upstream repositories at the user's request and never redistributed.
- **HelixSR** is used under the HelixSR Freeware License, which allows running the release unmodified. The network files that its setup derives from NVIDIA's DLSS DLL are created on, and stay on, the user's computer.
- **BIOS images and flashing tools** remain the property of their authors and of ASRock and AMI. Control Center only downloads them from the pinned sources above and writes them to a USB drive the user selects.

### QR pairing

[Nayuki QR Code generator](https://github.com/nayuki/QR-Code-generator) (MIT),
commit `bcfe1b018cec5f1f91b5705eca5bb4cdd34e9f8d`, is distributed in
`src/bc250cc/_vendor/qrcodegen.py`. Its original copyright and permission notice
are preserved; a file-level Ruff exemption was added and trailing whitespace removed. It generates the
Remote access pairing QR locally, with no network service or additional Python
package. The pinned source URL is in `QRCODEGEN_UPSTREAM` beside it.
