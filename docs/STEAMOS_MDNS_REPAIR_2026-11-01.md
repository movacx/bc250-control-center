# SteamOS local address repair — 1 November 2026

SteamOS's Avahi configuration disables publication with both
`disable-publishing=yes` and `disable-user-service-publishing=yes`. Control
Center's unprivileged publisher therefore cannot announce bc250cc.local.
Numeric web access remains independent of this failure.

The explicit Remote access > Repair local address action now handles this
SteamOS policy in the protected setup helper. It validates NSS configuration,
backs up the Avahi configuration, changes only the two publication flags,
restarts Avahi and verifies the address through Avahi and the browser's NSS
lookup path. Unrelated Avahi settings and the OS hostname are preserved.
Failed verification restores NSS and Avahi configuration and reloads Avahi.
The SteamOS atomic-update keep list retains the repaired configuration files.
Repeated repairs preserve the first backup and do not restart an already
working publication configuration. Existing unsupported immutable images are
not given an implicit package-manager workaround.

A lookup timeout keeps the explicit repair button available when a local
address exists. The alias is offered only after successful resolution to this
host; numeric addresses remain available. A foreign or mixed resolution is
refused. The confirmation explains enabling name publication on SteamOS.

Validation: 26 unittest cases passed, including existing resolver behavior,
SteamOS publication, failure rollback, collision rollback, idempotence,
ambiguous files, symlinks and timeout behavior. Compilation/syntax and package
payload validation supplement those cases. Tests use temporary files and
mocked commands; this development session did not change the live Avahi or NSS
configuration. Applying the repair from the installed app remains the physical
host check.

Host follow-up: the user installed package 1.21.4-7, ran the in-app repair and
confirmed that the local address works on this SteamOS installation.
