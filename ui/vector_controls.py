"""
Autorskie wektorowe kontrolki, animowane fale 60 FPS, zielone/białe oczka
oraz autorskie wektorowe ikony użytkowe (Zero emotek w całym projekcie).
Pełna kompatybilność z Windows: Lacze z telefonem, SMS, polaczenia, Discord, Steam.
"""
import math
import random
from PyQt6.QtCore import Qt, QTimer, QPointF, QRectF
from PyQt6.QtGui import QPainter, QColor, QPainterPath, QBrush, QPen, QCursor
from PyQt6.QtWidgets import QWidget, QPushButton, QHBoxLayout, QLabel


# Import opózniony - unikamy cyklu importu przy uruchamianiu modulu
def _get_theme_manager():
    from core.theme import theme_manager
    return theme_manager


class AppIconWidget(QWidget):
    """
    Wektorowa ikona aplikacji-nadawcy powiadomienia.
    Wszystkie ikony rysowane czystym QPainter - zero obrazkow, zero emotek.

    Obslugiwane rodzaje (kind):
      "phone"   - sluchawka telefonu (Lacze z telefonem)
      "sms"     - dymek wiadomosci (SMS z Phone Link)
      "call"    - dzwoniacy telefon (polaczenie przychodzace)
      "discord" - stylizowany kontroler (Discord)
      "steam"   - kolo zebate / trojkat uruchomienia (Steam)
      "teams"   - litera T w kwadracie (Teams)
      "xbox"    - okrag z X (Xbox)
      "generic" - dzwonek systemowy
    """
    KIND_PHONE   = "phone"
    KIND_SMS     = "sms"
    KIND_CALL    = "call"
    KIND_DISCORD = "discord"
    KIND_STEAM   = "steam"
    KIND_TEAMS   = "teams"
    KIND_XBOX    = "xbox"
    KIND_GENERIC = "generic"

    # Kolory badge dla kazdego rodzaju
    _COLORS = {
        "phone":   ("#34C759", "#FFFFFF"),   # Zielony, bialy
        "sms":     ("#0A84FF", "#FFFFFF"),   # Niebieski, bialy
        "call":    ("#34C759", "#FFFFFF"),   # Zielony, bialy
        "discord": ("#5865F2", "#FFFFFF"),   # Fioletowy, bialy
        "steam":   ("#1B2838", "#C6D4DF"),   # Ciemnoniebieski, jasny
        "teams":   ("#6264A7", "#FFFFFF"),   # Fioletowy Teams, bialy
        "xbox":    ("#107C10", "#FFFFFF"),   # Zielony Xbox, bialy
        "generic": ("#3A3A3C", "#FFFFFF"),   # Ciemnosary, bialy
    }

    def __init__(self, kind: str = "generic", size: int = 20, parent=None):
        super().__init__(parent)
        self.kind = kind
        self.setFixedSize(size, size)

    def set_kind(self, kind: str):
        self.kind = kind
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        cx = w / 2.0
        cy = h / 2.0
        r = min(w, h) / 2.0 - 0.5

        bg_hex, fg_hex = self._COLORS.get(self.kind, self._COLORS["generic"])
        bg = QColor(bg_hex)
        fg = QColor(fg_hex)

        # Okragle tlo
        painter.setBrush(QBrush(bg))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QRectF(0.5, 0.5, w - 1.0, h - 1.0))

        painter.setPen(QPen(fg, max(1.0, w * 0.09), Qt.PenStyle.SolidLine,
                            Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        painter.setBrush(Qt.BrushStyle.NoBrush)

        pad = w * 0.22

        if self.kind in (self.KIND_PHONE, self.KIND_CALL):
            # Sluchawka: wygiety ksztalt ze spirala
            path = QPainterPath()
            path.moveTo(cx - r * 0.5, cy - r * 0.6)
            path.cubicTo(cx - r * 0.5, cy - r * 0.9,
                         cx + r * 0.5, cy - r * 0.9,
                         cx + r * 0.5, cy - r * 0.6)
            path.cubicTo(cx + r * 0.5, cy - r * 0.3,
                         cx + r * 0.15, cy,
                         cx + r * 0.5, cy + r * 0.6)
            painter.drawPath(path)
            # Koniec sluchawki (maly okrag po lewej stronie)
            painter.setBrush(QBrush(fg))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(QRectF(cx - r * 0.65, cy + r * 0.3, r * 0.3, r * 0.3))
            painter.drawEllipse(QRectF(cx + r * 0.35, cy + r * 0.3, r * 0.3, r * 0.3))

            if self.kind == self.KIND_CALL:
                # Fale sygnalu przy dzwoniacym telefonie
                painter.setBrush(Qt.BrushStyle.NoBrush)
                pen2 = QPen(fg, max(0.8, w * 0.07))
                pen2.setCapStyle(Qt.PenCapStyle.RoundCap)
                painter.setPen(pen2)
                arc1 = QRectF(cx - r * 0.9, cy - r * 0.3, r * 0.3, r * 0.6)
                painter.drawArc(arc1, 60 * 16, 60 * 16)
                arc2 = QRectF(cx + r * 0.6, cy - r * 0.3, r * 0.3, r * 0.6)
                painter.drawArc(arc2, 120 * 16, -60 * 16)

        elif self.kind == self.KIND_SMS:
            # Dymek wiadomosci
            path = QPainterPath()
            path.addRoundedRect(pad, pad, w - pad * 2, h - pad * 2.5, r * 0.35, r * 0.35)
            # Ogon dymka
            path.moveTo(cx - r * 0.1, h - pad * 2.2)
            path.lineTo(cx - r * 0.5, h - pad * 0.6)
            path.lineTo(cx + r * 0.3, h - pad * 2.2)
            painter.setBrush(QBrush(fg))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawPath(path)
            # Trzy kreski tekstu w dymku
            painter.setBrush(QBrush(bg))
            painter.setPen(Qt.PenStyle.NoPen)
            line_h = max(1.0, h * 0.07)
            for i, lx in enumerate([pad * 1.6, pad * 1.6, pad * 1.6]):
                ly = pad * 1.5 + i * (line_h + h * 0.08)
                lw = (w - pad * 3.2) * (0.9 if i < 2 else 0.6)
                painter.drawRoundedRect(QRectF(lx, ly, lw, line_h), 0.5, 0.5)

        elif self.kind == self.KIND_DISCORD:
            # Stylizowany kontroler / maska Discord (uproszczony)
            painter.setBrush(QBrush(fg))
            painter.setPen(Qt.PenStyle.NoPen)
            # Glowna maska - zaokraglony prostopadloscian
            mask = QPainterPath()
            mask.addRoundedRect(pad * 0.8, pad * 1.2, w - pad * 1.6, h - pad * 2.0, r * 0.4, r * 0.4)
            painter.drawPath(mask)
            # Dwa oczka
            painter.setBrush(QBrush(bg))
            eye_r = max(1.5, r * 0.18)
            painter.drawEllipse(QRectF(cx - r * 0.42 - eye_r, cy - eye_r, eye_r * 2, eye_r * 2))
            painter.drawEllipse(QRectF(cx + r * 0.42 - eye_r, cy - eye_r, eye_r * 2, eye_r * 2))
            # Usmiech
            pen3 = QPen(bg, max(1.0, w * 0.085))
            pen3.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen3)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            smile = QRectF(cx - r * 0.32, cy + r * 0.08, r * 0.64, r * 0.4)
            painter.drawArc(smile, 0, -180 * 16)

        elif self.kind == self.KIND_STEAM:
            # Trojkat "uruchom" w kole (Steam launch arrow)
            painter.setBrush(QBrush(fg))
            painter.setPen(Qt.PenStyle.NoPen)
            path = QPainterPath()
            s = r * 0.55
            path.moveTo(cx - s * 0.65, cy - s)
            path.lineTo(cx + s * 1.1, cy)
            path.lineTo(cx - s * 0.65, cy + s)
            path.closeSubpath()
            painter.drawPath(path)

        elif self.kind == self.KIND_TEAMS:
            # Litera T + maly okrag z czlowiekiem
            painter.setBrush(QBrush(fg))
            painter.setPen(Qt.PenStyle.NoPen)
            # Pozioma belka T
            beam_h = max(1.5, h * 0.12)
            beam_w = w - pad * 1.4
            painter.drawRoundedRect(QRectF(pad * 0.7, pad * 1.1, beam_w, beam_h), 0.8, 0.8)
            # Pionowa belka T
            vert_w = max(2.0, w * 0.13)
            vert_h = h - pad * 2.6
            painter.drawRoundedRect(QRectF(cx - vert_w / 2, pad * 1.1 + beam_h, vert_w, vert_h), 0.8, 0.8)
            # Maly okrag (glowa czlowieka)
            head_r = r * 0.22
            painter.drawEllipse(QRectF(cx + r * 0.28, pad * 0.5, head_r * 2, head_r * 2))

        elif self.kind == self.KIND_XBOX:
            # Duze X wpisane w okrag
            pen4 = QPen(fg, max(1.5, w * 0.14))
            pen4.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen4)
            d = r * 0.52
            painter.drawLine(QPointF(cx - d, cy - d), QPointF(cx + d, cy + d))
            painter.drawLine(QPointF(cx + d, cy - d), QPointF(cx - d, cy + d))

        else:
            # Dzwonek systemowy (generic)
            painter.setBrush(QBrush(fg))
            painter.setPen(Qt.PenStyle.NoPen)
            # Kapelusz dzwonka
            bell = QPainterPath()
            bell.moveTo(cx, pad * 0.9)
            bell.cubicTo(cx + r * 0.7, pad * 0.9, cx + r * 0.75, cy, cx + r * 0.75, cy + r * 0.3)
            bell.lineTo(cx + r * 0.9, cy + r * 0.6)
            bell.lineTo(cx - r * 0.9, cy + r * 0.6)
            bell.lineTo(cx - r * 0.75, cy + r * 0.3)
            bell.cubicTo(cx - r * 0.75, cy, cx - r * 0.7, pad * 0.9, cx, pad * 0.9)
            painter.drawPath(bell)
            # Raczka dzwonka
            clapper_r = r * 0.18
            painter.drawEllipse(QRectF(cx - clapper_r, cy + r * 0.6, clapper_r * 2, clapper_r * 2))


