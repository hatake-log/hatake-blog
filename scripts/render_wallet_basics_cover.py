# ウォレット基礎記事(wallet-basics)用のカバー画像レンダラ
# 使い方: python3 scripts/render_wallet_basics_cover.py
#   - カバー画像 → static/images/wallet-basics-cover.png (1200x630)
#     (用語集アイコン terms/wallet を使うので先に render_icons.py を実行しておくこと)
#   - 依存: Pillow
import os
from PIL import Image

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
IMAGES = os.path.normpath(os.path.join(SCRIPT_DIR, "..", "static", "images"))

CW, CH = 1200, 630
SURFACE = "#fcfcfb"
cover = Image.new("RGB", (CW, CH), SURFACE)
size = 360
ic = Image.open(os.path.join(IMAGES, "terms", "wallet.png")).resize((size, size), Image.LANCZOS)
cover.paste(ic, ((CW - size) // 2, (CH - size) // 2))
cover.save(os.path.join(IMAGES, "wallet-basics-cover.png"))
print("done: cover ->", os.path.join(IMAGES, "wallet-basics-cover.png"))
