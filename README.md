# Floating Island

Windows desktop island written in Python and PyQt6.

## Install

Run `FloatingIsland_Setup.exe` from the latest successful **Build Windows installer** workflow run. The installer puts the app in the current user's LocalAppData folder so GitHub source updates can replace its files without administrator rights. Python with PyQt6 must be installed on the computer.

## Automatic updates

The app checks `szymonpokrywka42-spec/Floating-Island` on branch `main` eight seconds after startup and every 15 minutes. When a newer commit is available, it downloads the source archive, safely extracts project files, records the commit SHA and restarts the app. Updates require an internet connection.

Every push to `main` runs the Windows installer workflow. The generated setup executable is available as a workflow artifact for 30 days.
