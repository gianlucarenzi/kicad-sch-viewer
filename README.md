# kicad-sch-viewer

A viewer for KiCad 4/5 schematics (legacy `.sch`, "EESchema Schematic File
Version 2..4") with the hierarchical sheets and the symbols of the legacy
libraries (`.lib`). KiCad 6+ `.kicad_sch` files are not supported.

## Contents

| Path | What |
|---|---|
| `kicad_sch_viewer.py` | the program (one file) |
| `fonts/` | DejaVu Sans (the schematic texts) and Noto Sans (the window), with their licences |
| `kicad_sch_viewer.ini` | the settings (the theme), written next to the program on the first change |

Everything the viewer uses is in this directory; the only thing that comes
from the system is PyQt5 (Python 3, Qt 5).

### Installing PyQt5 on Debian / Ubuntu

```sh
sudo apt update
sudo apt install python3 python3-pyqt5 python3-pyqt5.qtsvg \
                 libqt5printsupport5 libqt5gui5 libqt5svg5
```

| Package | Gives the viewer |
|---|---|
| `python3-pyqt5` | QtCore, QtGui, QtWidgets and QtPrintSupport (window, drawing, print dialog, print preview, PDF export) |
| `libqt5printsupport5` | Qt's print support with the CUPS plugin (`qt5/plugins/printsupport/libcupsprintersupport.so`): the system printers in the print dialog |
| `libqt5gui5` | the platform plugins: `xcb` (the window on X11 / XWayland) and `offscreen` (`--export` without a display) |
| `python3-pyqt5.qtsvg`, `libqt5svg5` | QtSvg: the SVG export (optional; PNG and PDF work without it) |

`libqt5printsupport5` and `libqt5gui5` come with `python3-pyqt5` anyway;
they are named so that nothing is left out. The printers themselves come
from CUPS, which a desktop install already has; on a minimal system:

```sh
sudo apt install cups cups-client          # the print system and its tools (lpstat, lp)
```

Optional:

```sh
sudo apt install qtwayland5                # native Wayland window (otherwise XWayland)
sudo apt install qt5-gtk-platformtheme     # GTK file dialogs with the "System" theme
```

Check the installation:

```sh
python3 -c "from PyQt5 import QtWidgets, QtPrintSupport; print('PyQt5 ok')"
python3 -c "from PyQt5 import QtSvg; print('SVG export ok')"
lpstat -p                                  # the printers the print dialog will list
```

Tested on Debian 11 (bullseye) with the distribution packages (PyQt5 5.15,
Qt 5.15).

## Use

```sh
./kicad_sch_viewer.py board.sch [-L extra.lib ...] [--theme light|dark|system]
./kicad_sch_viewer.py board.sch --export out.png              # sheet 1
./kicad_sch_viewer.py board.sch --export out.pdf --sheet 3
./kicad_sch_viewer.py board.sch --export out.png --sheet 0    # all: out-1.png, out-2.png, ...
```

The symbol libraries are found by themselves: the project's `*-cache.lib`,
`*-rescue.lib` and the `LibName` entries of the `.pro` file; `-L` adds
others.

- Mouse: wheel = zoom, drag = pan, click = a symbol's fields in the panel,
  double-click on a sheet = open it.
- Keys: `Home`/`F` fit, `Backspace`/`Alt+Left` parent sheet, `Ctrl+F` find
  (reference, value, label; all sheets), `F3` next, `Ctrl+E` export,
  `Ctrl+P` print, `Ctrl+Shift+P` print preview, `Ctrl+O` open.
- Print: one sheet per paper page, scaled to fit. The pages of the dialog are
  the sheets in the order of the hierarchy tree (1 = root): all, the current
  sheet, a range, or "Selection" = the sheets selected in the tree
  (Ctrl/Shift+click).
- Theme menu: Material light, Material dark (a style sheet over Qt's Fusion
  style, no extra packages) or the system look.

## Known approximations

The texts use DejaVu Sans instead of KiCad's stroke font; global label
outlines are simplified; Bézier curves are drawn as their control polygon;
embedded bitmaps (`$Bitmap`) are skipped.

## Licences

The fonts keep their own licences: DejaVu (Bitstream Vera licence,
`fonts/LICENSE-DejaVu.txt`), Noto Sans (SIL Open Font License 1.1,
`fonts/LICENSE-Noto.txt`).
