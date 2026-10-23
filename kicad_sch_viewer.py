#!/usr/bin/env python3
"""kicad_sch_viewer.py - a viewer for KiCad 4/5 schematics (legacy .sch).

Opens an "EESchema Schematic File Version 2..4" file, follows its
hierarchical sheets and draws the symbols from the legacy libraries
("EESchema-LIBRARY Version 2.x"): the project's *-cache.lib, the
*-rescue.lib and the libraries listed in the .pro file are found by
themselves, others are added with -L.

  kicad_sch_viewer.py board.sch [-L extra.lib ...]
  kicad_sch_viewer.py board.sch --export out.png|out.pdf|out.svg [--sheet N]

Mouse: wheel = zoom, drag (left or middle) = pan, click = select a symbol
(its fields in the panel), double-click a sheet = open it.
Keys: Home/F = fit, Backspace/Alt+Left = parent sheet, Ctrl+F = find,
Ctrl+E = export, Ctrl+P = print, Ctrl+O = open, Ctrl+Q = quit.

Printing: one sheet per paper page, scaled to fit; the pages of the print
dialog are the sheets in the order of the hierarchy tree (1 = root).  All,
the current sheet, a range, or "Selection" = the sheets selected in the tree
(Ctrl/Shift+click).

Units: the scene is in mils, like the files.
"""

import argparse
import math
import os
import re
import shlex
import sys

from PyQt5.QtCore import Qt, QPointF, QRectF, QSettings, QSizeF, QMarginsF
from PyQt5.QtGui import (QBrush, QColor, QFont, QFontDatabase, QFontMetricsF,
                         QImage, QPalette,
                         QPainter, QPainterPath, QPen, QPolygonF, QTransform,
                         QKeySequence, QPdfWriter, QPageSize)
from PyQt5.QtWidgets import (QAbstractItemView, QAction, QApplication,
                             QDockWidget, QFileDialog,
                             QGraphicsItem, QGraphicsItemGroup,
                             QGraphicsPathItem, QGraphicsRectItem,
                             QGraphicsScene, QGraphicsSimpleTextItem,
                             QGraphicsView, QInputDialog, QLabel, QMainWindow,
                             QMessageBox, QTreeWidget, QTreeWidgetItem,
                             QTableWidget, QTableWidgetItem, QHeaderView,
                             QActionGroup, QStyleFactory, QToolBar)

from PyQt5.QtPrintSupport import (QAbstractPrintDialog, QPrintDialog,
                                  QPrinter, QPrintPreviewDialog)

try:
    from PyQt5.QtSvg import QSvgGenerator
except ImportError:                     # python3-pyqt5.qtsvg not installed
    QSvgGenerator = None

# KiCad 5 default colours (eeschema, light background)
COL = {
    'background': '#FFFFFF', 'wire': '#008400', 'bus': '#000084',
    'junction': '#008400', 'body': '#840000', 'body_fill': '#FFFFC2',
    'pin': '#840000', 'pin_name': '#008484', 'pin_num': '#840000',
    'ref': '#008484', 'value': '#008484', 'field': '#840084',
    'label': '#000000', 'glabel': '#840000', 'hlabel': '#848400',
    'notes': '#0000C2', 'noconnect': '#0000C2', 'sheet': '#840084',
    'sheet_name': '#008484', 'sheet_file': '#840000',
    'sheet_label': '#848400', 'frame': '#840000', 'missing': '#FF0000',
    'select': '#FF8000',
}

FONT_FAMILY = 'DejaVu Sans'           # the schematic texts
CANVAS = '#E8E8E8'                     # the scene around the page (set by the theme)

# Everything the viewer uses lives next to this file: the fonts (fonts/,
# DejaVu Sans for the drawings, Noto Sans for the window; their licences
# are there too) and the settings (kicad_sch_viewer.ini).  Only PyQt5 comes
# from the system.
HERE = os.path.dirname(os.path.abspath(__file__))
FONT_DIR = os.path.join(HERE, 'fonts')
SETTINGS_FILE = os.path.join(HERE, 'kicad_sch_viewer.ini')


def load_fonts():
    """Register the fonts of fonts/ with Qt (before any text is drawn)."""
    if not os.path.isdir(FONT_DIR):
        return
    for f in sorted(os.listdir(FONT_DIR)):
        if f.lower().endswith(('.ttf', '.otf')):
            QFontDatabase.addApplicationFont(os.path.join(FONT_DIR, f))


def settings():
    return QSettings(SETTINGS_FILE, QSettings.IniFormat)


# =========================================================================
# Material theme (a style sheet over Fusion; no extra packages)
# =========================================================================

THEMES = {
    'light': dict(bg='#FAFAFA', surface='#FFFFFF', bar='#1E88E5', bar_text='#FFFFFF',
                  text='#212121', text2='#616161', line='#E0E0E0', hover='#EEEEEE',
                  accent='#1E88E5', accent_soft='#BBDEFB', canvas='#ECEFF1',
                  scroll='#BDBDBD', tip='#616161', tip_text='#FFFFFF'),
    'dark': dict(bg='#121212', surface='#1E1E1E', bar='#1F1F1F', bar_text='#E0E0E0',
                 text='#E0E0E0', text2='#9E9E9E', line='#333333', hover='#2C2C2C',
                 accent='#64B5F6', accent_soft='#1E3A5F', canvas='#263238',
                 scroll='#555555', tip='#424242', tip_text='#FFFFFF'),
}

MATERIAL_QSS = """
* {{ font-family: "Noto Sans", "DejaVu Sans"; font-size: 10pt; }}
QMainWindow, QDialog, QWidget {{ background: {bg}; color: {text}; }}
QMenuBar {{ background: {bar}; color: {bar_text}; padding: 2px 4px; border: none; }}
QMenuBar::item {{ background: transparent; padding: 6px 12px; border-radius: 4px; }}
QMenuBar::item:selected {{ background: rgba(255,255,255,0.18); }}
QMenu {{ background: {surface}; color: {text}; border: 1px solid {line};
         border-radius: 6px; padding: 6px 0; }}
QMenu::item {{ padding: 7px 28px 7px 20px; }}
QMenu::item:selected {{ background: {hover}; color: {accent}; }}
QMenu::separator {{ height: 1px; background: {line}; margin: 6px 0; }}
QToolBar {{ background: {bar}; border: none; padding: 2px 6px; spacing: 2px; }}
QToolBar QToolButton {{ background: transparent; color: {bar_text}; border: none;
         border-radius: 4px; padding: 6px 12px; font-weight: 600; }}
QToolBar QToolButton:hover {{ background: rgba(255,255,255,0.18); }}
QToolBar QToolButton:pressed {{ background: rgba(255,255,255,0.30); }}
QToolBar::separator {{ background: rgba(255,255,255,0.35); width: 1px; margin: 6px 6px; }}
QDockWidget {{ color: {text2}; font-weight: 600; }}
QDockWidget::title {{ background: {bg}; padding: 8px 10px; text-align: left;
         border-bottom: 1px solid {line}; }}
QTreeWidget, QTableWidget, QListView, QTreeView {{ background: {surface}; color: {text};
         border: none; outline: 0; alternate-background-color: {bg};
         selection-background-color: {accent_soft}; selection-color: {text}; }}
QTreeWidget::item, QTreeView::item {{ padding: 5px 2px; border: none; }}
QTreeWidget::item:hover, QTreeView::item:hover {{ background: {hover}; }}
QTreeWidget::item:selected, QTreeView::item:selected,
QTableWidget::item:selected {{ background: {accent_soft}; color: {text}; }}
QHeaderView::section {{ background: {surface}; color: {text2}; border: none;
         border-bottom: 2px solid {line}; padding: 6px 8px; font-weight: 600; }}
QTableWidget {{ gridline-color: {line}; }}
QGraphicsView {{ border: none; background: {canvas}; }}
QStatusBar {{ background: {surface}; color: {text2}; border-top: 1px solid {line}; }}
QStatusBar QLabel {{ color: {text2}; padding: 0 8px; }}
QToolTip {{ background: {tip}; color: {tip_text}; border: none; border-radius: 4px;
         padding: 6px 8px; }}
QPushButton {{ background: {accent}; color: #FFFFFF; border: none; border-radius: 4px;
         padding: 7px 18px; font-weight: 600; min-width: 64px; }}
QPushButton:hover {{ background: {accent}; border: 2px solid {accent_soft}; padding: 5px 16px; }}
QPushButton:disabled {{ background: {line}; color: {text2}; }}
QPushButton:flat {{ background: transparent; color: {accent}; }}
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QPlainTextEdit, QTextEdit {{
         background: {surface}; color: {text}; border: none;
         border-bottom: 2px solid {line}; border-radius: 0; padding: 5px 6px;
         selection-background-color: {accent_soft}; selection-color: {text}; }}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
         border-bottom: 2px solid {accent}; }}
QComboBox QAbstractItemView {{ background: {surface}; color: {text}; border: 1px solid {line};
         selection-background-color: {hover}; selection-color: {accent}; }}
QComboBox::drop-down {{ border: none; width: 20px; }}
QGroupBox {{ border: 1px solid {line}; border-radius: 6px; margin-top: 14px; padding-top: 8px; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 4px; color: {accent};
         font-weight: 600; }}
QCheckBox, QRadioButton {{ spacing: 8px; color: {text}; }}
QTabBar::tab {{ background: transparent; color: {text2}; padding: 8px 16px; border: none;
         border-bottom: 2px solid transparent; }}
QTabBar::tab:selected {{ color: {accent}; border-bottom: 2px solid {accent}; }}
QTabWidget::pane {{ border: none; border-top: 1px solid {line}; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 0; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 0; }}
QScrollBar::handle {{ background: {scroll}; border-radius: 5px; min-height: 30px; min-width: 30px; }}
QScrollBar::handle:hover {{ background: {text2}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QSplitter::handle, QMainWindow::separator {{ background: {line}; width: 1px; height: 1px; }}
"""

