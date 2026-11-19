"""
Konfiguracja wizualna i parametry zachowania Pływającej Wyspy.
"""
from PyQt6.QtGui import QColor

# --- Wymiary pigułki (Pill) ---
COLLAPSED_WIDTH = 190
COLLAPSED_HEIGHT = 36

# --- Wymiary rozwiniętej wyspy (Island) ---
EXPANDED_WIDTH = 420
EXPANDED_HEIGHT = 135

# --- Pozycja ---
TOP_OFFSET = 12  # Dystans od górnej krawędzi ekranu w pikselach

# --- Animacje ---
ANIMATION_DURATION_MS = 260

# --- Paleta kolorów (Dark / OLED style) ---
BG_COLOR = QColor(18, 18, 20, 240)       # Półprzezroczysty grafit
BORDER_COLOR = QColor(255, 255, 255, 28) # Dyskretna krawędź
SHADOW_COLOR = QColor(0, 0, 0, 180)      # Miękki cień pod spodem
SHADOW_BLUR_RADIUS = 28
