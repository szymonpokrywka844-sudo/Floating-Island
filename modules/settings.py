"""
Panel ustawien Floating Island.
Sekcje: Motyw, Pozycja, Przezroczystosc, Autostart, Reset.
Wszystkie ikony rysowane QPainter - zero emotek, zero obrazkow.
"""
from PyQt6.QtCore import Qt, QSettings, QUrl
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QSlider, QScrollArea, QFrame, QLineEdit, QApplication
)
from PyQt6.QtGui import QPainter, QColor, QDesktopServices

from core.theme import theme_manager
from core import config
from core.autostart import is_autostart_enabled, set_autostart
from ui.vector_controls import VectorToggleSwitch
from core.secret_store import load_github_token, save_github_token


# ---------------------------------------------------------------------------
# Pomocnicze widgety sekcji
# ---------------------------------------------------------------------------

class _SectionLabel(QLabel):
    """Naglowek sekcji (maly, szary, uppercase)."""
    def __init__(self, text: str, parent=None):
        super().__init__(text.upper(), parent)
        self.apply_theme()

    def apply_theme(self):
        sec_color = theme_manager.text_secondary
        self.setStyleSheet(
            f"color: {sec_color}; font-size: 9px; font-weight: bold; "
            f"letter-spacing: 0.8px; padding: 0 2px 2px 2px;"
        )


