#!/bin/bash
# run-e2e.sh [kind...] -- the whole chain as a desktop user: install-local.sh,
# install-decky-quick-access.sh, then Game Mode's plugin against the installed
# root helpers, then the uninstaller. Rootless.
here=$(cd "$(dirname "$0")" && pwd); QA=${BC250_QA:-$HOME/.cache/bc250-qa}
declare -A ROOTFS=( [arch-grub-new]=archlinux-current [cachyos-limine]=archlinux-current [steamos]=archlinux-current
  [debian-grub]=debian-trixie [ubuntu-grub]=ubuntu-noble [mint-grub]=ubuntu-noble [py310-refused]=mint-zena [fedora-grubby]=fedora-44
  [nobara-grubby]=fedora-44 [bazzite]=fedora-44 )
declare -A OSREL=( [mint-grub]=linuxmint [py310-refused]=ubuntu2204 [cachyos-limine]=cachyos [steamos]=steamos [nobara-grubby]=nobara [bazzite]=bazzite )
kinds=("$@"); [ ${#kinds[@]} -eq 0 ] && kinds=(arch-grub-new cachyos-limine steamos debian-grub ubuntu-grub mint-grub py310-refused fedora-grubby nobara-grubby bazzite)
rc=0
for kind in "${kinds[@]}"; do
  echo "=== e2e $kind"
  args=(); [ -n "${OSREL[$kind]:-}" ] && args=(--os-release "$here/os-release/${OSREL[$kind]}")
  flag=""; [ "$kind" = steamos ] && flag="--unsupported"
  if [ "$kind" = py310-refused ]; then
    BC250_QA=$QA "$here/enter-user.sh" "${ROOTFS[$kind]}" "${args[@]}" --root "/src/scripts/qa/rootless-matrix/prep.sh $kind" \
      --user "BC250_SKIP_DEPENDENCY_INSTALL=1 bash /src/scripts/install-local.sh 2>&1 | tail -n 3 | grep -q 'needs Python 3.11' && echo '  PASS  Python 3.10 systems are refused with a clear message' || { echo '  FAIL  Python 3.10 was not refused cleanly'; exit 1; }" || rc=1
    continue
  fi
  BC250_QA=$QA "$here/enter-user.sh" "${ROOTFS[$kind]}" "${args[@]}" \
    --root "/src/scripts/qa/rootless-matrix/prep.sh $kind; printf '#!/bin/bash\necho disabled\n' > /usr/bin/steamos-readonly; chmod +x /usr/bin/steamos-readonly; mkdir -p /home/deck/homebrew/plugins; chown -R 1000:1000 /home/deck" \
    --user "set -e
      BC250_SKIP_DEPENDENCY_INSTALL=1 bash /src/scripts/install-local.sh >/tmp/install.log 2>&1 && echo '  PASS  install-local.sh as a desktop user' || { echo '  FAIL  install-local.sh'; tail -n 15 /tmp/install.log; exit 1; }
      if [ \"$kind\" = bazzite ]; then
        bash /src/scripts/install-decky-quick-access.sh >/tmp/decky.log 2>&1 && { echo '  FAIL  Bazzite should be pointed at the RPM'; exit 1; }
        grep -q 'BAZZITE LOCAL-INSTALL LIMITATION' /tmp/decky.log && echo '  PASS  immutable Bazzite is pointed at the RPM (its Game Mode path is run-packages.sh)' || { echo '  FAIL  Bazzite message'; tail -n 8 /tmp/decky.log; exit 1; }
        exit 0
      fi
      bash /src/scripts/install-decky-quick-access.sh >/tmp/decky.log 2>&1 && echo '  PASS  install-decky-quick-access.sh' || { echo '  FAIL  decky installer'; tail -n 15 /tmp/decky.log; exit 1; }
      sudo python3 /src/scripts/qa/rootless-matrix/plugin_e2e.py /home/deck/homebrew/plugins/bc250-quick-access $flag
      echo '--- the installed CLI'; /home/deck/.local/bin/bc250-control-center-cli --help >/tmp/cli.log 2>&1 && echo '  PASS  CLI --help' || { echo '  FAIL  CLI --help'; tail -n 8 /tmp/cli.log; }
      if [ \"$kind\" != steamos ]; then
        H=/usr/libexec/bc250-control-center/bc250-system-setup-helper
        sudo python3 -I \$H ttm-apply --ttm 8 >/dev/null
        PREFIX=\$HOME/.local bash \$HOME/.local/share/bc250-control-center/scripts/uninstall-local.sh --yes >/tmp/uninstall1.log 2>&1
        [ -x \$H ] && echo '  PASS  uninstall-local.sh keeps the root helper while a limit is set' || echo '  FAIL  uninstall removed the helper under a set limit'
        sudo python3 -I \$H ttm-apply --ttm -1 >/dev/null
        sudo rm -rf /var/lib/bc250-control-center-uninstall-probe
        BC250_SKIP_DEPENDENCY_INSTALL=1 bash /src/scripts/install-local.sh >/tmp/install2.log 2>&1
        PREFIX=\$HOME/.local bash \$HOME/.local/share/bc250-control-center/scripts/uninstall-local.sh --yes >/tmp/uninstall2.log 2>&1
        [ ! -e \$H ] && echo '  PASS  uninstall-local.sh removes the root helper once everything is restored' || echo '  FAIL  helper left behind after restore'
        exit 0
      fi
      " || rc=1
done
exit $rc
