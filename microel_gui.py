"""
microel_gui.py
Comprehensive tkinter GUI for MicroEL Card Analyzer and Editor.
Supports loading, editing, and saving Flipper Zero .nfc files.
Modern dark-themed UI with enhanced features.
"""

import json
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import copy
import os

from nfc_file_handler import NFCFile
from microel_card_analyzer import color_string

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SCHEMA = [
    (4, "Operation number"),
    (4, "Total input sum"),
    (2, "Deposit"),
    (4, "Credit"),
    (8, "Transaction date"),
    (4, "Points"),
    (4, "Last transaction amount"),
    (2, "Checksum"),
]

PARAM_DESCRIPTIONS = {
    "Operation number":       "Sequential counter for card transactions",
    "Total input sum":        "Cumulative total of all credits loaded",
    "Deposit":                "Security deposit / cauzione amount",
    "Credit":                 "Current available credit balance",
    "Transaction date":       "Timestamp of the last transaction (epoch)",
    "Points":                 "Loyalty / reward points accumulated",
    "Last transaction amount": "Amount of the most recent transaction",
    "Checksum":               "XOR checksum of preceding 15 bytes",
}

# Catppuccin Mocha-inspired dark palette
THEME = {
    "bg":          "#1e1e2e",   # base
    "surface":     "#181825",   # mantle (darker panels)
    "overlay":     "#313244",   # overlay0 (borders, separators)
    "text":        "#cdd6f4",   # text
    "subtext":     "#a6adc8",   # subtext0
    "accent":      "#89b4fa",   # blue
    "green":       "#a6e3a1",
    "yellow":      "#f9e2af",
    "red":         "#f38ba8",
    "orange":      "#fab387",
    "header_bg":   "#11111b",   # crust (table header)
    "row_even":    "#1e1e2e",
    "row_odd":     "#181825",
    "select_bg":   "#45475a",   # surface2
    "select_fg":   "#cdd6f4",
}

# Per-parameter accent colours (Catppuccin Mocha tones)
COLOR_PALETTE = [
    "#89dceb",  # sky
    "#94e2d5",  # teal
    "#a6e3a1",  # green
    "#f9e2af",  # yellow
    "#fab387",  # peach
    "#cba6f7",  # mauve
    "#89b4fa",  # blue
    "#f38ba8",  # red
]

APP_TITLE = "MicroEL Card Analyzer & Editor"
MAX_UNDO = 50

SHORTCUTS_HELP = (
    "Ctrl+N  New    Ctrl+O  Open    Ctrl+S  Save    "
    "Ctrl+Z  Undo    Ctrl+Y  Redo    Ctrl+Q  Quit"
)


# ---------------------------------------------------------------------------
# Helper functions (pure, no tkinter)
# ---------------------------------------------------------------------------

def hex_string_to_parsed(hex_string):
    """Return the same tuple list produced by color_string() in the CLI."""
    return color_string(hex_string)


def parsed_to_hex_string(parsed_data):
    """Reconstruct the 32-char hex string from parsed_data tuples."""
    return "".join(seg for _, seg, _, _, _ in parsed_data)


def validate_hex(value, expected_len):
    """Return True if *value* is a valid hex string of *expected_len* chars."""
    if len(value) != expected_len:
        return False
    try:
        int(value, 16)
        return True
    except ValueError:
        return False


def validate_decimal(value, max_digits):
    """Return True if *value* is a non-negative integer with ≤ max_digits hex digits."""
    try:
        n = int(value)
        return 0 <= n < (16 ** max_digits)
    except ValueError:
        return False


def invert_hex(hex_str):
    """Return the byte-inverted hex string."""
    return "".join(reversed([hex_str[i: i + 2] for i in range(0, len(hex_str), 2)]))


def apply_edit(parsed_data, param_index, new_value, fmt):
    """Apply an edit to *parsed_data* and return new parsed_data or raise ValueError."""
    parsed_data = list(parsed_data)
    description, original, _, _, _ = parsed_data[param_index]
    length = len(original)

    if fmt == "HEX":
        new_value = new_value.upper()
        if not validate_hex(new_value, length):
            raise ValueError(f"Expected {length}-char hex string")
        new_hex = new_value
        new_inv = invert_hex(new_hex)
        new_dec = int(new_inv, 16)
    elif fmt == "HEX INVERTED":
        new_value = new_value.upper()
        if not validate_hex(new_value, length):
            raise ValueError(f"Expected {length}-char hex string (inverted)")
        new_inv = new_value
        new_hex = invert_hex(new_inv)
        new_dec = int(new_inv, 16)
    elif fmt == "DECIMAL":
        if not validate_decimal(new_value, length):
            raise ValueError(f"Expected decimal 0–{16 ** length - 1}")
        new_dec = int(new_value)
        new_inv = f"{new_dec:0{length}X}"
        new_hex = invert_hex(new_inv)
    else:
        raise ValueError(f"Unknown format: {fmt}")

    full_string = parsed_to_hex_string(parsed_data)
    start = sum(len(parsed_data[i][1]) for i in range(param_index))
    new_full = full_string[:start] + new_hex + full_string[start + length:]
    return color_string(new_full)


def compute_checksum(parsed_data):
    """XOR-based checksum over the first 15 bytes (30 hex chars, 7 parameters)."""
    hex_str = parsed_to_hex_string(parsed_data)
    bytes_list = [int(hex_str[i: i + 2], 16) for i in range(0, 30, 2)]
    checksum = 0
    for b in bytes_list:
        checksum ^= b
    return f"{checksum:02X}"


