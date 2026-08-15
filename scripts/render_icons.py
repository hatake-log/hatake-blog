# 用語集アイコンレンダラ: フラットピクトグラムを static/images/terms/ に出力する
# 使い方: python3 scripts/render_icons.py
#   - 4倍サイズ(960px)で描いて240pxに縮小(PILに図形のアンチエイリアスがない代わり)
#   - 用語を増やすときは icon_xxx() 関数を書き足して ICONS と names に追加する
#   - 全アイコンの一覧は scripts/_sheet.png に出る(git管理外)ので目視確認に使う
#   - 依存: Pillow、Noto Sans CJK(fonts-noto-cjk)
import math
import os
from PIL import Image, ImageDraw, ImageFont

S = 960          # 作業キャンバス
OUT = 240        # 出力サイズ
W = 44           # 基本ストローク幅
TILE = "#f7f7f5"
BORDER = "#e3e2dc"
INK = "#3f3e3a"
BLUE = "#2a78d6"    # PC(厨房)
GREEN = "#1baf7a"   # 帳簿のしくみ
ORANGE = "#eb6834"  # マイニング
YELLOW = "#d98f00"  # ウォレット

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTDIR = os.path.normpath(os.path.join(SCRIPT_DIR, "..", "static", "images", "terms"))
os.makedirs(OUTDIR, exist_ok=True)

FONT = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"

def font(size):
    return ImageFont.truetype(FONT, size, index=0)

def new_tile():
    img = Image.new("RGB", (S, S), TILE)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([8, 8, S - 8, S - 8], radius=190, outline=BORDER, width=16)
    return img, d

def save(img, name):
    img.resize((OUT, OUT), Image.LANCZOS).save(os.path.join(OUTDIR, name + ".png"))

def ctext(d, xy, s, f, fill):
    l, t, r, b = d.textbbox((0, 0), s, font=f)
    d.text((xy[0] - (r - l) / 2 - l, xy[1] - (b - t) / 2 - t), s, font=f, fill=fill)

