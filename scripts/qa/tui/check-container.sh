#!/usr/bin/env bash
# Run inside a disposable rootless container only; repository mount is read-only.
set -euo pipefail
[[ "${BC250_TUI_QA_CONTAINER:-}" == 1 ]] || { echo 'Container-only QA: use the matrix runner.' >&2; exit 64; }
name=${1:?distribution name required}
export PYTHONDONTWRITEBYTECODE=1 QT_QPA_PLATFORM=offscreen
export PATH="/qa-venv/bin:$PATH"
export PYTHONPATH=/repo/src:/repo
export XDG_CONFIG_HOME=/tmp/bc250-qa-config XDG_STATE_HOME=/tmp/bc250-qa-state XDG_DATA_HOME=/tmp/bc250-qa-data
mkdir -p "$XDG_CONFIG_HOME" "$XDG_STATE_HOME" "$XDG_DATA_HOME"
cat /etc/os-release
python3 -V
python3 -c 'import curses,psutil; print("TTY_RUNTIME_OK", psutil.__version__)'
if [[ "$name" == kubuntu || "$name" == xubuntu || "$name" == lubuntu ]]; then
  dpkg-query -W "$name-desktop"
fi
# Gentoo's test venv contains psutil; its Portage recovery path is checked by
# dependency-plan tests, not by pretending pip installed a native package.
export BC250_SKIP_PRIVILEGED_HELPER=1 PREFIX=/opt/bc250-tui-qa
# Bazzite OCI has an unpopulated /var; /opt is a boot-time symlink into it.
if [[ "$name" == bazzite ]]; then export PREFIX=/tmp/bc250-tui-qa; fi
if [[ "$name" == gentoo ]]; then export BC250_SKIP_DEPENDENCY_INSTALL=1; fi
bash /repo/scripts/install-tui.sh > /tmp/tui-install.log 2>&1
"$PREFIX/bin/bc250-control-center-tui" --help
"$PREFIX/bin/bc250-control-center-tui" --version
set +e
"$PREFIX/bin/bc250-control-center-tui" < /dev/null > /tmp/non-tty.log 2>&1
status=$?
set -e
[[ "$status" == 2 ]] || { cat /tmp/non-tty.log; exit 1; }
cd /repo
# Ubuntu 24.04 ships pytest 7; upgrade test tooling in a disposable venv only.
if ! python3 -c 'import pytest; assert int(pytest.__version__.split(".")[0]) >= 8'; then
  python3 -m venv --system-site-packages /qa-venv
  /qa-venv/bin/python -m pip install 'pytest>=8' pytest-cov
fi
python3 -m pytest tests/tui -q -o addopts='' --override-ini cache_dir=/tmp/pytest-cache
bash "$PREFIX/share/bc250-control-center/scripts/uninstall-local.sh" --yes --keep-privileged > /tmp/tui-uninstall.log 2>&1
test ! -e "$PREFIX/bin/bc250-control-center-tui"
echo "TUI_CONTAINER_OK $name"
