"""Shared Floating Island app icon for Qt, the Windows tray, and shortcuts."""
import struct

from PyQt6.QtCore import QByteArray, QBuffer, QIODevice, QPointF, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QIcon, QImage, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap


ICON_SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)


def _render_icon(size: int) -> QImage:
    image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)

    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.scale(size / 256.0, size / 256.0)

    background_path = QPainterPath()
    background_path.addRoundedRect(QRectF(8, 8, 240, 240), 58, 58)
    background = QLinearGradient(28, 26, 226, 232)
    background.setColorAt(0.0, QColor("#18263A"))
    background.setColorAt(0.55, QColor("#101827"))
    background.setColorAt(1.0, QColor("#0A101A"))
    painter.fillPath(background_path, QBrush(background))
    painter.setPen(QPen(QColor(142, 214, 231, 80), 3))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawPath(background_path)

    # A few quiet stars make the island feel suspended without cluttering the mark.
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(202, 234, 245, 180))
    painter.drawEllipse(QRectF(54, 62, 6, 6))
    painter.drawEllipse(QRectF(197, 57, 5, 5))
    painter.setBrush(QColor(133, 221, 225, 170))
    painter.drawEllipse(QRectF(208, 177, 4, 4))

    # Soft floating glow beneath the island.
    painter.setPen(Qt.PenStyle.NoPen)
    glow = QLinearGradient(62, 0, 202, 0)
    glow.setColorAt(0.0, QColor(38, 215, 204, 0))
    glow.setColorAt(0.5, QColor(58, 218, 215, 115))
    glow.setColorAt(1.0, QColor(117, 111, 255, 0))
    painter.setBrush(QBrush(glow))
    painter.drawRoundedRect(QRectF(61, 174, 134, 18), 9, 9)

    # Bright rim and dark inner pill create a recognizable floating island.
    rim = QLinearGradient(40, 72, 218, 166)
    rim.setColorAt(0.0, QColor("#67E5D1"))
    rim.setColorAt(0.48, QColor("#69CDEB"))
    rim.setColorAt(1.0, QColor("#8B82FF"))
    painter.setPen(QPen(QColor(229, 255, 255, 210), 3))
    painter.setBrush(QBrush(rim))
    painter.drawRoundedRect(QRectF(34, 72, 188, 94), 47, 47)

    inner = QLinearGradient(0, 88, 0, 152)
    inner.setColorAt(0.0, QColor("#172435"))
    inner.setColorAt(1.0, QColor("#0D1522"))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(inner))
    painter.drawRoundedRect(QRectF(44, 82, 168, 74), 37, 37)

    # Two luminous eye-like windows echo the island's on-screen mascot.
    painter.setBrush(QColor("#F2FFFF"))
    painter.drawRoundedRect(QRectF(99, 104, 18, 32), 9, 9)
    painter.drawRoundedRect(QRectF(139, 104, 18, 32), 9, 9)
    painter.setBrush(QColor("#63DCD4"))
    painter.drawEllipse(QRectF(104, 114, 8, 12))
    painter.drawEllipse(QRectF(144, 114, 8, 12))

    painter.end()
    return image


def create_app_icon() -> QIcon:
    """Return one high-DPI icon with useful sizes for Windows surfaces."""
    icon = QIcon()
    for size in ICON_SIZES:
        icon.addPixmap(QPixmap.fromImage(_render_icon(size)))
    return icon


def save_app_icon_ico(path: str) -> bool:
    """Write the shared mark as a multi-size PNG-backed Windows ICO."""
    try:
        entries = []
        payloads = []
        offset = 6 + 16 * len(ICON_SIZES)

        for size in ICON_SIZES:
            image = _render_icon(size)
            data = QByteArray()
            buffer = QBuffer(data)
            if not buffer.open(QIODevice.OpenModeFlag.WriteOnly):
                return False
            if not image.save(buffer, "PNG"):
                buffer.close()
                return False
            buffer.close()
            payload = bytes(data)
            entries.append(struct.pack(
                "<BBBBHHII",
                0 if size == 256 else size,
                0 if size == 256 else size,
                0, 0, 1, 32, len(payload), offset,
            ))
            payloads.append(payload)
            offset += len(payload)

        with open(path, "wb") as icon_file:
            icon_file.write(struct.pack("<HHH", 0, 1, len(entries)))
            icon_file.write(b"".join(entries))
            icon_file.write(b"".join(payloads))
        return True
    except (OSError, RuntimeError, TypeError, ValueError):
        return False
