"""Generate the PWA PNG icons.

There is no image library (PIL) available in this environment and the project
must stay at zero cost, so the icons are rendered with plain Python: a navy
rounded square with concentric white rings and a green centre (a "ping" mark).

Run from the frontend directory:

    python scripts/generate_icons.py

Outputs public/icons/icon-192.png, icon-512.png and icon-maskable-512.png.
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

NAVY = (0, 0, 128)
WHITE = (255, 255, 255)
SEAGREEN = (46, 139, 87)
TRANSPARENT = (0, 0, 0, 0)


def blend(base: tuple[int, int, int, int], top: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    """Alpha-composite ``top`` over ``base`` (straight alpha, both 0-255)."""
    top_a = top[3] / 255
    if top_a >= 1:
        return top
    base_a = base[3] / 255
    out_a = top_a + base_a * (1 - top_a)
    if out_a == 0:
        return TRANSPARENT
    channels = []
    for index in range(3):
        value = (top[index] * top_a + base[index] * base_a * (1 - top_a)) / out_a
        channels.append(max(0, min(255, round(value))))
    return (channels[0], channels[1], channels[2], round(out_a * 255))


def create_canvas(size: int) -> list[list[tuple[int, int, int, int]]]:
    return [[TRANSPARENT for _ in range(size)] for _ in range(size)]


def fill_rounded_rect(
    canvas: list[list[tuple[int, int, int, int]]],
    size: int,
    colour: tuple[int, int, int],
    radius_ratio: float,
    inset_ratio: float = 0.0,
) -> None:
    inset = size * inset_ratio
    radius = size * radius_ratio
    for y in range(size):
        for x in range(size):
            px, py = x + 0.5, y + 0.5
            left, top = inset, inset
            right, bottom = size - inset, size - inset
            if not (left <= px <= right and top <= py <= bottom):
                continue
            dx = max(left + radius - px, 0, px - (right - radius))
            dy = max(top + radius - py, 0, py - (bottom - radius))
            if dx * dx + dy * dy <= radius * radius:
                canvas[y][x] = (*colour, 255)


def draw_ring(
    canvas: list[list[tuple[int, int, int, int]]],
    size: int,
    radius_ratio: float,
    thickness_ratio: float,
    colour: tuple[int, int, int],
    alpha: float = 1.0,
) -> None:
    centre = size / 2
    radius = size * radius_ratio
    half = size * thickness_ratio / 2
    for y in range(size):
        for x in range(size):
            distance = ((x + 0.5 - centre) ** 2 + (y + 0.5 - centre) ** 2) ** 0.5
            if abs(distance - radius) <= half:
                edge = 1 - max(0.0, (abs(distance - radius) - half + 1) / 1)
                layer = (*colour, round(255 * alpha * max(0.0, min(1.0, edge))))
                canvas[y][x] = blend(canvas[y][x], layer)


def draw_disc(
    canvas: list[list[tuple[int, int, int, int]]],
    size: int,
    radius_ratio: float,
    colour: tuple[int, int, int],
) -> None:
    centre = size / 2
    radius = size * radius_ratio
    for y in range(size):
        for x in range(size):
            if (x + 0.5 - centre) ** 2 + (y + 0.5 - centre) ** 2 <= radius * radius:
                canvas[y][x] = (*colour, 255)


def render(size: int, maskable: bool) -> list[list[tuple[int, int, int, int]]]:
    canvas = create_canvas(size)
    if maskable:
        # Maskable icons need their content inside the safe zone: fill the whole
        # square and keep the mark well inside the centre 80%.
        fill_rounded_rect(canvas, size, NAVY, radius_ratio=0.0)
        scale = 0.72
    else:
        fill_rounded_rect(canvas, size, NAVY, radius_ratio=0.19)
        scale = 1.0

    draw_ring(canvas, size, 0.29 * scale, 0.055 * scale, WHITE)
    draw_ring(canvas, size, 0.185 * scale, 0.045 * scale, WHITE, alpha=0.85)
    draw_disc(canvas, size, 0.075 * scale, SEAGREEN)
    draw_ring(canvas, size, 0.075 * scale, 0.033 * scale, WHITE)
    return canvas


def encode_png(canvas: list[list[tuple[int, int, int, int]]]) -> bytes:
    height = len(canvas)
    width = len(canvas[0])
    raw = bytearray()
    for row in canvas:
        raw.append(0)
        for pixel in row:
            raw.extend(pixel)

    def chunk(tag: bytes, payload: bytes) -> bytes:
        return (
            struct.pack('>I', len(payload))
            + tag
            + payload
            + struct.pack('>I', zlib.crc32(tag + payload) & 0xFFFFFFFF)
        )

    header = struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0)
    return (
        b'\x89PNG\r\n\x1a\n'
        + chunk(b'IHDR', header)
        + chunk(b'IDAT', zlib.compress(bytes(raw), 9))
        + chunk(b'IEND', b'')
    )


def main() -> None:
    output = Path(__file__).resolve().parent.parent / 'public' / 'icons'
    output.mkdir(parents=True, exist_ok=True)

    targets = [
        ('icon-192.png', 192, False),
        ('icon-512.png', 512, False),
        ('icon-maskable-512.png', 512, True),
        ('apple-touch-icon.png', 180, False),
    ]
    for name, size, maskable in targets:
        canvas = render(size, maskable)
        (output / name).write_bytes(encode_png(canvas))
        print(f'wrote {name} ({size}x{size})')


if __name__ == '__main__':
    main()
