# ウォレット種類記事(wallet-types)用の画像レンダラ
# 使い方: python3 scripts/render_wallet_images.py
#   - H2節アイコン4つ → static/images/sections/wallet-*.png (240px)
#   - カバー画像 → static/images/wallet-types-cover.png (1200x630)
#     (カバーは既存の用語集アイコン terms/wallet, private-key, seed も並べるので
#      先に render_icons.py を実行しておくこと)
#   - 描画スタイル・色は render_icons.py と共通(4倍で描いて縮小)
#   - 依存: Pillow
import math
import os
from PIL import Image, ImageDraw

S = 960          # 作業キャンバス
OUT = 240        # 出力サイズ
W = 44           # 基本ストローク幅
TILE = "#f7f7f5"
BORDER = "#e3e2dc"
INK = "#3f3e3a"
BLUE = "#2a78d6"    # コールド
GREEN = "#1baf7a"   # エアギャップ(QR)
ORANGE = "#eb6834"  # ホット
YELLOW = "#d98f00"  # ウォレット

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
IMAGES = os.path.normpath(os.path.join(SCRIPT_DIR, "..", "static", "images"))
OUTDIR = os.path.join(IMAGES, "sections")
os.makedirs(OUTDIR, exist_ok=True)


def new_tile():
    img = Image.new("RGB", (S, S), TILE)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([8, 8, S - 8, S - 8], radius=190, outline=BORDER, width=16)
    return img, d


def save(img, name):
    img.resize((OUT, OUT), Image.LANCZOS).save(os.path.join(OUTDIR, name + ".png"))


def flame(d, cx, cy, s, color):
    # 炎: しずく形の輪郭+内側をタイル色でくり抜き
    pts = [(cx, cy - s)]
    for adeg in range(-70, 251, 15):
        a = math.radians(adeg)
        pts.append((cx + 0.62 * s * math.cos(a), cy + 0.38 * s + 0.55 * s * math.sin(a)))
    d.polygon(pts, fill=color)
    pts2 = [(cx, cy - 0.30 * s)]
    for adeg in range(-70, 251, 15):
        a = math.radians(adeg)
        pts2.append((cx + 0.30 * s * math.cos(a), cy + 0.48 * s + 0.26 * s * math.sin(a)))
    d.polygon(pts2, fill=TILE)


def snowflake(d, cx, cy, r, color, w=30):
    # 雪の結晶: 6本のスポーク+枝
    for k in range(6):
        a = math.radians(k * 60)
        d.line([cx, cy, cx + r * math.cos(a), cy + r * math.sin(a)], fill=color, width=w)
        bx, by = cx + 0.58 * r * math.cos(a), cy + 0.58 * r * math.sin(a)
        for da in (0.6, -0.6):
            d.line([bx, by, bx + 0.34 * r * math.cos(a + da), by + 0.34 * r * math.sin(a + da)],
                   fill=color, width=int(w * 0.8))


# ---- 1. ハードウェアウォレット: 画面に鍵が表示されたUSBデバイス ----

def icon_wallet_hw():
    img, d = new_tile()
    # USB端子(上)
    d.rectangle([420, 130, 540, 240], outline=INK, width=30)
    for x in (455, 505):
        d.line([x, 165, x, 205], fill=INK, width=20)
    # 本体
    d.rounded_rectangle([300, 240, 660, 790], radius=90, outline=INK, width=W)
    # 画面の中に鍵(=鍵はデバイスの中から出ない)
    d.rounded_rectangle([360, 330, 600, 550], radius=30, outline=INK, width=26)
    d.ellipse([395, 400, 465, 470], outline=YELLOW, width=26)
    d.line([460, 435, 565, 435], fill=YELLOW, width=26)
    d.line([530, 435, 530, 480], fill=YELLOW, width=26)
    # 物理ボタン
    d.ellipse([435, 610, 525, 700], outline=INK, width=30)
    save(img, "wallet-hw")


# ---- 2. ホット/コールド: 炎と雪の結晶 ----

