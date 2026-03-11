"""
microel_gui.py
Comprehensive tkinter GUI for MicroEL Card Analyzer and Editor.
Supports loading, editing, and saving Flipper Zero .nfc files.
"""

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

# Colours matching the CLI colour scheme (ANSI → tkinter)
COLOR_PALETTE = ["#00FFFF", "#00CDCD", "#CD00CD", "#0000CD", "#CDCD00"]

APP_TITLE = "MicroEL Card Analyzer & Editor"
MAX_UNDO = 50


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


# ---------------------------------------------------------------------------
# Main application window
# ---------------------------------------------------------------------------

class MicroELApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.resizable(True, True)
        self.minsize(820, 640)

        self._nfc_file = None          # NFCFile instance
        self._current_path = None      # str path of the open file
        self._current_block = 0        # int block number
        self._parsed_data = None       # list of tuples from color_string()
        self._modified = False

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
        menubar = tk.Menu(self)
        self.config(menu=menubar)

        file_menu = tk.Menu(menubar, tearoff=False)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="New (blank data)", command=self._new_file, accelerator="Ctrl+N")
        file_menu.add_command(label="Open .nfc…", command=self._open_file, accelerator="Ctrl+O")
        file_menu.add_separator()
        file_menu.add_command(label="Save", command=self._save_file, accelerator="Ctrl+S")
        file_menu.add_command(label="Save As…", command=self._save_file_as, accelerator="Ctrl+Shift+S")
        file_menu.add_separator()
        file_menu.add_command(label="Quit", command=self._quit, accelerator="Ctrl+Q")

        edit_menu = tk.Menu(menubar, tearoff=False)
        menubar.add_cascade(label="Edit", menu=edit_menu)
        edit_menu.add_command(label="Undo", command=self._undo, accelerator="Ctrl+Z")
        edit_menu.add_command(label="Redo", command=self._redo, accelerator="Ctrl+Y")
        edit_menu.add_separator()
        edit_menu.add_command(label="Recalculate Checksum", command=self._recalculate_checksum)

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
        # ── Top: file info + block selector ──────────────────────────
        top_frame = ttk.LabelFrame(self, text="File & Block", padding=6)
        top_frame.pack(fill=tk.X, padx=8, pady=(8, 0))

        ttk.Label(top_frame, text="Block:").pack(side=tk.LEFT)
        self._block_var = tk.StringVar(value="0")
        self._block_spinbox = ttk.Spinbox(
            top_frame, from_=0, to=255, width=5, textvariable=self._block_var
        )
        self._block_spinbox.pack(side=tk.LEFT, padx=(2, 8))
        self._block_spinbox.bind("<Return>", lambda _e: self._load_block())
        ttk.Button(top_frame, text="Load Block", command=self._load_block).pack(side=tk.LEFT)

        # NFC metadata labels
        self._meta_frame = ttk.Frame(top_frame)
        self._meta_frame.pack(side=tk.RIGHT, padx=8)
        self._uid_label = ttk.Label(self._meta_frame, text="UID: —", foreground="gray")
        self._uid_label.grid(row=0, column=0, padx=4)
        self._atqa_label = ttk.Label(self._meta_frame, text="ATQA: —", foreground="gray")
        self._atqa_label.grid(row=0, column=1, padx=4)
        self._sak_label = ttk.Label(self._meta_frame, text="SAK: —", foreground="gray")
        self._sak_label.grid(row=0, column=2, padx=4)
        self._type_label = ttk.Label(self._meta_frame, text="Type: —", foreground="gray")
        self._type_label.grid(row=0, column=3, padx=4)

        # ── Middle: hex display + parameter table ─────────────────────
        mid_frame = ttk.Frame(self)
        mid_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

        # Left: colour-coded hex string + parameter breakdown
        display_frame = ttk.LabelFrame(mid_frame, text="Data Display", padding=6)
        display_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Full hex string (colour-coded)
        ttk.Label(display_frame, text="Full hex string:").pack(anchor=tk.W)
        self._hex_canvas = tk.Text(
            display_frame, height=2, font=("Courier", 14, "bold"),
            bg="#1e1e1e", fg="white", state=tk.DISABLED, wrap=tk.NONE
        )
        self._hex_canvas.pack(fill=tk.X, pady=(0, 6))

        # Parameter table
        cols = ("Parameter", "HEX", "HEX Inverted", "Decimal")
        self._tree = ttk.Treeview(
            display_frame, columns=cols, show="headings", height=9, selectmode="browse"
        )
        for col in cols:
            self._tree.heading(col, text=col)
            self._tree.column(col, width=160, anchor=tk.CENTER)
        self._tree.column("Parameter", width=200, anchor=tk.W)
        self._tree.pack(fill=tk.BOTH, expand=True)
        self._tree.bind("<<TreeviewSelect>>", self._on_tree_select)

        # Scrollbar for table
        vsb = ttk.Scrollbar(display_frame, orient=tk.VERTICAL, command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)

        # Right: edit panel
        edit_frame = ttk.LabelFrame(mid_frame, text="Edit Parameter", padding=8)
        edit_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=(8, 0))

        ttk.Label(edit_frame, text="Parameter:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self._param_combo = ttk.Combobox(
            edit_frame, textvariable=self._param_var, state="readonly", width=22,
            values=[name for _, name in SCHEMA]
        )
        self._param_combo.grid(row=0, column=1, sticky=tk.W, pady=2)
        self._param_combo.bind("<<ComboboxSelected>>", self._on_param_selected)

        ttk.Label(edit_frame, text="Format:").grid(row=1, column=0, sticky=tk.W, pady=2)
        fmt_frame = ttk.Frame(edit_frame)
        fmt_frame.grid(row=1, column=1, sticky=tk.W)
        for fmt in ("HEX", "HEX INVERTED", "DECIMAL"):
            ttk.Radiobutton(
                fmt_frame, text=fmt, variable=self._format_var, value=fmt,
                command=self._on_format_changed
            ).pack(anchor=tk.W)

        ttk.Label(edit_frame, text="New value:").grid(row=2, column=0, sticky=tk.W, pady=2)
        self._input_entry = ttk.Entry(edit_frame, textvariable=self._input_var, width=24)
        self._input_entry.grid(row=2, column=1, sticky=tk.W, pady=2)
        self._input_entry.bind("<Return>", lambda _e: self._apply_edit())

        self._apply_btn = ttk.Button(edit_frame, text="Apply", command=self._apply_edit)
        self._apply_btn.grid(row=3, column=0, columnspan=2, pady=8)

        self._error_label = ttk.Label(edit_frame, text="", foreground="red", wraplength=200)
        self._error_label.grid(row=4, column=0, columnspan=2, sticky=tk.W)

        ttk.Separator(edit_frame, orient=tk.HORIZONTAL).grid(
            row=5, column=0, columnspan=2, sticky=tk.EW, pady=6
        )

        # Preview inside edit panel
        ttk.Label(edit_frame, text="Preview:").grid(row=6, column=0, sticky=tk.NW, pady=2)
        self._preview_frame = ttk.Frame(edit_frame)
        self._preview_frame.grid(row=6, column=1, sticky=tk.W)
        self._preview_hex = ttk.Label(self._preview_frame, text="HEX: —", font=("Courier", 10))
        self._preview_hex.pack(anchor=tk.W)
        self._preview_inv = ttk.Label(self._preview_frame, text="Inv: —", font=("Courier", 10))
        self._preview_inv.pack(anchor=tk.W)
        self._preview_dec = ttk.Label(self._preview_frame, text="Dec: —", font=("Courier", 10))
        self._preview_dec.pack(anchor=tk.W)

        self._input_var.trace_add("write", self._on_input_changed)

        ttk.Separator(edit_frame, orient=tk.HORIZONTAL).grid(
            row=7, column=0, columnspan=2, sticky=tk.EW, pady=6
        )
        ttk.Button(
            edit_frame, text="Recalculate Checksum", command=self._recalculate_checksum
        ).grid(row=8, column=0, columnspan=2)

        # ── Bottom: status bar ────────────────────────────────────────
        self._status_var = tk.StringVar(value="No file loaded. Use File → Open or File → New.")
        status_bar = ttk.Label(
            self, textvariable=self._status_var, relief=tk.SUNKEN, anchor=tk.W, padding=(4, 2)
        )
        status_bar.pack(fill=tk.X, side=tk.BOTTOM, padx=0, pady=0)

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
        for i, (desc, seg, _, inv, dec) in enumerate(self._parsed_data):
            color = COLOR_PALETTE[i % len(COLOR_PALETTE)]
            iid = self._tree.insert(
                "", tk.END,
                values=(desc, seg, inv, dec),
                tags=(f"color_{i}",)
            )
            self._tree.tag_configure(f"color_{i}", foreground=color)

    def _refresh_metadata(self):
        if self._nfc_file is None:
            self._uid_label.config(text="UID: —", foreground="gray")
            self._atqa_label.config(text="ATQA: —", foreground="gray")
            self._sak_label.config(text="SAK: —", foreground="gray")
            self._type_label.config(text="Type: —", foreground="gray")
        else:
            uid = self._nfc_file.uid or "—"
            atqa = self._nfc_file.atqa or "—"
            sak = self._nfc_file.sak or "—"
            ctype = self._nfc_file.card_type or "—"
            self._uid_label.config(text=f"UID: {uid}", foreground="white")
            self._atqa_label.config(text=f"ATQA: {atqa}", foreground="white")
            self._sak_label.config(text=f"SAK: {sak}", foreground="white")
            self._type_label.config(text=f"Type: {ctype}", foreground="white")

    # ------------------------------------------------------------------
    # Edit panel interactions
    # ------------------------------------------------------------------

    def _on_tree_select(self, _event=None):
        sel = self._tree.selection()
        if not sel:
            return
        idx = self._tree.index(sel[0])
        param_name = SCHEMA[idx][1]
        self._param_var.set(param_name)
        self._populate_edit_from_index(idx)

    def _on_param_selected(self, _event=None):
        name = self._param_var.get()
        idx = next((i for i, (_, n) in enumerate(SCHEMA) if n == name), 0)
        self._populate_edit_from_index(idx)

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
            self._preview_hex.config(text=f"HEX: {hex_val}", foreground="lightgreen")
            self._preview_inv.config(text=f"Inv: {inv_val}", foreground="lightgreen")
            self._preview_dec.config(text=f"Dec: {dec_val}", foreground="lightgreen")
            self._error_label.config(text="")
        except Exception:
            self._preview_hex.config(text="HEX: —", foreground="gray")
            self._preview_inv.config(text="Inv: —", foreground="gray")
            self._preview_dec.config(text="Dec: —", foreground="gray")

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
            self._error_label.config(text=str(exc))
            return

        self._push_undo()
        self._parsed_data = new_parsed
        self._modified = True
        self._refresh_display()
        self._error_label.config(text="")
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
        messagebox.showinfo("Checksum", f"Checksum recalculated: {checksum_hex}")

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
            path_info = self._current_path
            block_info = f"  |  Block: {self._current_block}"
            mod_info = "  |  Modified" if self._modified else "  |  Saved"
        else:
            path_info = "No file"
            block_info = ""
            mod_info = ""
        self._status_var.set(f"{path_info}{block_info}{mod_info}")

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