def parsed_to_json(parsed_data):
    """Serialize parsed_data to a JSON string."""
    records = [
        {"parameter": desc, "hex": seg, "hex_inverted": inv, "decimal": dec}
        for desc, seg, _, inv, dec in parsed_data
    ]
    return json.dumps(records, indent=2)


def parsed_to_html(parsed_data, file_path=None, block=0):
    """Generate a standalone HTML report from parsed_data."""
    rows = ""
    for i, (desc, seg, _, inv, dec) in enumerate(parsed_data):
        color = COLOR_PALETTE[i % len(COLOR_PALETTE)]
        bg = THEME["row_even"] if i % 2 == 0 else THEME["row_odd"]
        rows += (
            f'<tr style="background:{bg}">'
            f'<td style="color:{color};font-weight:bold">{desc}</td>'
            f'<td style="font-family:monospace;color:{color}">{seg}</td>'
            f'<td style="font-family:monospace;color:{color}">{inv}</td>'
            f'<td style="color:{color}">{dec}</td>'
            f"</tr>\n"
        )
    source = file_path or "Manual Entry"
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>MicroEL Card Report</title>
<style>
  body {{background:{THEME['bg']};color:{THEME['text']};font-family:sans-serif;padding:20px}}
  h1 {{color:{THEME['accent']};border-bottom:2px solid {THEME['overlay']};padding-bottom:8px}}
  p.meta {{color:{THEME['subtext']};font-size:0.9em}}
  table {{border-collapse:collapse;width:100%}}
  th {{background:{THEME['header_bg']};color:{THEME['accent']};padding:10px 14px;text-align:left}}
  td {{padding:8px 14px;border-bottom:1px solid {THEME['overlay']}}}
  tr:hover td {{background:{THEME['select_bg']}}}
</style>
</head>
<body>
<h1>MicroEL Card Analyzer Report</h1>
<p class="meta">Source: {source} &nbsp;|&nbsp; Block: {block}</p>
<table>
<tr><th>Parameter</th><th>HEX</th><th>HEX Inverted</th><th>Decimal</th></tr>
{rows}</table>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Tooltip helper
# ---------------------------------------------------------------------------

