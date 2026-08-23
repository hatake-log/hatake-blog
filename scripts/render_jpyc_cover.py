# JPYC体験記事(jpyc-hands-on)用のカバー画像レンダラ
# 使い方: python3 scripts/render_jpyc_cover.py
#   - 入力: static/images/jpyc/jpyc-logo.png(JPYC公式GitHub組織 github.com/jpycoin のアイコン、400x400)
#   - 出力: static/images/jpyc-symbol-cover.png (1200x630)
#   - 依存: Pillow
import os
from PIL import Image

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
IMAGES = os.path.normpath(os.path.join(SCRIPT_DIR, "..", "static", "images"))

CW, CH = 1200, 630
SURFACE = "#fcfcfb"
cover = Image.new("RGB", (CW, CH), SURFACE)
size = 400
logo = Image.open(os.path.join(IMAGES, "jpyc", "jpyc-logo.png")).convert("RGBA").resize((size, size), Image.LANCZOS)
cover.paste(logo, ((CW - size) // 2, (CH - size) // 2), logo)
cover.save(os.path.join(IMAGES, "jpyc-symbol-cover.png"))
print("done: cover ->", os.path.join(IMAGES, "jpyc-symbol-cover.png"))
