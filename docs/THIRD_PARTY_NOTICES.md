# Third-party notices

BC250 Control Center is MIT-licensed and does not claim ownership of any project listed here. This notice mirrors the **Official repositories** panel in the desktop application: 38 entries in total, consisting of this project and the 37 external sources below.

Every canonical URL was checked and returned HTTP 200: on 29 August 2026, and the boot logo reference on 25 September 2026. A link or reference does not mean that its code is packaged, executed or endorsed by BC250 Control Center.

## Integration boundary

- **Integrated** means the application can install, invoke or package a reviewed upstream component through an explicit user action.
- **Reference** means it is shown for provenance or compatibility research only. It is not automatically downloaded, built or run.
- **External install** means the user explicitly opts into an upstream package, repository, kernel, module or image; it remains outside the BC250 package.


## Sources

| Source | Role in BC250 Control Center | Boundary |
|---|---|---|
| [cyan-skillfish-governor](https://github.com/filippor/cyan-skillfish-governor/tree/smu) | GPU governor | Integrated; MIT upstream |
| [Oberon Governor](https://gitlab.com/mothenjoyer69/oberon-governor) | Alternative GPU governor | Integrated when selected; MIT upstream |
| [bc250_smu_oc](https://github.com/bc250-collective/bc250_smu_oc) | CPU SMU detection and tuning | Reviewed bundled snapshot; MIT upstream |
| [bc250-cu-live-manager](https://github.com/WinnieLV/bc250-cu-live-manager) | Standard CU topology workflow | Integrated runtime fetch; no license grant recorded |
| [bc250-cu-live-manager-SteamOS](https://github.com/F5GO/bc250-cu-live-manager-SteamOS) | SteamOS CU topology workflow | Integrated runtime fetch; no license grant recorded |
| [bc250-40cu-unlock](https://github.com/duggasco/bc250-40cu-unlock) | 40 CU research | Reference only |
| [bc250-core-unlock](https://github.com/rw-r-r-0644/bc250-core-unlock) | Experimental CPU core unlock | Integrated explicit workflow; MIT upstream |
| [bc250-steamos](https://github.com/keyboardspecialist/bc250-steamos) | SteamOS AMDGPU and RADV compatibility | Integrated explicit workflow |
| [bc250-gfx1013-fix](https://github.com/DryhoppedIPA/bc250-gfx1013-fix) | GFX1013 compute queue, kernel and Mesa/RADV stack | External install; Control Center updates official `main`, applies only the reviewed Fedora 44 RPM 6 source-path compatibility repair when its exact upstream line is present, and invokes the complete upstream lifecycle after local safety gates |
| [bc250-async-compute-bazzite](https://github.com/tri3gubki-ops/bc250-async-compute-bazzite) | Separate GFX1013 async-compute RADV for Bazzite 44 | Integrated explicit release workflow; v0.2.4 archive and SHA-256 are pinned, Bazzite/BC-250/OGC-kernel gates are enforced, and system Mesa is not replaced; MIT upstream |
| [bc250-steamos-real-toolkit](https://github.com/rpf16rj/bc250-steamos-real-toolkit) | SteamOS ASIC fallback research | Reference only |
| [bc250-toolkit](https://github.com/redbeard1083/bc250-toolkit) | Community toolkit research; its installed files are detected read-only so overlapping ownership of shared services and configuration can be reported | Reference only; never downloaded, executed or modified |
| [Latest Bazzite AMD BC-250 Patched Images](https://github.com/62fixolab/Latest-Bazzite-AMD-BC-250-Patched-Images) | Bazzite image reference | Reference only |
| [linux-cachyos-bc250](https://github.com/MastaG/linux-cachyos-bc250) | Matched Arch/CachyOS BC-250 kernel and Mesa/RADV with GFX1013 async-compute fixes | Integrated explicit opt-in repository; GPL-2.0 upstream; Manjaro is not enabled |
| [bc250-fsr4-fork](https://github.com/daniel-h-0/bc250-fsr4-fork) | FSR4 INT8 for BC-250 through the BC250 build of OptiScaler Client (GPL-3.0-or-later, by Agustín Montaña and contributors; BC250 additions MIT) with OptiScaler and OptiPatcher downloaded by the client from their pinned upstream locations | Integrated per-user workflow: release `opticlient-v1.0.7-bc250.3` is downloaded at runtime, verified against its published SHA-256 and its internal SHA256SUMS, installed under the user's data folder and opened from Control Center; nothing is redistributed |
| [bc250-fsr4](https://github.com/dmorazasanchez/bc250-fsr4) | Superseded by the OptiScaler Client route above; only its uninstaller is still offered. FSR4 V3 per-game RADV runtime; registered in the shared external-tool manifest, and redistribution stays gated because upstream declares no license | Integrated per-user workflow using official branch `v3`; Fedora 44, Bazzite and Debian/Ubuntu build it reproducibly in the upstream Fedora 44 container with rootless Podman, Fedora requires the repaired GFX1013 boot, and Manjaro remains ABI-gated experimental |
| [BC250-Telemetry](https://github.com/onlinermm/BC250-Telemetry) | CPU/GPU VRM temperature source | Integrated passive read; Control Center never installs or drives this daemon, it only reads its public `/run/apu_telemetry.json` snapshot when present; MIT upstream |
| [bc250-memory-temperature](https://github.com/pan-Rijovich/bc250-memory-temperature) | GDDR6 per-chip memory (VRAM) temperature via SMU/UMC | Integrated explicit workflow behind an inspection window with mandatory confirmation; reverse-engineered and not fully verified by its own author — see the in-app warning; MIT upstream |
| [bc250-batocera-tools](https://github.com/tmghd272/bc250-batocera-tools) | Batocera compatibility research | Reference only |
| [bc250-acpi-fix](https://github.com/e-tho/bc250-acpi-fix) | ACPI compatibility fix | Integrated explicit compatibility workflow; MIT upstream |
| [bc250-acpi-fix-updated-8c](https://github.com/mendesrr/bc250-acpi-fix-updated-8c) | 8-core ACPI research | Reference only |
| [BC250-Native-Mesh-Shaders-](https://github.com/lonewolf0622/BC250-Native-Mesh-Shaders-) | Native mesh shader research | Reference only |
| [bc250_memcfg](https://github.com/fanoush/bc250_memcfg) | CMOS VRAM (UMA_SIZE) configuration | Integrated explicit workflow; CMOS offsets reimplemented in Python from the published layout, memory timing straps are read back unmodified and never exposed; MIT upstream |
| [bc250-efi-core-unlock](https://github.com/Hexxeh/bc250-efi-core-unlock) | EFI core unlock research | Reference only |
| [AMD BC-250 UEFI Firmware Menu Script](https://github.com/Forbidden-Darkness/AMD-BC-250-UEFI-v2.2-Firmware-Menu-Script) | UEFI Shell 2.2 the BIOS update USB boots, the MeiMeiDXE v3 images (P3.00 with eight cores unlocked, 16 boot logos) and the AFU build and flags they are flashed with | Integrated explicit workflow on the Firmware (BIOS) page: files are downloaded at runtime from one pinned commit, verified against pinned SHA-256 values and written only to the USB drive the user confirms; nothing is redistributed or flashed by Control Center |
| [bc250-bios](https://gitlab.com/TuxThePenguin0/bc250-bios) | Stock P3.00 and the P3.00 Chipset Menu BIOS (the community default) | Integrated explicit workflow on the Firmware (BIOS) page: downloaded at runtime from one pinned commit and verified against pinned SHA-256 values; nothing is redistributed |
| [BC-250](https://github.com/kenavru/BC-250) | Mirror of ASRock's 4U12G BIOS update kit (AFU flasher, official P5.00 image and its flash command) and the P2.00 image | Integrated explicit workflow on the Firmware (BIOS) page: downloaded at runtime from one pinned commit and verified against pinned SHA-256 values; nothing is redistributed |
| [bc250-custom-bios-logo](https://github.com/tmghd272/bc250-custom-bios-logo) | Custom boot logo research: its ROM, made with AMI's ChangeLogo, was compared with the images Control Center builds on the Firmware (BIOS) page, and its 672 × 378 recommendation matches the MeiMeiDXE logos | Reference only; its ROM and ChangeLogo.exe are never downloaded, run or redistributed by Control Center |
| [nct6687d](https://github.com/Fred78290/nct6687d) | NCT sensor and PWM driver | Integrated explicit kernel-module workflow; GPL-2.0 upstream |
| [USB-WiFi](https://github.com/morrownr/USB-WiFi) | USB Wi-Fi compatibility reference | Reference only |
| [CUPS](https://github.com/OpenPrinting/cups) | Printing compatibility reference | Reference only |
| [ipp-usb](https://github.com/OpenPrinting/ipp-usb) | USB printing reference | Reference only |
| [system-config-printer](https://github.com/OpenPrinting/system-config-printer) | Printer configuration reference | Reference only |
| [foomatic-db](https://github.com/OpenPrinting/foomatic-db) | Printer database reference | Reference only |
| [PAPPL](https://github.com/michaelrsweet/pappl) | Printing framework reference | Reference only |
| [pappl-retrofit](https://github.com/OpenPrinting/pappl-retrofit) | Legacy printer support reference | Reference only |
| [BlueZ](https://github.com/bluez/bluez) | Bluetooth compatibility reference | Reference only |