def icon_wallet_hot_cold():
    img, d = new_tile()
    flame(d, 300, 430, 240, ORANGE)
    snowflake(d, 655, 480, 175, BLUE)
    # 境界の点線
    for y in range(220, 740, 90):
        d.line([480, y, 480, y + 45], fill=BORDER, width=18)
    save(img, "wallet-hot-cold")


# ---- 3. エアギャップ: ケーブルが届かないQRコードのスマホ ----

def icon_wallet_air_gap():
    img, d = new_tile()
    # 左からのケーブル+プラグ
    d.line([70, 480, 240, 480], fill=INK, width=30)
    d.rectangle([240, 435, 330, 525], outline=INK, width=28)
    # 切断マーク(空気の隙間)
    for off in (0, 45):
        d.line([395 + off, 415, 365 + off, 545], fill=ORANGE, width=24)
    # スマホ
    d.rounded_rectangle([490, 190, 810, 770], radius=60, outline=INK, width=W)
    d.line([600, 250, 700, 250], fill=INK, width=22)
    # QRコード(緑)
    m = 40  # モジュール1個
    qx, qy = 530, 330
    for gx, gy in ((0, 0), (4, 0), (0, 4)):  # 3隅のファインダ
        d.rectangle([qx + gx * m, qy + gy * m, qx + gx * m + 2 * m, qy + gy * m + 2 * m],
                    outline=GREEN, width=18)
    for gx, gy in ((3, 1), (4, 3), (3, 4), (5, 5), (2, 2), (5, 2), (1, 3), (4, 5)):
        d.rectangle([qx + gx * m + 6, qy + gy * m + 6,
                     qx + (gx + 1) * m - 6, qy + (gy + 1) * m - 6], fill=GREEN)
    save(img, "wallet-air-gap")


# ---- 4. 受取はホット・保管はコールド: 炎の箱 → 雪の箱 ----

def icon_wallet_plan():
    img, d = new_tile()
    d.rounded_rectangle([110, 330, 410, 630], radius=50, outline=INK, width=W - 8)
    flame(d, 260, 460, 105, ORANGE)
    d.rounded_rectangle([550, 330, 850, 630], radius=50, outline=INK, width=W - 8)
    snowflake(d, 700, 480, 92, BLUE, w=22)
    # 矢印
    d.line([420, 480, 530, 480], fill=INK, width=30)
    for da in (2.6, -2.6):
        d.line([540, 480, 540 + 50 * math.cos(da), 480 + 50 * math.sin(da)], fill=INK, width=30)
    save(img, "wallet-plan")


for fn in (icon_wallet_hw, icon_wallet_hot_cold, icon_wallet_air_gap, icon_wallet_plan):
    fn()

# ---- カバー: 節アイコン+用語集のウォレット系アイコンを3x2で並べる ----

CW, CH = 1200, 630
SURFACE = "#fcfcfb"
cover = Image.new("RGB", (CW, CH), SURFACE)
icons = [
    os.path.join(IMAGES, "terms", "wallet.png"),
    os.path.join(OUTDIR, "wallet-hw.png"),
    os.path.join(IMAGES, "terms", "private-key.png"),
    os.path.join(OUTDIR, "wallet-hot-cold.png"),
    os.path.join(OUTDIR, "wallet-air-gap.png"),
    os.path.join(OUTDIR, "wallet-plan.png"),
]
size = 240
cols, rows = 3, 2
gx = (CW - cols * size) // (cols + 1)
gy = (CH - rows * size) // (rows + 1)
for i, path in enumerate(icons):
    ic = Image.open(path).resize((size, size), Image.LANCZOS)
    x = gx + (i % cols) * (size + gx)
    y = gy + (i // cols) * (size + gy)
    cover.paste(ic, (x, y))
cover.save(os.path.join(IMAGES, "wallet-types-cover.png"))
print("done: 4 section icons ->", OUTDIR, "/ cover ->", os.path.join(IMAGES, "wallet-types-cover.png"))
