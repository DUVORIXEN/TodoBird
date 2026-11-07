"""
TODO BIRD — PURE-PYTHON ISO/IEC 18004 QR CODE GENERATOR & QT WIDGET
Generates genuine, phone-scannable QR codes (Versions 1–4, ECC Level L, Byte Mode)
using pure Python GF(256) Reed-Solomon error correction and renders them crisply via QPainter.
Zero external dependencies required.
"""

from typing import List, Tuple
from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QPainter, QColor

# Version capacities for ECC Level L (Byte mode):
# (version, size, total_data_codewords, ec_codewords_per_block, alignment_centers)
_VERSION_SPECS = [
    (1, 21, 19, 7, []),
    (2, 25, 34, 10, [6, 18]),
    (3, 29, 55, 15, [6, 22]),
    (4, 33, 80, 20, [6, 26]),
]


def _gf_tables() -> Tuple[List[int], List[int]]:
    exp = [0] * 512
    log = [0] * 256
    x = 1
    for i in range(255):
        exp[i] = x
        log[x] = i
        x <<= 1
        if x & 0x100:
            x ^= 0x11D
    for i in range(255, 512):
        exp[i] = exp[i - 255]
    return exp, log


_GF_EXP, _GF_LOG = _gf_tables()


def _gf_mul(a: int, b: int) -> int:
    if a == 0 or b == 0:
        return 0
    return _GF_EXP[_GF_LOG[a] + _GF_LOG[b]]


def _rs_generator_poly(degree: int) -> List[int]:
    poly = [1]
    for i in range(degree):
        next_poly = [0] * (len(poly) + 1)
        root = _GF_EXP[i]
        for j, coeff in enumerate(poly):
            next_poly[j] ^= coeff
            next_poly[j + 1] ^= _gf_mul(coeff, root)
        poly = next_poly
    return poly


def _rs_encode(data: List[int], ec_len: int) -> List[int]:
    gen = _rs_generator_poly(ec_len)
    res = list(data) + [0] * ec_len
    for i in range(len(data)):
        coef = res[i]
        if coef != 0:
            for j in range(1, len(gen)):
                res[i + j] ^= _gf_mul(gen[j], coef)
    return res[len(data):]


