# MicroEL Card Analyzer and Editor

A Python toolkit for analysing, editing, and saving MicroEL card data — with full support for **Flipper Zero `.nfc` files** and a graphical user interface.

## Features

- Parse and display the contents of Sector 1, Rows 1‑3 of MicroEL cards.
- Modify specific parameters in HEX, HEX INVERTED, or DECIMAL format.
- **Load and save Flipper Zero `.nfc` files** (read/write block data).
- **GUI application** with colour-coded display, real-time previews, Undo/Redo, and checksum recalculation.

## Parameters

The script processes a 32-character hexadecimal string (16 bytes / one NFC block):

| # | Parameter | Length |
|---|-----------|--------|
| 1 | Operation number | 4 chars (2 bytes) |
| 2 | Total input sum | 4 chars (2 bytes) |
| 3 | Deposit | 2 chars (1 byte) |
| 4 | **Credit** | 4 chars (2 bytes) |
| 5 | Transaction date | 8 chars (4 bytes) |
| 6 | Points | 4 chars (2 bytes) |
| 7 | Last transaction amount | 4 chars (2 bytes) |
| 8 | Checksum | 2 chars (1 byte) |

## Files

| File | Description |
|------|-------------|
| `microel_card_analyzer.py` | Command-line analyzer and editor |
| `nfc_file_handler.py` | Flipper Zero `.nfc` file parser / writer |
| `microel_gui.py` | **Graphical user interface** (tkinter) |

## Requirements

- Python 3.6 or higher
- `tkinter` (included in standard Python installations)

## Usage

### GUI (recommended)

```bash
python microel_gui.py
```

**Workflow:**
1. **File → Open** — select a Flipper Zero `.nfc` file
2. Choose the block to analyse (default: block 0)
3. View colour-coded parameter breakdown
4. Click a row in the table to select a parameter for editing
5. Choose the input format (HEX / HEX INVERTED / DECIMAL) and enter a value
6. Click **Apply** (or press Enter) — a live preview appears before you commit
7. Use **Edit → Recalculate Checksum** to fix the checksum after edits
8. **File → Save** to write changes back to the `.nfc` file

### Command-line

```bash
# Analyse a hex string directly
python microel_card_analyzer.py "112233445566778899AABBCCDDEEFF00"

# Load a Flipper Zero .nfc file (default block 0)
python microel_card_analyzer.py -f my_card.nfc

# Load a specific block from an .nfc file
python microel_card_analyzer.py -f my_card.nfc -b 4
```

## Flipper Zero `.nfc` File Format

Flipper Zero saves cards as plain-text files with the following structure:

```
Filetype: Flipper NFC device
Version: 4
UID: 2C A1 2E 00
ATQA: 00 04
SAK: 08
Block 0: 2C A1 2E 00 12 08 04 00 62 63 64 65 66 67 68 69
Block 1: 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
...
```

Each block is 16 bytes (32 hex chars). The MicroEL credit data typically lives in the first block of Sector 1 (Block 4 in absolute terms).