_DEFAULT_STYLE = None


def apply_theme(app, name):
    """'light' / 'dark' = Material, 'system' = the platform look."""
    global CANVAS, _DEFAULT_STYLE
    if _DEFAULT_STYLE is None:
        _DEFAULT_STYLE = app.style().objectName()
    if name not in THEMES:
        app.setStyleSheet('')
        app.setStyle(QStyleFactory.create(_DEFAULT_STYLE))
        app.setPalette(app.style().standardPalette())
        CANVAS = '#E8E8E8'
        return
    t = THEMES[name]
    app.setStyle(QStyleFactory.create('Fusion'))
    pal = QPalette()
    for role, key in ((QPalette.Window, 'bg'), (QPalette.WindowText, 'text'),
                      (QPalette.Base, 'surface'), (QPalette.AlternateBase, 'bg'),
                      (QPalette.Text, 'text'), (QPalette.Button, 'surface'),
                      (QPalette.ButtonText, 'text'), (QPalette.Highlight, 'accent'),
                      (QPalette.ToolTipBase, 'tip'), (QPalette.ToolTipText, 'tip_text'),
                      (QPalette.Link, 'accent')):
        pal.setColor(role, QColor(t[key]))
    pal.setColor(QPalette.HighlightedText, QColor('#FFFFFF'))
    pal.setColor(QPalette.Disabled, QPalette.Text, QColor(t['text2']))
    pal.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(t['text2']))
    app.setPalette(pal)
    app.setStyleSheet(MATERIAL_QSS.format(**t))
    CANVAS = t['canvas']
FONT_SCALE = 1.35          # KiCad text size (cap height, mils) -> pixel size


# =========================================================================
# Legacy library (.lib)
# =========================================================================

def lib_split(line):
    """Split a .lib/.sch line, keeping "quoted strings" together."""
    try:
        return shlex.split(line, posix=True)
    except ValueError:                  # an unbalanced quote: plain split
        return line.split()


class LibSymbol:
    def __init__(self, name):
        self.name = name
        self.ref = 'U'
        self.text_offset = 40
        self.show_pin_num = True
        self.show_pin_name = True
        self.unit_count = 1
        self.power = False
        self.draw = []                  # (kind, unit, convert, data)
        self.fields = {}                # n -> (text, x, y, size, orient, visible, hj, vj)


def load_library(path, symbols):
    """Read a legacy library into the dict name -> LibSymbol (first wins)."""
    try:
        f = open(path, encoding='utf-8', errors='replace')
    except OSError:
        return 0
    n = 0
    cur = None
    in_draw = False
    with f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith('#'):
                continue
            if line.startswith('DEF '):
                t = line.split()
                name = t[1].lstrip('~')
                cur = LibSymbol(name)
                cur.ref = t[2]
                cur.text_offset = int(t[4])
                cur.show_pin_num = t[5] == 'Y'
                cur.show_pin_name = t[6] == 'Y'
                cur.unit_count = int(t[7])
                cur.power = len(t) > 9 and t[9] == 'P'
                in_draw = False
                continue
            if cur is None:
                continue
            if line.startswith('ENDDEF'):
                symbols.setdefault(cur.name, cur)
                n += 1
                cur = None
                continue
            if line.startswith('ALIAS'):
                for a in line.split()[1:]:
                    symbols.setdefault(a, cur)
                continue
            if line == 'DRAW':
                in_draw = True
                continue
            if line == 'ENDDRAW':
                in_draw = False
                continue
            if not in_draw:
                m = re.match(r'F(\d+)\s', line)
                if m:
                    t = lib_split(line)
                    try:
                        cur.fields[int(m.group(1))] = (
                            t[1], int(t[2]), int(t[3]), int(t[4]), t[5],
                            t[6] == 'V', t[7], t[8][0])
                    except (IndexError, ValueError):
                        pass
                continue
            try:
                parse_draw(cur, line)
            except (IndexError, ValueError):
                pass                    # an item we do not understand
    return n


def parse_draw(sym, line):
    t = lib_split(line)
    k = t[0]
    if k == 'A':                        # arc: x y r a1 a2 unit conv thick fill sx sy ex ey
        x, y, r = int(t[1]), int(t[2]), int(t[3])
        unit, conv, thick = int(t[6]), int(t[7]), int(t[8])
        fill = t[9] if len(t) > 9 else 'N'
        if len(t) > 13:
            s = (int(t[10]), int(t[11]))
            e = (int(t[12]), int(t[13]))
        else:
            a1, a2 = int(t[4]) / 10.0, int(t[5]) / 10.0
            s = (x + r * math.cos(math.radians(a1)), y + r * math.sin(math.radians(a1)))
            e = (x + r * math.cos(math.radians(a2)), y + r * math.sin(math.radians(a2)))
        sym.draw.append(('A', unit, conv, (x, y, r, s, e, thick, fill)))
    elif k == 'C':                      # circle: x y r unit conv thick fill
        sym.draw.append(('C', int(t[4]), int(t[5]),
                         (int(t[1]), int(t[2]), int(t[3]), int(t[6]),
                          t[7] if len(t) > 7 else 'N')))
    elif k == 'P':                      # polyline: n unit conv thick x y ... fill
        cnt = int(t[1])
        pts = [(int(t[5 + 2 * i]), int(t[6 + 2 * i])) for i in range(cnt)]
        fill = t[5 + 2 * cnt] if len(t) > 5 + 2 * cnt else 'N'
        sym.draw.append(('P', int(t[2]), int(t[3]), (pts, int(t[4]), fill)))
    elif k == 'B':                      # bezier: drawn as its control polygon
        cnt = int(t[1])
        pts = [(int(t[5 + 2 * i]), int(t[6 + 2 * i])) for i in range(cnt)]
        sym.draw.append(('P', int(t[2]), int(t[3]), (pts, int(t[4]), 'N')))
    elif k == 'S':                      # rectangle: x1 y1 x2 y2 unit conv thick fill
        sym.draw.append(('S', int(t[5]), int(t[6]),
                         (int(t[1]), int(t[2]), int(t[3]), int(t[4]), int(t[7]),
                          t[8] if len(t) > 8 else 'N')))
    elif k == 'T':                      # text: angle x y size hidden unit conv text italic bold hj vj
        text = t[8].replace('~', ' ')
        hj = t[11] if len(t) > 11 else 'C'
        vj = t[12] if len(t) > 12 else 'C'
        sym.draw.append(('T', int(t[6]), int(t[7]),
                         (int(t[1]), int(t[2]), int(t[3]), int(t[4]),
                          t[5] != '0', text, hj, vj)))
    elif k == 'X':                      # pin: name num x y len orient snum sname unit conv type [shape]
        shape = t[12] if len(t) > 12 else ''
        sym.draw.append(('X', int(t[9]), int(t[10]),
                         (t[1], t[2], int(t[3]), int(t[4]), int(t[5]), t[6],
                          int(t[7]), int(t[8]), t[11], shape)))


