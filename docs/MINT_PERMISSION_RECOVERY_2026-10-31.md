# Mint follow-up: application-owned permission recovery

Report **R-ab4baf4e** demonstrates that the revision 2 fix did not resolve the
reporter's installation. The previous repair accepted exactly root:root 0775;
the mounted Mint Ext4 filesystem's root was confirmed from the host as
**UID 0, GID 0, mode 0777**. This is not a container's remapped `nobody` reading.
The original workflow also independently records the privileged helper rejecting
`/`. How the filesystem acquired 0777 is not established by those observations.

The Mint partition was inspected, not chmod/chowned. Its root remained 0777
throughout validation. Tests that change root permissions use disposable
rootless containers exclusively.

## Application recovery

`TerminalRepository` runs a recovery preflight before handing a workflow to
the embedded or external console. Thus the Memory & Swap workflow and the
Dashboard's dependency preparation can repair the known installation condition
as part of the application, rather than asking the user to run chmod externally.

The preflight embeds the installer's canonical finite repair program. It does
not execute/import an installed helper through the unsafe path. This also lets
updated application code recover an older installed helper. Healthy installations
do not request authorization at this step. An unprivileged application requests
sudo authorization when repair is needed; failure/cancellation aborts the
workflow before the requested operation. Normal helper validation still follows.

Native packages include this canonical program as application runtime data as
well as the root maintenance entry point. A staging regression imports the
recovery module from the staged application, catching missing runtime files.

The canonical policy is shared with package post-install and the local installer:

- Only `/`, `/usr`, `/usr/libexec`, `/etc`, `/var`, `/var/lib` are candidates.
- Only directories owned by UID 0/GID 0 with exact mode 0775 or 0777 are tightened
  to 0755. There is no ownership change or recursive normalization.
- Descriptor-relative traversal uses `O_DIRECTORY` and `O_NOFOLLOW` at every
  component. `fstat`/`fchmod` operate on the same open directory; a symlink cannot
  redirect repair into another tree.
- User-owned directories, unfamiliar ownership/modes and special permission bits
  are not normalized. Writable helper modules remain rejected.
- The embedded repair protocol is checked before constructing a workflow, so a
  mixed old application-maintenance payload cannot silently supply a different
  repair function.

The system-setup helper's refusal now reports path, numeric UID/GID, mode and
symlink state. Trust failures use **BC250-PERM-002**, whose existing translated
remediation points to preparation from the Dashboard rather than repeating the
generic reinstall/Bazzite deployment suggestion. The error catalog and generated
Decky distribution are synchronized.

## Verification

- Broad regression run: **1163 passed, 16 skipped** across packaging,
  distributions, unit, terminal workflow, error catalog and diagnosis tests.
- Final focused run: **14 passed**, including healthy workflows requiring no
  extra authorization, cancelled/failed repair preventing the original action,
  and refusal of an old mismatched repair-program protocol.
- Native application recovery passed in 17 userspaces: Ubuntu 24.04 (Mint base),
  Ubuntu 26.04, Debian, Devuan, Kali, Parrot, Kubuntu, Xubuntu, Lubuntu, Fedora 44,
  Bazzite 44, Arch, CachyOS, Manjaro, Artix OpenRC, Alpine and Gentoo.
- The check runs the real application's terminal repository and embedded-console
  launch request, after intentionally making the disposable root 0777. The
  installed helper first refuses it, the application repairs it, then the same
  helper returns protocol 2. A writable Python dependency is still refused.
- Native revision 3 DEB installation was additionally started with root 0777;
  post-install repaired it. RPM and pacman installations exercised actual
  dependency resolution on Bazzite, Arch, Manjaro and Artix. Those native checks
  also import the actual installed application, comparing its recovery modules
  with the reviewed source before invoking the workflow. Source-based checks
  reuse prepared runtime dependencies; no Gentoo Portage transaction is claimed.
- A separate compatibility check used the older helper already in the Ubuntu
  test image, without reinstalling it. Updated application code recovered the
  root permission and successfully invoked that older helper.

The native tests use a headless console adapter and read-only helper status.
They do not certify a live Mint GUI session, swap creation, CPU/GPU changes or
physical boot persistence. The real Mint filesystem metadata was read directly;
that partition's permissions were not manually repaired to make the test pass.

The native package revision is **1.21.4-3**, ordered after revision 2. Development
source and local artifacts are updated; this is not publication of a GitHub
release or replacement of the packages already downloaded by other beta users.
