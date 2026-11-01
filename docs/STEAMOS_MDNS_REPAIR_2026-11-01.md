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

## Chrome Flatpak follow-up

The user's later check confirmed the alias worked from a phone, while Chrome
Flatpak on the host still returned NXDOMAIN after a browser restart. Inspection
found that Chrome uses org.freedesktop.Platform 25.08: its NSS path uses files,
myhostname, resolve and DNS, without the host's nss-mdns module. The live Flatpak
lookup could not be executed from this restricted development session.

The in-app SteamOS repair now also records a managed bc250cc.local entry for
127.0.0.1 in /etc/hosts. This machine can therefore use the alias without relying
on a browser's mDNS support, while other LAN devices still use Avahi's LAN
address. Existing unrelated hosts entries are preserved. An existing alias to
a foreign address is refused; failed verification restores the previous hosts
file and removes the new keep list. A first backup is retained, and repeated
repairs do not append duplicate aliases. The setup confirmation describes the
local entry. The IPv4 web listener's loopback address is accepted by the local
health check; a foreign/mixed address remains rejected.

Validation now covers 30 unittest cases, including the local hosts entry,
loopback verification, repeat repair, conflict refusal and rollback. The host
repair must be run again after updating the package. Chrome Flatpak should be
fully closed and reopened afterwards to refresh its local files and DNS state.

The repair button now stays available when LAN web access is active and the
host alias already resolves. A successful host check cannot establish Flatpak
browser resolution; hiding the button prevented applying the local-hosts
follow-up repair. Nine offscreen Qt rendering tests pass, including a fresh
ready state and the pending-operation interaction.
