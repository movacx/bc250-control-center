"""The GDDR6 helpers must share the SMU window with the board's other clients.

Register 0xB8 selects an SMN address and 0xBC carries the data; the pair is
one indirect transaction and is not atomic. The packaged CPU OC tool already
takes an advisory lock on that config file (``bc250_smu_oc`` builds its
transport with ``use_flock=True``). Advisory locking only works when every
participant asks, so these helpers have to ask too.
"""

import runpy
import subprocess
import sys
import time
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "privileged/helpers"
WINDOW = "/sys/bus/pci/devices/0000:00:00.0/config"

HOLDER = (
    "import fcntl,os,sys,time;"
    f"fd=os.open({WINDOW!r}, os.O_RDONLY);"
    "fcntl.flock(fd, fcntl.LOCK_EX);"
    "print('held', flush=True);"
    "time.sleep(float(sys.argv[1]));"
    "fcntl.flock(fd, fcntl.LOCK_UN)"
)


def test_the_cpu_oc_tool_still_locks_the_window_this_lock_pairs_with():
    """If upstream ever drops its lock, ours protects nothing."""
    vendor = zipfile.ZipFile(ROOT / "privileged/lib/bc250_smu_oc_vendor.zip")
    transport = vendor.read("bc250_smu/transport.py").decode()
    assert "flock" in transport
    for entry in ("bc250_apply.py", "bc250_detect.py"):
        assert "use_flock=True" in vendor.read(entry).decode()


@pytest.mark.parametrize(
    "helper", ["bc250-gddr6-temp-reader", "bc250-gddr6-temp-helper"]
)
def test_both_helpers_take_the_shared_window_lock(helper):
    namespace = runpy.run_path(str(HELPERS / helper))
    assert namespace["SMN_WINDOW_PATH"] == WINDOW
    assert callable(namespace["smn_window_lock"])


@pytest.mark.skipif(
    not Path(WINDOW).exists(), reason="no BC-250 root complex on this machine"
)
@pytest.mark.parametrize(
    "helper", ["bc250-gddr6-temp-reader", "bc250-gddr6-temp-helper"]
)
def test_the_lock_gives_up_instead_of_hanging_a_polkit_process(helper):
    """A blocking flock would leave a privileged helper stuck with no output."""
    lock = runpy.run_path(str(HELPERS / helper))["smn_window_lock"]
    holder = subprocess.Popen(
        [sys.executable, "-c", HOLDER, "3"], stdout=subprocess.PIPE, text=True
    )
    try:
        holder.stdout.readline()
        started = time.monotonic()
        with pytest.raises(RuntimeError, match="SMU_BUSY"):
            with lock(timeout=0.3):
                pass
        assert time.monotonic() - started < 2.0
    finally:
        holder.kill()
        holder.wait()
