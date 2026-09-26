"""LZMA exactly as a BC-250 BIOS stores it, through the system's liblzma.

Every compressed section of the BIOS is one LZMA1 stream behind a 13-byte
header: the properties byte, the dictionary size and the uncompressed size.
The stream has no end marker: the firmware's decompressor, EDK2's
LzmaCustomDecompressLib, takes the size from the header. Every image in the
catalog, ASRock's and the mods alike, is built that way.

Python's ``lzma`` module cannot write such a stream: its LZMA1 encoder always
ends with the marker and its ``.lzma`` header always says the size is
unknown. liblzma, the library that module is built on, can since 5.4 through
its LZMA1EXT filter, so the functions here call it directly. The decoder is
strict the same way: a stream with an end marker, with bytes left over or
decoding to a different size is an error, not a warning.

Nothing here guesses. Without liblzma 5.4 the functions refuse to run and
the caller says a custom logo cannot be built on this system.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import struct
import threading

#: lc=3, lp=0, pb=2 and a 16 MiB dictionary: the parameters of every
#: compressed section in the catalog's images.
PROPERTIES = bytes((0x5D,)) + struct.pack("<I", 1 << 24)
HEADER_BYTES = 13
#: liblzma 5.4.0, the first stable release with LZMA1EXT.
MINIMUM_VERSION = 50040002
PRESET = 9
#: The largest output a stream may declare. A BC-250 image is 16 MiB and its
#: DXE volume about 4.3 MiB; a header claiming more is refused before any
#: memory is set aside for it.
MAX_OUTPUT_BYTES = 64 * 1024 * 1024

_FILTER_LZMA1EXT = 0x4000000000000002
_VLI_UNKNOWN = 0xFFFFFFFFFFFFFFFF
_LZMA_OK = 0
_LZMA_BUF_ERROR = 10


class Lzma1Error(RuntimeError):
    """liblzma is missing, too old, or refused the data."""


class _Options(ctypes.Structure):
    """``lzma_options_lzma`` from lzma/lzma12.h, reserved fields included."""

    _fields_ = [
        ("dict_size", ctypes.c_uint32),
        ("preset_dict", ctypes.c_void_p),
        ("preset_dict_size", ctypes.c_uint32),
        ("lc", ctypes.c_uint32),
        ("lp", ctypes.c_uint32),
        ("pb", ctypes.c_uint32),
        ("mode", ctypes.c_int),
        ("nice_len", ctypes.c_uint32),
        ("mf", ctypes.c_int),
        ("depth", ctypes.c_uint32),
        ("ext_flags", ctypes.c_uint32),
        ("ext_size_low", ctypes.c_uint32),
        ("ext_size_high", ctypes.c_uint32),
        ("reserved_int4", ctypes.c_uint32),
        ("reserved_int5", ctypes.c_uint32),
        ("reserved_int6", ctypes.c_uint32),
        ("reserved_int7", ctypes.c_uint32),
        ("reserved_int8", ctypes.c_uint32),
        ("reserved_enum1", ctypes.c_int),
        ("reserved_enum2", ctypes.c_int),
        ("reserved_enum3", ctypes.c_int),
        ("reserved_enum4", ctypes.c_int),
        ("reserved_ptr1", ctypes.c_void_p),
        ("reserved_ptr2", ctypes.c_void_p),
    ]


class _Filter(ctypes.Structure):
    _fields_ = [("id", ctypes.c_uint64), ("options", ctypes.c_void_p)]


_library: ctypes.CDLL | None = None
_library_error = ""
_lock = threading.Lock()


def _load() -> ctypes.CDLL:
    global _library, _library_error
    with _lock:
        if _library is not None:
            return _library
        if _library_error:
            raise Lzma1Error(_library_error)
        name = ctypes.util.find_library("lzma") or "liblzma.so.5"
        try:
            library = ctypes.CDLL(name)
            library.lzma_version_number.restype = ctypes.c_uint32
            library.lzma_version_number.argtypes = []
            version = int(library.lzma_version_number())
            if version < MINIMUM_VERSION:
                _library_error = (
                    f"liblzma {_version_text(version)} is too old; 5.4 or newer is needed."
                )
                raise Lzma1Error(_library_error)
            library.lzma_lzma_preset.restype = ctypes.c_ubyte
            library.lzma_lzma_preset.argtypes = [ctypes.POINTER(_Options), ctypes.c_uint32]
            library.lzma_raw_buffer_encode.restype = ctypes.c_int
            library.lzma_raw_buffer_encode.argtypes = [
                ctypes.POINTER(_Filter), ctypes.c_void_p,
                ctypes.c_char_p, ctypes.c_size_t,
                ctypes.c_void_p, ctypes.POINTER(ctypes.c_size_t), ctypes.c_size_t,
            ]
            library.lzma_raw_buffer_decode.restype = ctypes.c_int
            library.lzma_raw_buffer_decode.argtypes = [
                ctypes.POINTER(_Filter), ctypes.c_void_p,
                ctypes.c_char_p, ctypes.POINTER(ctypes.c_size_t), ctypes.c_size_t,
                ctypes.c_void_p, ctypes.POINTER(ctypes.c_size_t), ctypes.c_size_t,
            ]
        except (OSError, AttributeError) as error:
            _library_error = f"liblzma could not be loaded: {error}"
            raise Lzma1Error(_library_error) from error
        _library = library
        return library


def _version_text(number: int) -> str:
    return f"{number // 10000000}.{number // 10000 % 1000}.{number // 10 % 1000}"


def available() -> str:
    """"" when streams can be built here, otherwise why not. Never raises:
    the page asks this while it is being built."""
    try:
        _load()
    except Exception as error:  # noqa: BLE001 - any failure only disables the logo
        return str(error) or "liblzma could not be loaded."
    return ""


def _filters(library: ctypes.CDLL, size: int) -> tuple[ctypes.Array, _Options]:
    options = _Options()
    if library.lzma_lzma_preset(ctypes.byref(options), PRESET):
        raise Lzma1Error("liblzma rejected its own compression preset.")
    options.dict_size = 1 << 24
    options.lc, options.lp, options.pb = 3, 0, 2
    # No LZMA_LZMA1EXT_ALLOW_EOPM: the encoder writes no end marker and the
    # decoder refuses a stream that has one.
    options.ext_flags = 0
    options.ext_size_low = size & 0xFFFFFFFF
    options.ext_size_high = size >> 32
    filters = (_Filter * 2)()
    filters[0].id = _FILTER_LZMA1EXT
    filters[0].options = ctypes.cast(ctypes.pointer(options), ctypes.c_void_p)
    filters[1].id = _VLI_UNKNOWN
    filters[1].options = None
    return filters, options


def compress(data: bytes) -> bytes:
    """``data`` as a firmware LZMA stream: header, then the stream, no marker."""
    library = _load()
    data = bytes(data)
    filters, _options = _filters(library, len(data))
    capacity = len(data) + len(data) // 2 + 64 * 1024
    output = ctypes.create_string_buffer(capacity)
    written = ctypes.c_size_t(0)
    result = library.lzma_raw_buffer_encode(
        filters, None, data, len(data), output, ctypes.byref(written), capacity
    )
    if result != _LZMA_OK:
        raise Lzma1Error(f"liblzma could not compress the data (error {result}).")
    return PROPERTIES + struct.pack("<Q", len(data)) + output.raw[: written.value]


def decompress(stream: bytes) -> bytes:
    """The data behind a firmware LZMA stream, refusing anything but an exact one."""
    library = _load()
    stream = bytes(stream)
    if len(stream) < HEADER_BYTES:
        raise Lzma1Error("The compressed data is shorter than its header.")
    if stream[:5] != PROPERTIES:
        raise Lzma1Error("The compressed data uses unexpected LZMA parameters.")
    size = struct.unpack_from("<Q", stream, 5)[0]
    if size > MAX_OUTPUT_BYTES:
        raise Lzma1Error("The compressed data declares an impossible size.")
    filters, _options = _filters(library, size)
    body = stream[HEADER_BYTES:]
    output = ctypes.create_string_buffer(max(size, 1))
    consumed = ctypes.c_size_t(0)
    produced = ctypes.c_size_t(0)
    result = library.lzma_raw_buffer_decode(
        filters, None, body, ctypes.byref(consumed), len(body),
        output, ctypes.byref(produced), size,
    )
    if result != _LZMA_OK:
        reason = "is cut short" if result == _LZMA_BUF_ERROR else f"is damaged (error {result})"
        raise Lzma1Error(f"The compressed data {reason}.")
    if consumed.value != len(body) or produced.value != size:
        raise Lzma1Error("The compressed data does not end where its header says.")
    return output.raw[:size]
