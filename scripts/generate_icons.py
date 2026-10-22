"""Generate the browser tab icon and the PWA icon set from the main logo.

The single source of truth is ``frontend/public/icons/schemeping_logo.png``.
Running this script regenerates every icon file the app references:

    python scripts/generate_icons.py

The favicon and the small PWA icons use the emblem (the top part of the
lockup) because the wordmark is unreadable below roughly 100px. The larger
"any" icons keep a white background so they stay visible on any device
background, and the maskable icon sits on a navy field inside the safe zone.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
ICONS_DIR = ROOT / "frontend" / "public" / "icons"
SOURCE = ICONS_DIR / "schemeping_logo.png"

NAVY = (0, 0, 128)
WHITE = (255, 255, 255)


INK_THRESHOLD = 40


def ink_box(image: Image.Image) -> tuple[int, int, int, int]:
    """Bounding box of the visible artwork, ignoring faint anti-alias noise."""
    alpha = image.getchannel("A").point(lambda value: 255 if value > INK_THRESHOLD else 0)
    return alpha.getbbox() or (0, 0, image.width, image.height)


def content_box(image: Image.Image) -> tuple[int, int, int, int]:
    """Bounding box of the visible (non transparent) part of the logo."""
    return image.getchannel("A").getbbox() or (0, 0, image.width, image.height)


def emblem(image: Image.Image) -> Image.Image:
    """Crop the emblem: the artwork above the wordmark.

    The emblem is the largest solid block of ink in the upper part of the
    lockup; the wordmark and the tagline sit in separate bands below it.
    Finding the band this way keeps the script working if the logo artwork
    is replaced later.
    """
    left, top, right, bottom = content_box(image)
    alpha = image.getchannel("A")

    runs: list[tuple[int, int]] = []
    run_start: int | None = None
    for y in range(top, bottom):
        has_ink = alpha.crop((0, y, image.width, y + 1)).getextrema()[1] > INK_THRESHOLD
        if has_ink and run_start is None:
            run_start = y
        elif not has_ink and run_start is not None:
            runs.append((run_start, y - 1))
            run_start = None
    if run_start is not None:
        runs.append((run_start, bottom - 1))

    upper_limit = top + int((bottom - top) * 0.7)
    candidates = [run for run in runs if run[0] <= upper_limit]
    if not candidates:
        return image.crop(ink_box(image))

    emblem_top, emblem_bottom = max(candidates, key=lambda run: run[1] - run[0])

    cropped = image.crop((left, emblem_top, right, emblem_bottom + 1))
    box = ink_box(cropped)
    if box is None:
        return cropped
    return cropped.crop(box)


def on_background(art: Image.Image, size: int, background: tuple[int, int, int], ratio: float) -> Image.Image:
    """Centre the artwork on a solid square canvas."""
    canvas = Image.new("RGB", (size, size), background)
    inner = int(size * ratio)
    art = art.copy()
    art.thumbnail((inner, inner), Image.LANCZOS)
    canvas.paste(art, ((size - art.width) // 2, (size - art.height) // 2), art)
    return canvas


def main() -> None:
    logo = Image.open(SOURCE).convert("RGBA")

    emblem_art = emblem(logo)

    # Browser tab icon: several sizes in one .ico file.
    ico_source = emblem_art.copy()
    ico_source.thumbnail((64, 64), Image.LANCZOS)
    favicon = ICONS_DIR.parent / "favicon.ico"
    ico_source.save(favicon, format="ICO", sizes=[(16, 16), (32, 32), (48, 48)])
    print(f"wrote {favicon}")

    # PWA icons.
    for size in (192, 512):
        path = ICONS_DIR / f"icon-{size}.png"
        on_background(emblem_art, size, WHITE, 0.92).save(path, optimize=True)
        print(f"wrote {path}")

    maskable = ICONS_DIR / "icon-maskable-512.png"
    on_background(emblem_art, 512, NAVY, 0.56).save(maskable, optimize=True)
    print(f"wrote {maskable}")

    apple = ICONS_DIR / "apple-touch-icon.png"
    on_background(emblem_art, 180, WHITE, 0.92).save(apple, optimize=True)
    print(f"wrote {apple}")

    # Lightweight copy of the full lockup for the header and login screen.
    header = logo.copy()
    header.thumbnail((320, 320), Image.LANCZOS)
    header_path = ICONS_DIR / "schemeping_logo-320.png"
    header.save(header_path, optimize=True)
    print(f"wrote {header_path}")


if __name__ == "__main__":
    main()
