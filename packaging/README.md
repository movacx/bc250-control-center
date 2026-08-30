# builders

These scripts create reviewable artifacts only; they never install packages,
modify the host, publish a release, or invoke hardware helpers.

- `scripts/build-tarball.sh [output-dir]` creates a deterministic source archive.
- `scripts/build-local-pkg.sh [output-dir]` creates an Arch-compatible local package.
- `scripts/build-rpm.sh [output-dir]` creates the single noarch RPM used by
  Fedora, Nobara and Bazzite/Fedora Atomic.
- `scripts/build-deb.sh [output-dir]` creates the Ubuntu/Debian `all` package.

Package upgrades remove the retired 1.18 `mvc/` application tree after the
new payload is installed. Package removal never deletes files from user home
directories; use the local uninstaller's explicit `--purge-user-data` option
when that cleanup is wanted.
