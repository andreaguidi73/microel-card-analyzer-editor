"""
mct_file_handler.py
Handles reading and writing MIFARE Classic Tool (.mct) files.

MCT files use a plain-text format where each sector is preceded by a
``+Sector: N`` header line, and each block is a 32-character hex string
(no spaces).  Lines beginning with ``#`` are treated as comments.

Example::

    # Cardnumber:
    # Date:
    +Sector: 0
    2CA12E001208040062636465666768
    00000000000000000000000000000000
    00000000000000000000000000000000
    FFFFFFFFFFFFFF078069FFFFFFFFFFFF
    +Sector: 1
    00000000000000000000000000000000
    ...

Absolute block numbers follow the standard Mifare Classic 1K layout:
    - Sector N starts at absolute block N * 4

The public API mirrors :class:`nfc_file_handler.NFCFile` so that callers
can treat both file types uniformly.
"""

import re


class MCTFile:
    """Represents a MIFARE Classic Tool .mct file."""

    BLOCKS_PER_SECTOR = 4

    def __init__(self):
        self.comments = []        # lines that start with '#'
        self.blocks = {}          # absolute block_number (int) -> list of 16 int bytes
        self._sector_order = []   # list of sector numbers, in the order they appear

    # ------------------------------------------------------------------
    # Reading
    # ------------------------------------------------------------------

    @classmethod
    def from_file(cls, path):
        """Load a .mct file from *path* and return an MCTFile instance."""
        with open(path, "r", encoding="utf-8") as fh:
            content = fh.read()
        return cls.from_string(content)

    @classmethod
    def from_string(cls, content):
        """Parse *content* (string) and return an MCTFile instance."""
        obj = cls()
        sector_re = re.compile(r"^\+Sector:\s*(\d+)", re.IGNORECASE)

        current_sector = None
        current_block_in_sector = 0

        for line in content.splitlines():
            stripped = line.strip()

            if not stripped:
                continue

            if stripped.startswith("#"):
                obj.comments.append(stripped)
                continue

            m = sector_re.match(stripped)
            if m:
                current_sector = int(m.group(1))
                current_block_in_sector = 0
                if current_sector not in obj._sector_order:
                    obj._sector_order.append(current_sector)
                continue

            if current_sector is None:
                # Data line before any sector header — skip gracefully
                continue

            # Expect a 32-char hex string (spaces stripped)
            hex_str = stripped.replace(" ", "")
            if len(hex_str) == 32:
                try:
                    byte_values = [int(hex_str[i: i + 2], 16) for i in range(0, 32, 2)]
                except ValueError:
                    byte_values = [0] * 16

                abs_block = current_sector * cls.BLOCKS_PER_SECTOR + current_block_in_sector
                obj.blocks[abs_block] = byte_values
                current_block_in_sector += 1

        return obj

    # ------------------------------------------------------------------
    # Block data access  (same interface as NFCFile)
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
        # Ensure the sector containing this block appears in sector_order
        sector = block_number // self.BLOCKS_PER_SECTOR
        if sector not in self._sector_order:
            self._sector_order.append(sector)

    # ------------------------------------------------------------------
    # Metadata helpers  (same interface as NFCFile, stubs for MCT)
    # ------------------------------------------------------------------

    @property
    def uid(self):
        """MCT files do not store UID metadata; returns empty string."""
        return ""

    @property
    def atqa(self):
        """MCT files do not store ATQA metadata; returns empty string."""
        return ""

    @property
    def sak(self):
        """MCT files do not store SAK metadata; returns empty string."""
        return ""

    @property
    def card_type(self):
        """MCT files do not store card-type metadata; returns empty string."""
        return ""

    @property
    def available_blocks(self):
        """Return a sorted list of absolute block numbers present in the file."""
        return sorted(self.blocks.keys())

    # ------------------------------------------------------------------
    # Writing
    # ------------------------------------------------------------------

    def to_string(self):
        """Serialise the MCTFile back to a .mct-formatted string."""
        lines = []
        # Write comments first
        for c in self.comments:
            lines.append(c)

        for sector in sorted(self._sector_order):
            lines.append(f"+Sector: {sector}")
            for block_in_sector in range(self.BLOCKS_PER_SECTOR):
                abs_block = sector * self.BLOCKS_PER_SECTOR + block_in_sector
                if abs_block in self.blocks:
                    byte_str = "".join(f"{b:02X}" for b in self.blocks[abs_block])
                    lines.append(byte_str)
                else:
                    lines.append("00" * 16)

        return "\n".join(lines) + "\n"

    def save(self, path):
        """Write the .mct file to *path*."""
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(self.to_string())

    @classmethod
    def create_minimal(cls, block_number=0):
        """Return a minimal MCTFile with one sector containing *block_number*."""
        obj = cls()
        sector = block_number // cls.BLOCKS_PER_SECTOR
        obj._sector_order = [sector]
        # Initialise the sector with zero blocks
        for i in range(cls.BLOCKS_PER_SECTOR):
            obj.blocks[sector * cls.BLOCKS_PER_SECTOR + i] = [0] * 16
        return obj