class _Tooltip:
    """Simple hover tooltip for any tkinter widget."""

    def __init__(self, widget, text):
        self._widget = widget
        self._text = text
        self._tip_win = None
        widget.bind("<Enter>", self._show)
        widget.bind("<Leave>", self._hide)

    def _show(self, _event=None):
        if self._tip_win or not self._text:
            return
        x = self._widget.winfo_rootx() + 20
        y = self._widget.winfo_rooty() + self._widget.winfo_height() + 4
        self._tip_win = tw = tk.Toplevel(self._widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        tk.Label(
            tw, text=self._text, justify=tk.LEFT,
            background="#2a2a3e", foreground=THEME["text"],
            relief=tk.SOLID, borderwidth=1,
            font=("Segoe UI", 9), padx=6, pady=4
        ).pack()

    def _hide(self, _event=None):
        if self._tip_win:
            self._tip_win.destroy()
            self._tip_win = None


# ---------------------------------------------------------------------------
# Theme setup
# ---------------------------------------------------------------------------

def _apply_dark_theme(root):
    """Configure ttk.Style for a dark Catppuccin Mocha-inspired look."""
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass

    bg = THEME["bg"]
    surface = THEME["surface"]
    overlay = THEME["overlay"]
    text = THEME["text"]
    subtext = THEME["subtext"]
    accent = THEME["accent"]
    select_bg = THEME["select_bg"]

    # Global widget defaults
    style.configure(".",
                    background=bg,
                    foreground=text,
                    fieldbackground=surface,
                    troughcolor=surface,
                    bordercolor=overlay,
                    darkcolor=surface,
                    lightcolor=overlay,
                    relief="flat",
                    font=("Segoe UI", 10))

    style.configure("TFrame", background=bg)
    style.configure("TLabel", background=bg, foreground=text)
    style.configure("TLabelframe", background=bg, foreground=accent,
                    bordercolor=overlay, relief="solid")
    style.configure("TLabelframe.Label", background=bg, foreground=accent,
                    font=("Segoe UI", 10, "bold"))

    # Buttons
    style.configure("TButton",
                    background=overlay, foreground=text,
                    bordercolor=overlay, focuscolor=accent,
                    padding=(8, 4), relief="flat")
    style.map("TButton",
              background=[("active", select_bg), ("pressed", accent)],
              foreground=[("pressed", bg)])

    style.configure("Accent.TButton",
                    background=accent, foreground=bg,
                    font=("Segoe UI", 10, "bold"), padding=(10, 5))
    style.map("Accent.TButton",
              background=[("active", "#74c7ec"), ("pressed", "#74c7ec")])

    style.configure("Danger.TButton",
                    background="#45475a", foreground=THEME["red"],
                    font=("Segoe UI", 9))

    # Entries / Spinbox / Combobox
    style.configure("TEntry",
                    fieldbackground=surface, foreground=text,
                    insertcolor=accent, bordercolor=overlay,
                    relief="solid", padding=4)
    style.configure("TSpinbox",
                    fieldbackground=surface, foreground=text,
                    arrowcolor=subtext, bordercolor=overlay, relief="solid")
    style.configure("TCombobox",
                    fieldbackground=surface, foreground=text,
                    arrowcolor=subtext, bordercolor=overlay, relief="solid")
    style.map("TCombobox",
              fieldbackground=[("readonly", surface)],
              foreground=[("readonly", text)])

    # Radiobutton / Checkbutton
    style.configure("TRadiobutton", background=bg, foreground=text)
    style.map("TRadiobutton",
              background=[("active", bg)],
              indicatorcolor=[("selected", accent), ("!selected", overlay)])

    # Treeview
    style.configure("Treeview",
                    background=THEME["row_even"],
                    fieldbackground=THEME["row_even"],
                    foreground=text,
                    rowheight=26,
                    bordercolor=overlay,
                    relief="flat",
                    font=("Consolas", 10))
    style.configure("Treeview.Heading",
                    background=THEME["header_bg"],
                    foreground=accent,
                    font=("Segoe UI", 10, "bold"),
                    relief="flat",
                    bordercolor=overlay)
    style.map("Treeview",
              background=[("selected", select_bg)],
              foreground=[("selected", text)])
    style.map("Treeview.Heading",
              background=[("active", overlay)])

    # Scrollbar
    style.configure("TScrollbar",
                    background=surface, troughcolor=bg,
                    arrowcolor=subtext, bordercolor=overlay,
                    relief="flat")
    style.map("TScrollbar",
              background=[("active", overlay)])

    # Separator
    style.configure("TSeparator", background=overlay)

    # Notebook (not used currently, but styled for consistency)
    style.configure("TNotebook", background=bg, bordercolor=overlay)
    style.configure("TNotebook.Tab",
                    background=surface, foreground=subtext,
                    padding=(10, 4))
    style.map("TNotebook.Tab",
              background=[("selected", bg)],
              foreground=[("selected", accent)])

    # Root window background
    root.configure(bg=bg)


# ---------------------------------------------------------------------------
# Main application window
# ---------------------------------------------------------------------------

class MicroELApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.resizable(True, True)
        self.minsize(960, 680)

        _apply_dark_theme(self)

        self._nfc_file = None          # NFCFile instance
        self._current_path = None      # str path of the open file
        self._current_block = 0        # int block number
        self._parsed_data = None       # list of tuples from color_string()
        self._modified = False
        self._filter_var = tk.StringVar()

        # Undo / redo stacks hold snapshots of _parsed_data
        self._undo_stack = []
        self._redo_stack = []

        # StringVars for the edit panel
        self._param_var = tk.StringVar(value=SCHEMA[0][1])
        self._format_var = tk.StringVar(value="HEX")
        self._input_var = tk.StringVar()

        self._build_menu()
        self._build_ui()
        self._update_title()

    # ------------------------------------------------------------------
    # Menu
    # ------------------------------------------------------------------

    def _build_menu(self):
        bg = THEME["surface"]
        fg = THEME["text"]
        active_bg = THEME["overlay"]

        menubar = tk.Menu(self, bg=bg, fg=fg, activebackground=active_bg,
                          activeforeground=THEME["accent"], relief="flat",
                          borderwidth=0)
        self.config(menu=menubar)

        def _menu(label):
            m = tk.Menu(menubar, tearoff=False, bg=bg, fg=fg,
                        activebackground=active_bg,
                        activeforeground=THEME["accent"],
                        relief="flat", borderwidth=0)
            menubar.add_cascade(label=label, menu=m)
            return m

        file_menu = _menu("File")
        file_menu.add_command(label="New (blank data)", command=self._new_file,
                              accelerator="Ctrl+N")
        file_menu.add_command(label="Open .nfc…", command=self._open_file,
                              accelerator="Ctrl+O")
        file_menu.add_separator()
        file_menu.add_command(label="Save", command=self._save_file,
                              accelerator="Ctrl+S")
        file_menu.add_command(label="Save As…", command=self._save_file_as,
                              accelerator="Ctrl+Shift+S")
        file_menu.add_separator()
        file_menu.add_command(label="Export JSON…", command=self._export_json)
        file_menu.add_command(label="Export HTML…", command=self._export_html)
        file_menu.add_separator()
        file_menu.add_command(label="Quit", command=self._quit,
                              accelerator="Ctrl+Q")

        edit_menu = _menu("Edit")
        edit_menu.add_command(label="Undo", command=self._undo,
                              accelerator="Ctrl+Z")
        edit_menu.add_command(label="Redo", command=self._redo,
                              accelerator="Ctrl+Y")
        edit_menu.add_separator()
        edit_menu.add_command(label="Recalculate Checksum",
                              command=self._recalculate_checksum)
        edit_menu.add_separator()
        edit_menu.add_command(label="Copy Full HEX to Clipboard",
                              command=self._copy_full_hex)

        self.bind_all("<Control-n>", lambda _e: self._new_file())
        self.bind_all("<Control-o>", lambda _e: self._open_file())
        self.bind_all("<Control-s>", lambda _e: self._save_file())
        self.bind_all("<Control-S>", lambda _e: self._save_file_as())
        self.bind_all("<Control-z>", lambda _e: self._undo())
        self.bind_all("<Control-y>", lambda _e: self._redo())
        self.bind_all("<Control-q>", lambda _e: self._quit())

    # ------------------------------------------------------------------
    # UI layout
    # ------------------------------------------------------------------

    def _build_ui(self):
        bg = THEME["bg"]
        surface = THEME["surface"]
        overlay = THEME["overlay"]
        accent = THEME["accent"]
        text = THEME["text"]
        subtext = THEME["subtext"]

        # ── Header bar ────────────────────────────────────────────────
        header = tk.Frame(self, bg=THEME["header_bg"], height=48)
        header.pack(fill=tk.X)
        header.pack_propagate(False)

        tk.Label(
            header,
            text="⬡  MicroEL Card Analyzer & Editor",
            bg=THEME["header_bg"], fg=accent,
            font=("Segoe UI", 14, "bold"),
            padx=14, pady=10
        ).pack(side=tk.LEFT)

        # File-state indicator
        self._state_dot = tk.Label(
            header, text="●", bg=THEME["header_bg"], fg=subtext,
            font=("Segoe UI", 16), padx=6
        )
        self._state_dot.pack(side=tk.RIGHT, padx=(0, 14))
        _Tooltip(self._state_dot, "Green = saved  |  Orange = unsaved changes  |  Grey = no file")

        # ── Top toolbar: file info + block selector ───────────────────
        toolbar = ttk.LabelFrame(self, text="  File & Block  ", padding=(10, 6))
        toolbar.pack(fill=tk.X, padx=10, pady=(8, 0))

        ttk.Label(toolbar, text="Block:", foreground=subtext).pack(side=tk.LEFT)
        self._block_var = tk.StringVar(value="0")
        self._block_spinbox = ttk.Spinbox(
            toolbar, from_=0, to=255, width=5, textvariable=self._block_var
        )
        self._block_spinbox.pack(side=tk.LEFT, padx=(4, 6))
        self._block_spinbox.bind("<Return>", lambda _e: self._load_block())

        ttk.Button(toolbar, text="Load Block", command=self._load_block).pack(
            side=tk.LEFT, padx=(0, 12))

        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(
            side=tk.LEFT, fill=tk.Y, pady=2, padx=6)

        # NFC metadata labels
        self._meta_frame = tk.Frame(toolbar, bg=bg)
        self._meta_frame.pack(side=tk.LEFT, padx=4)
        self._uid_label = tk.Label(
            self._meta_frame, text="UID: —", fg=subtext, bg=bg,
            font=("Consolas", 9))
        self._uid_label.grid(row=0, column=0, padx=8)
        self._atqa_label = tk.Label(
            self._meta_frame, text="ATQA: —", fg=subtext, bg=bg,
            font=("Consolas", 9))
        self._atqa_label.grid(row=0, column=1, padx=8)
        self._sak_label = tk.Label(
            self._meta_frame, text="SAK: —", fg=subtext, bg=bg,
            font=("Consolas", 9))
        self._sak_label.grid(row=0, column=2, padx=8)
        self._type_label = tk.Label(
            self._meta_frame, text="Type: —", fg=subtext, bg=bg,
            font=("Consolas", 9))
        self._type_label.grid(row=0, column=3, padx=8)

        # Export buttons on the right of toolbar
        ttk.Button(toolbar, text="⬇ JSON", command=self._export_json,
                   style="TButton").pack(side=tk.RIGHT, padx=2)
        ttk.Button(toolbar, text="⬇ HTML", command=self._export_html,
                   style="TButton").pack(side=tk.RIGHT, padx=2)

        # ── Middle: hex display + parameter table (left) + edit panel (right) ─
        mid_frame = tk.Frame(self, bg=bg)
        mid_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=8)
        mid_frame.columnconfigure(0, weight=1)
        mid_frame.columnconfigure(1, weight=0)
        mid_frame.rowconfigure(0, weight=1)

        # ── Left: display panel ───────────────────────────────────────
        display_frame = ttk.LabelFrame(mid_frame, text="  Data Display  ", padding=(10, 8))
        display_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        display_frame.columnconfigure(0, weight=1)
        display_frame.rowconfigure(2, weight=1)

        # Full hex string (colour-coded) + copy button
        hex_header = tk.Frame(display_frame, bg=bg)
        hex_header.grid(row=0, column=0, sticky="ew", pady=(0, 4))
        tk.Label(hex_header, text="Full hex string:", fg=subtext, bg=bg,
                 font=("Segoe UI", 9)).pack(side=tk.LEFT)
        self._copy_hex_btn = ttk.Button(
            hex_header, text="⧉ Copy", command=self._copy_full_hex,
            style="TButton"
        )
        self._copy_hex_btn.pack(side=tk.RIGHT)
        _Tooltip(self._copy_hex_btn, "Copy full hex string to clipboard")

        self._hex_canvas = tk.Text(
            display_frame, height=2,
            font=("Consolas", 15, "bold"),
            bg=THEME["header_bg"], fg=text,
            state=tk.DISABLED, wrap=tk.NONE,
            relief="flat", borderwidth=0,
            padx=8, pady=6,
            cursor="arrow",
            selectbackground=THEME["select_bg"]
        )
        self._hex_canvas.grid(row=1, column=0, sticky="ew", pady=(0, 8))

        # Search / filter bar
        filter_row = tk.Frame(display_frame, bg=bg)
        filter_row.grid(row=2, column=0, sticky="ew", pady=(0, 4))
        tk.Label(filter_row, text="🔍 Filter:", fg=subtext, bg=bg,
                 font=("Segoe UI", 9)).pack(side=tk.LEFT)
        self._filter_entry = ttk.Entry(
            filter_row, textvariable=self._filter_var, width=24)
        self._filter_entry.pack(side=tk.LEFT, padx=(4, 6))
        self._filter_var.trace_add("write", lambda *_: self._refresh_tree())
        ttk.Button(filter_row, text="✕ Clear",
                   command=lambda: self._filter_var.set("")).pack(side=tk.LEFT)

        # Parameter table
        table_frame = tk.Frame(display_frame, bg=bg)
        table_frame.grid(row=3, column=0, sticky="nsew")
        display_frame.rowconfigure(3, weight=1)

        cols = ("Parameter", "HEX", "HEX Inverted", "Decimal")
        self._tree = ttk.Treeview(
            table_frame, columns=cols, show="headings",
            height=9, selectmode="browse"
        )
        for col in cols:
            self._tree.heading(col, text=col)
            self._tree.column(col, width=150, anchor=tk.CENTER)
        self._tree.column("Parameter", width=220, anchor=tk.W)
        self._tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._tree.bind("<<TreeviewSelect>>", self._on_tree_select)

        vsb = ttk.Scrollbar(table_frame, orient=tk.VERTICAL,
                            command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)

        # ── Right: edit panel ────────────────────────────────────────
        edit_outer = ttk.LabelFrame(mid_frame, text="  Edit Parameter  ",
                                    padding=(12, 10))
        edit_outer.grid(row=0, column=1, sticky="ns")
        edit_outer.columnconfigure(1, weight=1)

        row = 0

        ttk.Label(edit_outer, text="Parameter:", foreground=subtext).grid(
            row=row, column=0, sticky=tk.W, pady=3)
        self._param_combo = ttk.Combobox(
            edit_outer, textvariable=self._param_var, state="readonly", width=22,
            values=[name for _, name in SCHEMA]
        )
        self._param_combo.grid(row=row, column=1, sticky=tk.W, pady=3, padx=(6, 0))
        self._param_combo.bind("<<ComboboxSelected>>", self._on_param_selected)
        row += 1

        # Tooltip / description label
        self._desc_label = tk.Label(
            edit_outer, text="", fg=THEME["subtext"], bg=bg,
            font=("Segoe UI", 8, "italic"), wraplength=220, justify=tk.LEFT
        )
        self._desc_label.grid(row=row, column=0, columnspan=2, sticky=tk.W, pady=(0, 4))
        row += 1

        ttk.Separator(edit_outer, orient=tk.HORIZONTAL).grid(
            row=row, column=0, columnspan=2, sticky=tk.EW, pady=4)
        row += 1

        ttk.Label(edit_outer, text="Format:", foreground=subtext).grid(
            row=row, column=0, sticky=tk.NW, pady=3)
        fmt_frame = tk.Frame(edit_outer, bg=bg)
        fmt_frame.grid(row=row, column=1, sticky=tk.W, padx=(6, 0))
        for fmt in ("HEX", "HEX INVERTED", "DECIMAL"):
            ttk.Radiobutton(
                fmt_frame, text=fmt, variable=self._format_var, value=fmt,
                command=self._on_format_changed
            ).pack(anchor=tk.W, pady=1)
        row += 1

        ttk.Separator(edit_outer, orient=tk.HORIZONTAL).grid(
            row=row, column=0, columnspan=2, sticky=tk.EW, pady=4)
        row += 1

        ttk.Label(edit_outer, text="New value:", foreground=subtext).grid(
            row=row, column=0, sticky=tk.W, pady=3)
        self._input_entry = ttk.Entry(
            edit_outer, textvariable=self._input_var, width=22,
            font=("Consolas", 11)
        )
        self._input_entry.grid(row=row, column=1, sticky=tk.EW, pady=3, padx=(6, 0))
        self._input_entry.bind("<Return>", lambda _e: self._apply_edit())
        row += 1

        self._apply_btn = ttk.Button(
            edit_outer, text="✔  Apply", command=self._apply_edit,
            style="Accent.TButton"
        )
        self._apply_btn.grid(row=row, column=0, columnspan=2, pady=8, sticky=tk.EW)
        row += 1

        # Error / validation label
        self._error_label = tk.Label(
            edit_outer, text="", fg=THEME["red"], bg=bg,
            wraplength=220, font=("Segoe UI", 9), justify=tk.LEFT
        )
        self._error_label.grid(row=row, column=0, columnspan=2, sticky=tk.W)
        row += 1

        ttk.Separator(edit_outer, orient=tk.HORIZONTAL).grid(
            row=row, column=0, columnspan=2, sticky=tk.EW, pady=6)
        row += 1

        # Preview panel
        preview_hdr = tk.Frame(edit_outer, bg=bg)
        preview_hdr.grid(row=row, column=0, columnspan=2, sticky=tk.EW)
        tk.Label(preview_hdr, text="Preview:", fg=subtext, bg=bg,
                 font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT)
        row += 1

        preview_box = tk.Frame(
            edit_outer, bg=THEME["surface"],
            relief="flat", borderwidth=0, pady=8, padx=8
        )
        preview_box.grid(row=row, column=0, columnspan=2, sticky=tk.EW,
                         pady=(2, 6))

        self._preview_hex = tk.Label(
            preview_box, text="HEX: —",
            bg=THEME["surface"], fg=subtext,
            font=("Consolas", 10), anchor=tk.W
        )
        self._preview_hex.pack(fill=tk.X)
        self._preview_inv = tk.Label(
            preview_box, text="Inv: —",
            bg=THEME["surface"], fg=subtext,
            font=("Consolas", 10), anchor=tk.W
        )
        self._preview_inv.pack(fill=tk.X)
        self._preview_dec = tk.Label(
            preview_box, text="Dec: —",
            bg=THEME["surface"], fg=subtext,
            font=("Consolas", 10), anchor=tk.W
        )
        self._preview_dec.pack(fill=tk.X)
        row += 1

        self._input_var.trace_add("write", self._on_input_changed)

        ttk.Separator(edit_outer, orient=tk.HORIZONTAL).grid(
            row=row, column=0, columnspan=2, sticky=tk.EW, pady=4)
        row += 1

        ttk.Button(
            edit_outer, text="⟳  Recalculate Checksum",
            command=self._recalculate_checksum,
            style="TButton"
        ).grid(row=row, column=0, columnspan=2, pady=4, sticky=tk.EW)
        row += 1

        ttk.Button(
            edit_outer, text="⧉  Copy Row HEX",
            command=self._copy_selected_hex,
            style="TButton"
        ).grid(row=row, column=0, columnspan=2, pady=2, sticky=tk.EW)

        # ── Bottom: status bar ────────────────────────────────────────
        status_bar = tk.Frame(self, bg=THEME["header_bg"], height=26)
        status_bar.pack(fill=tk.X, side=tk.BOTTOM)
        status_bar.pack_propagate(False)

        self._status_var = tk.StringVar(
            value="No file loaded. Use File → Open or File → New.")
        self._status_label = tk.Label(
            status_bar, textvariable=self._status_var,
            fg=subtext, bg=THEME["header_bg"],
            font=("Segoe UI", 9), anchor=tk.W, padx=10
        )
        self._status_label.pack(side=tk.LEFT, fill=tk.Y)

        # Keyboard shortcuts hint on the right
        tk.Label(
            status_bar,
            text=SHORTCUTS_HELP,
            fg=THEME["overlay"], bg=THEME["header_bg"],
            font=("Segoe UI", 8), anchor=tk.E, padx=10
        ).pack(side=tk.RIGHT, fill=tk.Y)

    # ------------------------------------------------------------------
    # File operations
    # ------------------------------------------------------------------

    def _new_file(self):
        if not self._confirm_discard():
            return
        self._nfc_file = None
        self._current_path = None
        self._current_block = 0
        self._load_hex_string("00" * 16)
        self._refresh_metadata()
        self._modified = False
        self._undo_stack.clear()
        self._redo_stack.clear()
        self._update_title()
        self._update_status()

    def _open_file(self):
        if not self._confirm_discard():
            return
        path = filedialog.askopenfilename(
            title="Open Flipper Zero NFC file",
            filetypes=[("NFC files", "*.nfc"), ("All files", "*.*")]
        )
        if not path:
            return
        try:
            nfc = NFCFile.from_file(path)
        except Exception as exc:
            messagebox.showerror("Error", f"Could not read file:\n{exc}")
            return

        self._nfc_file = nfc
        self._current_path = path
        self._modified = False
        self._undo_stack.clear()
        self._redo_stack.clear()

        # Populate block spinbox choices
        blocks = nfc.available_blocks
        self._block_spinbox.configure(values=blocks if blocks else [0])
        if blocks:
            self._block_spinbox.set(blocks[0])
            self._current_block = blocks[0]
        else:
            self._current_block = 0

        self._load_block()
        self._refresh_metadata()
        self._update_title()
        self._update_status()

    def _load_block(self):
        try:
            block = int(self._block_spinbox.get())
        except ValueError:
            messagebox.showerror("Error", "Block number must be an integer.")
            return
        self._current_block = block

        if self._nfc_file is not None:
            hex_str = self._nfc_file.get_block_hex(block)
            if hex_str is None:
                messagebox.showwarning(
                    "Block not found",
                    f"Block {block} is not present in the file.\nDisplaying zeros."
                )
                hex_str = "00" * 16
        else:
            hex_str = "00" * 16

        self._load_hex_string(hex_str)
        self._update_status()

    def _save_file(self):
        if self._current_path is None:
            self._save_file_as()
            return
        self._do_save(self._current_path)

    def _save_file_as(self):
        path = filedialog.asksaveasfilename(
            title="Save NFC file",
            defaultextension=".nfc",
            filetypes=[("NFC files", "*.nfc"), ("All files", "*.*")]
        )
        if not path:
            return
        self._current_path = path
        self._do_save(path)

    def _do_save(self, path):
        if self._parsed_data is None:
            messagebox.showwarning("Nothing to save", "No data loaded.")
            return
        new_hex = parsed_to_hex_string(self._parsed_data)
        if self._nfc_file is None:
            self._nfc_file = NFCFile.create_minimal(self._current_block)
        try:
            self._nfc_file.set_block_hex(new_hex, self._current_block)
            self._nfc_file.save(path)
        except Exception as exc:
            messagebox.showerror("Save Error", f"Could not save file:\n{exc}")
            return
        self._modified = False
        self._update_title()
        self._update_status()

    def _export_json(self):
        if self._parsed_data is None:
            messagebox.showwarning("No data", "Load a file or create new data first.")
            return
        path = filedialog.asksaveasfilename(
            title="Export JSON",
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(parsed_to_json(self._parsed_data))
            self._set_status(f"Exported JSON → {path}")
        except Exception as exc:
            messagebox.showerror("Export Error", f"Could not export JSON:\n{exc}")

    def _export_html(self):
        if self._parsed_data is None:
            messagebox.showwarning("No data", "Load a file or create new data first.")
            return
        path = filedialog.asksaveasfilename(
            title="Export HTML Report",
            defaultextension=".html",
            filetypes=[("HTML files", "*.html"), ("All files", "*.*")]
        )
        if not path:
            return
        try:
            html = parsed_to_html(
                self._parsed_data,
                file_path=self._current_path,
                block=self._current_block
            )
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(html)
            self._set_status(f"Exported HTML → {path}")
        except Exception as exc:
            messagebox.showerror("Export Error", f"Could not export HTML:\n{exc}")

    # ------------------------------------------------------------------
    # Clipboard helpers
    # ------------------------------------------------------------------

    def _copy_full_hex(self):
        if self._parsed_data is None:
            return
        hex_str = parsed_to_hex_string(self._parsed_data)
        self.clipboard_clear()
        self.clipboard_append(hex_str)
        self._set_status(f"Copied to clipboard: {hex_str}")

    def _copy_selected_hex(self):
        sel = self._tree.selection()
        if not sel:
            self._set_status("No row selected.")
            return
        idx = self._tree.index(sel[0])
        if self._parsed_data is None or idx >= len(self._parsed_data):
            return
        _, seg, _, inv, dec = self._parsed_data[idx]
        value = f"HEX={seg}  INV={inv}  DEC={dec}"
        self.clipboard_clear()
        self.clipboard_append(value)
        self._set_status(f"Copied: {value}")

    # ------------------------------------------------------------------
    # Data loading / display
    # ------------------------------------------------------------------

    def _load_hex_string(self, hex_string):
        hex_string = hex_string.upper().replace(" ", "")
        self._parsed_data = color_string(hex_string)
        self._refresh_display()

    def _refresh_display(self):
        if self._parsed_data is None:
            return
        self._refresh_hex_canvas()
        self._refresh_tree()

    def _refresh_hex_canvas(self):
        canvas = self._hex_canvas
        canvas.configure(state=tk.NORMAL)
        canvas.delete("1.0", tk.END)
        for i, (_, seg, _, _, _) in enumerate(self._parsed_data):
            color = COLOR_PALETTE[i % len(COLOR_PALETTE)]
            tag = f"param_{i}"
            canvas.tag_configure(tag, foreground=color)
            canvas.insert(tk.END, seg, tag)
        canvas.configure(state=tk.DISABLED)

    def _refresh_tree(self):
        self._tree.delete(*self._tree.get_children())
        if self._parsed_data is None:
            return
        filter_text = self._filter_var.get().lower()
        for i, (desc, seg, _, inv, dec) in enumerate(self._parsed_data):
            if filter_text and filter_text not in desc.lower():
                continue
            color = COLOR_PALETTE[i % len(COLOR_PALETTE)]
            row_bg = THEME["row_even"] if i % 2 == 0 else THEME["row_odd"]
            tag_name = f"row_{i}"
            self._tree.insert(
                "", tk.END,
                values=(desc, seg, inv, dec),
                tags=(tag_name,)
            )
            self._tree.tag_configure(
                tag_name,
                foreground=color,
                background=row_bg
            )

    def _refresh_metadata(self):
        subtext = THEME["subtext"]
        accent = THEME["accent"]
        bg = THEME["bg"]

        if self._nfc_file is None:
            for lbl in (self._uid_label, self._atqa_label,
                        self._sak_label, self._type_label):
                lbl.config(fg=subtext)
            self._uid_label.config(text="UID: —")
            self._atqa_label.config(text="ATQA: —")
            self._sak_label.config(text="SAK: —")
            self._type_label.config(text="Type: —")
        else:
            uid = self._nfc_file.uid or "—"
            atqa = self._nfc_file.atqa or "—"
            sak = self._nfc_file.sak or "—"
            ctype = self._nfc_file.card_type or "—"
            self._uid_label.config(text=f"UID: {uid}", fg=accent)
            self._atqa_label.config(text=f"ATQA: {atqa}", fg=accent)
            self._sak_label.config(text=f"SAK: {sak}", fg=accent)
            self._type_label.config(text=f"Type: {ctype}", fg=accent)

    # ------------------------------------------------------------------
    # Edit panel interactions
    # ------------------------------------------------------------------

    def _on_tree_select(self, _event=None):
        sel = self._tree.selection()
        if not sel:
            return
        # Find the actual index from displayed values (filter may hide rows)
        values = self._tree.item(sel[0], "values")
        if not values:
            return
        param_name = values[0]
        idx = next((i for i, (_, n) in enumerate(SCHEMA) if n == param_name), 0)
        self._param_var.set(param_name)
        self._populate_edit_from_index(idx)
        self._update_desc_label(param_name)

    def _on_param_selected(self, _event=None):
        name = self._param_var.get()
        idx = next((i for i, (_, n) in enumerate(SCHEMA) if n == name), 0)
        self._populate_edit_from_index(idx)
        self._update_desc_label(name)

    def _update_desc_label(self, name):
        desc = PARAM_DESCRIPTIONS.get(name, "")
        self._desc_label.config(text=desc)

    def _populate_edit_from_index(self, idx):
        if self._parsed_data is None:
            return
        _, seg, _, inv, dec = self._parsed_data[idx]
        fmt = self._format_var.get()
        if fmt == "HEX":
            self._input_var.set(seg)
        elif fmt == "HEX INVERTED":
            self._input_var.set(inv)
        else:
            self._input_var.set(str(dec))
        self._error_label.config(text="")

    def _on_format_changed(self):
        name = self._param_var.get()
        idx = next((i for i, (_, n) in enumerate(SCHEMA) if n == name), 0)
        self._populate_edit_from_index(idx)

    def _current_param_index(self):
        name = self._param_var.get()
        return next((i for i, (_, n) in enumerate(SCHEMA) if n == name), 0)

    def _on_input_changed(self, *_args):
        """Live preview as the user types."""
        if self._parsed_data is None:
            return
        idx = self._current_param_index()
        value = self._input_var.get().strip()
        fmt = self._format_var.get()
        try:
            preview = apply_edit(self._parsed_data, idx, value, fmt)
            _, hex_val, _, inv_val, dec_val = preview[idx]
            color = THEME["green"]
            self._preview_hex.config(text=f"HEX:  {hex_val}", fg=color)
            self._preview_inv.config(text=f"Inv:  {inv_val}", fg=color)
            self._preview_dec.config(text=f"Dec:  {dec_val}", fg=color)
            self._error_label.config(text="")
        except Exception:
            dim = THEME["subtext"]
            self._preview_hex.config(text="HEX:  —", fg=dim)
            self._preview_inv.config(text="Inv:  —", fg=dim)
            self._preview_dec.config(text="Dec:  —", fg=dim)

    def _apply_edit(self):
        if self._parsed_data is None:
            messagebox.showinfo("No data", "Load a file or create new data first.")
            return
        idx = self._current_param_index()
        value = self._input_var.get().strip()
        fmt = self._format_var.get()
        try:
            new_parsed = apply_edit(self._parsed_data, idx, value, fmt)
        except ValueError as exc:
            self._error_label.config(
                text=f"⚠  {exc}", fg=THEME["red"])
            return

        self._push_undo()
        self._parsed_data = new_parsed
        self._modified = True
        self._refresh_display()
        self._error_label.config(text="✔  Applied", fg=THEME["green"])
        self._update_title()
        self._update_status()

    # ------------------------------------------------------------------
    # Checksum
    # ------------------------------------------------------------------

    def _recalculate_checksum(self):
        if self._parsed_data is None:
            messagebox.showinfo("No data", "Load a file or create new data first.")
            return
        checksum_hex = compute_checksum(self._parsed_data)
        checksum_idx = len(SCHEMA) - 1  # last parameter
        try:
            new_parsed = apply_edit(self._parsed_data, checksum_idx, checksum_hex, "HEX")
        except ValueError as exc:
            messagebox.showerror("Checksum Error", str(exc))
            return
        self._push_undo()
        self._parsed_data = new_parsed
        self._modified = True
        self._refresh_display()
        self._update_title()
        self._update_status()
        self._set_status(f"Checksum recalculated: {checksum_hex}")

    # ------------------------------------------------------------------
    # Undo / Redo
    # ------------------------------------------------------------------

    def _push_undo(self):
        if self._parsed_data is not None:
            self._undo_stack.append(copy.deepcopy(self._parsed_data))
            if len(self._undo_stack) > MAX_UNDO:
                self._undo_stack.pop(0)
            self._redo_stack.clear()

    def _undo(self):
        if not self._undo_stack:
            return
        self._redo_stack.append(copy.deepcopy(self._parsed_data))
        self._parsed_data = self._undo_stack.pop()
        self._modified = True
        self._refresh_display()
        self._update_title()
        self._update_status()

    def _redo(self):
        if not self._redo_stack:
            return
        self._undo_stack.append(copy.deepcopy(self._parsed_data))
        self._parsed_data = self._redo_stack.pop()
        self._modified = True
        self._refresh_display()
        self._update_title()
        self._update_status()

    # ------------------------------------------------------------------
    # Status / title helpers
    # ------------------------------------------------------------------

    def _update_title(self):
        dirty = " *" if self._modified else ""
        name = os.path.basename(self._current_path) if self._current_path else "Untitled"
        self.title(f"{APP_TITLE} — {name}{dirty}")

    def _update_status(self):
        if self._current_path:
            name = os.path.basename(self._current_path)
            block_info = f"  │  Block: {self._current_block}"
            if self._modified:
                mod_info = "  │  ● Unsaved changes"
                self._state_dot.config(fg=THEME["orange"])
            else:
                mod_info = "  │  ✔ Saved"
                self._state_dot.config(fg=THEME["green"])
        else:
            name = "No file loaded"
            block_info = ""
            mod_info = ""
            self._state_dot.config(fg=THEME["subtext"])
        self._status_var.set(f"{name}{block_info}{mod_info}")

    def _set_status(self, message):
        """Temporarily override the status bar message."""
        self._status_var.set(message)
        self.after(4000, self._update_status)

    # ------------------------------------------------------------------
    # Quit
    # ------------------------------------------------------------------

    def _confirm_discard(self):
        if self._modified:
            return messagebox.askyesno(
                "Unsaved Changes",
                "You have unsaved changes. Discard them?"
            )
        return True

    def _quit(self):
        if not self._confirm_discard():
            return
        self.destroy()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    app = MicroELApp()
    app.mainloop()


if __name__ == "__main__":
    main()
