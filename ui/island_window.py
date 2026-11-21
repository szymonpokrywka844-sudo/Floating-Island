"""
Główne bezramkowe okno Pływającej Wyspy (Floating Island).
Zintegrowana obsługa Drop Shelf: Przeciągnięcie pliku nad wyspę automatycznie
ją rozszerza i pozwala zapisać plik na półce oraz wyciągać go do innych apek.
"""
from PyQt6.QtCore import Qt, QPropertyAnimation, QEasingCurve, QRect, QTimer
from PyQt6.QtGui import QPainter, QPainterPath, QColor, QPen, QCursor, QGuiApplication
from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout

from core import config
from core.win32 import apply_window_tweaks, is_fullscreen_active
from core.theme import theme_manager
from modules.base import BaseModule
from modules.dropshelf import shelf_manager


class FloatingIsland(QWidget):
    PEEK_VISIBLE_HEIGHT = 5  # Liczba pikseli wystających z góry w trybie fullscreen

    def __init__(self, parent=None):
        super().__init__(parent)
        self.is_expanded = False
        self.is_hidden_by_fullscreen = False
        self.is_fullscreen_revealed = False
        self.is_showing_alert = False
        self.is_manually_hidden = False
        self.active_module: BaseModule = None

        # 1. Konfiguracja flag okna Qt
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        # Włączenie obsługi upuszczania plików (Drag & Drop)
        self.setAcceptDrops(True)

        # 2. Wykrywanie aktywnego monitora i jego globalnych współrzędnych
        cursor_pos = QCursor.pos()
        self.current_screen = QGuiApplication.screenAt(cursor_pos) or QApplication.primaryScreen()

        # Wczytaj zapisane ustawienia (przezroczystosc i pozycja)
        _s = self._load_settings()
        self._bg_opacity = int(_s.value("bg_opacity", 248))
        saved_offset = int(_s.value("top_offset", config.TOP_OFFSET))
        config.TOP_OFFSET = saved_offset
        self._update_screen_metrics(self.current_screen)

        # Monitorowanie zmiany monitora (debounce)
        self.pending_screen = None
        self.pending_screen_ticks = 0

        # Debounce trybu fullscreen
        self.pending_fs_state = False
        self.pending_fs_ticks = 0

        # 3. Zezwolenie na swobodne kurczenie okna i startowa pozycja
        self.setMinimumSize(0, 0)
        self.setGeometry(self._get_collapsed_rect())

        # 4. Płynna animacja geometrii
        self.geo_anim = QPropertyAnimation(self, b"geometry")
        self.geo_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        # 5. Układ główny
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(14, 6, 14, 8)
        self.main_layout.setSpacing(0)

        self.pill_container = None
        self.expanded_container = None

        # Reakcja na zmiane motywu
        theme_manager.theme_changed.connect(self._on_theme_changed)

        # 6. Pancerny Watchdog: mysz, monitory i tryb Fullscreen (80ms)
        self.watchdog = QTimer(self)
        self.watchdog.timeout.connect(self._watchdog_tick)
        self.watchdog.start(80)

    def _update_screen_metrics(self, screen):
        """Przelicza pozycje z uwzględnieniem offsetów monitora."""
        geo = screen.geometry()
        self.screen_center_x = geo.x() + (geo.width() // 2)
        self.screen_raw_top_y = geo.y()
        self.screen_top_y = geo.y() + config.TOP_OFFSET

    @staticmethod
    def _load_settings():
        from PyQt6.QtCore import QSettings
        return QSettings("FloatingIsland", "FloatingIsland")

    def _on_theme_changed(self, theme: str):
        """Odswieza malowidlo wyspy po zmianie motywu."""
        self.update()

    def showEvent(self, event):
        super().showEvent(event)
        apply_window_tweaks(int(self.winId()))

    def set_module(self, module: BaseModule):
        self.active_module = module
        module.island = self

        if self.pill_container:
            self.pill_container.deleteLater()
        if self.expanded_container:
            self.expanded_container.deleteLater()

        self.pill_container = module.get_pill_widget(self)
        self.expanded_container = module.get_expanded_widget(self)
        self.expanded_container.setVisible(False)

        # Przekaz referencje do okna dla strony ustawien (po utworzeniu widgetow)
        if hasattr(module, "_settings_page") and module._settings_page is not None:
            module._settings_page.set_island(self)

        self.main_layout.addWidget(self.pill_container)
        self.main_layout.addWidget(self.expanded_container)

        module.request_expand.connect(self.expand)
        module.request_collapse.connect(self.collapse)

    # ==========================================================
    # OBSŁUGA DRAG & DROP (DROP SHELF)
    # ==========================================================
    def dragEnterEvent(self, event):
        """Użytkownik przeciąga plik nad wyspę -> rozwiń i otwórz półkę!"""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            if not self.is_expanded:
                self.expand()
            if hasattr(self.active_module, "on_drag_enter"):
                self.active_module.on_drag_enter()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        """Zapisuje upuszczone pliki na półce lub jako skrót aplikacji."""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            for url in event.mimeData().urls():
                local_path = url.toLocalFile()
                if local_path:
                    # Jeśli aktywna jest zakładka SKRÓTY (indeks 4) w module
                    if (
                        hasattr(self.active_module, "exp_stack") and
                        self.active_module.exp_stack and
                        self.active_module.exp_stack.currentIndex() == 4 and
                        hasattr(self.active_module, "add_shortcut_path")
                    ):
                        self.active_module.add_shortcut_path(local_path)
                    else:
                        shelf_manager.add_file(local_path)
        else:
            super().dropEvent(event)

    def enterEvent(self, event):
        if self.is_hidden_by_fullscreen and not self.is_fullscreen_revealed:
            self._reveal_from_fullscreen()
        elif not self.is_expanded and not self.is_hidden_by_fullscreen:
            self.expand()
        super().enterEvent(event)

    def leaveEvent(self, event):
        super().leaveEvent(event)

    def contextMenuEvent(self, event):
        """Menu kontekstowe pod prawym przyciskiem myszy na wyspie."""
        from ui.tray_manager import create_context_menu
        menu = create_context_menu(self)
        menu.exec(event.globalPos())

    def recenter(self):
        """Przywraca wyspę na środek aktywnego monitora."""
        cursor_pos = QCursor.pos()
        screen = QGuiApplication.screenAt(cursor_pos) or QApplication.primaryScreen()
        self._update_screen_metrics(screen)
        self.current_screen = screen
        self.is_hidden_by_fullscreen = False
        self.is_fullscreen_revealed = False
        if self.is_expanded:
            self.collapse()
        self.geo_anim.stop()
        self.geo_anim.setDuration(240)
        self.geo_anim.setStartValue(self.geometry())
        self.geo_anim.setEndValue(self._get_collapsed_rect())
        self.geo_anim.start()

    def _watchdog_tick(self):
        cursor_pos = QCursor.pos()

        # 1. DETEKCJA ZMIANY MONITORA
        screen_under_cursor = QGuiApplication.screenAt(cursor_pos)
        if screen_under_cursor and screen_under_cursor != self.current_screen:
            if self.pending_screen == screen_under_cursor:
                self.pending_screen_ticks += 1
                if self.pending_screen_ticks >= 2:
                    self._migrate_to_screen(screen_under_cursor)
                    self.pending_screen = None
                    self.pending_screen_ticks = 0
            else:
                self.pending_screen = screen_under_cursor
                self.pending_screen_ticks = 1
        else:
            self.pending_screen = None
            self.pending_screen_ticks = 0

        # 2. DETEKCJA FULLSCREEN DLA EKRANU
        raw_fs = is_fullscreen_active(self.current_screen.geometry(), int(self.winId()))
        if raw_fs != self.is_hidden_by_fullscreen:
            if raw_fs == self.pending_fs_state:
                self.pending_fs_ticks += 1
                if self.pending_fs_ticks >= 2:
                    self.is_hidden_by_fullscreen = raw_fs
                    self._handle_fullscreen_change(raw_fs)
                    self.pending_fs_ticks = 0
            else:
                self.pending_fs_state = raw_fs
                self.pending_fs_ticks = 1
        else:
            self.pending_fs_ticks = 0

        # 3. INTERAKCJA Z MYSZKĄ
        if self.is_hidden_by_fullscreen:
            if self.is_fullscreen_revealed:
                window_rect = self.geometry().adjusted(-4, -4, 4, 4)
                if not window_rect.contains(cursor_pos):
                    self._hide_back_to_fullscreen_peek()
            else:
                peek_rect = self._get_hidden_rect().adjusted(-2, 0, 2, 4)
                if peek_rect.contains(cursor_pos):
                    self._reveal_from_fullscreen()
        else:
            if self.is_expanded:
                window_rect = self.geometry().adjusted(-4, -4, 4, 4)
                if not window_rect.contains(cursor_pos):
                    # Native popup menus are separate top-level windows. Keep
                    # the island expanded while its device menu is being used.
                    popup = QApplication.activePopupWidget()
                    if popup and popup.isVisible():
                        return
                    self.collapse()

    def _migrate_to_screen(self, new_screen):
        self.current_screen = new_screen
        self._update_screen_metrics(new_screen)

        if self.is_expanded:
            self.collapse()

        new_screen_is_fs = is_fullscreen_active(new_screen.geometry(), int(self.winId()))
        self.is_hidden_by_fullscreen = new_screen_is_fs
        self.is_fullscreen_revealed = False

        if new_screen_is_fs:
            target_rect = self._get_hidden_rect()
        else:
            target_rect = self._get_collapsed_rect()

        self.geo_anim.stop()
        self.geo_anim.setDuration(340)
        self.geo_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.geo_anim.setStartValue(self.geometry())
        self.geo_anim.setEndValue(target_rect)
        self.geo_anim.start()

    def _handle_fullscreen_change(self, is_fullscreen: bool):
        if is_fullscreen:
            self.is_fullscreen_revealed = False
            if self.is_expanded:
                self.collapse()

            target_rect = self._get_hidden_rect()
            self.geo_anim.stop()
            self.geo_anim.setDuration(260)
            self.geo_anim.setEasingCurve(QEasingCurve.Type.InCubic)
            self.geo_anim.setStartValue(self.geometry())
            self.geo_anim.setEndValue(target_rect)
            self.geo_anim.start()
        else:
            self.is_fullscreen_revealed = False
            target_rect = self._get_collapsed_rect()
            self.geo_anim.stop()
            self.geo_anim.setDuration(280)
            self.geo_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
            self.geo_anim.setStartValue(self.geometry())
            self.geo_anim.setEndValue(target_rect)
            self.geo_anim.start()

    def _reveal_from_fullscreen(self):
        self.is_fullscreen_revealed = True
        target_rect = self._get_collapsed_rect()

        self.geo_anim.stop()
        self.geo_anim.setDuration(220)
        self.geo_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.geo_anim.setStartValue(self.geometry())
        self.geo_anim.setEndValue(target_rect)
        self.geo_anim.start()

    def _hide_back_to_fullscreen_peek(self):
        self.is_fullscreen_revealed = False
        if self.is_expanded:
            self.collapse()

        target_rect = self._get_hidden_rect()
        self.geo_anim.stop()
        self.geo_anim.setDuration(240)
        self.geo_anim.setEasingCurve(QEasingCurve.Type.InCubic)
        self.geo_anim.setStartValue(self.geometry())
        self.geo_anim.setEndValue(target_rect)
        self.geo_anim.start()

    def expand(self):
        if self.is_expanded:
            return
        self.is_expanded = True

        if self.expanded_container:
            self.expanded_container.setVisible(True)

        if self.active_module:
            self.active_module.on_expand()

        self.geo_anim.stop()
        self.geo_anim.setDuration(240)
        self.geo_anim.setStartValue(self.geometry())
        self.geo_anim.setEndValue(self._get_expanded_rect())
        self.geo_anim.start()

    def collapse(self):
        if not self.is_expanded:
            return
        self.is_expanded = False

        if self.expanded_container:
            self.expanded_container.setVisible(False)

        if self.active_module:
            self.active_module.on_collapse()

        if self.is_hidden_by_fullscreen and not self.is_fullscreen_revealed:
            target_rect = self._get_hidden_rect()
        else:
            target_rect = self._get_collapsed_rect()

        self.geo_anim.stop()
        self.geo_anim.setDuration(220)
        self.geo_anim.setStartValue(self.geometry())
        self.geo_anim.setEndValue(target_rect)
        self.geo_anim.start()

    def set_manually_hidden(self, hidden: bool):
        """Hide the always-on-top window so the underlying browser tab is clickable."""
        hidden = bool(hidden)
        if hidden == self.is_manually_hidden:
            return

        self.is_manually_hidden = hidden
        self.geo_anim.stop()
        if hidden:
            if self.is_expanded:
                self.is_expanded = False
                if self.expanded_container:
                    self.expanded_container.setVisible(False)
                if self.active_module:
                    self.active_module.on_collapse()
            if self.pill_container:
                self.pill_container.setVisible(True)
            self.hide()
            return

        self.is_expanded = False
        if self.expanded_container:
            self.expanded_container.setVisible(False)
        if self.pill_container:
            self.pill_container.setVisible(True)
        target = (
            self._get_hidden_rect() if self.is_hidden_by_fullscreen
            else self._get_collapsed_rect()
        )
        self.setGeometry(target)
        self.show()
        self.raise_()

    def restore_from_tray(self):
        self.set_manually_hidden(False)

    def show_alert_banner(self, duration_ms: int = 4200):
        """
        Rozszerza pigulke w podluzny baner powiadomienia na okreslony czas.
        Dziala rowniez gdy wyspa jest zwinięta - animacja szerokosci.
        Gdy wyspa jest aktualnie rozwijana, pomija animacje (UI i tak jest widoczne).
        """
        if self.is_hidden_by_fullscreen:
            return
        if self.is_expanded:
            # Wyspa juz rozlozoona - powiadomienie widac w zakladce ALERTY, nie animuj
            return

        self.is_showing_alert = True
        target_rect = self._get_alert_rect()

        self.geo_anim.stop()
        self.geo_anim.setDuration(260)
        self.geo_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.geo_anim.setStartValue(self.geometry())
        self.geo_anim.setEndValue(target_rect)
        self.geo_anim.start()

        QTimer.singleShot(duration_ms, self._dismiss_alert_banner)

    def _dismiss_alert_banner(self):
        if not self.is_showing_alert or self.is_expanded:
            return
        self.is_showing_alert = False
        target_rect = self._get_collapsed_rect()

        self.geo_anim.stop()
        self.geo_anim.setDuration(220)
        self.geo_anim.setEasingCurve(QEasingCurve.Type.InCubic)
        self.geo_anim.setStartValue(self.geometry())
        self.geo_anim.setEndValue(target_rect)
        self.geo_anim.start()

    def show_call_banner(self, caller_name: str, on_accept=None, on_reject=None):
        """
        Wyswietla specjalny baner polaczenia przychodzacego z przyciskami
        Odbierz (zielony) i Odrzuc (czerwony). Baner utrzymuje sie 25 sekund
        lub do nacisnietcia przycisku przez uzytkownika.
        """
        if self.is_hidden_by_fullscreen or self.is_expanded:
            return

        from ui.vector_controls import CallActionButton, AppIconWidget
        from PyQt6.QtWidgets import QHBoxLayout

        self.is_showing_alert = True

        # Budujemy tymczasowy widget banera polaczenia wewnątrz pigulki
        if hasattr(self, "_call_banner_widget") and self._call_banner_widget:
            self._call_banner_widget.deleteLater()
            self._call_banner_widget = None

        call_widget = QWidget(self)
        call_widget.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        call_layout = QHBoxLayout(call_widget)
        call_layout.setContentsMargins(10, 0, 10, 0)
        call_layout.setSpacing(8)

        icon = AppIconWidget(AppIconWidget.KIND_CALL, size=22, parent=call_widget)
        call_layout.addWidget(icon)

        from PyQt6.QtWidgets import QLabel
        name_label = QLabel(caller_name or "Polaczenie przychodzace", call_widget)
        name_label.setStyleSheet("color: #FFFFFF; font-size: 12px; font-weight: bold;")
        call_layout.addWidget(name_label)
        call_layout.addStretch()

        btn_accept = CallActionButton(CallActionButton.TYPE_ACCEPT, size=30, parent=call_widget)
        btn_reject = CallActionButton(CallActionButton.TYPE_REJECT, size=30, parent=call_widget)
        call_layout.addWidget(btn_accept)
        call_layout.addWidget(btn_reject)

        # Podmiana zawartosc pill_container
        if self.pill_container:
            self.pill_container.setVisible(False)

        call_widget.setGeometry(0, 0, self._get_call_rect().width(), config.COLLAPSED_HEIGHT)
        self._call_banner_widget = call_widget

        def _dismiss_call():
            if hasattr(self, "_call_banner_widget") and self._call_banner_widget:
                self._call_banner_widget.setVisible(False)
                self._call_banner_widget.deleteLater()
                self._call_banner_widget = None
            if self.pill_container:
                self.pill_container.setVisible(True)
            self._dismiss_alert_banner()

        def _on_accept():
            if on_accept:
                on_accept()
            _dismiss_call()

        def _on_reject():
            if on_reject:
                on_reject()
            _dismiss_call()

        btn_accept.clicked.connect(_on_accept)
        btn_reject.clicked.connect(_on_reject)

        target_rect = self._get_call_rect()
        self.geo_anim.stop()
        self.geo_anim.setDuration(280)
        self.geo_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.geo_anim.setStartValue(self.geometry())
        self.geo_anim.setEndValue(target_rect)
        self.geo_anim.start()

        call_widget.setGeometry(0, 0, target_rect.width(), config.COLLAPSED_HEIGHT)
        call_widget.show()

        # Auto-odrzucenie po 25 sekundach
        QTimer.singleShot(25000, _dismiss_call)

    def _get_call_rect(self) -> QRect:
        CALL_WIDTH = 400
        return QRect(
            self.screen_center_x - CALL_WIDTH // 2,
            self.screen_top_y,
            CALL_WIDTH,
            config.COLLAPSED_HEIGHT
        )

    def _get_alert_rect(self) -> QRect:
        ALERT_WIDTH = 360
        return QRect(
            self.screen_center_x - ALERT_WIDTH // 2,
            self.screen_top_y,
            ALERT_WIDTH,
            config.COLLAPSED_HEIGHT
        )

    def _get_collapsed_rect(self) -> QRect:
        return QRect(
            self.screen_center_x - config.COLLAPSED_WIDTH // 2,
            self.screen_top_y,
            config.COLLAPSED_WIDTH,
            config.COLLAPSED_HEIGHT
        )

    def _get_expanded_rect(self) -> QRect:
        return QRect(
            self.screen_center_x - config.EXPANDED_WIDTH // 2,
            self.screen_top_y,
            config.EXPANDED_WIDTH,
            config.EXPANDED_HEIGHT
        )

    def _get_hidden_rect(self) -> QRect:
        return QRect(
            self.screen_center_x - config.COLLAPSED_WIDTH // 2,
            self.screen_raw_top_y - config.COLLAPSED_HEIGHT + self.PEEK_VISIBLE_HEIGHT,
            config.COLLAPSED_WIDTH,
            config.COLLAPSED_HEIGHT
        )

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.rect()
        w = rect.width()
        h = rect.height()

        if not self.is_expanded:
            radius = h / 2.0
        else:
            radius = min(h / 2.0, 24.0)

        # Kolory z ThemeManager (reaguja na zmiane motywu)
        glow_c = theme_manager.glow_color
        bg_c = theme_manager.bg_color
        bg_c.setAlpha(self._bg_opacity)
        border_c = theme_manager.border_color

        # 1. Zewnetrzna poswata ambientowa
        glow_path = QPainterPath()
        glow_path.addRoundedRect(0.5, 0.5, w - 1.0, h - 1.0, radius, radius)
        painter.setPen(QPen(glow_c, 2.0))
        painter.drawPath(glow_path)

        # 2. Glowna pigulka
        body_path = QPainterPath()
        body_path.addRoundedRect(1.0, 1.0, w - 2.0, h - 2.0, radius - 0.5, radius - 0.5)
        painter.fillPath(body_path, bg_c)

        # 3. Subtelna szklana krawedz 1px
        painter.setPen(QPen(border_c, 1.0))
        painter.drawPath(body_path)
