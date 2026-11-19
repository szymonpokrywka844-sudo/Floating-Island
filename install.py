"""
Skrypt instalacyjny Floating Island.
Tworzy skrót .lnk na Pulpicie z wbudowaną ikoną rysowaną wektorowo
oraz opcjonalnie rejestruje autostart.

Uruchom raz: python install.py
"""
import os
import sys
import struct
import ctypes
import winreg

# --- Sciezki ------------------------------------------------------------------
SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
MAIN_PY      = os.path.join(SCRIPT_DIR, "main.py")
ICON_PATH    = os.path.join(SCRIPT_DIR, "island_icon.ico")
DESKTOP_PATH = os.path.join(os.path.expanduser("~"), "Desktop")
SHORTCUT_PATH = os.path.join(DESKTOP_PATH, "Floating Island.lnk")

# pythonw.exe obok python.exe (brak okna konsoli)
PYTHON_EXE   = sys.executable
PYTHONW_EXE  = PYTHON_EXE.replace("python.exe", "pythonw.exe")
if not os.path.isfile(PYTHONW_EXE):
    PYTHONW_EXE = PYTHON_EXE   # fallback


# --- Generowanie ikony .ico wektorowo (bez Pillow) ----------------------------
def _make_ico() -> bool:
    """
    Tworzy minimalistyczną ikonę 32x32 i 16x16 jako plik .ico (format BMP/ICO).
    Czarna pigulka z bialymi kropkami - rysowana czystymi bajtami, zero bibliotek zewnetrznych.
    """
    try:
        import struct as st

        def make_bmp_32x32():
            w, h = 32, 32
            # BITMAPINFOHEADER (40 bajtow)
            bih = st.pack('<lllHHIIllII',
                40, w, h*2, 1, 32, 0, 0, 0, 0, 0, 0)

            pixels = []
            cx, cy = w / 2.0, h / 2.0
            pill_rx, pill_ry = 14.0, 7.0  # pół-osie pigułki (owalny ksztalt)

            for row in range(h - 1, -1, -1):
                for col in range(w):
                    px = col - cx
                    py = row - cy
                    # Sprawdzenie czy punkt lezy w owalnym ksztalcie (elipsa)
                    inside = (px / pill_rx) ** 2 + (py / pill_ry) ** 2 <= 1.0
                    if inside:
                        # Wewnatrz pigulki - prawie-czarny (#0E0E10)
                        pixels.append(st.pack('<BBBB', 16, 14, 14, 255))
                        # Dwie biale kropki (oczy)
                        # Lewe oko: col ~11, row ~16-18
                        # Prawe oko: col ~20, row ~16-18
                        lx1, lx2 = 10, 13
                        rx1, rx2 = 19, 22
                        ey1, ey2 = 13, 18  # wiersz (odwrocony: 32-18=14 do 32-13=19 → row 14..19)
                        if (lx1 <= col <= lx2 or rx1 <= col <= rx2) and ey1 <= row <= ey2:
                            pixels[-1] = st.pack('<BBBB', 255, 255, 255, 255)
                    else:
                        pixels.append(st.pack('<BBBB', 0, 0, 0, 0))  # Przezroczysty

            xor_mask = b''.join(pixels)
            and_mask = bytes([0x00] * (w // 8 * h))  # Pelna przezroczystosc
            return bih + xor_mask + and_mask

        def make_bmp_16x16():
            w, h = 16, 16
            bih = st.pack('<lllHHIIllII',
                40, w, h*2, 1, 32, 0, 0, 0, 0, 0, 0)
            pixels = []
            cx, cy = w / 2.0, h / 2.0
            pill_rx, pill_ry = 7.0, 3.5

            for row in range(h - 1, -1, -1):
                for col in range(w):
                    px = col - cx
                    py = row - cy
                    inside = (px / pill_rx) ** 2 + (py / pill_ry) ** 2 <= 1.0
                    if inside:
                        pixels.append(st.pack('<BBBB', 16, 14, 14, 255))
                        if (4 <= col <= 6 or 9 <= col <= 11) and 6 <= row <= 9:
                            pixels[-1] = st.pack('<BBBB', 255, 255, 255, 255)
                    else:
                        pixels.append(st.pack('<BBBB', 0, 0, 0, 0))

            xor_mask = b''.join(pixels)
            and_mask = bytes([0x00] * (w // 8 * h))
            return bih + xor_mask + and_mask

        bmp32 = make_bmp_32x32()
        bmp16 = make_bmp_16x16()

        # Naglowek ICO: 2 obrazy
        num_images = 2
        header = st.pack('<HHH', 0, 1, num_images)

        # Offset do danych: 6 (header) + 2*16 (directory entries)
        offset1 = 6 + num_images * 16
        offset2 = offset1 + len(bmp32)

        # ICO Directory Entry: width, height, colorCount, reserved, planes, bitCount, size, offset
        entry32 = st.pack('<BBBBHHII', 32, 32, 0, 0, 1, 32, len(bmp32), offset1)
        entry16 = st.pack('<BBBBHHII', 16, 16, 0, 0, 1, 32, len(bmp16), offset2)

        ico_data = header + entry32 + entry16 + bmp32 + bmp16

        with open(ICON_PATH, 'wb') as f:
            f.write(ico_data)
        return True
    except Exception as e:
        print(f"  [!] Nie udalo sie stworzyc ikony: {e}")
        return False


# --- Tworzenie skrótu .lnk przez Windows COM (Shell) --------------------------
def _create_shortcut() -> bool:
    """
    Tworzy skrót .lnk przez interfejs COM Windows Shell (IShellLink).
    Nie wymaga bibliotek zewnetrznych - uzywa wbudowanego win32com via ctypes/COM.
    """
    try:
        import comtypes.client
        shell = comtypes.client.CreateObject("WScript.Shell")
        sc = shell.CreateShortCut(SHORTCUT_PATH)
        sc.TargetPath = PYTHONW_EXE
        sc.Arguments = f'"{MAIN_PY}"'
        sc.WorkingDirectory = SCRIPT_DIR
        sc.Description = "Floating Island - Plywajaca wyspa Windows"
        if os.path.isfile(ICON_PATH):
            sc.IconLocation = ICON_PATH
        sc.WindowStyle = 7  # Minimalizuje (uruchom w tle)
        sc.Save()
        return True
    except ImportError:
        return _create_shortcut_powershell()
    except Exception as e:
        print(f"  [!] comtypes error: {e}")
        return _create_shortcut_powershell()


def _create_shortcut_powershell() -> bool:
    """
    Fallback: tworzy skrót przez PowerShell (WScript.Shell).
    Dziala bez zadnych dodatkowych pakietow Python.
    """
    import subprocess

    icon_arg = f'; $sc.IconLocation = "{ICON_PATH}"' if os.path.isfile(ICON_PATH) else ""

    ps_script = f"""
$WshShell = New-Object -ComObject WScript.Shell
$sc = $WshShell.CreateShortcut("{SHORTCUT_PATH}")
$sc.TargetPath = "{PYTHONW_EXE}"
$sc.Arguments = '"{MAIN_PY}"'
$sc.WorkingDirectory = "{SCRIPT_DIR}"
$sc.Description = "Floating Island - Plywajaca wyspa Windows"
$sc.WindowStyle = 7{icon_arg}
$sc.Save()
Write-Output "OK"
"""
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script],
            capture_output=True, text=True, timeout=15
        )
        return "OK" in result.stdout or result.returncode == 0
    except Exception as e:
        print(f"  [!] PowerShell error: {e}")
        return False


# --- Autostart (opcjonalny) ---------------------------------------------------
def _add_autostart() -> bool:
    """Dodaje wpis do HKCU Run - Floating Island uruchamia sie ze startem Windows."""
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0, winreg.KEY_SET_VALUE
        )
        value = f'"{PYTHONW_EXE}" "{MAIN_PY}"'
        winreg.SetValueEx(key, "FloatingIsland", 0, winreg.REG_SZ, value)
        winreg.CloseKey(key)
        return True
    except Exception as e:
        print(f"  [!] Blad autostaru: {e}")
        return False


def _remove_autostart() -> bool:
    """Usuwa wpis autostartu z rejestru."""
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0, winreg.KEY_SET_VALUE
        )
        winreg.DeleteValue(key, "FloatingIsland")
        winreg.CloseKey(key)
        return True
    except FileNotFoundError:
        return True  # Juz nie istnieje
    except Exception as e:
        print(f"  [!] Blad usuwania autostaru: {e}")
        return False