# =========================================================================
# Schematic (.sch)
# =========================================================================

class Field:
    def __init__(self, n, text, orient, x, y, size, visible, hj, vj, name=''):
        self.n, self.text, self.orient = n, text, orient
        self.x, self.y, self.size = x, y, size
        self.visible, self.hj, self.vj = visible, hj, vj
        self.name = name


class Component:
    def __init__(self):
        self.lib = ''
        self.ref = ''
        self.unit = 1
        self.convert = 1
        self.stamp = ''
        self.x = self.y = 0
        self.m = (1, 0, 0, -1)
        self.fields = []
        self.ar = {}                    # sheet path -> (ref, unit)


class Sheet:
    def __init__(self):
        self.x = self.y = self.w = self.h = 0
        self.stamp = ''
        self.name = ''
        self.file = ''
        self.name_size = 50
        self.file_size = 50
        self.pins = []                  # (name, shape, side, x, y, size)


class Schematic:
    def __init__(self, path):
        self.path = path
        self.version = 0
        self.page = (11693, 8268)
        self.page_name = 'A4'
        self.title = {}
        self.components = []
        self.wires = []                 # (kind, x1, y1, x2, y2) kind wire/bus/notes/entry
        self.junctions = []
        self.noconns = []
        self.texts = []                 # (kind, x, y, orient, size, shape, italic, text)
        self.sheets = []
        self.load(path)

    def load(self, path):
        with open(path, encoding='utf-8', errors='replace') as f:
            lines = f.read().splitlines()
        if not lines or not lines[0].startswith('EESchema Schematic File Version'):
            raise ValueError(f'{path}: not a KiCad 4/5 schematic '
                             '(KiCad 6+ .kicad_sch files are not supported)')
        self.version = int(lines[0].split()[-1])
        i = 1
        n = len(lines)
        while i < n:
            line = lines[i]
            s = line.strip()
            i += 1
            if s.startswith('$Descr'):
                t = s.split()
                self.page_name = t[1]
                if len(t) >= 4:
                    self.page = (int(t[2]), int(t[3]))
                while i < n and not lines[i].strip().startswith('$EndDescr'):
                    tt = lib_split(lines[i])
                    if len(tt) >= 2 and tt[0] in ('Title', 'Date', 'Rev', 'Comp',
                                                  'Comment1', 'Comment2',
                                                  'Comment3', 'Comment4'):
                        self.title[tt[0]] = tt[1]
                    i += 1
                i += 1
            elif s.startswith('$Comp'):
                i = self.read_comp(lines, i)
            elif s.startswith('$Sheet'):
                i = self.read_sheet(lines, i)
            elif s.startswith('$Bitmap'):
                while i < n and not lines[i].strip().startswith('$EndBitmap'):
                    i += 1
                i += 1
            elif s.startswith('Wire ') or s.startswith('Entry '):
                t = s.split()
                kind = {'Wire': 'wire', 'Bus': 'bus', 'Notes': 'notes'}.get(t[1], 'wire')
                if t[0] == 'Entry':
                    kind = 'bus' if t[1] == 'Bus' else 'wire'
                if i < n:
                    c = lines[i].split()
                    i += 1
                    if len(c) >= 4:
                        self.wires.append((kind, int(c[0]), int(c[1]),
                                           int(c[2]), int(c[3])))
            elif s.startswith('Connection '):
                t = s.split()
                self.junctions.append((int(t[2]), int(t[3])))
            elif s.startswith('NoConn '):
                t = s.split()
                self.noconns.append((int(t[2]), int(t[3])))
            elif s.startswith('Text '):
                t = s.split()
                kind = t[1]
                x, y, orient, size = int(t[2]), int(t[3]), int(t[4]), int(t[5])
                shape = t[6] if len(t) > 6 else '~'
                italic = 'Italic' in t[6:]
                text = lines[i] if i < n else ''
                i += 1
                text = text.replace('\\n', '\n')
                self.texts.append((kind, x, y, orient, size, shape, italic, text))

    def read_comp(self, lines, i):
        c = Component()
        pos_seen = False
        while i < len(lines):
            s = lines[i].strip()
            i += 1
            if s.startswith('$EndComp'):
                break
            t = lib_split(s)
            if not t:
                continue
            if t[0] == 'L':
                c.lib = t[1]
                c.ref = t[2] if len(t) > 2 else ''
            elif t[0] == 'U':
                c.unit, c.convert, c.stamp = int(t[1]), int(t[2]), t[3]
            elif t[0] == 'P':
                c.x, c.y = int(t[1]), int(t[2])
            elif t[0] == 'AR':
                d = dict(a.split('=', 1) for a in t[1:] if '=' in a)
                if 'Path' in d:
                    c.ar[d['Path']] = (d.get('Ref', c.ref), int(d.get('Part', c.unit) or c.unit))
            elif t[0] == 'F':
                try:
                    vj = t[9] if len(t) > 9 else 'CNN'
                    c.fields.append(Field(int(t[1]), t[2], t[3], int(t[4]), int(t[5]),
                                          int(t[6]), not t[7].endswith('1'),
                                          t[8] if len(t) > 8 else 'C', vj[0],
                                          t[10] if len(t) > 10 else ''))
                except (IndexError, ValueError):
                    pass
            elif re.match(r'^-?\d+$', t[0]):
                if not pos_seen:        # "unit x y"
                    pos_seen = True
                elif len(t) >= 4:       # the orientation matrix
                    c.m = tuple(int(v) for v in t[:4])
        self.components.append(c)
        return i

    def read_sheet(self, lines, i):
        sh = Sheet()
        while i < len(lines):
            s = lines[i].strip()
            i += 1
            if s.startswith('$EndSheet'):
                break
            t = lib_split(s)
            if not t:
                continue
            if t[0] == 'S':
                sh.x, sh.y, sh.w, sh.h = (int(v) for v in t[1:5])
            elif t[0] == 'U':
                sh.stamp = t[1]
            elif t[0] == 'F0':
                sh.name, sh.name_size = t[1], int(t[2])
            elif t[0] == 'F1':
                sh.file, sh.file_size = t[1], int(t[2])
            elif re.match(r'^F\d+$', t[0]):
                try:                    # Fn "name" shape side x y size
                    sh.pins.append((t[1], t[2], t[3], int(t[4]), int(t[5]), int(t[6])))
                except (IndexError, ValueError):
                    pass
        self.sheets.append(sh)
        return i


# =========================================================================
# Drawing
# =========================================================================

