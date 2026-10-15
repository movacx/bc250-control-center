#!/usr/bin/env bash
# init-systems.sh: checks the init-system detection against real OpenRC (Alpine) and real systemd (Debian as PID 1).
set -u
REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd); PODMAN=${PODMAN:-podman}
probe='cd /repo && PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -c "from bc250cc.platform.init import services as s; x=s.detect_init_manager(); print(\"detected:\", x.kind, x.available, x.persistence_supported)"'
echo "== OpenRC (alpine)"
"$PODMAN" run --rm --network=host -v "$REPO":/repo:ro alpine:3.21 sh -c "apk add -q openrc python3 >/dev/null 2>&1; mkdir -p /run/openrc; touch /run/openrc/softlevel; $probe"
echo "== systemd as PID 1 (debian trixie)"
name=bc250-init-qa; "$PODMAN" rm -f $name >/dev/null 2>&1
"$PODMAN" run -d --name $name --network=host --systemd=always -v "$REPO":/repo:ro debian:trixie sh -c 'apt-get update -qq && apt-get install -y -qq systemd systemd-sysv python3 >/dev/null 2>&1; exec /lib/systemd/systemd' >/dev/null
for _ in $(seq 1 90); do "$PODMAN" exec $name test -d /run/systemd/system 2>/dev/null && break; sleep 2; done
"$PODMAN" exec $name sh -c "$probe"
"$PODMAN" rm -f $name >/dev/null 2>&1