class _Separator(QFrame):
    """Cienka pozioma linia oddzielajaca sekcje."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.HLine)
        self.setFixedHeight(1)
        self.apply_theme()

    def apply_theme(self):
        line_col = theme_manager.card_border
        self.setStyleSheet(f"background-color: {line_col}; border: none;")


class _ThemeButton(QPushButton):
    """Przycisk wyboru motywu: Ciemny / Jasny / Systemowy."""
    def __init__(self, label: str, mode_key: str, parent=None):
        super().__init__(label, parent)
        self.mode_key = mode_key
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(28)
        self._refresh_style(False)

    def _refresh_style(self, active: bool):
        if active:
            self.setStyleSheet(
                "QPushButton {"
                "  background-color: #0A84FF;"
                "  color: #FFFFFF;"
                "  font-size: 11px;"
                "  font-weight: bold;"
                "  border-radius: 6px;"
                "  border: none;"
                "  padding: 0 10px;"
                "}"
            )
        else:
            card_bg = theme_manager.card_bg
            border_c = theme_manager.card_border
            text_sec = theme_manager.text_secondary
            hover_bg = theme_manager.hover_bg
            text_pri = theme_manager.text_primary
            self.setStyleSheet(
                f"QPushButton {{"
                f"  background-color: {card_bg};"
                f"  color: {text_sec};"
                f"  font-size: 11px;"
                f"  font-weight: 500;"
                f"  border-radius: 6px;"
                f"  border: 1px solid {border_c};"
                f"  padding: 0 10px;"
                f"}}"
                f"QPushButton:hover {{"
                f"  background-color: {hover_bg};"
                f"  color: {text_pri};"
                f"}}"
            )

    def set_active(self, active: bool):
        self.setChecked(active)
        self._refresh_style(active)


# ---------------------------------------------------------------------------
# Glowny widget ustawien
# ---------------------------------------------------------------------------

class SettingsPage(QWidget):
    """
    Pełna strona ustawien wyspy.
    Zwracana przez MediaModule i wyswietlana w exp_stack jako strona 5.
    """

    def __init__(self, island_ref=None, parent=None):
        super().__init__(parent)
        self._island = island_ref
        self._settings = QSettings("FloatingIsland", "FloatingIsland")
        self._section_labels = []
        self._separators = []

        # Glowny scroll
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        inner = QWidget()
        inner.setStyleSheet("background: transparent;")
        self._inner_layout = QVBoxLayout(inner)
        self._inner_layout.setContentsMargins(2, 0, 2, 4)
        self._inner_layout.setSpacing(6)

        # --- SEKCJA: MOTYW ---
        lbl1 = _SectionLabel("Motyw")
        self._section_labels.append(lbl1)
        self._inner_layout.addWidget(lbl1)
        self._build_theme_section()

        sep1 = _Separator()
        self._separators.append(sep1)
        self._inner_layout.addWidget(sep1)

        # --- SEKCJA: POZYCJA (TOP OFFSET) ---
        lbl2 = _SectionLabel("Pozycja od gornej krawedzi")
        self._section_labels.append(lbl2)
        self._inner_layout.addWidget(lbl2)
        self._build_offset_section()

        sep2 = _Separator()
        self._separators.append(sep2)
        self._inner_layout.addWidget(sep2)

        # --- SEKCJA: PRZEZROCZYSTOSC ---
        lbl3 = _SectionLabel("Przezroczystosc tla")
        self._section_labels.append(lbl3)
        self._inner_layout.addWidget(lbl3)
        self._build_opacity_section()

        sep3 = _Separator()
        self._separators.append(sep3)
        self._inner_layout.addWidget(sep3)

        # --- SEKCJA: AUTOSTART ---
        lbl4 = _SectionLabel("Autostart z systemem")
        self._section_labels.append(lbl4)
        self._inner_layout.addWidget(lbl4)
        self._build_autostart_section()

        sep4 = _Separator()
        self._separators.append(sep4)
        self._inner_layout.addWidget(sep4)

        # --- SEKCJA: PRYWATNE AKTUALIZACJE GITHUB ---
        lbl5 = _SectionLabel("Aktualizacje z prywatnego GitHub")
        self._section_labels.append(lbl5)
        self._inner_layout.addWidget(lbl5)
        self._build_github_token_section()

        sep5 = _Separator()
        self._separators.append(sep5)
        self._inner_layout.addWidget(sep5)

        # --- SEKCJA: RESET ---
        lbl6 = _SectionLabel("Resetowanie")
        self._section_labels.append(lbl6)
        self._inner_layout.addWidget(lbl6)
        self._build_reset_section()

        self._inner_layout.addStretch()

        scroll.setWidget(inner)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(scroll)

        # Synchronizacja z motywem
        theme_manager.theme_changed.connect(self._on_theme_changed)
        self._on_theme_changed(theme_manager.effective_theme)

    # ------------------------------------------------------------------
    # Budowanie sekcji
    # ------------------------------------------------------------------

    def _build_theme_section(self):
        row = QHBoxLayout()
        row.setSpacing(5)
        row.setContentsMargins(0, 0, 0, 0)

        self._btn_dark = _ThemeButton("Ciemny", theme_manager.THEME_DARK)
        self._btn_light = _ThemeButton("Jasny", theme_manager.THEME_LIGHT)
        self._btn_system = _ThemeButton("Systemowy", theme_manager.THEME_SYSTEM)

        for btn in (self._btn_dark, self._btn_light, self._btn_system):
            btn.clicked.connect(lambda _, b=btn: self._on_theme_btn(b))
            row.addWidget(btn)

        self._sync_theme_buttons()

        container = QWidget()
        container.setStyleSheet("background: transparent;")
        container.setLayout(row)
        self._inner_layout.addWidget(container)

    def _build_offset_section(self):
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)

        saved_offset = int(self._settings.value("top_offset", config.TOP_OFFSET))

        self._offset_slider = QSlider(Qt.Orientation.Horizontal)
        self._offset_slider.setMinimum(4)
        self._offset_slider.setMaximum(40)
        self._offset_slider.setValue(saved_offset)
        self._offset_slider.setStyleSheet(self._slider_style())
        self._offset_slider.setCursor(Qt.CursorShape.PointingHandCursor)

        self._offset_val_label = QLabel(f"{saved_offset} px")
        self._offset_val_label.setStyleSheet(f"color: {theme_manager.text_secondary}; font-size: 11px; min-width: 36px;")
        self._offset_val_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        self._offset_slider.valueChanged.connect(self._on_offset_changed)

        row.addWidget(self._offset_slider, 1)
        row.addWidget(self._offset_val_label)

        container = QWidget()
        container.setStyleSheet("background: transparent;")
        container.setLayout(row)
        self._inner_layout.addWidget(container)

    def _build_opacity_section(self):
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)

        saved_opacity = int(self._settings.value("bg_opacity", 248))

        self._opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self._opacity_slider.setMinimum(80)
        self._opacity_slider.setMaximum(255)
        self._opacity_slider.setValue(saved_opacity)
        self._opacity_slider.setStyleSheet(self._slider_style())
        self._opacity_slider.setCursor(Qt.CursorShape.PointingHandCursor)

        pct = int((saved_opacity / 255) * 100)
        self._opacity_val_label = QLabel(f"{pct}%")
        self._opacity_val_label.setStyleSheet(f"color: {theme_manager.text_secondary}; font-size: 11px; min-width: 36px;")
        self._opacity_val_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        self._opacity_slider.valueChanged.connect(self._on_opacity_changed)

        row.addWidget(self._opacity_slider, 1)
        row.addWidget(self._opacity_val_label)

        container = QWidget()
        container.setStyleSheet("background: transparent;")
        container.setLayout(row)
        self._inner_layout.addWidget(container)

    def _build_autostart_section(self):
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)

        self._autostart_desc = QLabel("Uruchom wyspę przy starcie Windows")
        self._autostart_desc.setStyleSheet(f"color: {theme_manager.text_primary}; font-size: 11px;")

        self._autostart_toggle = VectorToggleSwitch(parent=self)
        self._autostart_toggle.setChecked(is_autostart_enabled())
        self._autostart_toggle.toggled.connect(self._on_autostart_toggle)

        row.addWidget(self._autostart_desc, 1)
        row.addWidget(self._autostart_toggle)

        container = QWidget()
        container.setStyleSheet("background: transparent;")
        container.setLayout(row)
        self._inner_layout.addWidget(container)

    def _build_reset_section(self):
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)

        self._btn_reset = QPushButton("Resetuj ustawienia")
        self._btn_reset.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_reset.setFixedHeight(26)
        self._refresh_reset_btn_style()
        self._btn_reset.clicked.connect(self._on_reset)

        row.addStretch()
        row.addWidget(self._btn_reset)

        container = QWidget()
        container.setStyleSheet("background: transparent;")
        container.setLayout(row)
        self._inner_layout.addWidget(container)

    def _build_github_token_section(self):
        description = QLabel(
            "Token fine-grained dla Floating-Island: Contents = Read-only. "
            "Jest szyfrowany dla tego konta Windows."
        )
        description.setWordWrap(True)
        description.setStyleSheet(
            f"color: {theme_manager.text_secondary}; font-size: 10px;"
        )
        self._inner_layout.addWidget(description)

        self._github_token_input = QLineEdit()
        self._github_token_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._github_token_input.setPlaceholderText(
            "Token skonfigurowany" if load_github_token() else "github_pat_…"
        )
        self._github_token_input.setFixedHeight(28)
        self._github_token_input.setStyleSheet(
            f"QLineEdit {{ background: {theme_manager.card_bg}; color: {theme_manager.text_primary}; "
            f"border: 1px solid {theme_manager.card_border}; border-radius: 5px; padding: 0 7px; }}"
        )
        self._inner_layout.addWidget(self._github_token_input)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        self._github_token_save = QPushButton("Zapisz token")
        self._github_token_save.setFixedHeight(26)
        self._github_token_save.setCursor(Qt.CursorShape.PointingHandCursor)
        self._github_token_save.clicked.connect(self._save_github_token)
        self._github_token_help = QPushButton("Utwórz token")
        self._github_token_help.setFixedHeight(26)
        self._github_token_help.setCursor(Qt.CursorShape.PointingHandCursor)
        self._github_token_help.clicked.connect(lambda: QDesktopServices.openUrl(
            QUrl("https://github.com/settings/personal-access-tokens/new")
        ))
        for button in (self._github_token_save, self._github_token_help):
            button.setStyleSheet(
                f"QPushButton {{ background: {theme_manager.card_bg}; color: {theme_manager.text_primary}; "
                f"border: 1px solid {theme_manager.card_border}; border-radius: 5px; padding: 0 8px; font-size: 10px; }}"
                f"QPushButton:hover {{ background: {theme_manager.hover_bg}; }}"
            )
        self._github_token_status = QLabel(
            "Token jest zapisany." if load_github_token() else "Brak tokena."
        )
        self._github_token_status.setStyleSheet(
            f"color: {theme_manager.text_secondary}; font-size: 9px;"
        )
        row.addWidget(self._github_token_save)
        row.addWidget(self._github_token_help)
        row.addWidget(self._github_token_status, 1)
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        container.setLayout(row)
        self._inner_layout.addWidget(container)

    def _save_github_token(self):
        token = self._github_token_input.text().strip()
        try:
            save_github_token(token)
            self._github_token_input.clear()
            self._github_token_input.setPlaceholderText(
                "Token skonfigurowany" if token else "github_pat_…"
            )
            self._github_token_status.setText(
                "Token zapisany. Sprawdzam aktualizacje…" if token else "Token usunięty."
            )
            app = QApplication.instance()
            updater = getattr(app, "_floating_island_updater", None) if app else None
            if updater and token:
                updater.check_for_updates()
        except Exception as error:
            self._github_token_status.setText(f"Nie udało się zapisać: {error}")

    def _refresh_reset_btn_style(self):
        if hasattr(self, '_btn_reset') and self._btn_reset:
            is_dark = theme_manager.is_dark
            border_c = "#3A1E1E" if is_dark else "#F5C2C2"
            hover_bg = "#2C1414" if is_dark else "#FDE8E8"
            self._btn_reset.setStyleSheet(
                f"QPushButton {{"
                f"  background: transparent;"
                f"  color: #FF453A;"
                f"  font-size: 10px;"
                f"  font-weight: bold;"
                f"  border: 1px solid {border_c};"
                f"  border-radius: 5px;"
                f"  padding: 0 10px;"
                f"}}"
                f"QPushButton:hover {{"
                f"  background-color: {hover_bg};"
                f"}}"
            )

    # ------------------------------------------------------------------
    # Handlery
    # ------------------------------------------------------------------

    def _on_theme_btn(self, btn: _ThemeButton):
        theme_manager.mode = btn.mode_key
        self._sync_theme_buttons()

    def _sync_theme_buttons(self):
        current = theme_manager.mode
        self._btn_dark.set_active(current == theme_manager.THEME_DARK)
        self._btn_light.set_active(current == theme_manager.THEME_LIGHT)
        self._btn_system.set_active(current == theme_manager.THEME_SYSTEM)

    def _on_offset_changed(self, value: int):
        self._offset_val_label.setText(f"{value} px")
        self._settings.setValue("top_offset", value)
        self._settings.sync()
        if self._island is not None:
            config.TOP_OFFSET = value
            self._island._update_screen_metrics(self._island.current_screen)
            self._island.geo_anim.stop()
            if self._island.is_expanded:
                target = self._island._get_expanded_rect()
            elif self._island.is_hidden_by_fullscreen:
                target = self._island._get_hidden_rect()
            else:
                target = self._island._get_collapsed_rect()
            self._island.setGeometry(target)

    def _on_opacity_changed(self, value: int):
        pct = int((value / 255) * 100)
        self._opacity_val_label.setText(f"{pct}%")
        self._settings.setValue("bg_opacity", value)
        self._settings.sync()
        if self._island is not None:
            self._island._bg_opacity = value
            self._island.update()

    def _on_autostart_toggle(self, checked: bool):
        set_autostart(checked)

    def _on_reset(self):
        """Resetuje ustawienia do wartosci domyslnych."""
        self._settings.remove("top_offset")
        self._settings.remove("bg_opacity")
        self._settings.remove("theme_mode")
        self._settings.sync()

        theme_manager.mode = theme_manager.THEME_DARK
        self._sync_theme_buttons()

        config.TOP_OFFSET = 12
        self._offset_slider.setValue(12)

        self._opacity_slider.setValue(248)

        if self._island is not None:
            self._island._bg_opacity = 248
            self._island._update_screen_metrics(self._island.current_screen)
            self._island.geo_anim.stop()
            if self._island.is_expanded:
                target = self._island._get_expanded_rect()
            else:
                target = self._island._get_collapsed_rect()
            self._island.setGeometry(target)
            self._island.update()

    def _on_theme_changed(self, theme: str):
        """Odswieza kolory kontrolek po zmianie motywu."""
        self._sync_theme_buttons()

        for lbl in self._section_labels:
            lbl.apply_theme()
        for sep in self._separators:
            sep.apply_theme()

        text_pri = theme_manager.text_primary
        text_sec = theme_manager.text_secondary

        if hasattr(self, '_offset_val_label') and self._offset_val_label:
            self._offset_val_label.setStyleSheet(f"color: {text_sec}; font-size: 11px; min-width: 36px;")
        if hasattr(self, '_opacity_val_label') and self._opacity_val_label:
            self._opacity_val_label.setStyleSheet(f"color: {text_sec}; font-size: 11px; min-width: 36px;")
        if hasattr(self, '_autostart_desc') and self._autostart_desc:
            self._autostart_desc.setStyleSheet(f"color: {text_pri}; font-size: 11px;")

        slider_css = self._slider_style()
        if hasattr(self, '_offset_slider') and self._offset_slider:
            self._offset_slider.setStyleSheet(slider_css)
        if hasattr(self, '_opacity_slider') and self._opacity_slider:
            self._opacity_slider.setStyleSheet(slider_css)

        self._refresh_reset_btn_style()

    def set_island(self, island):
        """Przekazuje referencje do okna wyspy po inicjalizacji."""
        self._island = island
        if island is not None:
            if hasattr(island, "_bg_opacity") and hasattr(self, "_opacity_slider"):
                self._opacity_slider.blockSignals(True)
                self._opacity_slider.setValue(island._bg_opacity)
                pct = int((island._bg_opacity / 255) * 100)
                self._opacity_val_label.setText(f"{pct}%")
                self._opacity_slider.blockSignals(False)
            if hasattr(self, "_offset_slider"):
                self._offset_slider.blockSignals(True)
                self._offset_slider.setValue(config.TOP_OFFSET)
                self._offset_val_label.setText(f"{config.TOP_OFFSET} px")
                self._offset_slider.blockSignals(False)

    # ------------------------------------------------------------------
    # Style pomoc
    # ------------------------------------------------------------------

    @staticmethod
    def _slider_style() -> str:
        is_dark = theme_manager.is_dark
        groove_bg = "#3A3A3C" if is_dark else "#D1D1D8"
        handle_bg = "#FFFFFF" if is_dark else "#1A1A1C"
        subpage_bg = "#0A84FF" if is_dark else "#007AFF"
        return f"""
            QSlider::groove:horizontal {{
                height: 4px;
                background: {groove_bg};
                border-radius: 2px;
            }}
            QSlider::handle:horizontal {{
                width: 14px;
                height: 14px;
                margin: -5px 0;
                background: {handle_bg};
                border-radius: 7px;
                border: none;
            }}
            QSlider::sub-page:horizontal {{
                background: {subpage_bg};
                border-radius: 2px;
            }}
        """
