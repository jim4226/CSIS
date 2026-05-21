"""Composite crisp labels onto the 3D Blender renders -> labelled PNGs for
the README (GitHub markdown can't do the HTML overlay the site uses).

Run:  python docs/diagrams/_label_renders.py
Outputs trust_lattice_labeled.png + memory_labeled.png.
"""
import json
import os
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
CREAM = (251, 244, 231)
INK = (31, 31, 31)
DIM = (111, 111, 111)
FAINT = (138, 133, 121)
BORDER = (200, 184, 144)

def font(name, size):
    for p in (r"C:\Windows\Fonts\%s" % name, "/usr/share/fonts/%s" % name):
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()

F_NAME = font("arialbd.ttf", 32)
F_SUB = font("arial.ttf", 22)
F_BADGE = font("arialbd.ttf", 32)
F_GATE = font("consola.ttf", 22)
F_GATEB = font("consolab.ttf", 22)
F_HEAD = font("consolab.ttf", 24)


def base(png_name, coords_name):
    coords = json.load(open(os.path.join(HERE, coords_name)))
    rw, rh = coords["res"]
    render = Image.open(os.path.join(HERE, png_name)).convert("RGBA")
    canvas = Image.new("RGBA", (rw, rh), CREAM + (255,))
    canvas.alpha_composite(render)
    return canvas, ImageDraw.Draw(canvas), coords["anchors"], rw, rh


def chip(d, cx, cy, badge_txt, badge_col, name, sub, w=348, h=78, anchor="lm",
         badge_font=F_BADGE):
    """rounded label card with a colour badge."""
    if anchor == "lm":
        x0 = cx
    elif anchor == "mm":
        x0 = cx - w // 2
    y0 = cy - h // 2
    d.rounded_rectangle([x0, y0, x0 + w, y0 + h], radius=13,
                        fill=(255, 253, 248, 240), outline=BORDER, width=2)
    # badge
    bs = 40
    bx, by = x0 + 14, cy - bs // 2
    d.rounded_rectangle([bx, by, bx + bs, by + bs], radius=9, fill=badge_col + (255,))
    bb = d.textbbox((0, 0), badge_txt, font=badge_font)
    d.text((bx + bs / 2 - (bb[2] - bb[0]) / 2 - bb[0],
            cy - (bb[3] - bb[1]) / 2 - bb[1]),
           badge_txt, font=badge_font, fill=(255, 255, 255))
    tx = bx + bs + 16
    d.text((tx, cy - 18), name, font=F_NAME, fill=INK)
    d.text((tx, cy + 12), sub, font=F_SUB, fill=DIM)


def leader(d, p_from, p_to, col=(194, 180, 143)):
    d.line([p_from, p_to], fill=col, width=3)
    r = 6
    for (x, y) in (p_from, p_to):
        d.ellipse([x - r, y - r, x + r, y + r], fill=col)


# ============================ TRUST ============================
def trust():
    canvas, d, A, rw, rh = base("trust_lattice.png", "trust_lattice.coords.json")
    order = ["promoted", "verified", "candidate", "untrusted", "raw"]
    meta = {
        "promoted":  ("4", (95, 154, 62),  "live - next iteration reads as truth"),
        "verified":  ("3", (74, 130, 188), "V1+V2 cert - cross-checkpoint"),
        "candidate": ("2", (217, 119, 87), "written - not yet visible to live"),
        "untrusted": ("1", (194, 152, 47), "stored on disk - may be poisoned"),
        "raw":       ("0", (138, 133, 121),"just-observed - in-memory only"),
    }
    chip_cx = int(0.635 * rw)
    chip_cys = [int(p * rh) for p in (0.27, 0.41, 0.545, 0.675, 0.80)]
    # leaders + chips
    for lvl, cy in zip(order, chip_cys):
        a = A[lvl]
        sx, sy = int(a["x"] * rw), int(a["y"] * rh)
        leader(d, (sx, sy), (chip_cx, cy))
    for lvl, cy in zip(order, chip_cys):
        bnum, bcol, sub = meta[lvl]
        chip(d, chip_cx, cy, bnum, bcol, lvl, sub)
    # gates between chips
    gates = [("gate 4", "hash-CAS atomic flip"),
             ("gate 3", "cross-checkpoint cert"),
             ("gate 2", "basic Verifier check"),
             ("gate 1", "write to storage")]
    for i, (gn, gt) in enumerate(gates):
        gy = (chip_cys[i] + chip_cys[i + 1]) // 2
        gx = chip_cx + 18
        d.ellipse([gx, gy - 13, gx + 26, gy + 13], outline=(90, 108, 70), width=3,
                  fill=(230, 235, 217, 255))
        d.text((gx + 40, gy - 12), gn, font=F_GATEB, fill=(90, 108, 70))
        d.text((gx + 40, gy + 8), gt, font=F_GATE, fill=DIM)
    # deprecated note, bottom-left
    nx, ny = int(0.04 * rw), int(0.84 * rh)
    d.rounded_rectangle([nx, ny, nx + 360, ny + 92], radius=11,
                        fill=(243, 219, 208, 255), outline=(196, 84, 59), width=0)
    d.rectangle([nx, ny, nx + 5, ny + 92], fill=(196, 84, 59))
    d.text((nx + 20, ny + 16), "level 5 - deprecated  (terminal)", font=F_NAME,
           fill=(124, 47, 24))
    d.text((nx + 20, ny + 52), "downgrade allowed from any non-raw level - no path out",
           font=F_SUB, fill=(196, 84, 59))
    out = os.path.join(HERE, "trust_lattice_labeled.png")
    canvas.convert("RGB").save(out, quality=95)
    print("WROTE", out)


