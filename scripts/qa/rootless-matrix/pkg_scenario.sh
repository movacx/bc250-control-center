#!/bin/bash
# pkg_scenario.sh <deb|rpm|arch> <kind> -- install the built package with the
# distribution's own package manager, set the GPU memory limit, check that removal
# is refused while it is set and works once it is restored.
fam=$1; kind=$2; out=/out; H=/usr/libexec/bc250-control-center/bc250-system-setup-helper
ok() { echo "  PASS  $1"; }; bad() { echo "  FAIL  $1"; rc=1; }; rc=0
/src/scripts/qa/rootless-matrix/prep.sh "$kind"
case $fam in
  deb)  pkg=$(ls $out/*.deb);  install() { dpkg -i --force-depends --force-confnew "$pkg"; }; remove() { dpkg -r bc250-control-center; }; listing() { dpkg -c "$pkg"; };;
  rpm)  pkg=$(ls $out/*.rpm);  install() { rpm -i --nodeps --noscripts "$pkg" && /usr/libexec/bc250-control-center/bc250-package-maintenance post-install; }; remove() { /usr/libexec/bc250-control-center/bc250-package-maintenance pre-remove && rpm -e --nodeps --noscripts bc250-control-center; }; listing() { rpm -qpl "$pkg"; };;
  arch) pkg=$(ls $out/*.pkg.tar.zst); install() { pacman -U --noconfirm --disable-sandbox --nodeps --nodeps "$pkg"; }; remove() { pacman -R --noconfirm --disable-sandbox bc250-control-center; }; listing() { tar --zstd -tf "$pkg"; };;
esac
listing 2>/dev/null | grep -q "lib/system_setup_ttm.py" && ok "package ships system_setup_ttm.py" || bad "package is missing system_setup_ttm.py"
install >/tmp/install.log 2>&1 && ok "package installs with the distribution's package manager" || { bad "package install"; tail -n 8 /tmp/install.log; exit 1; }
plugin=/usr/share/bc250-control-center/integrations/decky/bc250-quick-access
if python3 /src/scripts/qa/rootless-matrix/plugin_e2e.py "$plugin" > /tmp/plugin.log 2>&1; then ok "Game Mode plugin from the package drives the installed helpers ($(grep -c PASS /tmp/plugin.log) checks)"; else bad "Game Mode plugin from the package"; grep FAIL /tmp/plugin.log | head -n 5; fi
python3 -I $H ttm-apply --ttm 8 >/dev/null 2>&1 && ok "ttm-apply from the installed package" || bad "ttm-apply"
remove >/tmp/remove1.log 2>&1 && bad "removal was NOT refused while the limit is set" || ok "removal refused while the limit is set"
grep -q "GPU memory limit" /tmp/remove1.log && ok "the refusal names the limit and the command to restore" || { bad "refusal does not explain itself"; tail -n 6 /tmp/remove1.log; }
python3 -I $H ttm-apply --ttm -1 >/dev/null 2>&1 && ok "restore" || bad "restore"
remove >/tmp/remove2.log 2>&1 && ok "removal works once restored" || { bad "removal after restore"; tail -n 8 /tmp/remove2.log; }
[ ! -e /usr/libexec/bc250-control-center/lib/system_setup_ttm.py ] && ok "nothing left in /usr/libexec" || bad "files left behind: $(ls /usr/libexec/bc250-control-center/lib 2>&1 | head -n 3)"
exit $rc
