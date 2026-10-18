#!/usr/bin/env python3
"""Draw an original FLAPJAX 'nutrition label' meme — a calorie panel that is
actually a chain receipt. Everything drawn programmatically; no stock assets.

Output: meme/flapjax-meme-w1.png (1200x1500)
"""
import os
from PIL import Image, ImageDraw, ImageFont

W, H = 1200, 1500
BG = (14, 16, 20)
PAPER = (250, 248, 242)
INK = (18, 18, 18)
GREY = (110, 110, 110)
ACCENT = (222, 84, 42)

FB = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
FR = "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"
FM = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"


def f(path, size):
    return ImageFont.truetype(path, size)


img = Image.new("RGB", (W, H), BG)
d = ImageDraw.Draw(img)

# subtle vignette-ish grid, drawn not filtered
for x in range(0, W, 40):
    d.line([(x, 0), (x, H)], fill=(22, 25, 30))
for y in range(0, H, 40):
    d.line([(0, y), (W, y)], fill=(22, 25, 30))

# header above the label
d.text((70, 56), "COMPUTE IS CALORIES", font=f(FB, 54), fill=(240, 240, 240))
d.text((70, 124), "a nutrition label for a token transfer", font=f(FR, 30), fill=(150, 152, 158))

# ---- the label card -------------------------------------------------------
LX, LY, LW, LH = 70, 200, W - 140, 1010
d.rounded_rectangle([LX + 10, LY + 14, LX + LW + 10, LY + LH + 14], 26, fill=(6, 7, 9))
d.rounded_rectangle([LX, LY, LX + LW, LY + LH], 26, fill=PAPER)

pad = 46
x0, x1 = LX + pad, LX + LW - pad
y = LY + 34

d.text((x0, y), "Nutrition Facts", font=f(FB, 76), fill=INK)
y += 96
d.line([(x0, y), (x1, y)], fill=INK, width=6)
y += 14
d.text((x0, y), "1 serving per transfer  ·  serving size 1 settlement", font=f(FR, 27), fill=INK)
y += 44
d.line([(x0, y), (x1, y)], fill=INK, width=16)
y += 22

rows = [
    ("Calories", "0", 62, True),
    ("  from the token itself", "0", 27, False),
    ("  from work actually done", "not recorded", 27, False),
    ("Receipts", "1", 62, True),
    ("  re-derivable by a stranger", "yes", 27, False),
    ("  requires trusting the poster", "no", 27, False),
    ("Block height", "128,267,486", 44, True),
    ("Settlement", "100,000 FLAPJAX", 44, True),
    ("Sender", "0x7c34…359f (treasury)", 27, False),
    ("Status", "success", 44, True),
]

for label, val, size, bold in rows:
    d.text((x0, y), label, font=f(FB if bold else FR, size), fill=INK)
    tw = d.textlength(val, font=f(FB, size))
    d.text((x1 - tw, y), val, font=f(FB, size), fill=INK)
    y += size + 26
    if bold:
        d.line([(x0, y - 12), (x1, y - 12)], fill=(200, 198, 190), width=3)

y += 4
d.line([(x0, y), (x1, y)], fill=INK, width=16)
y += 20

d.text((x0, y), "Ingredients", font=f(FB, 34), fill=INK)
y += 46
d.text((x0, y), "one ERC-20 Transfer event, filtered to a single contract,", font=f(FR, 26), fill=GREY)
y += 36
d.text((x0, y), "decoded from the receipt at the cited block. Nothing else.", font=f(FR, 26), fill=GREY)
y += 52

# warning strip
d.rectangle([x0, y, x1, y + 96], fill=(24, 24, 24))
d.text((x0 + 20, y + 16), "A screenshot is not an ingredient.", font=f(FB, 34), fill=PAPER)
d.text((x0 + 20, y + 58), "Run the same call on any BSC node and get the same answer.", font=f(FR, 24), fill=(180, 180, 180))

# ---- footer: the actual re-run command ------------------------------------
FY = LY + LH + 46
d.text((70, FY), "$ python3 flapjax_verify.py tx 0x8e4c8cb7…b775", font=f(FM, 30), fill=(120, 220, 160))
d.text((70, FY + 52), "FLAPJAX  0x90c8889f428F9Ebb77BB8f15CAD3a50a9aC680df  ·  BSC", font=f(FM, 24), fill=(150, 152, 158))
d.text((70, FY + 92), "MIT  ·  stdlib only  ·  read-only  ·  no keys", font=f(FM, 24), fill=(150, 152, 158))

# accent tick
d.rectangle([W - 90, FY + 4, W - 70, FY + 124], fill=ACCENT)

os.makedirs("meme", exist_ok=True)
out = "meme/flapjax-meme-w1.png"
img.save(out, "PNG", optimize=True)
print("wrote", out, os.path.getsize(out), "bytes", img.size)
