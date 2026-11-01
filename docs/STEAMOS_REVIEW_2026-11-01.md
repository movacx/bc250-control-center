# SteamOS workflows — 1 November 2026

Reviewed nine SteamOS reports (251 attachments) from an export containing 52
Cloudflare reports. The report IDs and dispositions were recorded locally in
`/home/deck/Documents/bc250-report-review/REVISION-STEAMOS.md`.

The current kernel compatibility run, `workflow-1793559320417643876.log`, built
and verified AMDGPU for `7.2.7-valve2-2-neptune-72-g31504582a073`, including
vermagic and task_struct ABI validation. Installation then stopped while
copying the module into the protected backend because /usr was read-only.

Changes:

- Copy both validated build artifacts and invoke the protected installer inside
  one short SteamOS writable-root transaction. Keep fetching and compilation
  outside that transaction. Restore the initial read-only state on success and
  failure; retain existing artifact ownership/mode validation.
- Wrap the explicit Decky bootstrap and local Quick Access installation in the
  same SteamOS guard, including installer rollback. Other distribution families
  keep their existing commands.
- Capture the graphics uninstall pipeline status in an explicit conditional.
  Under the production `set -Eeuo pipefail` flags, an expected reboot stop now
  reaches its marker handling. Unrelated failures retain their status.
- Recover a missing or damaged managed kernel Git index from HEAD before build
  and before the tree-drift cleanup retry. Preserve downloaded packages and Git
  objects. Do not automatically remove locks or override source/ABI checks.

Validation used temporary repositories and mocked host commands, not the live
kernel cache. Real-shell cases cover initially protected and writable roots,
installation success/failure, copied build artifacts, Quick Access failure,
expected reboot stops and unrelated uninstall failures. The uninstall tests now
use production shell flags. Index cases use real Git; generated workflow,
bootstrap routing, policy ordering and package payload checks supplement them.
Pytest is absent on this host: targeted existing test functions were invoked
directly, and the transaction regressions run with Python unittest. This is not
a claim that the full pytest suite passed or that module installation/boot was
validated on physical hardware.

The older reports about unsupported kernel 7.2, mirror timeouts and the
safe-point instruction already have code changes. Insufficient /var capacity,
concurrent preparation and frequencies above the module ceiling remain guarded;
they must not be resolved by deleting arbitrary data, removing locks or changing
user tuning silently. Missing installed helpers and stale CU service database
configuration require the existing installation/preparation repair followed by
host verification.
