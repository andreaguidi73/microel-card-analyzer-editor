"""
nfc_file_handler.py
Handles reading and writing Flipper Zero .nfc files.

Flipper Zero .nfc files use a plain-text INI-like format, for example:

    Filetype: Flipper NFC device
    Version: 4
    UID: 2C A1 2E 00
    ATQA: 00 04
    SAK: 08
    Block 0: 2C A1 2E 00 12 08 04 00 62 63 64 65 66 67 68 69
    Block 1: 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
    ...

Each block contains 16 bytes (32 hex characters) separated by spaces.
"""

import re


class NFCFile:
    """Represents a Flipper Zero .nfc file."""

    def __init__(self):
        self.metadata = {}   # ordered key -> value pairs for non-block lines
        self.blocks = {}     # block_number (int) -> list of 16 int bytes
        self._line_order = []  # preserves original line order for round-trip writes

    # ------------------------------------------------------------------
    # Reading
    # ------------------------------------------------------------------

    @classmethod
    def from_file(cls, path):
        """Load a .nfc file from *path* and return an NFCFile instance."""
        with open(path, "r", encoding="utf-8") as fh:
            content = fh.read()
        return cls.from_string(content)

    @classmethod
    def from_string(cls, content):
        """Parse *content* (string) and return an NFCFile instance."""
        obj = cls()
        block_re = re.compile(r"^Block\s+(\d+)\s*:\s*(.+)$", re.IGNORECASE)

        for line in content.splitlines():
            stripped = line
            if not stripped or stripped.startswith("#"):
                obj._line_order.append(("raw", stripped))
                continue

            m = block_re.match(stripped)
            if m:
                block_num = int(m.group(1))
                byte_strs = m.group(2).strip().split()
                try:
                    byte_values = [int(b, 16) for b in byte_strs]
                except ValueError:
                    byte_values = []
                obj.blocks[block_num] = byte_values
                obj._line_order.append(("block", block_num))
                continue

            if ":" in stripped:
                key, _, value = stripped.partition(":")
                key = key.strip()
                value = value.strip()
                obj.metadata[key] = value
                obj._line_order.append(("meta", key))
            else:
                obj._line_order.append(("raw", stripped))

        return obj

    # ------------------------------------------------------------------
    # Block data access
    # ------------------------------------------------------------------

    def get_block_hex(self, block_number=0):
        """Return the 32-character hex string for *block_number*.

        Returns None if the block is not present in the file.
        """
        if block_number not in self.blocks:
            return None
        return "".join(f"{b:02X}" for b in self.blocks[block_number])

    def set_block_hex(self, hex_string, block_number=0):
        """Update *block_number* with the data encoded in *hex_string*.

        *hex_string* must be exactly 32 uppercase or lowercase hex characters.
        """
        hex_string = hex_string.upper().replace(" ", "")
        if len(hex_string) != 32:
            raise ValueError(
                f"hex_string must be 32 characters long, got {len(hex_string)}"
            )
        try:
            byte_values = [int(hex_string[i: i + 2], 16) for i in range(0, 32, 2)]
        except ValueError as exc:
            raise ValueError(f"Invalid hex string: {hex_string!r}") from exc
        self.blocks[block_number] = byte_values
        if ("block", block_number) not in self._line_order:
            self._line_order.append(("block", block_number))

    # ------------------------------------------------------------------
    # Metadata helpers
    # ------------------------------------------------------------------

    @property
    def uid(self):
        return self.metadata.get("UID", "")

    @property
    def atqa(self):
        return self.metadata.get("ATQA", "")

    @property
    def sak(self):
        return self.metadata.get("SAK", "")

    @property
    def card_type(self):
        return self.metadata.get("Mifare Classic type", self.metadata.get("Card type", ""))

    @property
    def available_blocks(self):
        """Return a sorted list of block numbers present in the file."""
        return sorted(self.blocks.keys())

    # ------------------------------------------------------------------
    # Writing
    # ------------------------------------------------------------------

    def to_string(self):
        """Serialise the NFCFile back to a .nfc-formatted string."""
        lines = []
        for entry in self._line_order:
            kind = entry[0]
            if kind == "raw":
                lines.append(entry[1])
            elif kind == "meta":
                key = entry[1]
                lines.append(f"{key}: {self.metadata[key]}")
            elif kind == "block":
                block_num = entry[1]
                if block_num in self.blocks:
                    byte_str = " ".join(f"{b:02X}" for b in self.blocks[block_num])
                    lines.append(f"Block {block_num}: {byte_str}")
        return "\n".join(lines) + "\n"

    def save(self, path):
        """Write the .nfc file to *path*."""
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(self.to_string())

    @classmethod
    def create_minimal(cls, block_number=0):
        """Return a minimal NFCFile with only a Filetype/Version header and one block."""
        obj = cls()
        obj.metadata["Filetype"] = "Flipper NFC device"
        obj.metadata["Version"] = "4"
        obj._line_order = [
            ("meta", "Filetype"),
            ("meta", "Version"),
            ("block", block_number),
        ]
        return obj
