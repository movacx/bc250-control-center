# builders

These scripts create reviewable artifacts only; they never install packages,
modify the host, publish a release, or invoke hardware helpers.

- `scripts/build-tarball.sh [output-dir]` creates a deterministic source archive.
- `scripts/build-local-pkg.sh [output-dir]` creates an Arch-compatible local package.
- `scripts/build-rpm.sh [output-dir]` creates a Fedora-compatible noarch RPM.
- `bazzite/build-rpm-bazzite.sh [output-dir]` creates the same RPM for explicit
  review and later `rpm-ostree` installation on Bazzite.