# ============================ MEMORY ============================
def memory():
    canvas, d, A, rw, rh = base("memory.png", "memory.coords.json")
    # column headers
    def header(cx, cy, txt, sub):
        w = 360
        d.rounded_rectangle([cx - w // 2, cy - 26, cx + w // 2, cy + 26], radius=10,
                            fill=(255, 253, 248, 240), outline=BORDER, width=2)
        full = txt + "   " + sub
        d.text((cx, cy), txt, font=F_HEAD, fill=INK, anchor="mm")
    header(int(0.30 * rw), int(0.07 * rh), "CANDIDATE  -  writes free", "")
    header(int(0.80 * rw), int(0.12 * rh), "LIVE  -  promote() only", "")
    tiers = [
        ("working", "in-flight scratch"),
        ("episodic", "iteration narrative + outcomes"),
        ("semantic", "durable facts"),
        ("procedural", "* reusable skills - self-improving surface"),
        ("causal", "why-this-fixed-that"),
    ]
    for i, (name, sub) in enumerate(tiers):
        a = A["cand_%d" % i]
        cx, cy = int(a["x"] * rw), int(a["y"] * rh)
        star = name == "procedural"
        bcol = (95, 154, 62) if star else (217, 119, 87)
        chip(d, cx, cy, "*" if star else "", bcol, name, sub, w=430, anchor="mm")
    # promote callout near the middle connector
    pm = A["live_2"]
    ca = A["cand_2"]
    px = int((pm["x"] + ca["x"]) / 2 * rw)
    py = int((pm["y"] + ca["y"]) / 2 * rh)
    d.ellipse([px - 14, py - 14, px + 14, py + 14], outline=(90, 108, 70), width=3,
              fill=(230, 235, 217, 255))
    d.text((px + 26, py - 12), "promote()", font=F_GATEB, fill=(90, 108, 70))
    d.text((px + 26, py + 10), "the only path to live", font=F_GATE, fill=DIM)
    out = os.path.join(HERE, "memory_labeled.png")
    canvas.convert("RGB").save(out, quality=95)
    print("WROTE", out)


# ============================ STACK ============================
def stack():
    canvas, d, A, rw, rh = base("stack.png", "stack.coords.json")
    layers = [
        ("L7", (95, 154, 62),  "Safety envelope",  "Constitution - TierGuard - tripwires"),
        ("L6", (150, 138, 110),"Meta-improvement", "deferred to Phase 1"),
        ("L5", (217, 119, 87), "Improvement",      "procedural skill accumulation"),
        ("L4", (74, 130, 188), "Verification",     "V1+V2 - on a different checkpoint"),
        ("L3", (217, 119, 87), "Curiosity",        "frontier-item generator"),
        ("L2", (217, 119, 87), "Memory hierarchy", "5 tiers - candidate / live"),
        ("L1", (217, 119, 87), "Agent runtime",    "Coordinator + 6 specialised roles"),
        ("L0", (217, 166, 71), "Substrate",        "event log - capability tags - hashing"),
    ]
    chip_x = int(0.585 * rw)
    for lid, bcol, name, sub in layers:
        a = A[lid]
        leader(d, (int(a["x"] * rw), int(a["y"] * rh)), (chip_x, int(a["y"] * rh)))
    for lid, bcol, name, sub in layers:
        a = A[lid]
        chip(d, chip_x, int(a["y"] * rh), lid, bcol, name, sub, w=402,
             badge_font=F_GATEB)
    out = os.path.join(HERE, "stack_labeled.png")
    canvas.convert("RGB").save(out, quality=95)
    print("WROTE", out)


if __name__ == "__main__":
    trust()
    memory()
    stack()
