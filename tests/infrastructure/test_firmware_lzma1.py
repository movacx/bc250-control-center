"""The LZMA codec that builds the BIOS's compressed sections.

What matters is the format, not the compression ratio: the 13-byte header
with the real size, no end marker, and a decoder that refuses anything else.
Every catalog image is built that way, and EDK2's decompressor reads exactly
that. A stream with an end marker is what Python's own ``lzma`` would have
written, so it is used here as the thing that must be refused.
"""

from __future__ import annotations

import ctypes
import lzma
import struct

import pytest

from bc250cc.infrastructure.firmware import lzma1

pytestmark = pytest.mark.skipif(bool(lzma1.available()), reason=lzma1.available() or "liblzma ready")

_FILTER = [{"id": lzma.FILTER_LZMA1, "lc": 3, "lp": 0, "pb": 2, "dict_size": 1 << 24}]


def _data(size: int) -> bytes:
    # Compressible, but not trivially: repeated structure with a changing counter.
    return b"".join(f"DXE{index:08d}".encode() + bytes(index % 7) for index in range(size // 16))[:size]


@pytest.mark.parametrize("data", [b"", b"a", bytes(4096), _data(300_000)])
def test_a_stream_decodes_to_exactly_what_went_in(data):
    stream = lzma1.compress(data)
    assert lzma1.decompress(stream) == data


def test_the_header_carries_the_firmware_parameters_and_the_real_size():
    data = _data(50_000)
    stream = lzma1.compress(data)
    assert stream[:5] == bytes.fromhex("5d00000001")
    assert struct.unpack_from("<Q", stream, 5)[0] == len(data)
    # Python's own .lzma reader agrees, header and all.
    assert lzma.LZMADecompressor(format=lzma.FORMAT_ALONE).decompress(stream) == data


def test_the_stream_has_no_end_marker():
    """A raw LZMA1 decoder needs the marker to finish; without it, it never does."""
    stream = lzma1.compress(_data(50_000))
    decoder = lzma.LZMADecompressor(format=lzma.FORMAT_RAW, filters=_FILTER)
    decoder.decompress(stream[lzma1.HEADER_BYTES:])
    assert not decoder.eof


def _with_end_marker(data: bytes) -> bytes:
    return lzma1.PROPERTIES + struct.pack("<Q", len(data)) + lzma.compress(
        data, format=lzma.FORMAT_RAW, filters=_FILTER
    )


def test_a_stream_with_an_end_marker_is_refused():
    with pytest.raises(lzma1.Lzma1Error, match="damaged"):
        lzma1.decompress(_with_end_marker(_data(20_000)))


@pytest.mark.parametrize(
    "damage",
    [
        pytest.param(lambda stream: stream + b"\x00", id="trailing byte"),
        pytest.param(lambda stream: stream[:-8], id="truncated"),
        pytest.param(lambda stream: stream[:5] + struct.pack("<Q", 20_001) + stream[13:], id="size + 1"),
        pytest.param(lambda stream: stream[:5] + struct.pack("<Q", 19_999) + stream[13:], id="size - 1"),
        pytest.param(lambda stream: b"\x5e" + stream[1:], id="other lc/lp/pb"),
        pytest.param(lambda stream: stream[:1] + struct.pack("<I", 1 << 23) + stream[5:], id="other dictionary"),
        pytest.param(lambda stream: stream[:5] + struct.pack("<Q", 1 << 40) + stream[13:], id="impossible size"),
        pytest.param(lambda stream: stream[:5] + struct.pack("<Q", lzma1.MAX_OUTPUT_BYTES + 1) + stream[13:],
                     id="larger than any firmware"),
        pytest.param(lambda stream: stream[:12], id="shorter than its header"),
    ],
)
def test_anything_but_an_exact_stream_is_refused(damage):
    stream = lzma1.compress(_data(20_000))
    with pytest.raises(lzma1.Lzma1Error):
        lzma1.decompress(damage(stream))


def test_an_old_liblzma_is_refused_with_its_version(monkeypatch):
    class _Old:
        class _Version:
            restype = None
            argtypes = None

            def __call__(self):
                return 50020050  # 5.2.5

        lzma_version_number = _Version()

    monkeypatch.setattr(lzma1, "_library", None)
    monkeypatch.setattr(lzma1, "_library_error", "")
    monkeypatch.setattr(lzma1.ctypes, "CDLL", lambda _name: _Old())
    reason = lzma1.available()
    assert "5.2.5 is too old" in reason and "5.4" in reason
    with pytest.raises(lzma1.Lzma1Error, match="too old"):
        lzma1.compress(b"x")


def test_a_missing_liblzma_says_so(monkeypatch):
    def _missing(_name):
        raise OSError("liblzma.so.5: cannot open shared object file")

    monkeypatch.setattr(lzma1, "_library", None)
    monkeypatch.setattr(lzma1, "_library_error", "")
    monkeypatch.setattr(lzma1.ctypes, "CDLL", _missing)
    assert "could not be loaded" in lzma1.available()


def test_the_options_structure_matches_liblzma():
    """Offsets from lzma/lzma12.h on x86-64; a shifted field would pass garbage."""
    options = lzma1._Options
    assert ctypes.sizeof(options) == 112
    assert (options.lc.offset, options.mode.offset, options.ext_flags.offset,
            options.ext_size_high.offset, options.reserved_ptr2.offset) == (20, 32, 48, 56, 104)


def test_a_liblzma_without_the_raw_functions_disables_the_logo_instead_of_failing(monkeypatch):
    class _Partial:
        class _Version:
            restype = None
            argtypes = None

            def __call__(self):
                return 50080032

        lzma_version_number = _Version()

        def __getattr__(self, name):
            raise AttributeError(f"undefined symbol: {name}")

    monkeypatch.setattr(lzma1, "_library", None)
    monkeypatch.setattr(lzma1, "_library_error", "")
    monkeypatch.setattr(lzma1.ctypes, "CDLL", lambda _name: _Partial())
    assert "could not be loaded" in lzma1.available()
