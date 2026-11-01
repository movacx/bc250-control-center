"""Per-installation local CA and renewable HTTPS leaf. Private keys stay local."""
from __future__ import annotations

import fcntl
import hashlib
import ipaddress
import os
import shutil
import ssl
import subprocess
import tempfile
from pathlib import Path

from bc250cc.infrastructure.persistence.config_paths import app_config_dir
from bc250cc.infrastructure.remote_access import addresses
from bc250cc.infrastructure.web_network import LOCAL_ALIAS, local_hostname
from bc250cc.shared.errors import ActionNeeded


def folder() -> Path:
    return app_config_dir() / "web-tls"


def fingerprint(path: Path) -> str:
    try:
        digest = hashlib.sha256(ssl.PEM_cert_to_DER_cert(path.read_text(encoding="ascii"))).hexdigest().upper()
        return ":".join(digest[i:i+2] for i in range(0, len(digest), 2))
    except (OSError, ValueError):
        return ""


def certificate() -> tuple[Path, Path]:
    openssl = shutil.which("openssl")
    if not openssl:
        raise ActionNeeded("HTTPS needs OpenSSL. Install openssl and start the web interface again.")
    directory = folder()
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    directory.chmod(0o700)
    cert, key = directory / "certificate.pem", directory / "private.pem"
    authority, authority_key = directory / "authority.crt", directory / "authority.key"

    def run(*args):
        return subprocess.run([openssl, *map(str, args)], capture_output=True, text=True, timeout=30, check=True)

    def current(path):
        try:
            run("x509", "-in", path, "-noout", "-checkend", "86400")
            return True
        except subprocess.CalledProcessError:
            return False

    fd = os.open(directory / ".lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "r+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        with tempfile.TemporaryDirectory(dir=directory) as temporary:
            stage = Path(temporary)
            new_ca = not (authority.is_file() and authority_key.is_file() and current(authority))
            if new_ca:
                run("req", "-x509", "-newkey", "rsa:3072", "-sha256", "-days", "3650", "-nodes",
                    "-subj", "/CN=BC250 local access authority", "-addext", "basicConstraints=critical,CA:TRUE,pathlen:0",
                    "-addext", "keyUsage=critical,keyCertSign,cRLSign", "-keyout", stage / "authority.key", "-out", stage / "authority.crt")
                (stage / "authority.key").chmod(0o600)
                os.replace(stage / "authority.key", authority_key)
                os.replace(stage / "authority.crt", authority)
            ips = {"127.0.0.1", *(str(ipaddress.ip_address(value)) for value in addresses())}
            names = {"localhost", LOCAL_ALIAS}
            if name := local_hostname():
                names.add(name)
            valid = not new_ca and cert.is_file() and key.is_file() and current(cert)
            if valid:
                try:
                    for name in names:
                        run("verify", "-CAfile", authority, "-verify_hostname", name, cert)
                    for ip in ips:
                        run("verify", "-CAfile", authority, "-verify_ip", ip, cert)
                except subprocess.CalledProcessError:
                    valid = False
            if not valid:
                run("req", "-new", "-newkey", "rsa:2048", "-nodes", "-subj", "/CN=BC250 Control Center",
                    "-keyout", stage / "private.pem", "-out", stage / "request.pem")
                extensions = stage / "extensions.cnf"
                extensions.write_text("basicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature,keyEncipherment\n"
                                      "extendedKeyUsage=serverAuth\nsubjectAltName=" +
                                      ",".join([*(f"DNS:{name}" for name in sorted(names)),
                                                *(f"IP:{ip}" for ip in sorted(ips))]) + "\n", encoding="ascii")
                run("x509", "-req", "-in", stage / "request.pem", "-CA", authority, "-CAkey", authority_key,
                    "-set_serial", "0x" + os.urandom(16).hex(), "-days", "365", "-sha256", "-extfile", extensions,
                    "-out", stage / "certificate.pem")
                (stage / "private.pem").chmod(0o600)
                os.replace(stage / "private.pem", key)
                os.replace(stage / "certificate.pem", cert)
        authority_key.chmod(0o600)
        key.chmod(0o600)
    return cert, key


def trust_certificate() -> Path:
    path = folder() / "authority.crt"
    if not path.is_file():
        raise ActionNeeded("Start the web interface first to prepare its local HTTPS certificate.")
    return path
