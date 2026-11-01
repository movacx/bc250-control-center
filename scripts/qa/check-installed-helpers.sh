#!/usr/bin/env bash
# Run only inside disposable native-package test containers, after installation.
set -euo pipefail
[[ "${BC250_QA_CONTAINER:-}" == 1 && "$EUID" == 0 && -f /run/.containerenv ]] || {
  echo 'Container-only helper QA; no host permission changes are permitted.' >&2
  exit 64
}
qa_repo=${1:?read-only repository required}
qa_helpers=/usr/libexec/bc250-control-center
for qa_file in "$qa_repo"/privileged/helpers/bc250-*; do
  cmp "$qa_file" "$qa_helpers/$(basename "$qa_file")"
done
for qa_file in "$qa_repo"/privileged/lib/*.py "$qa_repo"/privileged/lib/*.zip; do
  cmp "$qa_file" "$qa_helpers/lib/$(basename "$qa_file")"
done
python3 - "$qa_repo/packaging/common/bc250-package-maintenance" "$qa_helpers/bc250-package-maintenance" <<'PY'
import pathlib,sys
expected,actual=(pathlib.Path(p).read_bytes() for p in sys.argv[1:])
# RPM normalizes env-based Bash shebangs to its absolute interpreter. Every
# byte after that OS-owned normalization must still match the source.
if actual.startswith(b'#!/usr/bin/bash\n'):
    actual=b'#!/usr/bin/env bash\n'+actual.split(b'\n',1)[1]
assert actual==expected, 'Installed package-maintenance payload differs'
PY
python3 - "$qa_helpers" <<'PY'
import pathlib,sys
root=pathlib.Path(sys.argv[1])
for path in [root,*root.rglob('*')]:
    metadata=path.stat()
    assert metadata.st_uid==0 and not metadata.st_mode & 0o022, str(path)
PY
# Reproduce the Mint beta report and test the installed upgrade repair.
chmod 0775 /
if "$qa_helpers/bc250-system-setup-helper" status >/tmp/helper-blocked.log 2>&1; then
  echo 'Unsafe root directory was accepted' >&2
  exit 1
fi
grep -q 'Untrusted helper dependency: /' /tmp/helper-blocked.log
qa_maintenance="$qa_helpers/bc250-package-maintenance"
bash "$qa_maintenance" repair-permissions
"$qa_helpers/bc250-system-setup-helper" status >/tmp/helper-root.json
python3 - "$qa_helpers/bc250-system-setup-helper" >/tmp/helper-user.json <<'PY'
import os,sys
os.setgroups([])
os.setgid(65534)
os.setuid(65534)
os.execv(sys.argv[1], [sys.argv[1], 'status'])
PY
python3 - <<'PY'
import json
for path in ['/tmp/helper-root.json','/tmp/helper-user.json']:
    assert json.load(open(path))['protocol']==2
PY
# The repair must not weaken validation of a genuinely writable dependency.
chmod 0664 "$qa_helpers/lib/system_setup_common.py"
if "$qa_helpers/bc250-system-setup-helper" status >/tmp/helper-tampered.log 2>&1; then
  echo 'Writable privileged dependency was accepted' >&2
  exit 1
fi
chmod 0644 "$qa_helpers/lib/system_setup_common.py"
python3 "$qa_repo/scripts/qa/check-application-permission-recovery.py" "$qa_repo"
echo 'INSTALLED_HELPER_PAYLOAD_AND_TRUST_PASS'
