# builders

These scripts create reviewable artifacts only; they never install packages,
modify the host, publish a release, or invoke hardware helpers.

- `scripts/build-tarball.sh [output-dir]` creates a deterministic source archive.
- `scripts/build-local-pkg.sh [output-dir]` creates an Arch-compatible local package.
- `scripts/build-rpm.sh [output-dir]` creates the single noarch RPM used by
  Fedora, Nobara and Bazzite/Fedora Atomic.
- `scripts/build-deb.sh [output-dir]` creates the Ubuntu/Debian `all` package.
- `scripts/build-release.sh [output-dir]` runs all four into `dist/<version>/`
  and writes `SHA256SUMS.txt`: the files a GitHub release carries. Without
  `dpkg-deb` it runs only that tool in a local `debian:trixie` podman image.

## Publishing a release 

1. Bump `VERSION`, the `version` of `integrations/decky/bc250-quick-access/package.json`
   and add a `<release>` to the AppStream metainfo (the builders refuse a mismatch).
2. Optionally draft the GitHub release `v<version>` with its notes. Leave it as
   a draft: the workflow publishes it once the packages are attached.
3. Commit and push to `main`, then push the tag:
   `git tag v<version> && git push origin v<version>`.
   `.github/workflows/release.yml` checks that the tag matches `VERSION`,
   builds the four packages and `SHA256SUMS.txt` with
   `packaging/scripts/build-release.sh` in an Arch container, and attaches
   them to the release (creating it with generated notes when there is no
   draft). Tags are always `v<version>`.
4. The application's update notice reads the latest published release, so it
   appears only once that release carries its packages.
5. `bash packaging/arch/aur/publish-aur.sh` prepares the AUR update of
   `bc250-control-center-git` (pkgver from the pushed `main`, `.SRCINFO`, commit);
   `--push` publishes it. It needs an SSH key registered on the AUR account.

To build the same files locally: `bash packaging/scripts/build-release.sh`
(Arch needs `rpm-tools`, `dpkg`, `zstd` and `python`).

Install the Debian artifact with
`sudo apt install ./bc250-control-center_*.deb`; APT resolves the PyQt6, Qt SVG,
psutil and polkit runtime packages. `dpkg -i` alone does not download missing
dependencies. If it leaves an installation unconfigured, run
`sudo apt --fix-broken install`.

Package upgrades remove the retired 1.18 `mvc/` application tree after the
new payload is installed. Package removal never deletes files from user home
directories; use the local uninstaller's explicit `--purge-user-data` option
when that cleanup is wanted.

The optional FSR4 V3 action is not a package dependency. On Fedora 44, Debian,
Ubuntu and their derivatives, Control Center installs missing source-build
tools with DNF or APT only after the user requests that action, builds the
official upstream `v3` branch in its Fedora 44 container with rootless Podman,
and installs only a per-user Vulkan ICD for explicitly selected games. Fedora
requires the repaired GFX1013 boot to be active first. The matching small
libdrm runtime is kept inside that private directory so distribution libdrm
versions are not replaced. It never replaces system Mesa or libdrm.

Once the runtime is validated, the FSR4 card exposes a compact copy button for
the per-game Steam launch option. The copied value uses `$HOME` instead of an
account name and therefore works unchanged for every user. Source-built
Debian/Ubuntu and Bazzite runtimes include their private `LD_LIBRARY_PATH`;
Arch/CachyOS prebuilt runtimes need only `VK_DRIVER_FILES`.