def encode_qr_matrix(text: str) -> List[List[bool]]:
    """
    Encodes a string (up to 78 UTF-8 bytes) into a standard ISO/IEC 18004 QR matrix (2D bool grid).
    """
    raw_bytes = text.encode("utf-8")
    if len(raw_bytes) > 78:
        raw_bytes = raw_bytes[:78]

    spec = _VERSION_SPECS[-1]
    for candidate in _VERSION_SPECS:
        # Byte mode overhead: 4 bits mode + 8 bits length = 12 bits (1.5 bytes) -> capacity = data_cw - 2
        if len(raw_bytes) <= candidate[2] - 2:
            spec = candidate
            break

    _ver, size, data_cw, ec_cw, align_centers = spec

    # Build bit stream: 0100 (Byte mode) + 8-bit length + data bytes + terminator
    bits: List[int] = [0, 1, 0, 0]
    for i in range(7, -1, -1):
        bits.append((len(raw_bytes) >> i) & 1)
    for b in raw_bytes:
        for i in range(7, -1, -1):
            bits.append((b >> i) & 1)

    max_bits = data_cw * 8
    for _ in range(min(4, max_bits - len(bits))):
        bits.append(0)
    while len(bits) % 8 != 0:
        bits.append(0)

    codewords: List[int] = []
    for i in range(0, len(bits), 8):
        val = 0
        for bit in bits[i:i + 8]:
            val = (val << 1) | bit
        codewords.append(val)

    pad_bytes = [0xEC, 0x11]
    pad_idx = 0
    while len(codewords) < data_cw:
        codewords.append(pad_bytes[pad_idx % 2])
        pad_idx += 1

    ec_codewords = _rs_encode(codewords, ec_cw)
    all_codewords = codewords + ec_codewords

    matrix = [[False] * size for _ in range(size)]
    reserved = [[False] * size for _ in range(size)]

    def set_func(r: int, c: int, dark: bool):
        if 0 <= r < size and 0 <= c < size:
            matrix[r][c] = dark
            reserved[r][c] = True

    # Finder patterns + separators
    for fr, fc in ((0, 0), (0, size - 7), (size - 7, 0)):
        for dr in range(-1, 8):
            for dc in range(-1, 8):
                rr, cc = fr + dr, fc + dc
                if 0 <= rr < size and 0 <= cc < size:
                    in_outer = (0 <= dr <= 6 and (dc in (0, 6) or dr in (0, 6)))
                    in_inner = (2 <= dr <= 4 and 2 <= dc <= 4)
                    set_func(rr, cc, in_outer or in_inner)

    # Alignment patterns
    for ar in align_centers:
        for ac in align_centers:
            if (ar == 6 and ac == 6) or (ar == 6 and ac == size - 7) or (ar == size - 7 and ac == 6):
                continue
            for dr in range(-2, 3):
                for dc in range(-2, 3):
                    dark = max(abs(dr), abs(dc)) in (0, 2)
                    set_func(ar + dr, ac + dc, dark)

    # Timing patterns
    for i in range(8, size - 8):
        set_func(6, i, i % 2 == 0)
        set_func(i, 6, i % 2 == 0)

    # Dark module & reserve format areas
    set_func(size - 8, 8, True)
    for i in range(9):
        if not reserved[8][i]:
            reserved[8][i] = True
        if not reserved[i][8]:
            reserved[i][8] = True
    for i in range(8):
        reserved[8][size - 1 - i] = True
        reserved[size - 1 - i][8] = True

    # Place data bits upward/downward in 2-column zig-zags
    full_bits: List[int] = []
    for cw in all_codewords:
        for i in range(7, -1, -1):
            full_bits.append((cw >> i) & 1)

    bit_idx = 0
    upward = True
    col = size - 1
    while col > 0:
        if col == 6:
            col -= 1
        row_iter = range(size - 1, -1, -1) if upward else range(size)
        for r in row_iter:
            for dc in (0, 1):
                c = col - dc
                if not reserved[r][c]:
                    bit = full_bits[bit_idx] if bit_idx < len(full_bits) else 0
                    bit_idx += 1
                    # Apply Mask Pattern 0: (r + c) % 2 == 0
                    if (r + c) % 2 == 0:
                        bit ^= 1
                    matrix[r][c] = bool(bit)
        upward = not upward
        col -= 2

    # Format info for ECC Level L (01) + Mask 0 (000) -> 0x77C4 (15 bits: 111011111000100)
    fmt_bits = [(0x77C4 >> i) & 1 for i in range(14, -1, -1)]
    # Around top-left
    tl_coords_r = [(8, 0), (8, 1), (8, 2), (8, 3), (8, 4), (8, 5), (8, 7), (8, 8),
                   (7, 8), (5, 8), (4, 8), (3, 8), (2, 8), (1, 8), (0, 8)]
    for i, (r, c) in enumerate(tl_coords_r):
        matrix[r][c] = bool(fmt_bits[i])

    # Split across bottom-left and top-right
    for i in range(7):
        matrix[size - 1 - i][8] = bool(fmt_bits[i])
    for i in range(7, 15):
        matrix[8][size - 15 + i] = bool(fmt_bits[i])

    return matrix


class QRCodeWidget(QWidget):
    """
    Renders a crisp, phone-scannable QR Code for the given URL.
    """
    def __init__(self, url: str = "https://razorpay.me/@duvorixen", size_px: int = 126, parent=None):
        super().__init__(parent)
        self._url = ""
        self._matrix: List[List[bool]] = []
        self.setFixedSize(size_px, size_px)
        self.set_url(url)

    def set_url(self, url: str):
        self._url = str(url or "https://razorpay.me/@duvorixen").strip()
        self._matrix = encode_qr_matrix(self._url)
        self.setToolTip(f"Scan with Phone (UPI / Razorpay): {self._url}")
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)

        # White quiet-zone background for reliable phone camera scanning
        painter.fillRect(self.rect(), QColor("#FFFFFF"))

        if not self._matrix:
            painter.end()
            return

        n = len(self._matrix)
        quiet = 3
        total_modules = n + quiet * 2
        cell = min(self.width(), self.height()) / float(total_modules)
        offset_x = (self.width() - cell * total_modules) / 2.0
        offset_y = (self.height() - cell * total_modules) / 2.0

        dark_color = QColor("#0F172A")
        for r in range(n):
            for c in range(n):
                if self._matrix[r][c]:
                    rx = offset_x + (c + quiet) * cell
                    ry = offset_y + (r + quiet) * cell
                    painter.fillRect(QRectF(rx, ry, cell + 0.35, cell + 0.35), dark_color)

        painter.end()