class VectorCloseButton(QPushButton):
    """
    Autorski wektorowy przycisk zamykania (X).
    Rysowany czystą geometrią w QPainter, brak znaku tekstowego '×'.
    """
    def __init__(self, size: int = 18, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.is_hovered = False

    def enterEvent(self, event):
        self.is_hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.is_hovered = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()

        if self.is_hovered:
            painter.setBrush(QBrush(QColor(255, 69, 58, 220)))  # Czerwone tło hover
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(1, 1, w - 2, h - 2)
            cross_color = QColor(255, 255, 255)
        else:
            tm = _get_theme_manager()
            cross_color = QColor(tm.text_secondary)

        # Wektorowe skrzyżowanie linii
        pen = QPen(cross_color, 1.4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)

        pad = w * 0.32
        painter.drawLine(int(pad), int(pad), int(w - pad), int(h - pad))
        painter.drawLine(int(w - pad), int(pad), int(pad), int(h - pad))


class ShelfBadgeWidget(QFrame if False else QWidget):
    """
    Autorski wektorowy badge na pigułce informujący o plikach na półce (np. [ [tacka] 2 ]).
    Zero emotek - ikonka tacki rysowana wektorowo.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.count = 0
        self.setFixedHeight(18)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setVisible(False)

    def set_count(self, count: int):
        self.count = count
        if count > 0:
            # Dopasuj szerokość do cyfr
            w = 26 if count < 10 else 32
            self.setFixedSize(w, 18)
            self.setVisible(True)
        else:
            self.setVisible(False)
        self.update()

    def paintEvent(self, event):
        if self.count <= 0:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()

        tm = _get_theme_manager()
        is_dark = tm.is_dark

        # Tło kapsułki
        bg_path = QPainterPath()
        bg_path.addRoundedRect(0.5, 0.5, w - 1, h - 1, 4.0, 4.0)
        bg_col = QColor(40, 40, 44) if is_dark else QColor(225, 225, 230)
        border_col = QColor(60, 60, 66) if is_dark else QColor(200, 200, 205)
        pen_col = QColor(220, 220, 225) if is_dark else QColor(40, 40, 45)
        text_col = QColor(245, 245, 250) if is_dark else QColor(26, 26, 28)

        painter.fillPath(bg_path, bg_col)
        painter.setPen(QPen(border_col, 1.0))
        painter.drawPath(bg_path)

        # 1. Wektorowa ikonka otwartej tacki/półki na pliki
        pen = QPen(pen_col, 1.1, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        tray = QPainterPath()
        # Rysowanie tacki
        tray.moveTo(4.0, 6.0)
        tray.lineTo(4.0, 12.0)
        tray.lineTo(12.0, 12.0)
        tray.lineTo(12.0, 6.0)
        painter.drawPath(tray)

        # Wnętrze tacki (mała pozioma kreska pliku)
        painter.drawLine(6, 9, 10, 9)

        # 2. Liczba plików
        painter.setPen(text_col)
        font = painter.font()
        font.setPixelSize(10)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(QRectF(14.0, 0.0, w - 14.0, h), Qt.AlignmentFlag.AlignCenter, str(self.count))


class LivingEyesWidget(QWidget):
    """
    Dwie minimalistyczne, neonowo-białe kropki z organiczną płynnością (Liquid Inertia).
    Mruganie oparte na fali sinusoidalnej, a ruch gałek na miękkiej inercji (lerp 0.12).
    """
    def __init__(self, size: str = "small", parent=None):
        super().__init__(parent)
        self.size_mode = size
        self.dot_color = QColor("#FFFFFF")

        if size == "small":
            self.setFixedSize(26, 20)
            self.dot_w = 4.0
            self.dot_h = 7.0
            self.spacing = 8.0
            self.max_drift = 3.2
        else:
            self.setFixedSize(54, 34)
            self.dot_w = 8.0
            self.dot_h = 15.0
            self.spacing = 18.0
            self.max_drift = 6.0

        self.drift_x = 0.0
        self.drift_y = 0.0
        self.target_drift_x = 0.0
        self.target_drift_y = 0.0

        self.blink_progress = 0.0
        self.is_blinking = False

        self.blink_timer = QTimer(self)
        self.blink_timer.timeout.connect(self._trigger_blink)
        self._schedule_next_blink()

        self.anim_timer = QTimer(self)
        self.anim_timer.timeout.connect(self._tick)
        self.anim_timer.start(16)

        # Synchronizacja koloru z motywem
        tm = _get_theme_manager()
        self._sync_color(tm.effective_theme)
        tm.theme_changed.connect(self._sync_color)

    def _sync_color(self, theme: str):
        """Ustawia kolor kropelek zgodny z biezacym motywem."""
        tm = _get_theme_manager()
        self.dot_color = QColor(tm.eyes_color)
        self.update()

    def set_color(self, hex_color: str):
        self.dot_color = QColor(hex_color)
        self.update()

    def _schedule_next_blink(self):
        ms = random.randint(2800, 5200)
        self.blink_timer.start(ms)

    def _trigger_blink(self):
        if not self.is_blinking:
            self.is_blinking = True
            self.blink_progress = 0.0
        self._schedule_next_blink()

    def _tick(self):
        if self.is_blinking:
            self.blink_progress += 0.09
            if self.blink_progress >= 1.0:
                self.blink_progress = 0.0
                self.is_blinking = False

        global_cursor = QCursor.pos()
        local_pos = self.mapFromGlobal(global_cursor)

        center_x = self.width() / 2.0
        center_y = self.height() / 2.0

        dx = local_pos.x() - center_x
        dy = local_pos.y() - center_y
        dist = math.hypot(dx, dy)

        if dist > 0.1:
            angle = math.atan2(dy, dx)
            intensity = min(1.0, math.sqrt(dist / 400.0))
            self.target_drift_x = math.cos(angle) * (self.max_drift * intensity)
            self.target_drift_y = math.sin(angle) * (self.max_drift * intensity)
        else:
            self.target_drift_x = 0.0
            self.target_drift_y = 0.0

        self.drift_x += (self.target_drift_x - self.drift_x) * 0.12
        self.drift_y += (self.target_drift_y - self.drift_y) * 0.12

        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        cx = (self.width() / 2.0) + self.drift_x
        cy = (self.height() / 2.0) + self.drift_y

        left_x = cx - (self.spacing / 2.0) - (self.dot_w / 2.0)
        right_x = cx + (self.spacing / 2.0) - (self.dot_w / 2.0)

        if self.is_blinking:
            blink_curve = math.sin(self.blink_progress * math.pi)
            factor = 1.0 - (0.82 * blink_curve)
        else:
            factor = 1.0

        current_h = max(1.6, self.dot_h * factor)
        y = cy - (current_h / 2.0)
        radius = self.dot_w / 2.0

        painter.setBrush(QBrush(self.dot_color))
        painter.setPen(Qt.PenStyle.NoPen)

        painter.drawRoundedRect(int(left_x), int(y), int(self.dot_w), int(current_h), radius, radius)
        painter.drawRoundedRect(int(right_x), int(y), int(self.dot_w), int(current_h), radius, radius)


class WaveformVisualizer(QWidget):
    """
    Wizualizator fal audio z organiczną inercją cieczy (Liquid Wave).
    Dostosowuje kolor do biezacego motywu (czarne fale w jasnym motywie, biale w ciemnym).
    """
    def __init__(self, num_bars: int = 5, bar_width: int = 3, bar_gap: int = 3, parent=None):
        super().__init__(parent)
        self.num_bars = num_bars
        self.bar_width = bar_width
        self.bar_gap = bar_gap
        self.is_playing = False
        self._custom_accent = False
        self.wave_color = QColor(_get_theme_manager().text_primary)

        self.current_heights = [3.0] * num_bars
        self.target_heights = [3.0] * num_bars
        self.phases = [random.uniform(0, math.pi * 2) for _ in range(num_bars)]
        self.frequencies = [random.uniform(3.0, 6.0) for _ in range(num_bars)]

        self.time_counter = 0.0
        self.hover_pos_x = -1.0

        self.anim_timer = QTimer(self)
        self.anim_timer.timeout.connect(self._tick)
        self.anim_timer.start(16)

        total_w = num_bars * bar_width + (num_bars - 1) * bar_gap
        self.setFixedSize(total_w + 4, 22)
        self.setMouseTracking(True)

        _get_theme_manager().theme_changed.connect(self._sync_theme)

    def _sync_theme(self, theme: str):
        if not self._custom_accent:
            self.wave_color = QColor(_get_theme_manager().text_primary)
            self.update()

    def set_playing(self, playing: bool):
        self.is_playing = playing
        if not playing:
            self._custom_accent = False
            self.wave_color = QColor(_get_theme_manager().text_primary)
            self.update()

    def set_accent_color(self, hex_color: str):
        tm = _get_theme_manager()
        if hex_color.upper() in ("#FFFFFF", "#FFF") and not tm.is_dark:
            hex_color = tm.text_primary
        self.wave_color = QColor(hex_color)
        self._custom_accent = True
        self.update()

    def enterEvent(self, event):
        self.hover_pos_x = event.position().x()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.hover_pos_x = -1.0
        super().leaveEvent(event)

    def mouseMoveEvent(self, event):
        self.hover_pos_x = event.position().x()
        super().mouseMoveEvent(event)

    def _tick(self):
        self.time_counter += 0.04
        max_h = float(self.height() - 4)
        min_h = 3.0

        for i in range(self.num_bars):
            if self.is_playing:
                raw_wave = (
                    math.sin(self.time_counter * self.frequencies[i] + self.phases[i]) * 0.65 +
                    math.cos(self.time_counter * (self.frequencies[i] * 0.45)) * 0.35
                )
                norm = max(0.12, (raw_wave + 1.0) / 2.0)
                target = min_h + norm * (max_h - min_h)

                if self.hover_pos_x >= 0:
                    bar_x = i * (self.bar_width + self.bar_gap)
                    dist = abs(self.hover_pos_x - bar_x)
                    if dist < 24:
                        boost = (1.0 - (dist / 24.0)) * 6.5
                        target = min(max_h, target + boost)

                self.target_heights[i] = target
            else:
                self.target_heights[i] = min_h

            self.current_heights[i] += (self.target_heights[i] - self.current_heights[i]) * 0.13

        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        center_y = self.height() / 2.0
        painter.setBrush(QBrush(self.wave_color))
        painter.setPen(Qt.PenStyle.NoPen)

        for i in range(self.num_bars):
            h = self.current_heights[i]
            x = i * (self.bar_width + self.bar_gap) + 2
            y = center_y - (h / 2.0)
            radius = self.bar_width / 2.0
            painter.drawRoundedRect(int(x), int(y), int(self.bar_width), int(h), radius, radius)


class VectorIconButton(QPushButton):
    """
    Autorski przycisk z wektorową ikoną i aksamitnym stanem przejścia.
    """
    TYPE_PLAY = "play"
    TYPE_PAUSE = "pause"
    TYPE_NEXT = "next"
    TYPE_PREV = "prev"

    def __init__(self, icon_type: str, size: int = 32, is_primary: bool = False, parent=None):
        super().__init__(parent)
        self.icon_type = icon_type
        self.is_primary = is_primary
        self.is_hovered = False
        self.is_pressed_state = False

        self.setFixedSize(size, size)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_icon_type(self, icon_type: str):
        if self.icon_type != icon_type:
            self.icon_type = icon_type
            self.update()

    def enterEvent(self, event):
        self.is_hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.is_hovered = False
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        self.is_pressed_state = True
        self.update()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        self.is_pressed_state = False
        self.update()
        super().mouseReleaseEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        radius = min(w, h) / 2.0

        tm = _get_theme_manager()
        is_dark = tm.is_dark

        if self.is_primary:
            if is_dark:
                if self.is_pressed_state:
                    bg = QColor(195, 195, 200)
                elif self.is_hovered:
                    bg = QColor(255, 255, 255, 245)
                else:
                    bg = QColor(255, 255, 255, 215)
                icon_color = QColor(10, 10, 12)
            else:
                if self.is_pressed_state:
                    bg = QColor(60, 60, 64)
                elif self.is_hovered:
                    bg = QColor(10, 10, 12)
                else:
                    bg = QColor(28, 28, 30)
                icon_color = QColor(255, 255, 255)
        else:
            if is_dark:
                if self.is_pressed_state:
                    bg = QColor(22, 22, 24)
                elif self.is_hovered:
                    bg = QColor(50, 50, 54)
                else:
                    bg = QColor(34, 34, 36)
                icon_color = QColor(240, 240, 245)
            else:
                if self.is_pressed_state:
                    bg = QColor(190, 190, 196)
                elif self.is_hovered:
                    bg = QColor(210, 210, 216)
                else:
                    bg = QColor(226, 226, 232)
                icon_color = QColor(28, 28, 30)

        painter.setBrush(QBrush(bg))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(0, 0, w, h, radius, radius)

        painter.setBrush(QBrush(icon_color))
        painter.setPen(Qt.PenStyle.NoPen)

        cx = w / 2.0
        cy = h / 2.0

        if self.icon_type == self.TYPE_PLAY:
            path = QPainterPath()
            s = w * 0.28
            path.moveTo(cx - s * 0.7, cy - s)
            path.lineTo(cx + s * 1.1, cy)
            path.lineTo(cx - s * 0.7, cy + s)
            path.closeSubpath()
            painter.drawPath(path)

        elif self.icon_type == self.TYPE_PAUSE:
            bar_w = w * 0.12
            bar_h = h * 0.44
            gap = w * 0.10
            r = bar_w / 2.0
            painter.drawRoundedRect(int(cx - gap - bar_w), int(cy - bar_h / 2), int(bar_w), int(bar_h), r, r)
            painter.drawRoundedRect(int(cx + gap), int(cy - bar_h / 2), int(bar_w), int(bar_h), r, r)

        elif self.icon_type == self.TYPE_NEXT:
            path = QPainterPath()
            s = w * 0.22
            path.moveTo(cx - s * 0.9, cy - s)
            path.lineTo(cx + s * 0.4, cy)
            path.lineTo(cx - s * 0.9, cy + s)
            path.closeSubpath()
            painter.drawPath(path)
            bar_w = 2.5
            bar_h = s * 2.0
            painter.drawRoundedRect(int(cx + s * 0.5), int(cy - bar_h / 2), int(bar_w), int(bar_h), 1.0, 1.0)

        elif self.icon_type == self.TYPE_PREV:
            path = QPainterPath()
            s = w * 0.22
            bar_w = 2.5
            bar_h = s * 2.0
            painter.drawRoundedRect(int(cx - s * 0.5 - bar_w), int(cy - bar_h / 2), int(bar_w), int(bar_h), 1.0, 1.0)
            path.moveTo(cx + s * 0.9, cy - s)
            path.lineTo(cx - s * 0.4, cy)
            path.lineTo(cx + s * 0.9, cy + s)
            path.closeSubpath()
            painter.drawPath(path)



class CallActionButton(QPushButton):
    """
    Wektorowy przycisk akcji polaczenia (Odbierz / Odrzuc).
    Zielony = odbierz (sluchawka w gore), czerwony = odrzuc (sluchawka w dol).
    """
    TYPE_ACCEPT = "accept"
    TYPE_REJECT = "reject"

    def __init__(self, btn_type: str, size: int = 36, parent=None):
        super().__init__(parent)
        self.btn_type = btn_type
        self.is_hovered = False
        self.is_pressed_state = False
        self.setFixedSize(size, size)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def enterEvent(self, event):
        self.is_hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.is_hovered = False
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        self.is_pressed_state = True
        self.update()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        self.is_pressed_state = False
        self.update()
        super().mouseReleaseEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        cx = w / 2.0
        cy = h / 2.0
        r = min(w, h) / 2.0 - 0.5

        if self.btn_type == self.TYPE_ACCEPT:
            if self.is_pressed_state:
                bg = QColor(50, 180, 90)
            elif self.is_hovered:
                bg = QColor(60, 215, 100)
            else:
                bg = QColor(52, 199, 89)   # Zielony systemowy
        else:
            if self.is_pressed_state:
                bg = QColor(190, 50, 42)
            elif self.is_hovered:
                bg = QColor(230, 60, 50)
            else:
                bg = QColor(255, 69, 58)   # Czerwony systemowy

        # Okragle tlo
        painter.setBrush(QBrush(bg))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QRectF(0.5, 0.5, w - 1.0, h - 1.0))

        # Wektorowa sluchawka (skierowana w gore = odbierz, w dol = odrzuc)
        pen = QPen(QColor(255, 255, 255), max(1.4, w * 0.09),
                   Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        # Luk sluchawki (gorna czesc)
        arc_rect = QRectF(cx - r * 0.5, cy - r * 0.65, r, r * 0.7)
        painter.drawArc(arc_rect, 0, 180 * 16)

        # Lewa czesc sluchawki (pionowa kreska w dol-lewo)
        painter.setBrush(QBrush(QColor(255, 255, 255)))
        painter.setPen(Qt.PenStyle.NoPen)
        end_r = r * 0.19

        if self.btn_type == self.TYPE_ACCEPT:
            # Sluchawka normalna (pionowo)
            painter.drawEllipse(QRectF(cx - r * 0.5 - end_r * 0.5, cy - r * 0.3, end_r * 2, end_r * 2))
            painter.drawEllipse(QRectF(cx + r * 0.5 - end_r * 1.5, cy - r * 0.3, end_r * 2, end_r * 2))
        else:
            # Sluchawka obrócona (odrzucenie - 135 stopni)
            painter.setBrush(QBrush(QColor(255, 255, 255)))
            path = QPainterPath()
            angle = math.radians(45)
            ax = math.cos(angle)
            ay = math.sin(angle)
            lx = cx - r * 0.5
            ly = cy + r * 0.1
            rx2 = cx + r * 0.5
            ry2 = cy - r * 0.4
            painter.drawEllipse(QRectF(lx - end_r, ly - end_r, end_r * 2, end_r * 2))
            painter.drawEllipse(QRectF(rx2 - end_r, ry2 - end_r, end_r * 2, end_r * 2))



class VectorGearButton(QPushButton):
    """
    Autorski wektorowy przycisk zębatki (Ustawienia).
    Rysowany czystą geometrią QPainter - zero emotek i grafik.
    """
    def __init__(self, size: int = 24, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.is_hovered = False

    def enterEvent(self, event):
        self.is_hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.is_hovered = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        cx = w / 2.0
        cy = h / 2.0
        r_outer = min(w, h) * 0.42
        r_inner = r_outer * 0.48

        tm = _get_theme_manager()
        is_dark = tm.is_dark
        is_active = bool(self.property("active"))

        if is_active or self.is_hovered:
            color = QColor(255, 255, 255) if is_dark else QColor(26, 26, 28)
            bg_c = QColor(255, 255, 255, 24) if is_dark else QColor(0, 0, 0, 20)
            bg_path = QPainterPath()
            bg_path.addRoundedRect(1, 1, w - 2, h - 2, 4, 4)
            painter.fillPath(bg_path, bg_c)
        else:
            color = QColor(142, 142, 147) if is_dark else QColor(108, 108, 112)

        # Wektorowe zęby zębatki (6 ząbków)
        num_teeth = 6
        pen = QPen(color, max(1.8, w * 0.12), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)

        for i in range(num_teeth):
            angle = i * (2 * math.pi / num_teeth)
            x1 = cx + math.cos(angle) * (r_outer * 0.6)
            y1 = cy + math.sin(angle) * (r_outer * 0.6)
            x2 = cx + math.cos(angle) * r_outer
            y2 = cy + math.sin(angle) * r_outer
            painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))

        # Zewnętrzny pierścień
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QRectF(cx - r_outer * 0.72, cy - r_outer * 0.72, r_outer * 1.44, r_outer * 1.44))

        # Wewnętrzny otwór
        painter.setBrush(QBrush(color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QRectF(cx - r_inner * 0.5, cy - r_inner * 0.5, r_inner, r_inner))


class VectorToggleSwitch(QPushButton):
    """
    Wektorowy przełącznik suwakowy (Włącz / Wyłącz) w stylu iOS / Windows 11.
    Zero grafik rastrowych i emotek - czysty QPainter.
    """
    def __init__(self, checked: bool = False, width: int = 38, height: int = 20, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(checked)
        self.setFixedSize(width, height)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.toggled.connect(lambda: self.update())

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        radius = h / 2.0
        is_on = self.isChecked()

        # Tło kapsułki
        bg_color = QColor(52, 199, 89) if is_on else QColor(58, 58, 60)
        bg_path = QPainterPath()
        bg_path.addRoundedRect(QRectF(0, 0, w, h), radius, radius)
        painter.fillPath(bg_path, bg_color)

        # Suwak (biała kropka)
        thumb_r = (h - 4.0) / 2.0
        thumb_x = (w - h + 2.0) if is_on else 2.0
        thumb_y = 2.0

        painter.setBrush(QBrush(QColor(255, 255, 255)))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QRectF(thumb_x, thumb_y, thumb_r * 2.0, thumb_r * 2.0))
