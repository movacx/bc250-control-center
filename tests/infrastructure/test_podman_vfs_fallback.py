"""R-a148c990: podman on btrfs without overlay support must fall back to vfs."""

import os
import subprocess
import textwrap

from bc250cc.infrastructure import container_network


def _run(tmp_path, podman_script):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "podman").write_text(podman_script)
    (bin_dir / "podman").chmod(0o755)
    (bin_dir / "sudo").write_text('#!/bin/sh\nexec "$@"\n')
    (bin_dir / "sudo").chmod(0o755)
    script = container_network.PICK_PODMAN + '\necho "PICKED=$bc250_podman"\n'
    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}"}
    out = subprocess.run(["bash", "-c", script], capture_output=True, text=True, env=env, check=True)
    return out.stdout


BTRFS = textwrap.dedent("""\
    #!/bin/sh
    case "$*" in
      *vfs*) exit 0;;
    esac
    echo "Error: configure storage: kernel does not support overlay fs: 'overlay' is not supported over btrfs" >&2
    exit 125
    """)


def test_falls_back_to_vfs_when_overlay_is_unsupported(tmp_path):
    out = _run(tmp_path, BTRFS)
    assert "PICKED=sudo podman --storage-driver vfs" in out
    assert "vfs storage driver" in out


def test_keeps_plain_podman_when_it_works(tmp_path):
    out = _run(tmp_path, "#!/bin/sh\nexit 0\n")
    assert "PICKED=podman\n" in out
    assert "vfs" not in out
