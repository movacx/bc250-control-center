import stat

from bc250cc.infrastructure.protected_file_health import (
    ProtectedFileEvidence,
)


def evidence(mode=stat.S_IFREG | 0o755, uid=0, **updates):
    values = {"exists": True, "is_symlink": False, "mode": mode, "uid": uid}
    values.update(updates)
    return ProtectedFileEvidence(**values)

