"""
Główny moduł wyspy integrujący:
1. Tryb Standby (białe minimalistyczne kropki śledzące kursor).
2. Odtwarzacz audio (SoundCloud, Spotify, YouTube).
3. Drop Shelf (półka na pliki w stylu Yoink/Dropover).
4. System Windows Notifications Hub (Łącze z telefonem / SMS / Discord / System).
"""
import os
import time
import base64
import subprocess
import threading
from PyQt6.QtCore import Qt, QTimer, QTime, QDate, QSettings, QUrl, QFileInfo, QSize, QPoint, pyqtSignal
from PyQt6.QtGui import QAction, QActionGroup, QDesktopServices, QPixmap
from PyQt6.QtWidgets import (
    QApplication, QWidget, QHBoxLayout, QVBoxLayout, QLabel, QStackedWidget,
    QPushButton, QScrollArea, QFrame, QFileDialog, QFileIconProvider, QMenu
)
from modules.base import BaseModule
from core.media_service import (
    MediaMonitorWorker, media_play_pause, media_next, media_prev, media_seek,
    get_system_volume, set_system_volume, POWERSHELL_ARTWORK_SCRIPT
)
from core.notifications_service import NotificationMonitorWorker
from core.privacy_monitor import PrivacyMonitorWorker
from core.bluetooth_monitor import BluetoothDeviceMonitorWorker
from core.audio_outputs import list_audio_outputs, set_default_audio_output
from ui.vector_controls import (
    IslandSlider, WaveformVisualizer, VectorIconButton, LivingEyesWidget,
    ShelfBadgeWidget, BluetoothBatteryBadgeWidget, VectorCloseButton, AppIconWidget,
    VectorGearButton, island_scroll_area_style
)
from modules.dropshelf import shelf_manager, DraggableFileCard
from modules.settings import SettingsPage
from core.theme import theme_manager