class Painter:
    """Puts the items of one schematic sheet into a QGraphicsScene."""

    def __init__(self, scene, libs, path_stamps):
        self.scene = scene
        self.libs = libs
        self.path = path_stamps         # "/stamp1/stamp2" of this sheet instance
        self.fonts = {}

    # -- primitives -------------------------------------------------------
    def pen(self, colour, width=6, style=Qt.SolidLine):
        p = QPen(QColor(COL[colour]), max(width, 4))
        p.setCapStyle(Qt.RoundCap)
        p.setJoinStyle(Qt.RoundJoin)
        p.setStyle(style)
        p.setCosmetic(False)
        return p

    def font(self, size, italic=False, bold=False):
        key = (size, italic, bold)
        f = self.fonts.get(key)
        if f is None:
            f = QFont(FONT_FAMILY)
            f.setPixelSize(max(1, int(round(size * FONT_SCALE))))
            f.setItalic(italic)
            f.setBold(bold)
            self.fonts[key] = f
        return f

    def path_item(self, path, colour, width=6, fill=None, style=Qt.SolidLine, parent=None):
        it = QGraphicsPathItem(path, parent)
        it.setPen(self.pen(colour, width, style))
        if fill:
            it.setBrush(QBrush(QColor(COL[fill])))
        if parent is None:
            self.scene.addItem(it)
        return it

    def text(self, x, y, s, size, colour, vertical=False, hj='C', vj='C',
             italic=False, bold=False, parent=None):
        """Text anchored at (x, y): hj L/C/R along the text, vj T/C/B across
        it; vertical text reads bottom to top (KiCad 90 degrees)."""
        if not s:
            return None
        it = QGraphicsSimpleTextItem(s, parent)
        it.setFont(self.font(size, italic, bold))
        it.setBrush(QBrush(QColor(COL[colour])))
        br = it.boundingRect()
        # the box of the glyphs: use the cap height band around the text
        fm = QFontMetricsF(it.font())
        lines = s.count('\n') + 1
        h_text = fm.height() * lines
        w = br.width()
        dx = {'L': 0, 'C': -w / 2, 'R': -w}.get(hj, -w / 2)
        dy = {'T': 0, 'C': -h_text / 2, 'B': -h_text}.get(vj, -h_text / 2)
        tr = QTransform()
        tr.translate(x, y)
        if vertical:
            tr.rotate(-90)
        tr.translate(dx, dy)
        it.setTransform(tr)
        if parent is None:
            self.scene.addItem(it)
        return it

    # -- the sheet --------------------------------------------------------
    def draw(self, sch, sheet_label=''):
        self.draw_frame(sch, sheet_label)
        for kind, x1, y1, x2, y2 in sch.wires:
            p = QPainterPath(QPointF(x1, y1))
            p.lineTo(x2, y2)
            if kind == 'bus':
                self.path_item(p, 'bus', 12)
            elif kind == 'notes':
                self.path_item(p, 'notes', 6, style=Qt.DashLine)
            else:
                self.path_item(p, 'wire', 6)
        for x, y in sch.junctions:
            p = QPainterPath()
            p.addEllipse(QPointF(x, y), 18, 18)
            self.path_item(p, 'junction', 1, fill='junction')
        for x, y in sch.noconns:
            p = QPainterPath(QPointF(x - 25, y - 25))
            p.lineTo(x + 25, y + 25)
            p.moveTo(x - 25, y + 25)
            p.lineTo(x + 25, y - 25)
            self.path_item(p, 'noconnect', 6)
        for t in sch.texts:
            self.draw_text_item(*t)
        for sh in sch.sheets:
            self.draw_sheet(sh)
        for c in sch.components:
            self.draw_component(c)

    def draw_frame(self, sch, sheet_label):
        w, h = sch.page
        r = QGraphicsRectItem(0, 0, w, h)
        r.setPen(QPen(Qt.NoPen))
        r.setBrush(QBrush(QColor(COL['background'])))
        r.setZValue(-10)
        self.scene.addItem(r)
        m = 400                         # KiCad 5 page margins: 10 mm
        p = QPainterPath()
        p.addRect(QRectF(m, m, w - 2 * m, h - 2 * m))
        p.addRect(QRectF(m + 80, m + 80, w - 2 * m - 160, h - 2 * m - 160))
        self.path_item(p, 'frame', 6)
        # the title block, bottom right
        bw, bh = 4400, 1000
        bx, by = w - m - 80 - bw, h - m - 80 - bh
        p = QPainterPath()
        p.addRect(QRectF(bx, by, bw, bh))
        for yy in (by + 250, by + 500, by + 750):
            p.moveTo(bx, yy)
            p.lineTo(bx + bw, yy)
        self.path_item(p, 'frame', 6)
        t = sch.title
        self.text(bx + 60, by + 125, t.get('Comp', ''), 60, 'frame', hj='L')
        self.text(bx + 60, by + 375, 'Title: ' + t.get('Title', ''), 70, 'frame', hj='L', bold=True)
        self.text(bx + 60, by + 625, f"Sheet: {sheet_label}   File: {os.path.basename(sch.path)}",
                  50, 'frame', hj='L')
        self.text(bx + 60, by + 875, f"Size: {sch.page_name}   Date: {t.get('Date', '')}   "
                  f"Rev: {t.get('Rev', '')}", 50, 'frame', hj='L')
        comments = [t.get(f'Comment{k}', '') for k in range(1, 5)]
        comments = '   '.join(c for c in comments if c)
        if comments:
            self.text(bx + 60, by - 60, comments, 50, 'frame', hj='L', vj='B')

    # -- texts and labels ---------------------------------------------------
    def draw_text_item(self, kind, x, y, orient, size, shape, italic, text):
        vertical = orient in (1, 3)
        if kind in ('Label', 'Notes'):
            # spin 0: right of the anchor, 1: up, 2: left, 3: down; the text
            # sits above the anchor line
            hj = 'L' if orient in (0, 1) else 'R'
            colour = 'label' if kind == 'Label' else 'notes'
            off = 0 if kind == 'Notes' else 10
            if vertical:
                self.text(x - off, y, text, size, colour, True, hj, 'B', italic)
            else:
                self.text(x, y - off, text, size, colour, False, hj, 'B', italic)
            return
        # global / hierarchical labels: spin 0 points left (text on the
        # left of the anchor), 1 up, 2 right, 3 down
        colour = 'glabel' if kind == 'GLabel' else 'hlabel'
        d = {0: (-1, 0), 1: (0, -1), 2: (1, 0), 3: (0, 1)}.get(orient, (-1, 0))
        f = self.font(size, italic)
        tw = QFontMetricsF(f).horizontalAdvance(text) if hasattr(
            QFontMetricsF, 'horizontalAdvance') else QFontMetricsF(f).width(text)
        hh = size * 0.75                # half height of the outline
        if kind == 'GLabel':
            tip = hh                    # the arrow length at the anchor
            body = tw + size * 0.8
            path = self.label_outline(x, y, d, hh, tip, body, shape)
            self.path_item(path, colour, 6)
            gap = tip + size * 0.4
        else:
            # the hierarchical shape: a small flag at the anchor
            path = self.hlabel_flag(x, y, d, size, shape)
            self.path_item(path, colour, 6)
            gap = size + size * 0.4
        tx, ty = x + d[0] * gap, y + d[1] * gap
        hj = 'L' if d[0] > 0 or d[1] < 0 else 'R'
        self.text(tx, ty, text, size, colour, vertical, hj, 'C', italic)

    @staticmethod
    def _poly(pts, close=True):
        p = QPainterPath(QPointF(*pts[0]))
        for q in pts[1:]:
            p.lineTo(*q)
        if close:
            p.closeSubpath()
        return p

    def label_outline(self, x, y, d, hh, tip, body, shape):
        """A global label outline from the anchor along d: shapes Input
        (pointed at the anchor side... as KiCad: the arrow into the sheet),
        Output, BiDi, 3State, UnSpc."""
        # local frame: u along d, v across
        def P(u, v):
            return (x + d[0] * u - d[1] * v, y + d[1] * u + d[0] * v)
        near_tip = shape in ('Input', 'BiDi', '3State')
        far_tip = shape in ('Output', 'BiDi', '3State')
        end = tip + body
        pts = []
        pts.append(P(0, 0) if near_tip else P(0, -hh))
        if not near_tip:
            pts = [P(0, -hh)]
        pts.append(P(tip if near_tip else 0, -hh))
        if far_tip:
            pts += [P(end, -hh), P(end + tip, 0), P(end, hh)]
        else:
            pts += [P(end + tip, -hh), P(end + tip, hh)]
        pts.append(P(tip if near_tip else 0, hh))
        if not near_tip:
            pts.append(P(0, hh))
        return self._poly(pts)

    def hlabel_flag(self, x, y, d, size, shape):
        def P(u, v):
            return (x + d[0] * u - d[1] * v, y + d[1] * u + d[0] * v)
        s = size
        h = s / 2
        if shape == 'Input':
            pts = [P(0, -h), P(h, -h), P(s, 0), P(h, h), P(0, h)]
        elif shape == 'Output':
            pts = [P(0, 0), P(h, -h), P(s, -h), P(s, h), P(h, h)]
        elif shape in ('BiDi', '3State'):
            pts = [P(0, 0), P(h, -h), P(s, 0), P(h, h)]
        else:
            pts = [P(0, -h), P(s, -h), P(s, h), P(0, h)]
        return self._poly(pts)

    # -- hierarchical sheets ------------------------------------------------
    def draw_sheet(self, sh):
        p = QPainterPath()
        p.addRect(QRectF(sh.x, sh.y, sh.w, sh.h))
        it = self.path_item(p, 'sheet', 10)
        it.setData(0, ('sheet', sh))
        it.setBrush(QBrush(QColor(255, 255, 255, 1)))  # clickable inside
        it.setToolTip(f'{sh.name}\n{sh.file}\n(double-click to open)')
        self.text(sh.x, sh.y - 20, 'Sheet: ' + sh.name, sh.name_size, 'sheet_name', hj='L', vj='B')
        self.text(sh.x, sh.y + sh.h + 20, 'File: ' + sh.file, sh.file_size, 'sheet_file', hj='L', vj='T')
        for name, shape, side, x, y, size in sh.pins:
            d = {'L': (1, 0), 'R': (-1, 0), 'T': (0, 1), 'B': (0, -1)}.get(side, (1, 0))
            self.path_item(self.hlabel_flag(x, y, d, size, shape), 'sheet_label', 6)
            gap = size * 1.4
            hj = 'L' if d[0] > 0 or d[1] < 0 else 'R'
            self.text(x + d[0] * gap, y + d[1] * gap, name, size, 'sheet_label',
                      side in ('T', 'B'), hj, 'C')

    # -- symbols ------------------------------------------------------------
    def draw_component(self, c):
        a, b, cc, d = c.m

        def T(x, y):                    # library coordinates (y up) -> sheet
            return (c.x + a * x + b * y, c.y + cc * x + d * y)

        group = QGraphicsItemGroup()
        self.scene.addItem(group)
        ref, unit = c.ref, c.unit
        if c.ar:
            r = c.ar.get(self.path + '/' + c.stamp)
            if r:
                ref, unit = r
        name = c.lib
        sym = self.libs.get(name) or self.libs.get(name.replace(':', '_')) \
            or self.libs.get(name.split(':')[-1])
        if sym is None:
            x0, y0 = c.x, c.y
            p = QPainterPath()
            p.addRect(QRectF(x0 - 100, y0 - 100, 200, 200))
            self.path_item(p, 'missing', 8, parent=group)
            self.text(x0, y0, '?', 120, 'missing', parent=group)
        else:
            self.draw_symbol(sym, c, unit, T, group)
        rotated = a == 0                # 90 / 270 degrees
        for f in c.fields:
            if not f.visible or not f.text or f.text == '~':
                continue
            text = f.text
            if f.n == 0:
                text = ref
                if sym is not None and sym.unit_count > 1:
                    text += chr(ord('A') + unit - 1)
            colour = {0: 'ref', 1: 'value'}.get(f.n, 'field')
            self.draw_field(c, f, text, colour, rotated, group)
        info = [f'{ref}  ({c.lib})']
        for f in c.fields:
            if f.n in (1, 2, 3) and f.text:
                info.append(f'{("Value", "Footprint", "Datasheet")[f.n - 1]}: {f.text}')
        group.setToolTip('\n'.join(info))
        group.setData(0, ('comp', c, ref, unit))
        group.setFlag(QGraphicsItem.ItemIsSelectable, True)

    def draw_field(self, c, f, text, colour, rotated, group):
        """KiCad 5 places a field by the box its justification gives in the
        symbol frame, turned by the symbol orientation, and draws the text
        centred in that box (always readable).  The position in the file is
        in the symbol frame too: the sheet position is the symbol position
        plus the transformed offset (SCH_FIELD::GetPosition)."""
        a, b, cc, d = c.m
        font = self.font(f.size)
        fm = QFontMetricsF(font)
        w = fm.horizontalAdvance(text) if hasattr(fm, 'horizontalAdvance') else fm.width(text)
        h = f.size * 1.0
        vert = (f.orient == 'V')
        # the box in the field frame (x along the text, y down)
        x0 = {'L': 0, 'C': -w / 2, 'R': -w}[f.hj if f.hj in 'LCR' else 'C']
        y0 = {'T': 0, 'C': -h / 2, 'B': -h}[f.vj if f.vj in 'TCB' else 'C']
        cx, cy = x0 + w / 2, y0 + h / 2   # its centre, relative to the text pos
        if vert:                          # text frame turned 90 degrees
            cx, cy = cy, -cx
        # the box centre from the symbol position, in the symbol frame (the
        # text box mirrored in y, as KiCad does), then the symbol transform
        rx, ry = f.x - c.x + cx, f.y - c.y - cy
        ox, oy = a * rx + b * ry, cc * rx + d * ry
        disp_vert = vert != rotated
        self.text(c.x + ox, c.y + oy, text, f.size, colour, disp_vert, 'C', 'C', parent=group)

    def draw_symbol(self, sym, c, unit, T, group):
        conv = c.convert
        for kind, u, cv, data in sym.draw:
            if u not in (0, unit) or cv not in (0, conv):
                continue
            if kind == 'P':
                pts, thick, fill = data
                path = self._poly([T(*q) for q in pts], close=False)
                if fill != 'N' and len(pts) > 2:
                    path.closeSubpath()
                self.shape(path, thick, fill, group)
            elif kind == 'S':
                x1, y1, x2, y2, thick, fill = data
                pts = [T(x1, y1), T(x2, y1), T(x2, y2), T(x1, y2)]
                self.shape(self._poly(pts), thick, fill, group)
            elif kind == 'C':
                x, y, r, thick, fill = data
                p = QPainterPath()
                p.addEllipse(QPointF(*T(x, y)), r, r)
                self.shape(p, thick, fill, group)
            elif kind == 'A':
                x, y, r, s, e, thick, fill = data
                cx, cy = T(x, y)
                sx, sy = T(*s)
                ex, ey = T(*e)
                a1 = math.degrees(math.atan2(-(sy - cy), sx - cx))
                a2 = math.degrees(math.atan2(-(ey - cy), ex - cx))
                sweep = (a2 - a1 + 180) % 360 - 180
                p = QPainterPath(QPointF(sx, sy))
                p.arcTo(QRectF(cx - r, cy - r, 2 * r, 2 * r), a1, sweep)
                if fill != 'N':
                    p.closeSubpath()
                self.shape(p, thick, fill, group)
            elif kind == 'T':
                angle, x, y, size, hidden, text, hj, vj = data
                if hidden:
                    continue
                tx, ty = T(x, y)
                vert = (angle == 900) != (c.m[0] == 0)
                self.text(tx, ty, text, size, 'body', vert, 'C', 'C', parent=group)
            elif kind == 'X':
                self.draw_pin(sym, data, T, group)

    def shape(self, path, thick, fill, group):
        it = self.path_item(path, 'body', thick or 6,
                            fill={'F': 'body', 'f': 'body_fill'}.get(fill),
                            parent=group)
        if fill == 'f':
            it.setZValue(-1)
        return it

    def draw_pin(self, sym, data, T, group):
        name, num, x, y, length, orient, snum, sname, etype, shape = data
        if shape.startswith('N'):       # invisible pin
            return
        dx, dy = {'R': (1, 0), 'L': (-1, 0), 'U': (0, 1), 'D': (0, -1)}.get(orient, (1, 0))
        x2, y2 = x + dx * length, y + dy * length
        p0 = T(x, y)
        p1 = T(x2, y2)
        path = QPainterPath(QPointF(*p0))
        path.lineTo(*p1)
        self.path_item(path, 'pin', 6, parent=group)
        # the direction pin end -> body, in the sheet
        ux, uy = p1[0] - p0[0], p1[1] - p0[1]
        ln = math.hypot(ux, uy) or 1
        ux, uy = ux / ln, uy / ln
        if 'I' in shape:                # inverted: a bubble at the body
            b = QPainterPath()
            b.addEllipse(QPointF(p1[0] - ux * 20, p1[1] - uy * 20), 20, 20)
            self.path_item(b, 'pin', 6, parent=group)
        if 'C' in shape:                # clock: a triangle inside the body
            nx, ny = -uy, ux
            tri = self._poly([(p1[0] + nx * 25, p1[1] + ny * 25),
                              (p1[0] + ux * 40, p1[1] + uy * 40),
                              (p1[0] - nx * 25, p1[1] - ny * 25)], close=False)
            self.path_item(tri, 'pin', 6, parent=group)
        vertical = abs(uy) > abs(ux)
        name = name if name != '~' else ''
        if sym.power:
            name = ''
        mx, my = (p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2
        if sym.text_offset > 0:
            if name and sym.show_pin_name:
                off = sym.text_offset
                ax, ay = p1[0] + ux * off, p1[1] + uy * off
                if vertical:
                    self.text(ax, ay, name, sname, 'pin_name', True,
                              'L' if uy < 0 else 'R', 'C', parent=group)
                else:
                    self.text(ax, ay, name, sname, 'pin_name', False,
                              'L' if ux > 0 else 'R', 'C', parent=group)
            if sym.show_pin_num and num != '~':
                if vertical:
                    self.text(mx - 10, my, num, snum, 'pin_num', True, 'C', 'B', parent=group)
                else:
                    self.text(mx, my - 10, num, snum, 'pin_num', False, 'C', 'B', parent=group)
        else:
            if name and sym.show_pin_name:
                if vertical:
                    self.text(mx - 10, my, name, sname, 'pin_name', True, 'C', 'B', parent=group)
                else:
                    self.text(mx, my - 10, name, sname, 'pin_name', False, 'C', 'B', parent=group)
            if sym.show_pin_num and num != '~':
                if vertical:
                    self.text(mx + 10, my, num, snum, 'pin_num', True, 'C', 'T', parent=group)
                else:
                    self.text(mx, my + 10, num, snum, 'pin_num', False, 'C', 'T', parent=group)


# =========================================================================
# Project: the root sheet, the hierarchy and the libraries
# =========================================================================

class SheetNode:
    def __init__(self, sch, name, path, parent=None):
        self.sch = sch                  # Schematic or None (file missing)
        self.name = name
        self.path = path                # "/stamp/stamp" of the instance
        self.parent = parent
        self.children = []
        self.number = 0


class Project:
    def __init__(self, root_path, extra_libs=()):
        self.root_path = os.path.abspath(root_path)
        self.dir = os.path.dirname(self.root_path)
        self.files = {}                 # path -> Schematic (shared by instances)
        self.errors = []
        self.libs = {}
        self.lib_files = []
        for p in extra_libs:
            self.add_lib(p)
        self.find_libs()
        self.root = SheetNode(self.load(self.root_path), '/', '')
        self.nodes = [self.root]
        self.build(self.root, set())
        for k, n in enumerate(self.nodes, 1):
            n.number = k

    def add_lib(self, path):
        if os.path.isfile(path) and path not in self.lib_files:
            self.lib_files.append(path)
            load_library(path, self.libs)

    def find_libs(self):
        base = os.path.splitext(self.root_path)[0]
        for cand in (base + '-cache.lib', base + '-rescue.lib'):
            self.add_lib(cand)
        for f in sorted(os.listdir(self.dir)):
            if f.endswith('-cache.lib') or f.endswith('-rescue.lib'):
                self.add_lib(os.path.join(self.dir, f))
        pro = base + '.pro'
        if os.path.isfile(pro):         # [eeschema/libraries] LibName1=...
            with open(pro, encoding='utf-8', errors='replace') as f:
                for line in f:
                    m = re.match(r'LibName\d+=(.*)', line.strip())
                    if m:
                        p = m.group(1)
                        if not p.endswith('.lib'):
                            p += '.lib'
                        if not os.path.isabs(p):
                            p = os.path.join(self.dir, p)
                        self.add_lib(p)

    def load(self, path):
        path = os.path.abspath(path)
        if path not in self.files:
            try:
                self.files[path] = Schematic(path)
            except (OSError, ValueError) as e:
                self.errors.append(str(e))
                self.files[path] = None
        return self.files[path]

    def build(self, node, seen):
        if node.sch is None:
            return
        base = os.path.dirname(node.sch.path)
        for sh in node.sch.sheets:
            sub = os.path.join(base, sh.file)
            child = SheetNode(None, sh.name, node.path + '/' + sh.stamp, node)
            if os.path.abspath(sub) in seen:
                self.errors.append(f'{sh.file}: recursive sheet, not followed')
            else:
                child.sch = self.load(sub)
            node.children.append(child)
            self.nodes.append(child)
            self.build(child, seen | {os.path.abspath(node.sch.path)})


def render_sheet(project, node):
    scene = QGraphicsScene()
    scene.setBackgroundBrush(QBrush(QColor(CANVAS)))
    if node.sch is not None:
        label = f'{node.name}  ({node.number}/{len(project.nodes)})'
        Painter(scene, project.libs, node.path).draw(node.sch, label)
        w, h = node.sch.page
        scene.setSceneRect(QRectF(-200, -200, w + 400, h + 400))
    return scene


def export_scene(scene, node, out):
    """Write the page of a sheet as .png (300 dpi... 4 px per 10 mils),
    .pdf (page size of the sheet) or .svg."""
    w, h = node.sch.page if node.sch else (11693, 8268)
    src = QRectF(0, 0, w, h)
    ext = os.path.splitext(out)[1].lower()
    if ext == '.pdf':
        pdf = QPdfWriter(out)
        pdf.setPageSize(QPageSize(QSizeF(w / 1000.0, h / 1000.0), QPageSize.Inch))
        pdf.setPageMargins(QMarginsF(0, 0, 0, 0))
        pdf.setResolution(600)
        p = QPainter(pdf)
        p.setRenderHint(QPainter.Antialiasing)
        scene.render(p, QRectF(0, 0, pdf.width(), pdf.height()), src)
        p.end()
    elif ext == '.svg':
        if QSvgGenerator is None:
            raise RuntimeError('SVG export needs PyQt5.QtSvg (python3-pyqt5.qtsvg)')
        g = QSvgGenerator()
        g.setFileName(out)
        g.setSize(QRectF(0, 0, w / 5, h / 5).size().toSize())
        g.setViewBox(QRectF(0, 0, w / 5, h / 5))
        p = QPainter(g)
        scene.render(p, QRectF(0, 0, w / 5, h / 5), src)
        p.end()
    else:
        scale = 0.4                     # 400 px per inch... 0.4 px per mil
        img = QImage(int(w * scale), int(h * scale), QImage.Format_RGB32)
        img.fill(QColor(COL['background']))
        p = QPainter(img)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)
        scene.render(p, QRectF(0, 0, img.width(), img.height()), src)
        p.end()
        if not img.save(out):
            raise RuntimeError(f'{out}: cannot write the image')


