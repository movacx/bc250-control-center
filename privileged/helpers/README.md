# Privileged helpers

The public helper entry points remain separate during stabilization.

Desktop CU requests use `bc250-cu-helper`, installed together with the Polkit
`compute-units` action (`auth_admin_keep`). It accepts only the fixed CU command
set, shares the root-owned typed executor with Game Mode, and serializes desktop
CU requests. A custom profile submits removals, additions, optional boot save and
final readback through one authorization. Intermediate dashboards go to stderr;
only the final verified snapshot goes to stdout.

Authorization caching is temporary and controlled by Polkit. It does not grant
general shell access or permanently remove password prompts. After updating the
source, update the installed application/helpers before testing this route.
