#!/bin/bash
# run-matrix.sh [kind...] -- kernel-argument scenario on every distribution family,
# rootless (bubblewrap), on throw-away clones of the rootfs images.
here=$(cd "$(dirname "$0")" && pwd); QA=${BC250_QA:-$HOME/.cache/bc250-qa}
declare -A ROOTFS=( [arch-grub-new]=archlinux-current [arch-grub-old]=archlinux-current [cachyos-limine]=archlinux-current
  [steamos]=archlinux-current [debian-grub]=debian-trixie [ubuntu-grub]=ubuntu-noble [mint-grub]=ubuntu-noble [py310-refused]=mint-zena
  [fedora-grubby]=fedora-44 [nobara-grubby]=fedora-44 [bazzite]=fedora-44 )
declare -A OSREL=( [mint-grub]=linuxmint [py310-refused]=ubuntu2204 [cachyos-limine]=cachyos [steamos]=steamos [nobara-grubby]=nobara [bazzite]=bazzite [arch-grub-old]=manjaro )
kinds=("$@"); [ ${#kinds[@]} -eq 0 ] && kinds=(arch-grub-new arch-grub-old cachyos-limine steamos debian-grub ubuntu-grub mint-grub fedora-grubby nobara-grubby bazzite)
rc=0
for kind in "${kinds[@]}"; do
  args=(); [ -n "${OSREL[$kind]:-}" ] && args=(--os-release "$here/os-release/${OSREL[$kind]}")
  BC250_QA=$QA "$QA/enter.sh" "${ROOTFS[$kind]}" "${args[@]}" -- bash -c "/src/scripts/qa/rootless-matrix/prep.sh $kind && python3 /src/scripts/qa/rootless-matrix/scenario.py $kind" || rc=1
done
exit $rc
