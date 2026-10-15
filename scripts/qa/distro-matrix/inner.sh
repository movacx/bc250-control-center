#!/bin/bash
export PYTHONDONTWRITEBYTECODE=1 QT_QPA_PLATFORM=offscreen HOME=/home/tester
cd "$HOME"
t() { # name cmd...
  local n=$1; shift
  local out; out=$(timeout 180 "$@" </dev/null 2>&1); local rc=$?
  printf 'RESULT\t%s\t%s\trc=%s\t%s\n' "$n" "$*" "$rc" "$(printf '%s' "$out" | grep -iE 'error|not found|no such|fail|traceback|usage|unsupported|cannot|warning' | head -3 | tr '\n' '|' | cut -c1-400)"
  [ $rc -ne 0 ] && printf 'TAIL\t%s\t%s\n' "$n" "$(printf '%s' "$out" | tail -4 | tr '\n' '|' | cut -c1-500)"
}
R=/repo
if [ "$PHASE" = scripts ]; then
export BC250_SKIP_PRIVILEGED_HELPER=1 BC250_SKIP_DEPENDENCY_INSTALL=1
t validate-source bash $R/scripts/qa/validate-install-source.sh $R
t smoke-layout bash $R/scripts/qa/smoke-install-layout.sh
t install-local bash $R/scripts/install-local.sh
export PATH=$HOME/.local/bin:$PATH
t cli-help bc250-control-center-cli --help
t cli-version bc250-control-center-cli --version
t daemon-help bc250-control-centerd --help
t gui-help bc250-control-center --help
t repo-entry-cli sh $R/scripts/entrypoints/bc250-control-center-cli --help
t update-local-help bash $R/scripts/maintenance/update-local.sh --help
t update-local-run bash $R/scripts/maintenance/update-local.sh --source $R --prefix $HOME/.local
for f in $R/scripts/system/*; do b=$(basename $f)
  case $b in *.sh) t "$b:syntax" bash -n $f; t "$b:help" bash $f --help;;
             *.py) t "$b:syntax" python3 -c "import ast,sys;ast.parse(open(sys.argv[1]).read())" $f; t "$b:help" python3 $f --help;; esac
done
t sysdeps-plan bash $R/scripts/system/bc250-install-system-deps.sh --mode plan
t sysdeps-check bash $R/scripts/system/bc250-install-system-deps.sh --mode check
t voltage-status bash $R/scripts/system/bc250-gpu-voltage-lab.sh status
t uninstall-dry bash $R/scripts/uninstall-local.sh -y --dry-run
t uninstall bash $R/scripts/uninstall-local.sh -y
t uninstall-again bash $R/scripts/uninstall-local.sh -y
t qa-clean-list bash $R/scripts/qa/qa-clean-install-containers.sh --list
elif [ "$PHASE" = detail ]; then
cp -a $R /work/repo 2>/dev/null; cd /work/repo; python3 -m venv /work/v >/dev/null 2>&1; . /work/v/bin/activate; pip install -q pytest pytest-qt pytest-cov PyQt6 psutil >/dev/null 2>&1; echo "git=$(command -v git)"; python -m pytest -q --no-cov -p no:cacheprovider -rf --tb=line tests 2>&1 | grep -E "^(FAILED|/work|E  |[0-9]+ failed)|Error" | sed "s/^/D\t/" | cut -c1-330 | head -150
else
cp -a $R /work/repo 2>/dev/null; cd /work/repo
python3 -m venv /work/v 2>&1 | tail -2
. /work/v/bin/activate 2>/dev/null
t pip pip install -q --disable-pip-version-check pytest pytest-qt pytest-cov PyQt6 psutil
t pytest python -m pytest -q -x --no-cov -p no:cacheprovider tests
python -m pytest -q --no-cov -p no:cacheprovider tests 2>&1 | tail -15 | sed 's/^/PYTEST\t/'
fi
