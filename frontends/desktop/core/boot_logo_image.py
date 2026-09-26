"""Any picture the user picks, turned into the boot logo the firmware reads.

The board draws its logo centred on a black screen, and the one kind of
picture its firmware has been seen to read is the kind every catalog logo is:
a baseline JPEG of 672 × 378 pixels in 4:2:0 colour. So whatever is chosen
(a PNG with transparency, a phone photo lying on its side, a small icon, an
SVG) is drawn here onto a black canvas of exactly that size and encoded that
way. Transparent areas become black, like the screen around the logo.

The encoder starts at the highest quality that still writes 4:2:0 and steps
down until the picture fits the space the firmware has for it. Every attempt
is checked against the same profile ``boot_logo.check_logo_jpeg`` enforces
when the image is built, so a picture this module accepts is never refused
later, and one it cannot make fit is refused here, with the reason.

Loading runs on a worker thread: QImage and QImageReader are safe there.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PyQt6.QtCore import QBuffer, QByteArray, QIODevice, QPoint, QSize, Qt
from PyQt6.QtGui import QColor, QImage, QImageReader, QImageWriter, QPainter

from bc250cc.domain.firmware.boot_logo import (
    LOGO_HEIGHT,
    LOGO_WIDTH,
    MAX_LOGO_BYTES,
    BootLogoError,
    check_logo_jpeg,
)

#: Larger files are refused before they are opened.
MAX_FILE_BYTES = 100 * 1024 * 1024
#: Larger pictures are refused before they are decoded.
MAX_SOURCE_PIXELS = 300_000_000
#: A picture is decoded at no more than twice the logo's size: enough to
#: scale down smoothly, and a 50-megapixel photo never sits in memory whole.
DECODE_BOUND = QSize(LOGO_WIDTH * 2, LOGO_HEIGHT * 2)
VECTOR_FORMATS = frozenset({b"svg", b"svgz"})
#: From the best Qt still writes as 4:2:0 down to the least worth showing.
QUALITIES = (90, 85, 80, 75, 70, 60, 50, 40, 30)
SIZE_RANGE = (30, 100)


class LogoImageError(ValueError):
    """The picture cannot become a boot logo; the message says why."""


@dataclass(frozen=True)
class Picture:
    """A picture as chosen, upright and ready to draw."""

    image: QImage
    name: str
    #: The picture's own size in pixels, after turning it upright.
    width: int
    height: int


def readable_patterns() -> str:
    """File dialog patterns for every picture format this Qt can read."""
    formats = sorted({bytes(name).decode("ascii", "ignore").lower() for name in QImageReader.supportedImageFormats()})
    return " ".join(f"*.{name}" for name in formats if name)


def load_picture(path: str) -> Picture:
    """Read ``path`` as a picture, refusing what would not fit in memory."""
    file = Path(path)
    try:
        size = file.stat().st_size
    except OSError as error:
        raise LogoImageError("The picture file could not be opened.") from error
    if size > MAX_FILE_BYTES:
        raise LogoImageError("The file is too large to be a logo.")
    reader = QImageReader(str(file))
    reader.setDecideFormatFromContent(True)
    reader.setAutoTransform(True)
    if not reader.canRead():
        raise LogoImageError("The file is not a picture this system can read.")
    stored = reader.size()
    if stored.isValid():
        if stored.width() * stored.height() > MAX_SOURCE_PIXELS:
            raise LogoImageError("The picture is too large to be a logo.")
        vector = bytes(reader.format()).lower() in VECTOR_FORMATS
        if vector or stored.width() > DECODE_BOUND.width() or stored.height() > DECODE_BOUND.height():
            reader.setScaledSize(stored.scaled(DECODE_BOUND, Qt.AspectRatioMode.KeepAspectRatio))
    image = reader.read()
    if image.isNull() or image.width() < 1 or image.height() < 1:
        raise LogoImageError("The file is not a picture this system can read.")
    return Picture(
        image=image.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied),
        name=file.name,
        width=image.width(),
        height=image.height(),
    )


def render_logo(picture: Picture, size_percent: int) -> QImage:
    """The logo as the board shows it: ``picture`` centred on black.

    ``size_percent`` is how much of the logo's frame the picture may fill,
    keeping its proportions.
    """
    percent = max(SIZE_RANGE[0], min(SIZE_RANGE[1], int(size_percent)))
    bound = QSize(max(1, LOGO_WIDTH * percent // 100), max(1, LOGO_HEIGHT * percent // 100))
    scaled = picture.image.scaled(
        bound, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
    )
    canvas = QImage(LOGO_WIDTH, LOGO_HEIGHT, QImage.Format.Format_RGB32)
    canvas.fill(QColor(0, 0, 0))
    painter = QPainter(canvas)
    painter.drawImage(
        QPoint((LOGO_WIDTH - scaled.width()) // 2, (LOGO_HEIGHT - scaled.height()) // 2), scaled
    )
    painter.end()
    # Three colour channels, never grey: the firmware's logos are all YCbCr.
    return canvas.convertToFormat(QImage.Format.Format_RGB888)


def _jpeg(canvas: QImage, quality: int) -> bytes:
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    writer = QImageWriter(buffer, b"jpeg")
    writer.setQuality(quality)
    written = writer.write(canvas)
    buffer.close()
    return bytes(data) if written else b""


def encode_logo(canvas: QImage) -> bytes:
    """``canvas`` as the JPEG the firmware gets, or LogoImageError."""
    if canvas.size() != QSize(LOGO_WIDTH, LOGO_HEIGHT):
        raise LogoImageError("The logo canvas has the wrong size.")
    too_large = False
    for quality in QUALITIES:
        data = _jpeg(canvas, quality)
        if not data:
            continue
        if len(data) > MAX_LOGO_BYTES:
            too_large = True
            continue
        try:
            check_logo_jpeg(data)
        except BootLogoError:
            continue
        return data
    if too_large:
        raise LogoImageError(
            "The picture has too much fine detail to fit in the firmware. "
            "Try a simpler picture or a smaller size."
        )
    raise LogoImageError("This system cannot write the kind of JPEG the firmware reads.")