# =========================================================================
# The window
# =========================================================================

class View(QGraphicsView):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setViewportUpdateMode(QGraphicsView.SmartViewportUpdate)
        self.setMouseTracking(True)

    def wheelEvent(self, ev):
        f = 1.25 if ev.angleDelta().y() > 0 else 0.8
        s = self.transform().m11() * f
        if 0.005 < s < 20:
            self.scale(f, f)

    def mousePressEvent(self, ev):
        if ev.button() == Qt.MiddleButton:  # pan with the middle button too
            fake = type(ev)(ev.type(), ev.localPos(), Qt.LeftButton,
                            Qt.LeftButton, ev.modifiers())
            super().mousePressEvent(fake)
            return
        super().mousePressEvent(ev)
        self.win.select_at(self.mapToScene(ev.pos()))

    def mouseReleaseEvent(self, ev):
        if ev.button() == Qt.MiddleButton:
            fake = type(ev)(ev.type(), ev.localPos(), Qt.LeftButton,
                            Qt.NoButton, ev.modifiers())
            super().mouseReleaseEvent(fake)
            return
        super().mouseReleaseEvent(ev)

    def mouseDoubleClickEvent(self, ev):
        self.win.open_sheet_at(self.mapToScene(ev.pos()))

    def mouseMoveEvent(self, ev):
        super().mouseMoveEvent(ev)
        p = self.mapToScene(ev.pos())
        self.win.show_pos(p)


