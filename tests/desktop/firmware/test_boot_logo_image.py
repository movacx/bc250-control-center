"""Turning whatever picture the user picks into a logo the firmware reads.

Every picture that comes out has to pass the same profile the firmware image
builder enforces; every picture that cannot become one has to say why,
before anything is downloaded or written.
"""

from __future__ import annotations

import random

import pytest
from PyQt6.QtCore import QRect
from PyQt6.QtGui import QColor, QImage, QImageIOHandler, QImageWriter, QPainter

from bc250cc.domain.firmware.boot_logo import (
    LOGO_HEIGHT,
    LOGO_WIDTH,
    MAX_LOGO_BYTES,
    BootLogoError,
    check_logo_jpeg,
)
from frontends.desktop.core import boot_logo_image
from frontends.desktop.core.boot_logo_image import (
    LogoImageError,
    encode_logo,
    load_picture,
    readable_patterns,
    render_logo,
)


def _save(image: QImage, path, fmt: bytes = b"png", **options) -> str:
    writer = QImageWriter(str(path), fmt)
    if "transformation" in options:
        writer.setTransformation(options["transformation"])
    assert writer.write(image), writer.errorString()
    return str(path)


def _square(size: int = 300, fill=QColor(0, 0, 0, 0)) -> QImage:
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(fill)
    painter = QPainter(image)
    painter.fillRect(QRect(size // 3, size // 3, size // 3, size // 3), QColor("white"))
    painter.end()
    return image


def test_a_transparent_png_lands_on_black_in_the_middle(qapp, tmp_path):
    picture = load_picture(_save(_square(), tmp_path / "logo.png"))
    assert (picture.name, picture.width, picture.height) == ("logo.png", 300, 300)
    canvas = render_logo(picture, 100)
    assert (canvas.width(), canvas.height()) == (LOGO_WIDTH, LOGO_HEIGHT)
    assert canvas.format() == QImage.Format.Format_RGB888
    assert canvas.pixelColor(0, 0) == QColor(0, 0, 0)
    assert canvas.pixelColor(LOGO_WIDTH - 1, LOGO_HEIGHT - 1) == QColor(0, 0, 0)
    assert canvas.pixelColor(LOGO_WIDTH // 2, LOGO_HEIGHT // 2) == QColor(255, 255, 255)
    check_logo_jpeg(encode_logo(canvas))


def test_a_photo_lying_on_its_side_is_turned_upright_without_stretching(qapp, tmp_path):
    wide = QImage(4000, 2000, QImage.Format.Format_RGB32)
    wide.fill(QColor("navy"))
    path = _save(wide, tmp_path / "phone.jpg", b"jpeg",
                 transformation=QImageIOHandler.Transformation.TransformationRotate90)
    picture = load_picture(path)
    # Decoded upright and no larger than twice the logo, proportions kept.
    assert picture.height > picture.width
    assert abs(picture.height / picture.width - 2.0) < 0.02
    assert picture.height <= LOGO_HEIGHT * 2


def test_a_small_picture_is_scaled_up_to_the_size_chosen(qapp, tmp_path):
    picture = load_picture(_save(_square(30, QColor("red")), tmp_path / "tiny.png"))
    full = render_logo(picture, 100)
    small = render_logo(picture, 30)
    # The square fills the logo's height at 100 % and 30 % of it at 30 %.
    assert full.pixelColor(LOGO_WIDTH // 2 - LOGO_HEIGHT // 2 + 2, LOGO_HEIGHT // 2) == QColor("red")
    assert small.pixelColor(LOGO_WIDTH // 2 - LOGO_HEIGHT // 2 + 2, LOGO_HEIGHT // 2) == QColor(0, 0, 0)
    assert render_logo(picture, 5).pixelColor(LOGO_WIDTH // 2 - 50, LOGO_HEIGHT // 2) == QColor("red"), (
        "sizes below the slider's range are clamped to it"
    )


def test_a_grey_picture_still_becomes_a_colour_logo(qapp, tmp_path):
    grey = _square(200, QColor(128, 128, 128)).convertToFormat(QImage.Format.Format_Grayscale8)
    jpeg = encode_logo(render_logo(load_picture(_save(grey, tmp_path / "grey.png")), 80))
    check_logo_jpeg(jpeg)


def test_a_detailed_picture_is_squeezed_under_the_cap(qapp):
    noise = QImage(LOGO_WIDTH, LOGO_HEIGHT, QImage.Format.Format_RGB888)
    generator = random.Random(7)
    for y in range(LOGO_HEIGHT):
        row = noise.scanLine(y)
        row.setsize(LOGO_WIDTH * 3)
        row[:] = bytes(generator.getrandbits(8) for _ in range(LOGO_WIDTH * 3))
    jpeg = encode_logo(noise)
    assert len(jpeg) <= MAX_LOGO_BYTES
    check_logo_jpeg(jpeg)


def test_a_picture_that_cannot_fit_says_so(qapp, monkeypatch):
    monkeypatch.setattr(boot_logo_image, "MAX_LOGO_BYTES", 500)
    with pytest.raises(LogoImageError, match="too much fine detail"):
        encode_logo(render_logo(boot_logo_image.Picture(_square(), "x.png", 300, 300), 100))


def test_a_jpeg_writer_that_never_writes_the_profile_says_so(qapp, monkeypatch):
    """A Qt that wrote, say, 4:4:4 at every quality: refused, not passed on."""
    def never(_data):
        raise BootLogoError("The logo is not a 672 × 378 colour JPEG (4:2:0).")

    monkeypatch.setattr(boot_logo_image, "check_logo_jpeg", never)
    canvas = render_logo(boot_logo_image.Picture(_square(), "x.png", 300, 300), 100)
    with pytest.raises(LogoImageError, match="kind of JPEG the firmware reads"):
        encode_logo(canvas)


def test_a_canvas_of_another_size_is_refused(qapp):
    with pytest.raises(LogoImageError, match="wrong size"):
        encode_logo(QImage(100, 100, QImage.Format.Format_RGB888))


def test_a_file_that_is_not_a_picture_is_refused(qapp, tmp_path):
    fake = tmp_path / "logo.png"
    fake.write_bytes(b"this is not a picture")
    with pytest.raises(LogoImageError, match="not a picture"):
        load_picture(str(fake))


def test_a_missing_file_is_refused(qapp, tmp_path):
    with pytest.raises(LogoImageError, match="could not be opened"):
        load_picture(str(tmp_path / "gone.png"))


def test_an_enormous_file_is_refused_before_it_is_read(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(boot_logo_image, "MAX_FILE_BYTES", 10)
    with pytest.raises(LogoImageError, match="too large to be a logo"):
        load_picture(_save(_square(), tmp_path / "big.png"))


def test_an_enormous_picture_is_refused_before_it_is_decoded(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(boot_logo_image, "MAX_SOURCE_PIXELS", 100)
    with pytest.raises(LogoImageError, match="picture is too large"):
        load_picture(_save(_square(), tmp_path / "wide.png"))


def test_the_file_dialog_offers_the_formats_this_system_reads(qapp):
    patterns = readable_patterns().split()
    assert "*.png" in patterns and "*.jpg" in patterns
    assert all(pattern.startswith("*.") for pattern in patterns)