class MediaModule(BaseModule):
    album_artwork_loaded = pyqtSignal(str, str, str)
    audio_output_operation_done = pyqtSignal(str, bool, object, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._album_artwork_request_key = None
        self.album_artwork_loaded.connect(self._on_album_artwork_loaded)
        self.audio_output_operation_done.connect(self._on_audio_output_operation_done)
        self._audio_output_busy = False
        self._audio_output_action = None
        self._audio_output_show_menu = False
        self._audio_output_devices = []
        self._audio_output_menu = None
        self.island = None
        self.current_media = {"has_media": False, "status": "Stopped"}
        self.is_active_player = False
        self._media_subtitle = ""
        self.media_duration_seconds = 0.0
        self.media_position_seconds = 0.0
        self._media_position_timestamp = time.monotonic()
        self._media_is_playing = False
        self._last_volume_poll = 0.0
        self.seek_slider = None
        self.seek_time_label = None
        self.volume_slider = None
        self.volume_value_label = None
        self.audio_output_button = None
        self.media_session_lost_timer = QTimer(self)
        self.media_session_lost_timer.setSingleShot(True)
        self.media_session_lost_timer.setInterval(10000)
        self.media_session_lost_timer.timeout.connect(self._leave_player_if_session_lost)
        self.privacy_activity = {"microphone": [], "camera": [], "location": [], "screen": []}
        self.bluetooth_devices = []
        self.recent_notifications = []

        # Elementy pigułki
        self.pill_normal_widget = None
        self.pill_alert_widget = None
        self.alert_badge = None
        self.alert_text = None
        self.alert_app_icon = None

        self.pill_eyes = None
        self.pill_wave = None
        self.large_eyes = None
        self.exp_wave = None
        self.exp_album_art = None
        self.pill_title = None
        self.pill_subtitle = None
        self.pill_shelf_badge = None
        self.pill_bluetooth_badge = None

        # Elementy rozwinięte
        self.exp_stack = None
        self.tab_media_btn = None
        self.tab_shelf_btn = None
        self.tab_notifs_btn = None
        self.tab_shortcuts_btn = None
        self.tab_settings_btn = None
        self.shortcuts_layout = None
        self._settings_page = None
        self.shortcuts_container = None
        self.shortcuts_settings = QSettings("FloatingIsland", "FloatingIsland")
        self.shortcuts_settings.sync()
        stored_shortcuts = self.shortcuts_settings.value("shortcuts", [])
        if isinstance(stored_shortcuts, str):
            stored_shortcuts = [stored_shortcuts] if stored_shortcuts else []
        self.shortcuts = [str(path) for path in stored_shortcuts]

        # Drop Shelf
        self.shelf_cards_layout = None
        self.shelf_empty_label = None
        self.shelf_count_label = None

        # Notifications Hub
        self.notifs_layout = None
        self.notifs_empty_label = None
        self.notifs_count_label = None
        self.privacy_status_label = None
        self.privacy_mini_label = None

        # Zegar systemowy
        self.clock_timer = QTimer(self)
        self.clock_timer.timeout.connect(self._update_clock)
        self.clock_timer.start(1000)

        # Stały proces monitorowania multimediów w tle
        self.worker = MediaMonitorWorker(parent=self)
        self.worker.media_updated.connect(self._on_media_update)
        self.worker.start()

        # Stały proces nasłuchujący powiadomień Windows w tle
        self.notif_worker = NotificationMonitorWorker(parent=self)
        self.notif_worker.notification_arrived.connect(self._on_new_notification)
        self.notif_worker.start()

        self.privacy_worker = PrivacyMonitorWorker(parent=self)
        self.privacy_worker.activity_changed.connect(self._on_privacy_activity)
        self.privacy_worker.start()
        self.bluetooth_worker = BluetoothDeviceMonitorWorker(parent=self)
        self.bluetooth_worker.devices_changed.connect(self._on_bluetooth_devices)
        self.bluetooth_worker.start()
        app = QApplication.instance()
        if app:
            app.aboutToQuit.connect(self.worker.stop)
            app.aboutToQuit.connect(self.notif_worker.stop)
            app.aboutToQuit.connect(self.privacy_worker.stop)
            app.aboutToQuit.connect(self.bluetooth_worker.stop)

        # Subskrypcja zmian na półce
        shelf_manager.subscribe(self._on_shelf_updated)

        # Subskrypcja zmian motywu
        theme_manager.theme_changed.connect(self._apply_theme)

    def get_pill_widget(self, parent: QWidget) -> QWidget:
        root = QWidget(parent)
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # ---------------------------------------------------------
        # A. NORMALNY WIDOK PIGUŁKI (Standby / Muzyka / Półka)
        # ---------------------------------------------------------
        self.pill_normal_widget = QWidget(root)
        norm_layout = QHBoxLayout(self.pill_normal_widget)
        norm_layout.setContentsMargins(0, 0, 0, 0)
        norm_layout.setSpacing(8)

        self.pill_eyes = LivingEyesWidget(size="small", parent=self.pill_normal_widget)
        self.pill_wave = WaveformVisualizer(num_bars=4, bar_width=3, bar_gap=2, parent=self.pill_normal_widget)
        self.pill_wave.setVisible(False)

        self.pill_title = QLabel(QTime.currentTime().toString("HH:mm"), self.pill_normal_widget)
        self.pill_title.setStyleSheet("color: #FFFFFF; font-weight: bold; font-size: 12px;")

        self.pill_shelf_badge = ShelfBadgeWidget(parent=self.pill_normal_widget)
        self.pill_bluetooth_badge = BluetoothBatteryBadgeWidget(parent=self.pill_normal_widget)
        self.pill_bluetooth_badge.set_devices(self.bluetooth_devices)

        self.pill_subtitle = QLabel("Czuwanie", self.pill_normal_widget)
        self.pill_subtitle.setStyleSheet("color: #8E8E93; font-size: 11px;")

        norm_layout.addWidget(self.pill_eyes)
        norm_layout.addWidget(self.pill_wave)
        norm_layout.addWidget(self.pill_title)
        norm_layout.addWidget(self.pill_shelf_badge)
        norm_layout.addWidget(self.pill_bluetooth_badge)
        norm_layout.addStretch()
        norm_layout.addWidget(self.pill_subtitle)

        # ---------------------------------------------------------
        # B. DYNAMICZNY BANER POWIADOMIENIA (Łącze z telefonem / SMS / App)
        # ---------------------------------------------------------
        self.pill_alert_widget = QWidget(root)
        alert_layout = QHBoxLayout(self.pill_alert_widget)
        alert_layout.setContentsMargins(0, 0, 0, 0)
        alert_layout.setSpacing(8)

        self.alert_app_icon = AppIconWidget("generic", size=20, parent=self.pill_alert_widget)

        self.alert_badge = QLabel("ALERT", self.pill_alert_widget)
        self.alert_badge.setStyleSheet(
            "background-color: #2C2C2E; color: #FFFFFF; font-weight: bold; "
            "font-size: 9px; padding: 2px 6px; border-radius: 4px; border: 1px solid #3E3E42;"
        )

        self.alert_text = QLabel("Nowe powiadomienie", self.pill_alert_widget)
        self.alert_text.setStyleSheet("color: #FFFFFF; font-size: 12px; font-weight: 500;")

        alert_layout.addWidget(self.alert_app_icon)
        alert_layout.addWidget(self.alert_badge)
        alert_layout.addWidget(self.alert_text)
        alert_layout.addStretch()

        self.pill_alert_widget.setVisible(False)

        root_layout.addWidget(self.pill_normal_widget)
        root_layout.addWidget(self.pill_alert_widget)
        return root

    def get_expanded_widget(self, parent: QWidget) -> QWidget:
        container = QWidget(parent)
        root_layout = QVBoxLayout(container)
        root_layout.setContentsMargins(2, 0, 2, 2)
        root_layout.setSpacing(4)

        # Pasek zakładek u góry: [ STATUS/MUZYKA | PÓŁKA | ALERTY ]
        tab_row = QHBoxLayout()
        tab_row.setContentsMargins(0, 0, 0, 0)
        tab_row.setSpacing(4)

        tab_style = """
            QPushButton {
                background: transparent;
                color: #8E8E93;
                font-size: 11px;
                font-weight: bold;
                border: none;
                padding: 2px 8px;
                border-radius: 4px;
            }
            QPushButton:hover {
                color: #FFFFFF;
                background-color: #242426;
            }
        """

        self.tab_media_btn = QPushButton("STATUS", container)
        self.tab_media_btn.setStyleSheet(tab_style.replace("#8E8E93", "#FFFFFF") + "background-color: #242426;")
        self.tab_media_btn.clicked.connect(self._show_media_page)

        self.tab_shelf_btn = QPushButton("PÓŁKA", container)
        self.tab_shelf_btn.setStyleSheet(tab_style)
        self.tab_shelf_btn.clicked.connect(self._show_shelf_page)

        self.tab_notifs_btn = QPushButton("ALERTY", container)
        self.tab_notifs_btn.setStyleSheet(tab_style)
        self.tab_notifs_btn.clicked.connect(self._show_notifs_page)

        self.tab_shortcuts_btn = QPushButton("SKRÓTY", container)
        self.tab_shortcuts_btn.setStyleSheet(tab_style)
        self.tab_shortcuts_btn.clicked.connect(self._show_shortcuts_page)

        tab_row.addWidget(self.tab_media_btn)
        tab_row.addWidget(self.tab_shelf_btn)
        tab_row.addWidget(self.tab_notifs_btn)
        tab_row.addWidget(self.tab_shortcuts_btn)
        tab_row.addStretch()

        # Przycisk ustawien (zębate kółko) po prawej stronie paska zakładek
        self.tab_settings_btn = VectorGearButton(size=20, parent=container)
        self.tab_settings_btn.setToolTip("Ustawienia")
        self.tab_settings_btn.clicked.connect(self._show_settings_page)
        tab_row.addWidget(self.tab_settings_btn)

        root_layout.addLayout(tab_row)

        self.exp_stack = QStackedWidget(container)

        # ==========================================
        # STRONA 0: STANDBY
        # ==========================================
        standby_page = QWidget(self.exp_stack)
        st_layout = QHBoxLayout(standby_page)
        st_layout.setContentsMargins(6, 2, 6, 2)
        st_layout.setSpacing(14)

        self.large_eyes = LivingEyesWidget(size="large", parent=standby_page)

        info_col = QVBoxLayout()
        info_col.setContentsMargins(0, 0, 0, 0)
        info_col.setSpacing(2)

        self.standby_clock_label = QLabel(QTime.currentTime().toString("HH:mm:ss"), standby_page)
        self.standby_clock_label.setStyleSheet("color: #FFFFFF; font-size: 20px; font-weight: bold;")

        self.standby_date_label = QLabel(self._get_formatted_date(), standby_page)
        self.standby_date_label.setStyleSheet("color: #8E8E93; font-size: 11px;")

        self.st_badge = QLabel("SYSTEM GOTOWY", standby_page)
        self.st_badge.setStyleSheet(
            "background-color: #1C1C1E; color: #FFFFFF; font-size: 9px; "
            "font-weight: bold; padding: 2px 6px; border-radius: 4px; border: 1px solid #2C2C2E;"
        )

        badge_row = QHBoxLayout()
        badge_row.addWidget(self.st_badge)
        badge_row.addStretch()

        info_col.addWidget(self.standby_clock_label)
        info_col.addWidget(self.standby_date_label)
        info_col.addLayout(badge_row)

        self.privacy_status_label = QLabel(standby_page)
        self.privacy_status_label.setWordWrap(True)
        self.privacy_status_label.setStyleSheet("color: #8E8E93; font-size: 10px;")
        info_col.addWidget(self.privacy_status_label)

        st_layout.addWidget(self.large_eyes)
        st_layout.addLayout(info_col)
        st_layout.addStretch()
        self.exp_stack.addWidget(standby_page)

        # ==========================================
        # STRONA 1: ODTWARZACZ MUZYKI
        # ==========================================
        player_page = QWidget(self.exp_stack)
        pl_layout = QVBoxLayout(player_page)
        pl_layout.setContentsMargins(4, 0, 4, 0)
        pl_layout.setSpacing(3)

        top_row = QHBoxLayout()
        self.exp_badge = QLabel("MEDIA", player_page)
        self.exp_badge.setStyleSheet(
            "background-color: #3A3A3C; color: #FFFFFF; "
            "font-weight: bold; font-size: 9px; padding: 2px 7px; border-radius: 4px;"
        )
        self.exp_status = QLabel("Odtwarzanie", player_page)
        self.exp_status.setStyleSheet("color: #8E8E93; font-size: 11px;")

        top_row.addWidget(self.exp_badge)
        top_row.addWidget(self.exp_status)
        self.privacy_mini_label = QLabel(player_page)
        self.privacy_mini_label.setStyleSheet("color: #FF9F0A; font-size: 9px; font-weight: bold;")
        self.privacy_mini_label.setVisible(False)
        top_row.addWidget(self.privacy_mini_label)
        top_row.addStretch()
        self.audio_output_button = QPushButton("WYJŚCIE ▾", player_page)
        self.audio_output_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.audio_output_button.setFixedSize(132, 23)
        self.audio_output_button.setToolTip("Wybierz domyślne wyjście audio Windows")
        self.audio_output_button.clicked.connect(self._open_audio_output_menu)
        top_row.addWidget(self.audio_output_button)
        pl_layout.addLayout(top_row)

        self.exp_title = QLabel("Tytuł utworu", player_page)
        self.exp_title.setStyleSheet("color: #FFFFFF; font-size: 13px; font-weight: bold;")

        self.exp_artist = QLabel("Wykonawca", player_page)
        self.exp_artist.setStyleSheet("color: #A1A1A6; font-size: 11px;")

        self.exp_album_art = QLabel("♫", player_page)
        self.exp_album_art.setFixedSize(52, 52)
        self.exp_album_art.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.exp_album_art.setStyleSheet(
            f"background-color: {theme_manager.card_bg}; color: {theme_manager.text_secondary}; "
            "font-size: 23px; border-radius: 7px;"
        )
        track_info = QVBoxLayout()
        track_info.setContentsMargins(0, 0, 0, 0)
        track_info.setSpacing(3)
        track_info.addWidget(self.exp_title)
        track_info.addWidget(self.exp_artist)
        track_row = QHBoxLayout()
        track_row.setContentsMargins(0, 1, 0, 1)
        track_row.setSpacing(9)
        track_row.addWidget(self.exp_album_art)
        track_row.addLayout(track_info, 1)
        pl_layout.addLayout(track_row)

        self.seek_time_label = QLabel("0:00 / 0:00", player_page)
        self.seek_time_label.setStyleSheet("color: #8E8E93; font-size: 9px;")
        self.seek_time_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.seek_slider = IslandSlider(Qt.Orientation.Horizontal, player_page)
        self.seek_slider.setRange(0, 0)
        self.seek_slider.setFixedHeight(16)
        self.seek_slider.setEnabled(False)
        self.seek_slider.valueChanged.connect(self._on_seek_slider_changed)
        self.seek_slider.sliderReleased.connect(self._seek_media)
        seek_row = QHBoxLayout()
        seek_row.setContentsMargins(0, 0, 0, 0)
        seek_row.setSpacing(8)
        seek_row.addWidget(self.seek_slider, 1)
        seek_row.addWidget(self.seek_time_label)
        pl_layout.addLayout(seek_row)

        volume_row = QHBoxLayout()
        volume_row.setContentsMargins(0, 0, 0, 0)
        volume_row.setSpacing(8)
        volume_label = QLabel("Głośność", player_page)
        volume_label.setStyleSheet("color: #8E8E93; font-size: 9px;")
        self.volume_slider = IslandSlider(Qt.Orientation.Horizontal, player_page)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setFixedHeight(16)
        self.volume_slider.sliderMoved.connect(self._apply_media_volume)
        self.volume_slider.actionTriggered.connect(lambda _action: QTimer.singleShot(0, self._set_media_volume))
        self.volume_slider.sliderReleased.connect(self._set_media_volume)
        self.volume_value_label = QLabel("—", player_page)
        self.volume_value_label.setMinimumWidth(32)
        self.volume_value_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.volume_value_label.setStyleSheet("color: #8E8E93; font-size: 9px;")
        volume_row.addWidget(volume_label)
        volume_row.addWidget(self.volume_slider, 1)
        volume_row.addWidget(self.volume_value_label)
        self.volume_slider.valueChanged.connect(lambda value: self.volume_value_label.setText(f"{value}%"))
        pl_layout.addLayout(volume_row)
        initial_volume = get_system_volume()
        if initial_volume is not None:
            self.volume_slider.setValue(initial_volume)
            self.volume_value_label.setText(f"{initial_volume}%")

        bottom_row = QHBoxLayout()
        bottom_row.setContentsMargins(0, 2, 0, 0)
        bottom_row.setSpacing(12)

        self.exp_wave = WaveformVisualizer(num_bars=14, bar_width=3, bar_gap=3, parent=player_page)

        self.btn_prev = VectorIconButton(VectorIconButton.TYPE_PREV, size=32, parent=player_page)
        self.btn_prev.clicked.connect(media_prev)

        self.btn_play_pause = VectorIconButton(VectorIconButton.TYPE_PAUSE, size=38, is_primary=True, parent=player_page)
        self.btn_play_pause.clicked.connect(media_play_pause)

        self.btn_next = VectorIconButton(VectorIconButton.TYPE_NEXT, size=32, parent=player_page)
        self.btn_next.clicked.connect(media_next)

        bottom_row.addWidget(self.exp_wave)
        bottom_row.addStretch()
        bottom_row.addWidget(self.btn_prev)
        bottom_row.addWidget(self.btn_play_pause)
        bottom_row.addWidget(self.btn_next)

        pl_layout.addLayout(bottom_row)
        self.exp_stack.addWidget(player_page)

        # ==========================================
        # STRONA 2: DROP SHELF (PÓŁKA NA PLIKI)
        # ==========================================
        shelf_page = QWidget(self.exp_stack)
        sh_layout = QVBoxLayout(shelf_page)
        sh_layout.setContentsMargins(4, 0, 4, 0)
        sh_layout.setSpacing(4)

        shelf_header = QHBoxLayout()
        self.shelf_count_label = QLabel("Półka jest pusta", shelf_page)
        self.shelf_count_label.setStyleSheet("color: #8E8E93; font-size: 11px;")

        btn_clear = QPushButton("Wyczyść wszystko", shelf_page)
        btn_clear.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_clear.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #FF453A;
                font-size: 10px;
                font-weight: bold;
                border: none;
            }
            QPushButton:hover {
                text-decoration: underline;
            }
        """)
        btn_clear.clicked.connect(shelf_manager.clear)

        shelf_header.addWidget(self.shelf_count_label)
        shelf_header.addStretch()
        shelf_header.addWidget(btn_clear)
        sh_layout.addLayout(shelf_header)

        scroll = QScrollArea(shelf_page)
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(island_scroll_area_style())
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        self.shelf_cards_container = QWidget()
        self.shelf_cards_container.setStyleSheet("background: transparent;")
        self.shelf_cards_layout = QVBoxLayout(self.shelf_cards_container)
        self.shelf_cards_layout.setContentsMargins(0, 0, 0, 0)
        self.shelf_cards_layout.setSpacing(4)

        self.shelf_empty_label = QLabel("Upuść plik lub zdjęcie tutaj,\naby przechować je na półce", self.shelf_cards_container)
        self.shelf_empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.shelf_empty_label.setStyleSheet(
            "color: #636366; font-size: 11px; padding: 12px; "
            "border: 1px dashed #38383A; border-radius: 8px;"
        )
        self.shelf_cards_layout.addWidget(self.shelf_empty_label)

        scroll.setWidget(self.shelf_cards_container)
        sh_layout.addWidget(scroll)
        self.exp_stack.addWidget(shelf_page)

        # ==========================================
        # STRONA 3: WINDOWS NOTIFICATIONS HUB
        # ==========================================
        notifs_page = QWidget(self.exp_stack)
        no_layout = QVBoxLayout(notifs_page)
        no_layout.setContentsMargins(4, 0, 4, 0)
        no_layout.setSpacing(4)

        notif_header = QHBoxLayout()
        self.notifs_count_label = QLabel("Brak powiadomień", notifs_page)
        self.notifs_count_label.setStyleSheet("color: #8E8E93; font-size: 11px;")

        btn_clear_notifs = QPushButton("Wyczyść alerty", notifs_page)
        btn_clear_notifs.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_clear_notifs.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #FF453A;
                font-size: 10px;
                font-weight: bold;
                border: none;
            }
            QPushButton:hover {
                text-decoration: underline;
            }
        """)
        btn_clear_notifs.clicked.connect(self._clear_notifications)

        notif_header.addWidget(self.notifs_count_label)
        notif_header.addStretch()
        notif_header.addWidget(btn_clear_notifs)
        no_layout.addLayout(notif_header)

        notif_scroll = QScrollArea(notifs_page)
        notif_scroll.setWidgetResizable(True)
        notif_scroll.setStyleSheet(island_scroll_area_style())
        notif_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        notif_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        self.notifs_container = QWidget()
        self.notifs_container.setStyleSheet("background: transparent;")
        self.notifs_layout = QVBoxLayout(self.notifs_container)
        self.notifs_layout.setContentsMargins(0, 0, 0, 0)
        self.notifs_layout.setSpacing(4)

        self.notifs_empty_label = QLabel("Centrum powiadomień czuwa.\nTutaj pojawią się SMS-y i alerty.", self.notifs_container)
        self.notifs_empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.notifs_empty_label.setStyleSheet(
            "color: #636366; font-size: 11px; padding: 12px; "
            "border: 1px dashed #38383A; border-radius: 8px;"
        )
        self.notifs_layout.addWidget(self.notifs_empty_label)

        notif_scroll.setWidget(self.notifs_container)
        no_layout.addWidget(notif_scroll)
        self.exp_stack.addWidget(notifs_page)

        # STRONA 4: SZYBKIE SKRÓTY DO APLIKACJI
        shortcuts_page = QWidget(self.exp_stack)
        shortcuts_root = QVBoxLayout(shortcuts_page)
        shortcuts_root.setContentsMargins(4, 0, 4, 0)
        shortcuts_root.setSpacing(5)
        shortcuts_header = QHBoxLayout()
        self.shortcuts_hint = QLabel("Przypięte aplikacje i pliki", shortcuts_page)
        self.shortcuts_hint.setStyleSheet("color: #8E8E93; font-size: 11px;")
        self.add_shortcut_btn = QPushButton("+ Dodaj", shortcuts_page)
        self.add_shortcut_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.add_shortcut_btn.setStyleSheet("QPushButton { background: #242426; color: #FFFFFF; border: 1px solid #38383A; border-radius: 5px; padding: 4px 9px; font-size: 10px; font-weight: bold; } QPushButton:hover { background: #343438; }")
        self.add_shortcut_btn.clicked.connect(self._add_shortcut)
        shortcuts_header.addWidget(self.shortcuts_hint)
        shortcuts_header.addStretch()
        shortcuts_header.addWidget(self.add_shortcut_btn)
        shortcuts_root.addLayout(shortcuts_header)

        shortcuts_scroll = QScrollArea(shortcuts_page)
        shortcuts_scroll.setWidgetResizable(True)
        shortcuts_scroll.setStyleSheet(island_scroll_area_style())
        shortcuts_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        shortcuts_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        shortcuts_container = QWidget()
        self.shortcuts_container = shortcuts_container
        shortcuts_container.setStyleSheet("background: transparent;")
        self.shortcuts_layout = QVBoxLayout(shortcuts_container)
        self.shortcuts_layout.setContentsMargins(0, 0, 0, 0)
        self.shortcuts_layout.setSpacing(4)
        self.shortcuts_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        shortcuts_scroll.setWidget(shortcuts_container)
        shortcuts_root.addWidget(shortcuts_scroll)
        self.exp_stack.addWidget(shortcuts_page)
        self._refresh_shortcuts()

        # ==========================================
        # STRONA 5: USTAWIENIA
        # ==========================================
        self._settings_page = SettingsPage(island_ref=self.island, parent=self.exp_stack)
        self.exp_stack.addWidget(self._settings_page)

        self.exp_stack.setCurrentIndex(0)
        root_layout.addWidget(self.exp_stack)

        # Zaaplikuj biezacy motyw do wszystkich nowo powstalych kontrolek
        self._apply_theme()
        self._apply_privacy_activity()
        self._start_audio_output_operation("list")
        return container

    # -------------------------------------------------------------
    # OBSŁUGA NOWYCH POWIADOMIEŃ WINDOWS (Toast Alert Animation)
    # -------------------------------------------------------------
    def _on_new_notification(self, data: dict):
        app_name = data.get("app", "Powiadomienie")
        title = data.get("title", "")
        message = data.get("message", "")
        kind = data.get("kind", "generic")

        # Dodaj do historii
        self.recent_notifications.insert(0, data)
        if len(self.recent_notifications) > 15:
            self.recent_notifications.pop()

        self._refresh_notifications_ui()

        # --- Polaczenie przychodzace: specjalny baner z przyciskami ---
        if kind == "call":
            caller = title if title and title != app_name else app_name
            if hasattr(self, 'island') and self.island:
                self.island.show_call_banner(caller)
            return

        # --- Ikona aplikacji w banerze ---
        icon_kind = AppIconWidget.KIND_GENERIC
        if kind == "sms":
            icon_kind = AppIconWidget.KIND_SMS
        elif kind == "discord":
            icon_kind = AppIconWidget.KIND_DISCORD
        elif kind == "steam":
            icon_kind = AppIconWidget.KIND_STEAM
        elif kind == "teams":
            icon_kind = AppIconWidget.KIND_TEAMS
        elif kind == "xbox":
            icon_kind = AppIconWidget.KIND_XBOX
        elif kind in ("phone",):
            icon_kind = AppIconWidget.KIND_PHONE

        if self.alert_app_icon:
            self.alert_app_icon.set_kind(icon_kind)

        # Oczyszczenie nazwy aplikacji pod badge
        clean_badge = app_name.upper()
        if "TELEFON" in clean_badge or "PHONE" in clean_badge or "YOUR PHONE" in clean_badge:
            clean_badge = "SMS"
        elif "DISCORD" in clean_badge:
            clean_badge = "DISCORD"
        elif "STEAM" in clean_badge:
            clean_badge = "STEAM"
        elif "TEAMS" in clean_badge:
            clean_badge = "TEAMS"
        elif "XBOX" in clean_badge:
            clean_badge = "XBOX"
        elif len(clean_badge) > 10:
            clean_badge = clean_badge[:9]

        display_text = title
        if message:
            display_text += f": {message}"
        if len(display_text) > 34:
            display_text = display_text[:32] + "…"

        # Aktywacja banera w pigułce
        if self.alert_badge:
            self.alert_badge.setText(clean_badge)
        if self.alert_text:
            self.alert_text.setText(display_text)

        if self.pill_normal_widget and self.pill_alert_widget:
            self.pill_normal_widget.setVisible(False)
            self.pill_alert_widget.setVisible(True)

            # Rozszerzenie pigułki w baner na 4.2 sekundy
            if hasattr(self, 'island') and self.island:
                self.island.show_alert_banner(4200)

            QTimer.singleShot(4200, self._restore_pill_after_alert)

    def _restore_pill_after_alert(self):
        """Powrót do normalnego wyglądu pigułki po wygaśnięciu banera."""
        if self.pill_alert_widget and self.pill_normal_widget:
            self.pill_alert_widget.setVisible(False)
            self.pill_normal_widget.setVisible(True)

    @staticmethod
    def _looks_like_communicator(app_name: str) -> bool:
        normalized = "".join(ch for ch in app_name.lower() if ch.isalnum())
        return any(token in normalized for token in (
            "discord", "messenger", "teams", "zoom", "skype", "whatsapp",
            "telegram", "signal", "slack", "webex", "meet", "facetime",
        ))

    def _on_privacy_activity(self, activity: dict):
        self.privacy_activity = activity
        self._apply_privacy_activity()

    def _on_bluetooth_devices(self, devices: list):
        unique_devices = {}
        for item in devices:
            if not isinstance(item, dict) or not item.get("name"):
                continue
            try:
                item = {"name": str(item["name"]), "battery": max(0, min(100, int(item["battery"])))}
            except (KeyError, TypeError, ValueError):
                continue
            unique_devices[item["name"].casefold()] = item
        self.bluetooth_devices = list(unique_devices.values())
        self.bluetooth_devices.sort(key=lambda item: self._bluetooth_device_priority(item["name"]))
        if self.pill_bluetooth_badge:
            self.pill_bluetooth_badge.set_devices(self.bluetooth_devices)
            self._schedule_pill_geometry_refresh()

    def _schedule_pill_geometry_refresh(self):
        if self.island and hasattr(self.island, "refresh_collapsed_geometry"):
            QTimer.singleShot(0, self.island.refresh_collapsed_geometry)

    @staticmethod
    def _bluetooth_device_priority(name):
        normalized = name.casefold()
        if any(word in normalized for word in (
            "headphone", "headset", "earbud", "earphone", "airpod", "buds", "bose", "wh-", "wf-", "jbl",
            "philips", "soundcore", "anker", "beats", "sennheiser", "jabra", "freebuds", "enco", "tws",
        )):
            return 0
        if any(word in normalized for word in ("watch", "fitbit", "garmin", "band", "wearable")):
            return 2
        if any(word in normalized for word in ("phone", "iphone", "pixel", "mobile", "galaxy")):
            return 1
        return 3

    def _apply_privacy_activity(self):
        lines = []
        microphone_apps = self.privacy_activity.get("microphone", [])
        camera_apps = self.privacy_activity.get("camera", [])
        handled_microphone = set()

        for app_name in camera_apps:
            if app_name in microphone_apps and self._looks_like_communicator(app_name):
                lines.append(f"Rozmowa wideo · {app_name}")
                handled_microphone.add(app_name)
            else:
                lines.append(f"Kamera aktywna · {app_name}")

        for app_name in microphone_apps:
            if app_name not in handled_microphone:
                prefix = "Rozmowa / mikrofon" if self._looks_like_communicator(app_name) else "Mikrofon aktywny"
                lines.append(f"{prefix} · {app_name}")

        for app_name in self.privacy_activity.get("location", []):
            lines.append(f"Lokalizacja aktywna · {app_name}")
        for app_name in self.privacy_activity.get("screen", []):
            lines.append(f"Nagrywanie / udostępnianie ekranu · {app_name}")

        if self.privacy_status_label:
            self.privacy_status_label.setText(
                "\n".join(lines) if lines else "Brak wykrytego użycia mikrofonu, kamery, lokalizacji i ekranu."
            )

        compact = ""
        for key, prefix in (("screen", "EKRAN"), ("camera", "KAMERA"), ("microphone", "MIC"), ("location", "LOK")):
            apps = self.privacy_activity.get(key, [])
            if apps:
                app_label = apps[0] if len(apps[0]) <= 7 else apps[0][:6] + "…"
                compact = f"{prefix} · {app_label}"
                break
        if self.pill_subtitle:
            self.pill_subtitle.setToolTip("\n".join(lines) if lines else "Brak aktywnego użycia urządzeń")
            subtitle = compact or (QTime.currentTime().toString("HH:mm") if self.is_active_player else "Czuwanie")
            self.pill_subtitle.setText(subtitle)
        if self.privacy_mini_label:
            self.privacy_mini_label.setText(compact)
            self.privacy_mini_label.setToolTip("\n".join(lines) if lines else "Brak aktywnego użycia urządzeń")
            self.privacy_mini_label.setVisible(bool(compact))
        if self.privacy_status_label:
            self.privacy_status_label.setStyleSheet(
                f"color: {theme_manager.text_secondary}; font-size: 10px;"
            )
        self._schedule_pill_geometry_refresh()

    def _refresh_notifications_ui(self):
        count = len(self.recent_notifications)
        if self.tab_notifs_btn:
            self.tab_notifs_btn.setText("ALERTY")

        if self.notifs_count_label:
            self.notifs_count_label.setText(f"Odebrane alerty: {count}" if count > 0 else "Brak powiadomień")

        if self.notifs_layout:
            while self.notifs_layout.count():
                item = self.notifs_layout.takeAt(0)
                w = item.widget()
                if w:
                    if w == self.notifs_empty_label:
                        self.notifs_layout.removeWidget(w)
                    else:
                        w.deleteLater()

            if count == 0:
                if self.notifs_empty_label:
                    self.notifs_layout.addWidget(self.notifs_empty_label)
                    self.notifs_empty_label.setVisible(True)
            else:
                if self.notifs_empty_label:
                    self.notifs_empty_label.setVisible(False)
                for notif in self.recent_notifications:
                    card = self._create_notif_card(notif)
                    self.notifs_layout.addWidget(card)

    def _create_notif_card(self, notif: dict) -> QFrame:
        """Tworzy kartę powiadomienia w historii z wektorową ikoną aplikacji."""
        card_bg = theme_manager.card_bg
        card_border = theme_manager.card_border
        text_pri = theme_manager.text_primary
        text_sec = theme_manager.text_secondary

        frame = QFrame()
        frame.setStyleSheet(f"""
            QFrame {{
                background-color: {card_bg};
                border-radius: 8px;
                border: 1px solid {card_border};
            }}
        """)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(2)

        header_row = QHBoxLayout()

        # Wektorowa ikona aplikacji
        kind = notif.get("kind", "generic")
        icon_map = {
            "sms": AppIconWidget.KIND_SMS,
            "call": AppIconWidget.KIND_CALL,
            "phone": AppIconWidget.KIND_PHONE,
            "discord": AppIconWidget.KIND_DISCORD,
            "steam": AppIconWidget.KIND_STEAM,
            "teams": AppIconWidget.KIND_TEAMS,
            "xbox": AppIconWidget.KIND_XBOX,
        }
        icon_kind = icon_map.get(kind, AppIconWidget.KIND_GENERIC)
        notif_icon = AppIconWidget(icon_kind, size=18, parent=frame)
        header_row.addWidget(notif_icon)

        app_name = notif.get("app", "ALERT")
        # Skroc nazwę aplikacji dla badge
        badge_text = app_name.upper()
        if len(badge_text) > 10:
            badge_text = badge_text[:9]

        title_label = QLabel(notif.get("title", ""), frame)
        title_label.setStyleSheet(f"color: {text_pri}; font-size: 11px; font-weight: bold;")

        header_row.addWidget(title_label)
        header_row.addStretch()

        msg = notif.get("message", "")
        msg_label = QLabel(msg if len(msg) <= 50 else msg[:48] + "…", frame)
        msg_label.setStyleSheet(f"color: {text_sec}; font-size: 10px;")

        layout.addLayout(header_row)
        if msg:
            layout.addWidget(msg_label)

        return frame

    def _clear_notifications(self):
        self.recent_notifications.clear()
        self._refresh_notifications_ui()

    def on_drag_enter(self):
        self._show_shelf_page()

    def _show_media_page(self):
        self._set_active_tab(self.tab_media_btn)
        self.exp_stack.setCurrentIndex(1 if self.is_active_player else 0)

    def _show_shelf_page(self):
        self._set_active_tab(self.tab_shelf_btn)
        self.exp_stack.setCurrentIndex(2)

    def _show_notifs_page(self):
        self._set_active_tab(self.tab_notifs_btn)
        self.exp_stack.setCurrentIndex(3)

    def _show_shortcuts_page(self):
        self._set_active_tab(self.tab_shortcuts_btn)
        self.exp_stack.setCurrentIndex(4)

    def _show_settings_page(self):
        self._set_active_tab(None)
        # Podkrecamy gear button wizualnie
        if self.tab_settings_btn:
            self.tab_settings_btn.setProperty("active", True)
            self.tab_settings_btn.update()
        self.exp_stack.setCurrentIndex(5)

    def _set_active_tab(self, active_btn):
        card_bg = theme_manager.card_bg
        card_border = theme_manager.card_border
        text_pri = theme_manager.text_primary
        text_sec = theme_manager.text_secondary
        hover_bg = theme_manager.hover_bg

        # Resetuj styl gear buttona (nie jest QPushButton)
        if self.tab_settings_btn:
            self.tab_settings_btn.setProperty("active", active_btn is None)
            self.tab_settings_btn.update()

        for btn in (self.tab_media_btn, self.tab_shelf_btn, self.tab_notifs_btn, self.tab_shortcuts_btn):
            if btn is None:
                continue
            if btn == active_btn:
                btn.setStyleSheet(
                    f"QPushButton {{ background-color: {card_bg}; color: {text_pri}; "
                    f"font-size: 11px; font-weight: bold; border-radius: 4px; padding: 2px 8px; border: 1px solid {card_border}; }}"
                )
            else:
                btn.setStyleSheet(
                    f"QPushButton {{ background: transparent; color: {text_sec}; "
                    f"font-size: 11px; font-weight: bold; border: none; padding: 2px 8px; }} "
                    f"QPushButton:hover {{ color: {text_pri}; background-color: {hover_bg}; border-radius: 4px; }}"
                )

    @staticmethod
    def _safe_set_style(widget, style: str):
        if widget is not None:
            try:
                widget.setStyleSheet(style)
            except (RuntimeError, AttributeError):
                pass

    def _apply_theme(self, theme_name: str = None):
        """Dynamicznie odswieza style i kolory kontrolek po zmianie motywu."""
        text_pri = theme_manager.text_primary
        text_sec = theme_manager.text_secondary
        card_bg = theme_manager.card_bg
        card_border = theme_manager.card_border
        hover_bg = theme_manager.hover_bg

        # Wymus synchronizacje wektorowych kontrolek, takze gdy odtwarzacz
        # ma aktywny akcent ustawiony przed zmiana motywu.
        for eyes in (self.pill_eyes, self.large_eyes):
            if eyes:
                eyes._sync_color(theme_name or theme_manager.effective_theme)
        for wave in (self.pill_wave, self.exp_wave):
            if wave:
                wave._sync_theme(theme_name or theme_manager.effective_theme)

        # 1. Normalna pigułka
        self._safe_set_style(self.pill_title, f"color: {text_pri}; font-weight: bold; font-size: 12px;")
        self._safe_set_style(self.pill_subtitle, f"color: {text_sec}; font-size: 11px;")
        if self.pill_bluetooth_badge:
            self.pill_bluetooth_badge.update()

        # Alert banner w pigułce
        self._safe_set_style(
            self.alert_badge,
            f"background-color: {card_bg}; color: {text_pri}; font-weight: bold; "
            f"font-size: 9px; padding: 2px 6px; border-radius: 4px; border: 1px solid {card_border};"
        )
        self._safe_set_style(self.alert_text, f"color: {text_pri}; font-size: 12px; font-weight: 500;")

        # 2. Pasek zakładek
        active_btn = None
        if self.exp_stack is not None:
            idx = self.exp_stack.currentIndex()
            if idx in (0, 1):
                active_btn = self.tab_media_btn
            elif idx == 2:
                active_btn = self.tab_shelf_btn
            elif idx == 3:
                active_btn = self.tab_notifs_btn
            elif idx == 4:
                active_btn = self.tab_shortcuts_btn
            elif idx == 5:
                active_btn = None
        self._set_active_tab(active_btn)

        # 3. Strona Standby
        self._safe_set_style(self.standby_clock_label, f"color: {text_pri}; font-size: 20px; font-weight: bold;")
        self._safe_set_style(self.standby_date_label, f"color: {text_sec}; font-size: 11px;")
        if hasattr(self, 'st_badge'):
            self._safe_set_style(
                self.st_badge,
                f"background-color: {card_bg}; color: {text_pri}; font-size: 9px; "
                f"font-weight: bold; padding: 2px 6px; border-radius: 4px; border: 1px solid {card_border};"
            )

        # 4. Strona Muzyka
        if hasattr(self, 'exp_status'):
            self._safe_set_style(self.exp_status, f"color: {text_sec}; font-size: 11px;")
        if hasattr(self, 'exp_title'):
            self._safe_set_style(self.exp_title, f"color: {text_pri}; font-size: 13px; font-weight: bold;")
        if hasattr(self, 'exp_artist'):
            self._safe_set_style(self.exp_artist, f"color: {text_sec}; font-size: 11px;")
        if self.exp_album_art and self.exp_album_art.pixmap().isNull():
            self.exp_album_art.setStyleSheet(
                f"background-color: {card_bg}; color: {text_sec}; font-size: 23px; border-radius: 7px;"
            )
        if self.audio_output_button:
            self.audio_output_button.setStyleSheet(
                f"QPushButton {{ background-color: {card_bg}; color: {text_pri}; "
                f"border: 1px solid {card_border}; border-radius: 5px; padding: 2px 6px; "
                "font-size: 9px; font-weight: bold; text-align: left; } "
                f"QPushButton:hover {{ background-color: {hover_bg}; }} "
                "QPushButton:disabled { color: #8E8E93; }"
            )

        # 5. Półka
        self._safe_set_style(self.shelf_count_label, f"color: {text_sec}; font-size: 11px;")
        self._safe_set_style(
            self.shelf_empty_label,
            f"color: {text_sec}; font-size: 11px; padding: 12px; "
            f"border: 1px dashed {card_border}; border-radius: 8px;"
        )

        # 6. Alerty
        self._safe_set_style(self.notifs_count_label, f"color: {text_sec}; font-size: 11px;")
        self._safe_set_style(
            self.notifs_empty_label,
            f"color: {text_sec}; font-size: 11px; padding: 12px; "
            f"border: 1px dashed {card_border}; border-radius: 8px;"
        )

        # 7. Skróty
        if hasattr(self, 'shortcuts_hint'):
            self._safe_set_style(self.shortcuts_hint, f"color: {text_sec}; font-size: 11px;")
        if hasattr(self, 'add_shortcut_btn'):
            self._safe_set_style(
                self.add_shortcut_btn,
                f"QPushButton {{ background: {card_bg}; color: {text_pri}; border: 1px solid {card_border}; "
                f"border-radius: 5px; padding: 4px 9px; font-size: 10px; font-weight: bold; }} "
                f"QPushButton:hover {{ background: {hover_bg}; }}"
            )

        self._refresh_shortcuts()
        self._refresh_notifications_ui()
        self._apply_privacy_activity()

    def add_shortcut_path(self, path: str):
        """Dodaje skrót lub aplikację do listy i zapisuje do konfiguracji."""
        if not path:
            return
        clean_path = os.path.normpath(path).replace("\\", "/")
        if clean_path not in self.shortcuts:
            self.shortcuts.append(clean_path)
            self.shortcuts_settings.setValue("shortcuts", self.shortcuts)
            self.shortcuts_settings.sync()
        self._refresh_shortcuts()
        self._show_shortcuts_page()

    def _add_shortcut(self):
        path, _ = QFileDialog.getOpenFileName(
            self.exp_stack, "Wybierz aplikację lub plik", "",
            "Aplikacje i skróty (*.exe *.lnk *.bat *.cmd);;Wszystkie pliki (*.*)"
        )
        if path:
            self.add_shortcut_path(path)

    def _launch_shortcut(self, path: str):
        """Natywne uruchamianie pliku/skrótu przez powłokę Windows Shell."""
        try:
            if os.path.exists(path):
                os.startfile(path)
            else:
                QDesktopServices.openUrl(QUrl.fromLocalFile(path))
        except Exception as e:
            print(f"[Shortcuts Error] Nie można uruchomić {path}: {e}")

    def _refresh_shortcuts(self):
        # WAŻNE: sprawdzamy 'is None', a nie 'not self.shortcuts_layout',
        # ponieważ pusty QLayout w PyQt ma len == 0 i ewaluuje do False!
        if self.shortcuts_layout is None:
            return

        # Aktualizacja licznika na zakładce
        count = len(self.shortcuts)
        if self.tab_shortcuts_btn:
            self.tab_shortcuts_btn.setText(f"SKRÓTY ({count})" if count > 0 else "SKRÓTY")

        while self.shortcuts_layout.count():
            item = self.shortcuts_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        card_bg = theme_manager.card_bg
        card_border = theme_manager.card_border
        text_pri = theme_manager.text_primary
        text_sec = theme_manager.text_secondary
        hover_bg = theme_manager.hover_bg

        if not self.shortcuts:
            empty = QLabel("Brak przypiętych skrótów.\nKliknij „+ Dodaj” lub upuść plik tutaj.", self.shortcuts_container)
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setStyleSheet(
                f"color: {text_sec}; font-size: 11px; padding: 12px; "
                f"border: 1px dashed {card_border}; border-radius: 8px;"
            )
            self.shortcuts_layout.addWidget(empty)
            empty.show()
            return

        icon_provider = QFileIconProvider()

        for path in self.shortcuts:
            row = QWidget(self.shortcuts_container)
            row.setMinimumHeight(32)
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(6)

            base_name = os.path.basename(path)
            display_name = os.path.splitext(base_name)[0] if base_name.lower().endswith(".lnk") else base_name

            file_info = QFileInfo(path)
            file_icon = icon_provider.icon(file_info)

            launch_btn = QPushButton(display_name, row)
            if not file_icon.isNull():
                launch_btn.setIcon(file_icon)
                launch_btn.setIconSize(QSize(18, 18))
            launch_btn.setToolTip(path)
            launch_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            launch_btn.setStyleSheet(f"""
                QPushButton {{
                    background: {card_bg};
                    color: {text_pri};
                    text-align: left;
                    border: 1px solid {card_border};
                    border-radius: 6px;
                    padding: 6px 10px;
                    font-size: 11px;
                    font-weight: 500;
                }}
                QPushButton:hover {{
                    background-color: {hover_bg};
                    border-color: {card_border};
                }}
            """)
            launch_btn.clicked.connect(lambda checked=False, p=path: self._launch_shortcut(p))

            # Wektorowy przycisk usuwania (zero emotek)
            remove_btn = VectorCloseButton(size=18, parent=row)
            remove_btn.setToolTip("Usuń ten skrót")
            remove_btn.clicked.connect(lambda checked=False, p=path: self._remove_shortcut(p))

            row_layout.addWidget(launch_btn, 1)
            row_layout.addWidget(remove_btn)
            self.shortcuts_layout.addWidget(row)
            row.show()

        self.shortcuts_layout.addStretch()
        self.shortcuts_layout.activate()
        self.shortcuts_container.updateGeometry()
        self.shortcuts_container.update()

    def _remove_shortcut(self, path):
        self.shortcuts = [item for item in self.shortcuts if item != path]
        self.shortcuts_settings.setValue("shortcuts", self.shortcuts)
        self.shortcuts_settings.sync()
        self._refresh_shortcuts()

    def _on_shelf_updated(self, files: list):
        count = len(files)
        if self.tab_shelf_btn:
            self.tab_shelf_btn.setText("PÓŁKA")

        if self.pill_shelf_badge:
            self.pill_shelf_badge.set_count(count)
            self._schedule_pill_geometry_refresh()

        if self.shelf_count_label:
            self.shelf_count_label.setText(f"Zapisane pliki: {count}" if count > 0 else "Półka jest pusta")

        if self.shelf_cards_layout:
            while self.shelf_cards_layout.count():
                item = self.shelf_cards_layout.takeAt(0)
                w = item.widget()
                if w:
                    if w == self.shelf_empty_label:
                        self.shelf_cards_layout.removeWidget(w)
                    else:
                        w.deleteLater()

            if count == 0:
                if self.shelf_empty_label:
                    self.shelf_cards_layout.addWidget(self.shelf_empty_label)
                    self.shelf_empty_label.setVisible(True)
            else:
                if self.shelf_empty_label:
                    self.shelf_empty_label.setVisible(False)
                for fpath in files:
                    card = DraggableFileCard(fpath, on_remove_callback=shelf_manager.remove_file)
                    self.shelf_cards_layout.addWidget(card)

    def _get_formatted_date(self) -> str:
        date = QDate.currentDate()
        days = ["Poniedziałek", "Wtorek", "Środa", "Czwartek", "Piątek", "Sobota", "Niedziela"]
        months = [
            "stycznia", "lutego", "marca", "kwietnia", "maja", "czerwca",
            "lipca", "sierpnia", "września", "października", "listopada", "grudnia"
        ]
        day_name = days[date.dayOfWeek() - 1]
        month_name = months[date.month() - 1]
        return f"{day_name}, {date.day()} {month_name}"

    def _update_clock(self):
        curr_time_sec = QTime.currentTime().toString("HH:mm:ss")
        curr_time_min = QTime.currentTime().toString("HH:mm")

        if self.standby_clock_label:
            self.standby_clock_label.setText(curr_time_sec)

        if not self.is_active_player and self.pill_title:
            self.pill_title.setText(curr_time_min)
        elif self.is_active_player:
            self._apply_privacy_activity()

        self._refresh_seek_controls()
        if self.volume_slider and not self.volume_slider.isSliderDown() and time.monotonic() - self._last_volume_poll >= 3:
            self._last_volume_poll = time.monotonic()
            current_volume = get_system_volume()
            if current_volume is not None and current_volume != self.volume_slider.value():
                self.volume_slider.setValue(current_volume)

    @staticmethod
    def _format_media_time(seconds):
        seconds = max(0, int(seconds))
        hours, remainder = divmod(seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes}:{seconds:02d}"

    def _refresh_seek_controls(self):
        if not self.seek_slider or not self.seek_time_label:
            return
        duration = max(0, int(self.media_duration_seconds))
        position = self.media_position_seconds
        if self._media_is_playing:
            position += max(0, time.monotonic() - self._media_position_timestamp)
        position = min(max(0, position), duration) if duration else 0
        if not self.seek_slider.isSliderDown():
            self.seek_slider.blockSignals(True)
            self.seek_slider.setRange(0, duration)
            self.seek_slider.setValue(int(position))
            self.seek_slider.blockSignals(False)
        self.seek_slider.setEnabled(duration > 0)
        self.seek_time_label.setText(
            f"{self._format_media_time(self.seek_slider.value() if self.seek_slider.isSliderDown() else position)} / {self._format_media_time(duration)}"
        )

    def _on_seek_slider_changed(self, value):
        self.seek_time_label.setText(f"{self._format_media_time(value)} / {self._format_media_time(self.media_duration_seconds)}")

    def _seek_media(self):
        if self.media_duration_seconds <= 0:
            return
        self.media_position_seconds = float(self.seek_slider.value())
        self._media_position_timestamp = time.monotonic()
        media_seek(self.media_position_seconds)
        self._refresh_seek_controls()

    def _set_media_volume(self):
        volume = self.volume_slider.value()
        self._apply_media_volume(volume)

    def _apply_media_volume(self, volume):
        if set_system_volume(volume):
            self.volume_value_label.setText(f"{volume}%")

    def _start_audio_output_operation(self, action: str, device_id: str = ""):
        if self._audio_output_busy:
            return
        self._audio_output_busy = True
        self._audio_output_action = action
        if self.audio_output_button:
            self.audio_output_button.setEnabled(False)
            self.audio_output_button.setToolTip(
                "Wyszukiwanie wyjść audio…" if action == "list" else "Przełączanie wyjścia audio…"
            )

        def run_operation():
            try:
                if action == "list":
                    result = list_audio_outputs()
                else:
                    set_default_audio_output(device_id)
                    result = device_id
                self.audio_output_operation_done.emit(action, True, result, "")
            except Exception as error:
                self.audio_output_operation_done.emit(action, False, None, str(error))

        threading.Thread(target=run_operation, daemon=True).start()

    def _open_audio_output_menu(self):
        if self._audio_output_busy:
            if self._audio_output_action == "list":
                self._audio_output_show_menu = True
            return
        self._audio_output_show_menu = True
        self._start_audio_output_operation("list")

    def _on_audio_output_operation_done(self, action: str, success: bool, result, error: str):
        self._audio_output_busy = False
        self._audio_output_action = None
        if self.audio_output_button:
            self.audio_output_button.setEnabled(True)

        if action == "set":
            if success:
                self._start_audio_output_operation("list")
            else:
                if self.audio_output_button:
                    self.audio_output_button.setToolTip(
                        f"Nie udało się przełączyć wyjścia: {error[:180]}"
                    )
            return

        if not success:
            self._audio_output_show_menu = False
            if self.audio_output_button:
                self.audio_output_button.setText("WYJŚCIE ▾")
                self.audio_output_button.setToolTip(
                    f"Nie udało się pobrać wyjść audio: {error[:180]}"
                )
            return

        self._audio_output_devices = list(result or [])
        current = next((item for item in self._audio_output_devices if item.get("is_default")), None)
        if current:
            name = str(current.get("name", "Wyjście audio"))
            short_name = name if len(name) <= 15 else name[:14] + "…"
            if self.audio_output_button:
                self.audio_output_button.setText(f"{short_name} ▾")
                self.audio_output_button.setToolTip(f"Wyjście audio: {name}\nKliknij, aby przełączyć")
        elif self.audio_output_button:
            self.audio_output_button.setText("WYJŚCIE ▾")
            self.audio_output_button.setToolTip("Nie znaleziono aktywnych wyjść audio")

        if self._audio_output_show_menu:
            self._audio_output_show_menu = False
            self._show_audio_output_menu()

    def _show_audio_output_menu(self):
        if not self.audio_output_button:
            return
        menu = QMenu(self.audio_output_button)
        menu.setStyleSheet(
            f"QMenu {{ background-color: {theme_manager.card_bg}; color: {theme_manager.text_primary}; "
            f"border: 1px solid {theme_manager.card_border}; border-radius: 7px; padding: 4px; }} "
            f"QMenu::item {{ padding: 6px 18px; border-radius: 4px; }} "
            f"QMenu::item:selected {{ background-color: {theme_manager.hover_bg}; }}"
        )
        group = QActionGroup(menu)
        group.setExclusive(True)
        if not self._audio_output_devices:
            unavailable = QAction("Brak aktywnych wyjść audio", menu)
            unavailable.setEnabled(False)
            menu.addAction(unavailable)
        else:
            for device in self._audio_output_devices:
                name = str(device.get("name", "Wyjście audio"))
                action = QAction(name, menu)
                action.setCheckable(True)
                action.setChecked(bool(device.get("is_default")))
                group.addAction(action)
                menu.addAction(action)
                action.triggered.connect(
                    lambda _checked=False, selected=device: self._start_audio_output_operation(
                        "set", str(selected.get("id", ""))
                    )
                )
        self._audio_output_menu = menu
        menu.aboutToHide.connect(menu.deleteLater)
        menu.popup(self.audio_output_button.mapToGlobal(QPoint(0, self.audio_output_button.height())))

    def _on_media_update(self, data: dict):
        self.current_media = data
        has_session = bool(data.get("has_media", False))
        status = str(data.get("status", "Stopped"))
        is_playing = has_session and status.casefold() == "playing"
        self._media_is_playing = is_playing
        if has_session:
            self._request_album_artwork(
                str(data.get("title", "")),
                str(data.get("source", "")),
            )
            try:
                self.media_duration_seconds = max(0.0, float(data.get("duration_seconds", self.media_duration_seconds) or 0))
                self.media_position_seconds = max(0.0, float(data.get("position_seconds", self.media_position_seconds) or 0))
            except (TypeError, ValueError):
                pass
            self._media_position_timestamp = time.monotonic()
            self._refresh_seek_controls()

        if has_session:
            self.media_session_lost_timer.stop()
            if status.casefold() == "stopped":
                # The browser can keep an ended tab's SMTC session registered briefly.
                self.media_session_lost_timer.start(6000)
            elif not is_playing:
                # A closed browser tab can remain reported as paused; keep a short resume window.
                self.media_session_lost_timer.start(15000)
            if not self.is_active_player:
                self.is_active_player = True
                self._switch_mode(True)
        elif self.is_active_player:
            # Keep the last track visible briefly while the browser removes its SMTC session.
            if not self.media_session_lost_timer.isActive():
                self.media_session_lost_timer.start(10000)
            if self.pill_wave:
                self.pill_wave.set_playing(False)
            if self.exp_wave:
                self.exp_wave.set_playing(False)
            if self.exp_status:
                self.exp_status.setText("Wstrzymano")
            if self.btn_play_pause:
                self.btn_play_pause.set_icon_type(VectorIconButton.TYPE_PLAY)
            return
        else:
            return

        if has_session:
            title = data.get("title", "Nieznany utwór")
            artist = data.get("artist", "")
            source = data.get("source", "").lower()

            badge_text = "MEDIA"
            badge_color = "#3A3A3C" if theme_manager.is_dark else "#D8D8DE"
            accent_color = theme_manager.text_primary

            if "spotify" in source:
                badge_text = "SPOTIFY"
                badge_color = "#1DB954"
                accent_color = "#1DB954"
            elif "soundcloud" in title.lower() or "soundcloud" in source:
                badge_text = "SOUNDCLOUD"
                badge_color = "#FF5500"
                accent_color = "#FF5500"
            elif "youtube" in title.lower() or "youtube" in source:
                badge_text = "YOUTUBE"
                badge_color = "#FF0000"
                accent_color = "#FF3333"
            elif "chrome" in source:
                badge_text = "CHROME"
                badge_color = "#4285F4"
                accent_color = "#4285F4"
            elif "firefox" in source:
                badge_text = "FIREFOX"
                badge_color = "#FF7139"
                accent_color = "#FF7139"
            elif "msedge" in source:
                badge_text = "EDGE"
                badge_color = "#0078D7"
                accent_color = "#0078D7"

            if self.pill_wave:
                self.pill_wave.set_playing(is_playing)
                self.pill_wave.set_accent_color(accent_color)
            if self.exp_wave:
                self.exp_wave.set_playing(is_playing)
                self.exp_wave.set_accent_color(accent_color)

            if self.pill_title:
                compact_title = title[:18] + "…" if len(title) > 18 else title
                self.pill_title.setText(compact_title)
                self.pill_title.setToolTip(f"{title}\n{artist}".strip())
            clean_artist = artist[:12] + "…" if len(artist) > 12 else artist
            self._media_subtitle = clean_artist if clean_artist else badge_text
            self._apply_privacy_activity()

            if self.exp_badge:
                self.exp_badge.setText(badge_text)
                self.exp_badge.setStyleSheet(
                    f"background-color: {badge_color}; color: #FFFFFF; "
                    "font-weight: bold; font-size: 9px; padding: 2px 7px; border-radius: 4px;"
                )
            if self.exp_status:
                if is_playing:
                    self.exp_status.setText("Odtwarzanie")
                elif status.casefold() == "stopped":
                    self.exp_status.setText("Zatrzymano")
                else:
                    self.exp_status.setText("Wstrzymano")
            if self.exp_title:
                full_display = title if len(title) <= 40 else title[:38] + "…"
                self.exp_title.setText(full_display)
            if self.exp_artist:
                self.exp_artist.setText(artist if artist else "Brak informacji o wykonawcy")
            if self.btn_play_pause:
                self.btn_play_pause.set_icon_type(
                    VectorIconButton.TYPE_PAUSE if is_playing else VectorIconButton.TYPE_PLAY
                )

    def _set_album_art(self, encoded_image: str):
        """Update the player artwork from the active Windows media session."""
        if not self.exp_album_art:
            return
        self.exp_album_art.setPixmap(QPixmap())
        self.exp_album_art.setText("♫")
        if not encoded_image or len(encoded_image) > 6 * 1024 * 1024:
            return
        try:
            image_data = base64.b64decode(encoded_image, validate=True)
            pixmap = QPixmap()
            if not pixmap.loadFromData(image_data):
                return
            size = self.exp_album_art.size()
            scaled = pixmap.scaled(
                size,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            x = max(0, (scaled.width() - size.width()) // 2)
            y = max(0, (scaled.height() - size.height()) // 2)
            self.exp_album_art.setText("")
            self.exp_album_art.setPixmap(scaled.copy(x, y, size.width(), size.height()))
        except (ValueError, TypeError):
            pass

    def _request_album_artwork(self, title: str, source: str):
        key = (title, source)
        if not title or key == self._album_artwork_request_key:
            return
        self._album_artwork_request_key = key
        self._set_album_art("")
        threading.Thread(
            target=self._load_album_artwork,
            args=(title, source),
            daemon=True,
        ).start()

    def _load_album_artwork(self, title: str, source: str):
        """Fetch artwork out of band so a slow thumbnail cannot stall media polling."""
        command = base64.b64encode(POWERSHELL_ARTWORK_SCRIPT.encode("utf-16le")).decode("ascii")
        artwork = ""
        try:
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0
            result = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand", command],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=8,
                startupinfo=startupinfo,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if result.returncode == 0:
                artwork = result.stdout.strip().splitlines()[-1:]
                artwork = artwork[0] if artwork else ""
        except (OSError, subprocess.SubprocessError):
            pass
        self.album_artwork_loaded.emit(title, source, artwork)

    def _on_album_artwork_loaded(self, title: str, source: str, artwork: str):
        current_title = str(self.current_media.get("title", ""))
        current_source = str(self.current_media.get("source", ""))
        if (title, source) != (current_title, current_source):
            return
        self._set_album_art(artwork)

    def _leave_player_if_session_lost(self):
        if not self.is_active_player:
            return
        if self.current_media.get("has_media", False):
            status = str(self.current_media.get("status", "")).casefold()
            if status not in {"stopped", "paused"}:
                return
        self.is_active_player = False
        self._switch_mode(False)

    def _switch_mode(self, to_player: bool):
        if to_player:
            if self.pill_eyes:
                self.pill_eyes.setVisible(False)
            if self.pill_wave:
                self.pill_wave.setVisible(True)
            if self.exp_stack and self.exp_stack.currentIndex() not in (2, 3):
                self.exp_stack.setCurrentIndex(1)
                self.tab_media_btn.setText("MUZYKA")
        else:
            if self.pill_wave:
                self.pill_wave.setVisible(False)
                self.pill_wave.set_playing(False)
            if self.pill_eyes:
                self.pill_eyes.setVisible(True)
            if self.pill_title:
                self.pill_title.setText(QTime.currentTime().toString("HH:mm"))
            if self.pill_subtitle:
                self._media_subtitle = ""
                self._apply_privacy_activity()
            if self.exp_stack and self.exp_stack.currentIndex() not in (2, 3):
                self.exp_stack.setCurrentIndex(0)
                self.tab_media_btn.setText("STATUS")
        self._schedule_pill_geometry_refresh()