class Window(QMainWindow):
    def __init__(self, project=None):
        super().__init__()
        self.project = None
        self.node = None
        self.highlight = None
        self.find_hits = []
        self.find_index = 0
        self.view = View(self)
        self.setCentralWidget(self.view)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(['Sheet', 'File'])
        self.tree.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.tree.itemActivated.connect(self.tree_open)
        self.tree.itemClicked.connect(self.tree_click)
        dock = QDockWidget('Hierarchy', self)
        dock.setWidget(self.tree)
        self.addDockWidget(Qt.LeftDockWidgetArea, dock)
        self.props = QTableWidget(0, 2)
        self.props.setHorizontalHeaderLabels(['Field', 'Value'])
        self.props.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.props.verticalHeader().hide()
        dock2 = QDockWidget('Symbol', self)
        dock2.setWidget(self.props)
        self.addDockWidget(Qt.LeftDockWidgetArea, dock2)
        self.pos_label = QLabel()
        self.statusBar().addPermanentWidget(self.pos_label)
        self.make_menu()
        self.make_toolbar()
        self.resize(1400, 900)
        self.resizeDocks([dock, dock2], [360, 360], Qt.Horizontal)
        if project:
            self.set_project(project)

    def make_menu(self):
        m = self.menuBar().addMenu('&File')
        for text, key, fn in (('&Open...', QKeySequence.Open, self.open_file),
                              ('&Export sheet...', 'Ctrl+E', self.export),
                              ('&Print...', QKeySequence.Print, self.print_sheets),
                              ('Print pre&view...', 'Ctrl+Shift+P', self.print_preview),
                              ('&Quit', QKeySequence.Quit, self.close)):
            a = QAction(text, self)
            a.setShortcut(key)
            a.triggered.connect(fn)
            m.addAction(a)
        m = self.menuBar().addMenu('&View')
        for text, keys, fn in (('&Fit page', ['Home', 'F'], self.fit),
                               ('&Parent sheet', ['Backspace', 'Alt+Left'], self.parent_sheet),
                               ('Fi&nd...', ['Ctrl+F'], self.find),
                               ('Find &next', ['F3'], self.find_next),
                               ('Zoom &in', ['+', '='], lambda: self.view.scale(1.25, 1.25)),
                               ('Zoom &out', ['-'], lambda: self.view.scale(0.8, 0.8))):
            a = QAction(text, self)
            a.setShortcuts([QKeySequence(k) for k in keys])
            a.triggered.connect(fn)
            m.addAction(a)

        m = self.menuBar().addMenu('&Theme')
        group = QActionGroup(self)
        current = settings().value('theme', 'light')
        for name, text in (('light', 'Material &light'), ('dark', 'Material &dark'),
                           ('system', '&System')):
            a = QAction(text, self, checkable=True)
            a.setChecked(name == current)
            a.triggered.connect(lambda _=False, n=name: self.set_theme(n))
            group.addAction(a)
            m.addAction(a)

    def make_toolbar(self):
        tb = QToolBar('Tools', self)
        tb.setMovable(False)
        tb.setToolButtonStyle(Qt.ToolButtonTextOnly)
        for item in (('OPEN', self.open_file), ('PRINT', self.print_sheets),
                     ('EXPORT', self.export), None, ('UP', self.parent_sheet),
                     ('FIT', self.fit), ('ZOOM +', lambda: self.view.scale(1.25, 1.25)),
                     ('ZOOM \u2212', lambda: self.view.scale(0.8, 0.8)), None,
                     ('FIND', self.find)):
            if item is None:
                tb.addSeparator()
            else:
                tb.addAction(*item)
        self.addToolBar(Qt.TopToolBarArea, tb)

    def set_theme(self, name):
        settings().setValue('theme', name)
        apply_theme(QApplication.instance(), name)
        if self.node is not None:       # the canvas colour around the page
            self.view.scene().setBackgroundBrush(QBrush(QColor(CANVAS)))

    # -- project / sheets -------------------------------------------------
    def set_project(self, project):
        self.project = project
        self.setWindowTitle(f'{os.path.basename(project.root_path)} - KiCad schematic viewer')
        self.tree.clear()
        self.tree_items = {}

        def add(node, parent_item):
            it = QTreeWidgetItem([f'{node.number}. {node.name}',
                                  os.path.basename(node.sch.path) if node.sch else '(missing)'])
            it.setData(0, Qt.UserRole, node.number)
            self.tree_items[node.number] = it
            if parent_item is None:
                self.tree.addTopLevelItem(it)
            else:
                parent_item.addChild(it)
            for ch in node.children:
                add(ch, it)
        add(project.root, None)
        self.tree.expandAll()
        self.tree.resizeColumnToContents(0)
        self.show_node(project.root)
        if project.errors:
            QMessageBox.warning(self, 'Warnings', '\n'.join(project.errors[:30]))
        missing = self.missing_symbols()
        if missing:
            self.statusBar().showMessage(
                f'{len(missing)} symbol(s) not found in the libraries: '
                + ', '.join(sorted(missing)[:8]) + ' (use -L to add libraries)', 15000)

    def missing_symbols(self):
        miss = set()
        for sch in self.project.files.values():
            if sch is None:
                continue
            for c in sch.components:
                n = c.lib
                if not (n in self.project.libs or n.replace(':', '_') in self.project.libs
                        or n.split(':')[-1] in self.project.libs):
                    miss.add(n)
        return miss

    def show_node(self, node):
        self.node = node
        self.highlight = None
        scene = render_sheet(self.project, node)
        self.view.setScene(scene)
        self.fit()
        it = self.tree_items.get(node.number)
        if it:
            self.tree.setCurrentItem(it)
        self.props.setRowCount(0)

    def tree_click(self, item, col=0):
        # Ctrl/Shift+click only selects sheets (for printing)
        if not QApplication.keyboardModifiers() & (Qt.ControlModifier | Qt.ShiftModifier):
            self.tree_open(item, col)

    def tree_open(self, item, col=0):
        n = item.data(0, Qt.UserRole)
        node = self.project.nodes[n - 1]
        if node is not self.node:
            self.show_node(node)

    def fit(self):
        if self.node and self.node.sch:
            w, h = self.node.sch.page
            self.view.fitInView(QRectF(0, 0, w, h), Qt.KeepAspectRatio)

    def parent_sheet(self):
        if self.node and self.node.parent:
            self.show_node(self.node.parent)

    def open_sheet_at(self, p):
        for it in self.view.scene().items(p):
            d = it.data(0)
            if d and d[0] == 'sheet':
                for ch in self.node.children:
                    if ch.path.endswith('/' + d[1].stamp):
                        self.show_node(ch)
                        return

    def comp_at(self, p):
        for it in self.view.scene().items(p):
            g = it.group() or it
            d = g.data(0)
            if d and d[0] == 'comp':
                return g, d
        return None, None

    def select_at(self, p):
        g, d = self.comp_at(p)
        if g is None:
            return
        self.mark(g)
        c, ref, unit = d[1], d[2], d[3]
        rows = [('Reference', ref), ('Unit', str(unit)), ('Symbol', c.lib)]
        names = {1: 'Value', 2: 'Footprint', 3: 'Datasheet'}
        for f in c.fields:
            if f.n == 0:
                continue
            rows.append((f.name or names.get(f.n, f'Field{f.n}'), f.text))
        rows.append(('Position', f'{c.x}, {c.y} mil'))
        self.props.setRowCount(len(rows))
        for r, (k, v) in enumerate(rows):
            self.props.setItem(r, 0, QTableWidgetItem(k))
            self.props.setItem(r, 1, QTableWidgetItem(v))
        self.props.resizeColumnToContents(0)

    def mark(self, group):
        sc = self.view.scene()
        if self.highlight is not None and self.highlight.scene() is sc:
            sc.removeItem(self.highlight)
        r = group.sceneBoundingRect().adjusted(-30, -30, 30, 30)
        self.highlight = QGraphicsRectItem(r)
        pen = QPen(QColor(COL['select']), 12)
        pen.setStyle(Qt.DashLine)
        self.highlight.setPen(pen)
        self.highlight.setZValue(100)
        sc.addItem(self.highlight)

    def show_pos(self, p):
        self.pos_label.setText(f'X {p.x():.0f}  Y {p.y():.0f} mil   '
                               f'({p.x() * 0.0254:.2f}, {p.y() * 0.0254:.2f} mm)')

    # -- find ---------------------------------------------------------------
    def find(self):
        if not self.project:
            return
        s, ok = QInputDialog.getText(self, 'Find', 'Reference, value or label (all sheets):')
        if not ok or not s.strip():
            return
        s = s.strip().lower()
        hits = []
        for node in self.project.nodes:
            sch = node.sch
            if sch is None:
                continue
            for c in sch.components:
                ref = c.ar.get(node.path + '/' + c.stamp, (c.ref, 0))[0] if c.ar else c.ref
                vals = [ref] + [f.text for f in c.fields if f.n == 1]
                if any(s == v.lower() or (len(s) > 1 and s in v.lower()) for v in vals):
                    hits.append((node, ('comp', c.x, c.y)))
            for t in sch.texts:
                if t[0] != 'Notes' and s in t[7].lower():
                    hits.append((node, ('text', t[1], t[2])))
        self.find_hits = hits
        self.find_index = 0
        if not hits:
            self.statusBar().showMessage(f'"{s}": not found', 5000)
            return
        self.find_next()

    def find_next(self):
        if not self.find_hits:
            return
        node, (kind, x, y) = self.find_hits[self.find_index % len(self.find_hits)]
        self.find_index += 1
        if node is not self.node:
            self.show_node(node)
        self.view.resetTransform()
        self.view.scale(0.25, 0.25)
        self.view.centerOn(x, y)
        g, d = self.comp_at(QPointF(x, y)) if kind == 'comp' else (None, None)
        if g is not None:
            self.select_at(QPointF(x, y))
        self.statusBar().showMessage(
            f'hit {(self.find_index - 1) % len(self.find_hits) + 1} of {len(self.find_hits)} '
            f'(F3: next)', 5000)

    # -- printing -------------------------------------------------------------
    def selected_nodes(self):
        nums = sorted(it.data(0, Qt.UserRole) for it in self.tree.selectedItems())
        return [self.project.nodes[n - 1] for n in nums]

    def new_printer(self):
        pr = QPrinter(QPrinter.HighResolution)
        pr.setDocName(os.path.basename(self.project.root_path))
        w, h = self.node.sch.page if self.node and self.node.sch else (11693, 8268)
        pr.setPageOrientation(1 if w > h else 0)    # QPageLayout Landscape / Portrait
        return pr

    def print_sheets(self):
        if not self.project:
            return
        pr = self.new_printer()
        dlg = QPrintDialog(pr, self)
        dlg.setWindowTitle('Print sheets')
        n = len(self.project.nodes)
        dlg.setMinMax(1, n)
        dlg.setFromTo(1, n)
        opts = (QAbstractPrintDialog.PrintPageRange | QAbstractPrintDialog.PrintCurrentPage
                | QAbstractPrintDialog.PrintToFile | QAbstractPrintDialog.PrintShowPageSize
                | QAbstractPrintDialog.PrintCollateCopies)
        sel = self.selected_nodes()
        if len(sel) > 1:                # "Selection" = the sheets picked in the tree
            opts |= QAbstractPrintDialog.PrintSelection
        dlg.setOptions(opts)
        if len(sel) > 1:
            dlg.setPrintRange(QAbstractPrintDialog.Selection)
        if dlg.exec_() != QPrintDialog.Accepted:
            return
        nodes = self.nodes_for(pr, sel)
        if nodes:
            self.paint_sheets(pr, nodes)
            self.statusBar().showMessage(f'{len(nodes)} sheet(s) sent to {pr.printerName() or pr.outputFileName()}', 5000)

    def nodes_for(self, pr, sel):
        rng = pr.printRange()
        if rng == QPrinter.CurrentPage:
            return [self.node]
        if rng == QPrinter.Selection:
            return sel or [self.node]
        if rng == QPrinter.PageRange and pr.fromPage() > 0:
            return self.project.nodes[pr.fromPage() - 1:pr.toPage()]
        return list(self.project.nodes)

    def paint_sheets(self, pr, nodes):
        p = QPainter()
        if not p.begin(pr):
            QMessageBox.critical(self, 'Print', 'cannot start the print job')
            return
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)
        first = True
        for node in nodes:
            if node.sch is None:
                continue
            if not first:
                pr.newPage()
            first = False
            w, h = node.sch.page
            area = QRectF(pr.pageRect(QPrinter.DevicePixel))
            area.moveTo(0, 0)
            render_sheet(self.project, node).render(p, area, QRectF(0, 0, w, h), Qt.KeepAspectRatio)
        p.end()

    def print_preview(self):
        if not self.project:
            return
        sel = self.selected_nodes()
        nodes = sel if len(sel) > 1 else list(self.project.nodes)
        pr = self.new_printer()
        dlg = QPrintPreviewDialog(pr, self)
        dlg.setWindowTitle(f'Print preview: {len(nodes)} sheet(s)')
        dlg.paintRequested.connect(lambda printer: self.paint_sheets(printer, nodes))
        dlg.resize(1100, 800)
        dlg.exec_()

    # -- files ----------------------------------------------------------------
    def open_file(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Open schematic', '',
                                              'KiCad 4/5 schematic (*.sch)')
        if path:
            try:
                self.set_project(Project(path))
            except (OSError, ValueError) as e:
                QMessageBox.critical(self, 'Error', str(e))

    def export(self):
        if not self.node or not self.node.sch:
            return
        filt = 'PNG image (*.png);;PDF (*.pdf)'
        if QSvgGenerator is not None:
            filt += ';;SVG (*.svg)'
        base = os.path.splitext(os.path.basename(self.node.sch.path))[0]
        path, _ = QFileDialog.getSaveFileName(self, 'Export sheet', base + '.png', filt)
        if path:
            try:
                export_scene(render_sheet(self.project, self.node), self.node, path)
                self.statusBar().showMessage(f'written {path}', 5000)
            except RuntimeError as e:
                QMessageBox.critical(self, 'Error', str(e))