def chip(d, cx, cy, size, color=INK, pins=8, pin_len=52):
    h = size / 2
    for i in range(pins // 2):
        off = -h + (i + 0.5) * size / (pins // 2)
        for x0, y0, x1, y1 in [
            (cx + off, cy - h - pin_len, cx + off, cy - h),
            (cx + off, cy + h, cx + off, cy + h + pin_len),
            (cx - h - pin_len, cy + off, cx - h, cy + off),
            (cx + h, cy + off, cx + h + pin_len, cy + off),
        ]:
            d.line([x0, y0, x1, y1], fill=color, width=26)
    d.rounded_rectangle([cx - h, cy - h, cx + h, cy + h], radius=40, outline=color, width=W)

def arrow(d, p0, p1, color, width=32, head=54):
    d.line([p0, p1], fill=color, width=width)
    ang = math.atan2(p1[1] - p0[1], p1[0] - p0[0])
    for da in (2.6, -2.6):
        d.line([p1, (p1[0] + head * math.cos(ang + da), p1[1] + head * math.sin(ang + da))],
               fill=color, width=width)

# ---------------- PC(厨房)編: 青 ----------------

def icon_cpu():
    img, d = new_tile()
    chip(d, S/2, S/2, 460)
    d.rounded_rectangle([S/2-120, S/2-120, S/2+120, S/2+120], radius=24, outline=BLUE, width=W)
    save(img, "cpu")

def icon_core():
    img, d = new_tile()
    chip(d, S/2, S/2, 460)
    for ix in (-1, 1):
        for iy in (-1, 1):
            cx, cy = S/2 + ix*95, S/2 + iy*95
            d.rounded_rectangle([cx-70, cy-70, cx+70, cy+70], radius=18, fill=BLUE)
    save(img, "core")

def icon_thread():
    img, d = new_tile()
    chip(d, S/2, S/2, 460)
    # 1コアの中を2本の糸が走る
    for off, col in ((-60, BLUE), (60, BLUE)):
        pts = []
        for t in range(0, 21):
            y = S/2 - 150 + t * 15
            x = S/2 + off + 34 * math.sin(t / 20 * math.pi * 2 + (0 if off < 0 else math.pi))
            pts.append((x, y))
        d.line(pts, fill=col, width=34, joint="curve")
    save(img, "thread")

def icon_clock():
    img, d = new_tile()
    # クロック信号(矩形波)
    y_hi, y_lo = S/2 - 130, S/2 + 130
    xs = [150, 150, 310, 310, 470, 470, 630, 630, 810]
    ys = [y_lo, y_hi, y_hi, y_lo, y_lo, y_hi, y_hi, y_lo, y_lo]
    d.line(list(zip(xs, ys)), fill=INK, width=W, joint="curve")
    d.line([xs[4], y_lo, xs[5], y_hi], fill=BLUE, width=W)
    d.line([xs[5], y_hi, xs[6], y_hi], fill=BLUE, width=W)
    ctext(d, (S/2, S - 210), "GHz", font(120), BLUE)
    save(img, "clock")

def icon_gpu():
    img, d = new_tile()
    # グラボ: 本体+ファン2つ+端子
    d.rounded_rectangle([140, 300, 830, 640], radius=40, outline=INK, width=W)
    for cx in (350, 620):
        d.ellipse([cx-105, 365, cx+105, 575], outline=BLUE, width=36)
        for a in range(4):
            ang = math.pi/2 * a + 0.5
            d.line([cx, 470, cx + 78*math.cos(ang), 470 + 78*math.sin(ang)], fill=BLUE, width=30)
    d.rectangle([250, 640, 700, 700], outline=INK, width=24)
    d.line([140, 300, 140, 210], fill=INK, width=W)
    d.line([140, 210, 250, 210], fill=INK, width=W)
    save(img, "gpu")

def icon_asic():
    img, d = new_tile()
    chip(d, S/2, S/2, 460)
    # 中に稲妻1本=一芸特化
    d.polygon([(S/2+55, S/2-160), (S/2-90, S/2+30), (S/2-5, S/2+30),
               (S/2-55, S/2+160), (S/2+90, S/2-30), (S/2+5, S/2-30)], fill=BLUE)
    save(img, "asic")

def ram_stick(d, x0, y0, x1, y1, color=INK, chipcol=BLUE, nchips=4):
    d.rounded_rectangle([x0, y0, x1, y1], radius=24, outline=color, width=W-8)
    w = (x1 - x0) / nchips
    for i in range(nchips):
        cx = x0 + w * (i + 0.5)
        d.rectangle([cx - w*0.26, y0 + 55, cx + w*0.26, y0 + 145], fill=chipcol)
    # 端子
    for i in range(nchips * 2):
        cx = x0 + (x1 - x0) / (nchips*2) * (i + 0.5)
        d.line([cx, y1, cx, y1 + 46], fill=color, width=22)

def icon_ram():
    img, d = new_tile()
    ram_stick(d, 150, 360, 810, 560)
    save(img, "ram")

def icon_ram_size():
    img, d = new_tile()
    ram_stick(d, 150, 260, 810, 460)
    ctext(d, (S/2, 660), "16GB", font(170), BLUE)
    save(img, "ram-size")

def icon_ram_bandwidth():
    img, d = new_tile()
    ram_stick(d, 190, 190, 770, 360, nchips=4)
    d.rounded_rectangle([330, 660, 630, 850], radius=30, outline=INK, width=W-8)
    arrow(d, (400, 620), (400, 450), BLUE, width=36)
    arrow(d, (560, 450), (560, 620), BLUE, width=36)
    save(img, "ram-bandwidth")

def icon_dual_channel():
    img, d = new_tile()
    for y in (230, 540):
        ram_stick(d, 170, y, 790, y + 160, nchips=4)
    ctext(d, (S/2, 830), "×2", font(150), BLUE)
    save(img, "dual-channel")

def icon_optimization():
    img, d = new_tile()
    # スピードメーター: 針が右(速い)側
    cx, cy, r = S/2, S/2 + 110, 330
    d.arc([cx-r, cy-r, cx+r, cy+r], 180, 360, fill=INK, width=W)
    for adeg in (200, 240, 280, 320, 340):
        a = math.radians(adeg)
        d.line([cx + (r-70)*math.cos(a), cy + (r-70)*math.sin(a),
                cx + (r-16)*math.cos(a), cy + (r-16)*math.sin(a)], fill=INK, width=24)
    a = math.radians(325)
    d.line([cx, cy, cx + (r-110)*math.cos(a), cy + (r-110)*math.sin(a)], fill=BLUE, width=44)
    d.ellipse([cx-42, cy-42, cx+42, cy+42], fill=BLUE)
    save(img, "optimization")

def icon_hashrate():
    img, d = new_tile()
    ctext(d, (S/2 + 60, S/2), "#", font(430), INK)
    for i, y in enumerate((S/2 - 150, S/2, S/2 + 150)):
        d.line([120, y, 250 - i*30, y], fill=BLUE, width=36)
    save(img, "hashrate")

def icon_tdp():
    img, d = new_tile()
    # 温度計
    cx = S/2 - 90
    d.rounded_rectangle([cx-60, 160, cx+60, 620], radius=60, outline=INK, width=W-4)
    d.ellipse([cx-115, 570, cx+115, 800], outline=INK, width=W-4)
    d.ellipse([cx-70, 615, cx+70, 755], fill=BLUE)
    d.line([cx, 640, cx, 380], fill=BLUE, width=56)
    # 電源プラグ的な稲妻
    d.polygon([(720, 250), (610, 420), (680, 420), (620, 570), (740, 390), (670, 390)], fill=BLUE)
    save(img, "tdp")

# ---------------- 帳簿(ブロックチェーン)編: 緑 ----------------

def cube(d, cx, cy, s, color=INK, top=None):
    h = s/2
    dx, dy = s*0.42, s*0.24
    front = [(cx-h, cy-h+dy), (cx+h-dx, cy-h+dy), (cx+h-dx, cy+h), (cx-h, cy+h)]
    topf = [(cx-h, cy-h+dy), (cx-h+dx, cy-h), (cx+h, cy-h), (cx+h-dx, cy-h+dy)]
    side = [(cx+h-dx, cy-h+dy), (cx+h, cy-h), (cx+h, cy+h-dy), (cx+h-dx, cy+h)]
    if top:
        d.polygon(topf, fill=top)
        d.polygon(side, fill=top)
    for p in (front, topf, side):
        d.polygon(p, outline=color, width=30)
    return front

def icon_blockchain():
    img, d = new_tile()
    # 角丸ブロック3つを鎖リンクでつなぐ
    for i, cx in enumerate((215, 480, 745)):
        col = GREEN if i == 1 else None
        d.rounded_rectangle([cx-90, S/2-90, cx+90, S/2+90], radius=28,
                            fill=col, outline=INK, width=34)
        if i < 2:
            d.line([cx + 90, S/2, cx + 175, S/2], fill=INK, width=30)
    save(img, "blockchain")

def icon_block():
    img, d = new_tile()
    cube(d, S/2, S/2, 430, top=GREEN)
    save(img, "block")

def icon_transaction():
    img, d = new_tile()
    # レシート: ギザギザ下端+行+矢印
    x0, y0, x1 = 260, 140, 700
    zz = [(x0, y0)]
    d.line([x0, y0, x1, y0], fill=INK, width=W-8)
    d.line([x0, y0, x0, 700], fill=INK, width=W-8)
    d.line([x1, y0, x1, 700], fill=INK, width=W-8)
    pts = []
    n = 6
    for i in range(n + 1):
        px = x0 + (x1 - x0) / n * i
        pts.append((px, 700 if i % 2 == 0 else 760))
    d.line(pts, fill=INK, width=W-8, joint="curve")
    for y in (280, 400):
        d.line([x0+90, y, x1-90, y], fill=INK, width=26)
    arrow(d, (x0+90, 550), (x1-110, 550), GREEN, width=34)
    save(img, "transaction")

def icon_node():
    img, d = new_tile()
    cx, cy = S/2, S/2
    outer = [(cx, cy-300), (cx+290, cy-90), (cx+180, cy+270), (cx-180, cy+270), (cx-290, cy-90)]
    for p in outer:
        d.line([ (cx, cy), p], fill=INK, width=26)
    for p in outer:
        d.ellipse([p[0]-62, p[1]-62, p[0]+62, p[1]+62], fill=TILE, outline=INK, width=30)
    d.ellipse([cx-95, cy-95, cx+95, cy+95], fill=GREEN)
    save(img, "node")

def icon_testnet():
    img, d = new_tile()
    # 三角フラスコ+泡
    d.line([400, 160, 400, 380], fill=INK, width=W-4)
    d.line([560, 160, 560, 380], fill=INK, width=W-4)
    d.line([340, 160, 620, 160], fill=INK, width=W-4)
    d.polygon([(400, 380), (560, 380), (760, 780), (200, 780)], outline=INK, width=W-4)
    d.polygon([(345, 500), (615, 500), (740, 760), (220, 760)], fill=GREEN)
    for cx, cy, r in ((420, 640, 34), (540, 580, 26), (480, 700, 22)):
        d.ellipse([cx-r, cy-r, cx+r, cy+r], fill=TILE)
    save(img, "testnet")

def icon_privacy_coin():
    img, d = new_tile()
    d.ellipse([180, 180, 780, 780], outline=INK, width=W)
    d.ellipse([250, 250, 710, 710], outline=INK, width=24)
    # アイマスク
    d.rounded_rectangle([230, 420, 730, 560], radius=70, fill=GREEN)
    for cx in (390, 570):
        d.ellipse([cx-52, 450, cx+52, 530], fill=TILE)
    save(img, "privacy-coin")

# ---------------- マイニング編: 橙 ----------------

def icon_pow():
    img, d = new_tile()
    # つるはし: 柄の上端に刃のアーチが刺さる
    d.line([330, 850, 618, 265], fill=INK, width=52)  # 柄
    d.arc([320, 240, 960, 880], 210, 320, fill=ORANGE, width=60)  # 刃(柄の先端に接する)
    save(img, "pow")

def icon_nonce():
    img, d = new_tile()
    d.rounded_rectangle([230, 230, 730, 730], radius=90, outline=INK, width=W)
    for cx, cy in ((360, 360), (480, 480), (600, 600), (600, 360), (360, 600)):
        d.ellipse([cx-52, cy-52, cx+52, cy+52], fill=ORANGE)
    save(img, "nonce")

def icon_difficulty():
    img, d = new_tile()
    # 山2つ(低→高)+旗
    d.polygon([(140, 780), (400, 460), (620, 780)], outline=INK, width=W-8)
    d.polygon([(380, 780), (660, 300), (880, 780)], outline=INK, width=W-8)
    d.line([660, 300, 660, 150], fill=INK, width=28)
    d.polygon([(660, 150), (800, 195), (660, 245)], fill=ORANGE)
    save(img, "difficulty")

# ---------------- ウォレット編: 黄 ----------------

def icon_private_key():
    img, d = new_tile()
    d.ellipse([160, 330, 460, 630], outline=INK, width=W+8)
    d.line([440, 480, 820, 480], fill=INK, width=48)
    d.line([680, 480, 680, 610], fill=YELLOW, width=44)
    d.line([800, 480, 800, 640], fill=YELLOW, width=44)
    save(img, "private-key")

def icon_address():
    img, d = new_tile()
    # 封筒(宛先)
    x0, y0, x1, y1 = 170, 280, 790, 700
    d.rounded_rectangle([x0, y0, x1, y1], radius=40, outline=INK, width=W)
    d.line([x0+20, y0+20, (x0+x1)/2, (y0+y1)/2+40], fill=INK, width=36)
    d.line([(x0+x1)/2, (y0+y1)/2+40, x1-20, y0+20], fill=INK, width=36)
    # 宛名シール
    d.rounded_rectangle([555, 540, 730, 640], radius=24, fill=YELLOW)
    save(img, "address")

def icon_wallet():
    img, d = new_tile()
    d.rounded_rectangle([170, 300, 790, 720], radius=60, outline=INK, width=W)
    d.line([170, 400, 790, 400], fill=INK, width=30)
    d.rounded_rectangle([620, 460, 850, 620], radius=50, outline=INK, width=W-8)
    d.ellipse([700, 505, 770, 575], fill=YELLOW)
    save(img, "wallet")

def leaf(d, base, tip, width, color):
    # base→tipを軸に、両側へ膨らむ葉っぱ形ポリゴン
    bx, by = base; tx, ty = tip
    ax, ay = tx - bx, ty - by
    L = math.hypot(ax, ay)
    ux, uy = ax / L, ay / L
    px, py = -uy, ux
    pts = []
    for t in [i / 12 for i in range(13)]:
        w = width * math.sin(t * math.pi)
        pts.append((bx + ax*t + px*w, by + ay*t + py*w))
    for t in [i / 12 for i in range(12, -1, -1)]:
        w = width * math.sin(t * math.pi)
        pts.append((bx + ax*t - px*w, by + ay*t - py*w))
    d.polygon(pts, fill=color)

def flame(d, cx, cy, s, color):
    # 炎: しずく形の輪郭+内側をタイル色でくり抜き(render_wallet_images.pyと共通の形)
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


def snowflake(d, cx, cy, r, color, w=28):
    # 雪の結晶: 6本のスポーク+枝(render_wallet_images.pyと共通の形)
    for k in range(6):
        a = math.radians(k * 60)
        d.line([cx, cy, cx + r * math.cos(a), cy + r * math.sin(a)], fill=color, width=w)
        bx, by = cx + 0.58 * r * math.cos(a), cy + 0.58 * r * math.sin(a)
        for da in (0.6, -0.6):
            d.line([bx, by, bx + 0.34 * r * math.cos(a + da), by + 0.34 * r * math.sin(a + da)],
                   fill=color, width=int(w * 0.8))


def small_wallet(d):
    # ホット/コールド用の共通ウォレット(右上にバッジの余白を空けた縮小版)
    d.rounded_rectangle([140, 330, 700, 730], radius=54, outline=INK, width=W)
    d.line([140, 430, 700, 430], fill=INK, width=28)
    d.rounded_rectangle([550, 480, 760, 620], radius=44, outline=INK, width=W - 8)
    d.ellipse([620, 520, 685, 585], fill=YELLOW)


def icon_hot_wallet():
    img, d = new_tile()
    small_wallet(d)
    flame(d, 760, 230, 130, ORANGE)
    save(img, "hot-wallet")


def icon_cold_wallet():
    img, d = new_tile()
    small_wallet(d)
    snowflake(d, 760, 235, 115, BLUE, w=24)
    save(img, "cold-wallet")


def icon_seed():
    img, d = new_tile()
    # 双葉+土
    d.arc([180, 640, 780, 1060], 205, 335, fill=INK, width=W)
    d.line([480, 740, 480, 500], fill=INK, width=38)
    leaf(d, (480, 520), (270, 330), 95, YELLOW)
    leaf(d, (480, 520), (690, 330), 95, YELLOW)
    save(img, "seed")

ICONS = [icon_cpu, icon_core, icon_thread, icon_clock, icon_gpu, icon_asic,
         icon_ram, icon_ram_size, icon_ram_bandwidth, icon_dual_channel,
         icon_optimization, icon_hashrate, icon_tdp,
         icon_blockchain, icon_block, icon_transaction, icon_node,
         icon_testnet, icon_privacy_coin,
         icon_pow, icon_nonce, icon_difficulty,
         icon_private_key, icon_address, icon_wallet, icon_hot_wallet,
         icon_cold_wallet, icon_seed]

for fn in ICONS:
    fn()

# コンタクトシート
names = ["cpu", "core", "thread", "clock", "gpu", "asic", "ram", "ram-size",
         "ram-bandwidth", "dual-channel", "optimization", "hashrate", "tdp",
         "blockchain", "block", "transaction", "node", "testnet", "privacy-coin",
         "pow", "nonce", "difficulty", "private-key", "address", "wallet",
         "hot-wallet", "cold-wallet", "seed"]
cols = 6
rows = (len(names) + cols - 1) // cols
sheet = Image.new("RGB", (cols * 270 + 30, rows * 310 + 30), "#ffffff")
sd = ImageDraw.Draw(sheet)
lf = font(28)
for i, n in enumerate(names):
    x = 30 + (i % cols) * 270
    y = 30 + (i // cols) * 310
    sheet.paste(Image.open(os.path.join(OUTDIR, n + ".png")), (x, y))
    sd.text((x + 10, y + 245), n, font=lf, fill="#333")
sheet.save(os.path.join(SCRIPT_DIR, "_sheet.png"))
print("rendered", len(names), "icons ->", OUTDIR)
