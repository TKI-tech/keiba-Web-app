"""PWA用のプレースホルダーアイコンを生成する。

デザイン確定前の暫定アイコン。差し替える場合は static_pwa/icons/ 配下の
icon-192.png / icon-512.png / apple-touch-icon.png を上書きすればよい。
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT_DIR = Path(__file__).resolve().parent.parent / "static_pwa" / "icons"
OUT_DIR.mkdir(parents=True, exist_ok=True)

BG_COLOR = (191, 32, 38)  # 競馬らしい赤
FG_COLOR = (255, 255, 255)


def make_icon(size: int, path: Path) -> None:
    img = Image.new("RGB", (size, size), BG_COLOR)
    draw = ImageDraw.Draw(img)
    text = "競"
    font_size = int(size * 0.6)
    try:
        font = ImageFont.truetype("msgothic.ttc", font_size)
    except OSError:
        font = ImageFont.load_default()
    bbox = draw.textbbox((0, 0), text, font=font)
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(((size - w) / 2 - bbox[0], (size - h) / 2 - bbox[1]), text, fill=FG_COLOR, font=font)
    img.save(path)


make_icon(192, OUT_DIR / "icon-192.png")
make_icon(512, OUT_DIR / "icon-512.png")
make_icon(180, OUT_DIR / "apple-touch-icon.png")
print("icons written to", OUT_DIR)