def _has_autostart() -> bool:
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0, winreg.KEY_READ
        )
        winreg.QueryValueEx(key, "FloatingIsland")
        winreg.CloseKey(key)
        return True
    except Exception:
        return False


# --- Glowna funkcja instalacyjna ----------------------------------------------
def main():
    print()
    print("=" * 52)
    print("   Floating Island  -  Instalator skrótu")
    print("=" * 52)
    print()

    # 0. Usunięcie starej wersji
    print("[0/3] Zamykanie starych instancji i czyszczenie pamięci podręcznej...")
    try:
        from core.reloader import kill_previous_instances, cleanup_stale_pycache
        kill_previous_instances()
        cleanup_stale_pycache(SCRIPT_DIR)
        print("      Stare instancje zamknięte, cache wyczyszczony.")
    except Exception as e:
        print(f"      Uwaga: {e}")

    # 1. Ikona
    print("[1/3] Generowanie ikony...")
    if _make_ico():
        print(f"      Ikona zapisana: {ICON_PATH}")
    else:
        print("      Kontynuuje bez ikony.")

    # 2. Skrót na pulpicie
    print("[2/3] Tworzenie skrótu na Pulpicie...")
    if _create_shortcut():
        print(f"      Skrót utworzony: {SHORTCUT_PATH}")
    else:
        print("      BLAD: nie udalo sie stworzyc skrótu.")
        print(f"      Mozesz recznie uruchomic: {PYTHONW_EXE} \"{MAIN_PY}\"")

    # 3. Autostart
    print("[3/3] Autostart przy logowaniu...")
    already = _has_autostart()
    if already:
        print("      Autostart jest juz aktywny (wlaczony przez tray).")
    else:
        ans = input("      Dodac autostart? [t/N]: ").strip().lower()
        if ans in ("t", "tak", "y", "yes"):
            if _add_autostart():
                print("      Autostart WLACZONY.")
            else:
                print("      Nie udalo sie dodac autostaru.")
        else:
            print("      Pominieto (mozna wlaczyc z ikony tray prawym przyciskiem).")

    print()
    print("=" * 52)
    print("   Gotowe! Uruchom Floating Island z Pulpitu.")
    print("=" * 52)
    print()


if __name__ == "__main__":
    main()
