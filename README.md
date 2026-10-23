# kicad-sch-viewer

A viewer for KiCad schematics of every version, with their hierarchical
sheets:

- KiCad 4/5: legacy `.sch` ("EESchema Schematic File Version 2..4"), the
  symbols from the legacy libraries (`.lib`);
- KiCad 6, 7, 8, 9 and later: `.kicad_sch` (S-expressions), the symbols
  embedded in the file, the project's text variables from the `.kicad_pro`.

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
./kicad_sch_viewer.py board.kicad_sch [--theme light|dark|system]
./kicad_sch_viewer.py board.sch [-L extra.lib ...]          # KiCad 4/5
./kicad_sch_viewer.py board.sch --export out.png              # sheet 1
./kicad_sch_viewer.py board.sch --export out.pdf --sheet 3
./kicad_sch_viewer.py board.sch --export out.png --sheet 0    # all: out-1.png, out-2.png, ...
```

KiCad 4/5: the symbol libraries are found by themselves: the project's
`*-cache.lib`, `*-rescue.lib` and the `LibName` entries of the `.pro` file;
`-L` adds others. KiCad 6+ files need nothing else: the symbols are in the
file.

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

## What is drawn

Symbols (units, body styles, rotation, mirror, pins with their shapes,
names and numbers, "do not populate" cross), fields with KiCad's placement,
wires, buses, bus entries, junctions, no-connects, local / global /
hierarchical labels, texts with their colours, text boxes, graphic lines,
rectangles, circles, arcs and Bézier curves, sheet fill colours, embedded
images (KiCad 6+), the title block. KiCad 6+ text markup: `~{...}` overbar,
`_{...}` / `^{...}`, `${VAR}` from the title block, the `.kicad_pro` text
variables and the symbol's own fields.

Tested on KiCad 5 files (format 4) and KiCad 9 files (format 20250114); the
KiCad 6, 7 and 8 differences (sheet properties, `symbol_instances`, bare
`hide` flags, `convert` / `body_style`) are handled from the format
description, and unknown items of newer formats are skipped.

## Known approximations

The texts use DejaVu Sans instead of KiCad's stroke font or the TrueType
fonts chosen in KiCad 7+; global label outlines are simplified; the title
block is a fixed layout (custom `.kicad_wks` drawing sheets are not read);
KiCad 4/5 Bézier curves are drawn as their control polygon and embedded
bitmaps (`$Bitmap`) are skipped; KiCad 8+ tables, rule areas and net class
flags are skipped.

## Licences

The program is free software under the GNU General Public License version 3
or later (`LICENSE`). The fonts keep their own licences: DejaVu (Bitstream Vera licence,
`fonts/LICENSE-DejaVu.txt`), Noto Sans (SIL Open Font License 1.1,
`fonts/LICENSE-Noto.txt`).