def main():
    ap = argparse.ArgumentParser(description='Viewer for KiCad 4/5 schematics (.sch)')
    ap.add_argument('sch', nargs='?', help='the root schematic (.sch)')
    ap.add_argument('-L', '--lib', action='append', default=[],
                    help='an extra symbol library (.lib), repeatable')
    ap.add_argument('--export', metavar='OUT',
                    help='write a sheet to OUT (.png, .pdf, .svg) and exit')
    ap.add_argument('--theme', choices=('light', 'dark', 'system'),
                    help='Material light / dark or the system look (remembered)')
    ap.add_argument('--sheet', type=int, default=1,
                    help='with --export: the sheet number (1 = root, the order '
                         'of the hierarchy tree); 0 = all, OUT gets -N')
    a = ap.parse_args()
    if a.export:
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    app = QApplication(sys.argv[:1])
    load_fonts()
    project = None
    if a.sch:
        try:
            project = Project(a.sch, a.lib)
        except (OSError, ValueError) as e:
            sys.exit(f'kicad_sch_viewer: {e}')
    if a.export:
        if project is None:
            sys.exit('kicad_sch_viewer: --export needs a schematic')
        for e in project.errors:
            print('warning:', e, file=sys.stderr)
        nodes = project.nodes if a.sheet == 0 else [project.nodes[a.sheet - 1]]
        for node in nodes:
            out = a.export
            if a.sheet == 0:
                b, e = os.path.splitext(a.export)
                out = f'{b}-{node.number}{e}'
            export_scene(render_sheet(project, node), node, out)
            print(f'{out}: sheet {node.number} {node.name}')
        return
    cfg = settings()
    if a.theme:
        cfg.setValue('theme', a.theme)
    apply_theme(app, cfg.value('theme', 'light'))
    w = Window(project)
    w.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
