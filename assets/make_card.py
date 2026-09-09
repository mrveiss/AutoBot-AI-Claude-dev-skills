"""Render this repository's GitHub social preview card.

A social preview is a repository *setting*, not a file GitHub reads from the tree,
and there is no REST or GraphQL endpoint for it. Committing this PNG changes
nothing on its own -- it is uploaded once through Settings -> General -> Social
preview. The image lives here so the thing that gets uploaded is reviewable and
reproducible rather than existing only in a settings page.

Palette and type follow the property's landing page (mrveiss/mrveiss.github.io) so
a pasted repository link reads as part of the same property. That page is the
source of truth for these tokens; if it changes, this file has to be updated by
hand -- nothing enforces it.

The card carries no skill count, no metrics and no badges on purpose: a number
baked into a setting nobody revisits becomes false the first time a skill is
added. It names domains instead, which stays true as the set grows.

Fonts are not vendored -- see README.md. This module makes no network call.

Usage:
    python3 make_card.py --fonts ./fonts --out .
"""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT = 1280, 640
MARGIN = 88
RULE_Y = 430

BG = "#1e1418"
SUNKEN = "#150d11"
BORDER = "#402c34"
CREAM = "#f1e8de"
MUTED = "#b3a596"
SUBTLE = "#82737a"
ACCENT = "#e2842e"

EYEBROW = "CLAUDE CODE  ·  PLUGIN MARKETPLACE"
LICENCE = "Apache-2.0"

CARD = {
    "out": "social-preview.png",
    "title": "The AutoBot ",
    "accent": "workflow.",
    "sub": "One install gives every platform developer the same setup.",
    "detail": "implement  ·  review  ·  pre-merge validation  ·  full-stack debugging  ·  backlog drain",
    "command": "/plugin marketplace add mrveiss/AutoBot-AI-Claude-dev-skills",
}


def _font(fonts: Path, name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(fonts / f"{name}.ttf"), size)


def _tracked(draw, xy, text, font, fill, tracking) -> None:
    """Draw letter-spaced text; Pillow has no tracking of its own."""
    x, y = xy
    for char in text:
        draw.text((x, y), char, font=font, fill=fill)
        x += draw.textlength(char, font=font) + tracking


def _accent_mark(draw) -> None:
    """The property's favicon disc, bled off the top-right corner."""
    draw.ellipse([WIDTH - 150, -150, WIDTH + 150, 150], fill=ACCENT)
    draw.ellipse([WIDTH - 132, -132, WIDTH + 132, 132], fill=BG)
    draw.ellipse([WIDTH - 96, -96, WIDTH + 96, 96], fill=ACCENT)


def _draw_headline(draw, fonts: Path) -> None:
    _tracked(draw, (MARGIN, 92), EYEBROW, _font(fonts, "JetBrainsMono", 21), SUBTLE, 3.2)

    display = _font(fonts, "Fraunces", 82)
    draw.text((MARGIN, 158), CARD["title"], font=display, fill=CREAM)
    offset = MARGIN + draw.textlength(CARD["title"], font=display)
    draw.text((offset, 158), CARD["accent"], font=display, fill=ACCENT)

    draw.text((MARGIN, 274), CARD["sub"], font=_font(fonts, "Schibsted", 37), fill=MUTED)
    draw.text((MARGIN, 336), CARD["detail"], font=_font(fonts, "Schibsted", 25), fill=SUBTLE)


def _draw_install(draw, fonts: Path) -> None:
    """The hairline separates what this is from how you install it.

    The licence rides above the rule as a caption rather than beside the chip, so
    it cannot crowd a long command.
    """
    caption = _font(fonts, "JetBrainsMono", 19)
    draw.text(
        (WIDTH - MARGIN - draw.textlength(LICENCE, font=caption), RULE_Y - 30),
        LICENCE,
        font=caption,
        fill=SUBTLE,
    )
    draw.line([MARGIN, RULE_Y, WIDTH - MARGIN, RULE_Y], fill=BORDER, width=2)

    mono = _font(fonts, "JetBrainsMono", 25)
    pad_x, pad_y = 26, 20
    chip_w = draw.textlength(CARD["command"], font=mono) + pad_x * 2
    chip_h = 25 + pad_y * 2 + 6
    top = RULE_Y + 42
    draw.rounded_rectangle(
        [MARGIN, top, MARGIN + chip_w, top + chip_h],
        radius=12,
        fill=SUNKEN,
        outline=BORDER,
        width=2,
    )
    draw.text((MARGIN + pad_x, top + pad_y - 2), CARD["command"], font=mono, fill=CREAM)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fonts", type=Path, default=Path(__file__).parent / "fonts")
    parser.add_argument("--out", type=Path, default=Path(__file__).parent)
    args = parser.parse_args()

    image = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(image)
    _accent_mark(draw)
    _draw_headline(draw, args.fonts)
    _draw_install(draw, args.fonts)
    image.save(args.out / CARD["out"], "PNG", optimize=True)


if __name__ == "__main__":
    main()
