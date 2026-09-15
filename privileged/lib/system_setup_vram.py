"""BC250 CMOS VRAM (UMA_SIZE) configuration.

Writes the APU frame-buffer size into the battery-backed CMOS bank the
ABL/BIOS firmware reads at boot, using the offsets documented by
github.com/fanoush/bc250_memcfg (works unmodified with stock P3.00/P5.00
firmware). The value survives reboots by itself; it is only reverted by
clearing CMOS (jumper or battery removal), so unlike swap/TTM this needs no
BC250-owned boot-time systemd unit.

Only the UMA_SIZE field is ever changed. The rest of the 28-byte bank
(clock speed and every memory timing strap) is read back unmodified and
rewritten byte-for-byte on every apply, so nothing here can alter timings.
Access is through ``/dev/port`` (index/data pair on ports 0x72/0x73), the
same mechanism the upstream tool uses via ``iopl``/``inb``/``outb`` -
plain file I/O, no compiled helper needed.
"""
from __future__ import annotations

from system_setup_common import Host, SetupError

DEVICE = "/dev/port"
INDEX_PORT = 0x72
DATA_PORT = 0x73
BANK_OFFSET = 0x90          # absolute CMOS offset of the MemConf_t bank
BANK_SIZE = 28              # sizeof(MemConf_t) upstream
UMA_SIZE_OFFSET = 26        # bank-relative offset of the UMA_SIZE WORD (0xAA)
CHECKSUM_FIELD_OFFSET = 6   # bank-relative start of the checksummed range
SIGNATURE = 0x42435041      # LINUX_TOOL_SIGNATURE
UMA_SIZE_MIN_MB = 256
UMA_SIZE_MAX_MB = 16368     # highest value < 16384 aligned down to 16 MiB
UMA_SIZE_ALIGNMENT_MB = 16


def align_uma_size(value: int) -> int:
    return value & ~(UMA_SIZE_ALIGNMENT_MB - 1)


def _open_port():
    try:
        return open(DEVICE, "r+b", buffering=0)
    except OSError as exc:
        raise SetupError(f"Cannot access BC250 CMOS I/O ports ({DEVICE}): {exc}") from exc


def _read_index_byte(port, offset: int) -> int:
    port.seek(INDEX_PORT)
    port.write(bytes((offset,)))
    port.seek(DATA_PORT)
    read = port.read(1)
    if not read:
        raise SetupError("Short read from BC250 CMOS I/O ports")
    return read[0]


def _write_index_byte(port, offset: int, value: int) -> None:
    port.seek(INDEX_PORT)
    port.write(bytes((offset,)))
    port.seek(DATA_PORT)
    port.write(bytes((value & 0xFF,)))


def _read_bank(port) -> bytearray:
    return bytearray(_read_index_byte(port, BANK_OFFSET + i) for i in range(BANK_SIZE))


def _write_bank(port, bank: bytearray) -> None:
    for i, value in enumerate(bank):
        _write_index_byte(port, BANK_OFFSET + i, value)


def status(host: Host) -> dict:
    detected = host.bc250()
    present = host.path(DEVICE).exists()
    if not detected:
        reason = "AMD BC-250 hardware identity was not detected"
    elif not present:
        reason = "/dev/port is not available on this kernel"
    else:
        reason = ""
    return {"supported": detected and present, "reason": reason}


def read(host: Host, *, port_open=_open_port) -> dict:
    available = status(host)
    if not available["supported"]:
        raise SetupError(available["reason"] or "BC250 VRAM configuration is unavailable")
    port = port_open()
    try:
        bank = _read_bank(port)
    finally:
        port.close()
    uma_size_mb = bank[UMA_SIZE_OFFSET] | (bank[UMA_SIZE_OFFSET + 1] << 8)
    return {"supported": True, "uma_size_mb": uma_size_mb}


def apply(host: Host, uma_size_mb: int, *, port_open=_open_port) -> dict:
    if type(uma_size_mb) is not int or not (UMA_SIZE_MIN_MB <= uma_size_mb < 16384):
        raise SetupError(f"UMA_SIZE must be between {UMA_SIZE_MIN_MB} and 16383 MB")
    available = status(host)
    if not available["supported"]:
        raise SetupError(available["reason"] or "BC250 VRAM configuration is unavailable")
    aligned = align_uma_size(uma_size_mb)
    port = port_open()
    try:
        bank = _read_bank(port)
        bank[UMA_SIZE_OFFSET] = aligned & 0xFF
        bank[UMA_SIZE_OFFSET + 1] = (aligned >> 8) & 0xFF
        bank[0:4] = SIGNATURE.to_bytes(4, "little")
        checksum = sum(bank[CHECKSUM_FIELD_OFFSET:]) & 0xFFFF
        bank[4:6] = checksum.to_bytes(2, "little")
        _write_bank(port, bank)
    finally:
        port.close()
    return {"supported": True, "applied_uma_size_mb": aligned}
