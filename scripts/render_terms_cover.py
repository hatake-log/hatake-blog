# 用語集記事のカバー画像: アイコンのみ(テキストなし)
# 使い方: 先に render_icons.py を実行してから python3 scripts/render_terms_cover.py
#   → static/images/pc-terms-cover.png に出力
import os
from PIL import Image

BASE = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "static", "images"))
W, H = 1200, 630
SURFACE = "#fcfcfb"

img = Image.new("RGB", (W, H), SURFACE)

icons = ["cpu", "gpu", "ram", "blockchain",
         "node", "nonce", "private-key", "wallet"]
size = 240
cols, rows = 4, 2
gx = (W - cols * size) // (cols + 1)
gy = (H - rows * size) // (rows + 1)
for i, name in enumerate(icons):
    ic = Image.open(os.path.join(BASE, "terms", name + ".png")).resize((size, size), Image.LANCZOS)
    x = gx + (i % cols) * (size + gx)
    y = gy + (i // cols) * (size + gy)
    img.paste(ic, (x, y))

img.save(os.path.join(BASE, "pc-terms-cover.png"))
print("cover done")
