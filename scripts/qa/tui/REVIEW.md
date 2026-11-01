# TUI terminal review

The dashboard and sensor-section implementations are outside the redesign.

Ten review angles and required evidence:
1. Entry points, Python/curses/psutil dependencies and package installation.
2. TTY-only startup, no Qt requirement, locale/ASCII and terminal restoration.
3. Keyboard reachability of every section, tab, field and grid cell.
4. 60x14, 80x24, 100x30 and wide terminal resizing and scroll visibility.
5. Dialog selection, cancellation, safe confirmation and invalid input.
6. Streaming console output, completion, stderr, cancellation and PTY resize.
7. Password prompts in-terminal, privilege boundaries and no desktop fallback.
8. CPU/GPU/CU staged changes, rejected actions and boot persistence controls.
9. Resource samples, unavailable hardware, disk/network and stale/error recovery.
10. Remote ownership, session privacy, device permissions and SSH/init policies.

Container runs validate userspace, packages and real terminal sessions. Hardware
mutation tests use fakes and assert the command/arguments and authorization;
they do not claim to apply voltages, flash firmware or reboot host hardware.
Containers do not certify a distro kernel or an actual immutable deployment.

Latest recorded results: [2026-10-31 evidence](evidence-2026-10-31.json) and
[review report](../../../docs/TUI_REVIEW_2026-10-31.md).

Run `python3 scripts/qa/tui/run-matrix.py --list` to inspect profiles. Use
`--allow-network --pull` to prepare official base images and execute all profiles;
`--prepared --allow-network` reuses the local prepared images. Ubuntu variants
install their actual desktop metapackages on the official Ubuntu base. Gentoo's
psutil/test tooling uses a disposable venv, and its source-install dependency
transaction is explicitly skipped. OpenRC commands exist in Artix, Alpine and
Gentoo, but container PID 1 is not an OpenRC boot certification.
