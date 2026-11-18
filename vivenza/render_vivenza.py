#!/usr/bin/env python3
"""VIVENZA - Black Friday reel renderer (silent, 1080x1920, 30fps)."""
import os, sys, math, subprocess
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "src")
FONTS = os.path.join(HERE, "fonts")
W, H, FPS = 1080, 1920, 30

# ---------------------------------------------------------------- timeline
# Order requested: C (v3) -> B (v2, pause removed) -> A (v1)
SEGS = [("v3", 0.00, 8.60), ("v2", 0.30, 8.30), ("v2", 8.80, 20.88), ("v1", 0.00, 8.70)]
STARTS = []
_t = 0.0
for _, a, b in SEGS:
    STARTS.append(_t); _t += b - a
S0, S1, S2, S3 = STARTS
END_FOOT = _t
END_IN = END_FOOT - 0.75          # end-card panel starts rising
TOTAL = END_FOOT + 2.45
NFRAMES = int(round(TOTAL * FPS))

# ---------------------------------------------------------------- palette
INK = (17, 17, 19, 255)
WHITE = (255, 255, 255, 255)
SILVER_STOPS = [(0.0, (250, 250, 252)), (0.38, (204, 207, 213)), (0.55, (150, 155, 163)),
                (0.72, (226, 229, 233)), (1.0, (176, 180, 187))]

# ---------------------------------------------------------------- fonts
def mont(w, size): return ImageFont.truetype(f"{FONTS}/montserrat-latin-{w}-normal.woff", size)
def corm(w, size, italic=False):
    return ImageFont.truetype(f"{FONTS}/cormorant-garamond-latin-{w}-{'italic' if italic else 'normal'}.woff", size)

# ---------------------------------------------------------------- easing
def cl(x): return 0.0 if x < 0 else 1.0 if x > 1 else x
def prog(t, a, b): return cl((t - a) / (b - a))
def eo(x): x = cl(x); return 1 - (1 - x) ** 3
def eo5(x): x = cl(x); return 1 - (1 - x) ** 5
def ei(x): x = cl(x); return x ** 3
def eio(x): x = cl(x); return 4 * x ** 3 if x < .5 else 1 - (-2 * x + 2) ** 3 / 2
def eback(x, s=1.6):
    x = cl(x); c3 = s + 1; return 1 + c3 * (x - 1) ** 3 + s * (x - 1) ** 2
def env(t, a, b, fin=0.3, fout=0.3):
    if t < a or t > b: return 0.0
    return min(eo(prog(t, a, a + fin)), 1 - ei(prog(t, b - fout, b)))
def lerp(a, b, x): return a + (b - a) * x

# ---------------------------------------------------------------- sprite helpers
def fade(im, a):
    if a >= 0.999: return im
    im = im.copy()
    al = im.getchannel("A").point(lambda v: int(v * a))
    im.putalpha(al)
    return im

def put(base, im, x, y, a=1.0, clip=None):
    """alpha-composite sprite with top-left at (x,y), optional clip box."""
    if a <= 0.004 or im is None: return
    x = int(round(x)); y = int(round(y))
    cx0, cy0, cx1, cy1 = clip or (0, 0, W, H)
    cx0, cy0, cx1, cy1 = max(cx0, 0), max(cy0, 0), min(cx1, W), min(cy1, H)
    sx0, sy0 = max(cx0 - x, 0), max(cy0 - y, 0)
    sx1, sy1 = min(im.width, cx1 - x), min(im.height, cy1 - y)
    if sx1 <= sx0 or sy1 <= sy0: return
    if (sx0, sy0, sx1, sy1) != (0, 0, im.width, im.height):
        im = im.crop((sx0, sy0, sx1, sy1))
    base.alpha_composite(fade(im, a), (x + sx0, y + sy0))

def putc(base, im, cx, cy, a=1.0, s=1.0, rot=0.0, clip=None):
    """composite centred at (cx,cy) with scale / rotation."""
    if a <= 0.004: return
    if abs(s - 1) > 1e-3:
        im = im.resize((max(1, int(im.width * s)), max(1, int(im.height * s))), Image.BICUBIC)
    if abs(rot) > 0.05:
        im = im.rotate(rot, resample=Image.BICUBIC, expand=True)
    put(base, im, cx - im.width / 2, cy - im.height / 2, a, clip)

def silver_grad(h):
    ys = np.linspace(0, 1, h)
    out = np.zeros((h, 3), np.float32)
    for c in range(3):
        out[:, c] = np.interp(ys, [p for p, _ in SILVER_STOPS], [col[c] for _, col in SILVER_STOPS])
    return out

def silverize(im, y0=0, total_h=None):
    """recolour a white sprite with a metallic vertical gradient."""
    arr = np.array(im).astype(np.float32)
    total_h = total_h or im.height
    g = silver_grad(total_h)[y0:y0 + im.height]
    arr[:, :, :3] = g[:, None, :] * (arr[:, :, :3] / 255.0)
    return Image.fromarray(arr.clip(0, 255).astype(np.uint8), "RGBA")

def shadow_of(im, blur=10, a=0.45, grow=0):
    al = im.getchannel("A")
    pad = blur * 3
    canvas = Image.new("L", (im.width + 2 * pad, im.height + 2 * pad), 0)
    canvas.paste(al, (pad, pad))
    if grow: canvas = canvas.filter(ImageFilter.MaxFilter(grow * 2 + 1))
    canvas = canvas.filter(ImageFilter.GaussianBlur(blur)).point(lambda v: int(v * a))
    sh = Image.new("RGBA", canvas.size, (0, 0, 0, 255)); sh.putalpha(canvas)
    return sh, pad

def shimmer(im, phase, width=0.16, strength=0.85):
    """diagonal light sweep across sprite; phase 0..1."""
    if phase <= 0 or phase >= 1: return im
    arr = np.array(im).astype(np.float32)
    h, w = arr.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w]
    pos = (xx + yy * 0.45) / (w + h * 0.45)
    c = lerp(-width, 1 + width, phase)
    band = np.clip(1 - np.abs(pos - c) / width, 0, 1) ** 2 * strength
    arr[:, :, :3] = arr[:, :, :3] + (255 - arr[:, :, :3]) * band[:, :, None]
    return Image.fromarray(arr.clip(0, 255).astype(np.uint8), "RGBA")

class Line:
    """A line of text, renderable whole or character by character."""
    def __init__(self, text, font, fill=WHITE, tracking=0, silver=False, shadow=False):
        self.text, self.font, self.tracking = text, font, tracking
        asc, desc = font.getmetrics()
        self.pad = pad = int(font.size * 0.22) + 4
        self.h = asc + desc + 2 * pad
        self.asc = asc
        xs = [font.getlength(text[:i]) + i * tracking for i in range(len(text))]
        self.w = font.getlength(text) + tracking * (len(text) - 1)
        full = Image.new("RGBA", (int(self.w) + 2 * pad, self.h))
        d = ImageDraw.Draw(full)
        self.chars = []
        for ch, x in zip(text, xs):
            d.text((pad + x, pad), ch, font=font, fill=fill)
            if ch == " ": continue
            cw = int(font.getlength(ch)) + 2 * pad
            im = Image.new("RGBA", (cw, self.h))
            ImageDraw.Draw(im).text((pad, pad), ch, font=font, fill=fill)
            if silver: im = silverize(im)
            self.chars.append([im, x - pad + pad, None])  # x relative to line origin (incl pad)
        if silver: full = silverize(full)
        self.full = full
        self.sh = None
        if shadow:
            self.sh = shadow_of(full, blur=12, a=0.40)
            for c in self.chars: c[2] = shadow_of(c[0], blur=12, a=0.40)
        # visual vertical centre of caps/x-height region
        bb = full.getbbox() or (0, 0, full.width, full.height)
        self.vtop, self.vbot = bb[1], bb[3]

    def origin(self, cx, cy):
        """top-left so that visual box is centred at (cx, cy)."""
        return cx - self.full.width / 2, cy - (self.vtop + self.vbot) / 2

    def draw(self, base, cx, cy, a=1.0, dy=0, dx=0, clip=None, img=None):
        x, y = self.origin(cx, cy)
        if self.sh is not None:
            sh, p = self.sh
            put(base, sh, x - p + dx, y - p + dy + 4, a, clip)
        put(base, img or self.full, x + dx, y + dy, a, clip)

    def draw_chars(self, base, cx, cy, t, t0, stagger=0.04, dur=0.5, rise=None, mode="rise",
                   a_mul=1.0, clip_line=True):
        """per-character entrance. mode rise: slides up from a clip line."""
        x0, y0 = self.origin(cx, cy)
        rise = self.h * 0.75 if rise is None else rise
        clip = (0, int(y0 + self.vtop - 6), W, int(y0 + self.vbot + 10)) if clip_line else None
        if mode == "fade": clip = None
        for i, (im, x, sh) in enumerate(self.chars):
            p = prog(t, t0 + i * stagger, t0 + i * stagger + dur)
            if p <= 0: continue
            if mode == "rise":
                e = eo5(p); dy = (1 - e) * rise; a = min(1, p * 2.2)
            else:
                e = eo(p); dy = (1 - e) * rise; a = e
            if sh is not None:
                s_im, pd = sh
                put(base, s_im, x0 + x - pd, y0 + dy - pd + 4, a * a_mul * e, clip)
            put(base, im, x0 + x, y0 + dy, a * a_mul, clip)

    def exit_chars(self, base, cx, cy, t, t0, stagger=0.025, dur=0.35, dist=None):
        x0, y0 = self.origin(cx, cy)
        dist = self.h * 0.6 if dist is None else dist
        clip = (0, int(y0 + self.vtop - 6), W, int(y0 + self.vbot + 10))
        for i, (im, x, sh) in enumerate(self.chars):
            p = prog(t, t0 + i * stagger, t0 + i * stagger + dur)
            e = ei(p)
            if sh is not None and p < 1:
                s_im, pd = sh
                put(base, s_im, x0 + x - pd, y0 - e * dist - pd + 4, 1 - p, clip)
            put(base, im, x0 + x, y0 - e * dist, 1 - e * 0.3 if p < 1 else 0, clip)

def rrect(w, h, r, fill, outline=None, width=0):
    s = 3
    im = Image.new("RGBA", (w * s, h * s))
    ImageDraw.Draw(im).rounded_rectangle((0, 0, w * s - 1, h * s - 1), r * s, fill=fill,
                                         outline=outline, width=width * s)
    return im.resize((w, h), Image.LANCZOS)

def diamond(size, fill):
    s = 4; im = Image.new("RGBA", (size * s, size * s)); d = ImageDraw.Draw(im)
    c = size * s / 2
    d.polygon([(c, 0), (size * s, c), (c, size * s), (0, c)], fill=fill)
    return im.resize((size, size), Image.LANCZOS)

def hline(ov_draw, cx, y, w, col, width=2):
    if w <= 0.5: return
    ov_draw.line((cx - w / 2, y, cx + w / 2, y), fill=col, width=width)

# ---------------------------------------------------------------- assets
print("building assets...", flush=True)
A = {}
# intro (dark type over the light curtain)
A["i_viv"] = Line("VIVENZA", mont(600, 40), INK, tracking=26)
A["i_black"] = Line("BLACK", mont(700, 172), INK, tracking=18)
A["i_friday"] = Line("Friday", corm(500, 250, True), INK)
A["i_sub"] = Line("JOIAS EM PRATA 925", mont(500, 30), INK, tracking=12)
# lower third 1
A["l1_small"] = Line("BLACK FRIDAY", mont(600, 32), WHITE, tracking=18, shadow=True)
A["l1_big"] = Line("Vivenza", corm(500, 190, True), WHITE, shadow=True)
# lower third 2
A["l2_small"] = Line("JOIAS DELICADAS EM", mont(600, 30), WHITE, tracking=14, shadow=True)
A["l2_big"] = Line("Prata 925", corm(500, 180, True), WHITE, shadow=True)
# hero 30%
A["h_off"] = Line("OFF", mont(700, 104), WHITE, tracking=6, shadow=True)
A["h_l1"] = Line("EM TODAS", mont(600, 31), WHITE, tracking=7, shadow=True)
A["h_l2"] = Line("AS JOIAS", mont(600, 31), WHITE, tracking=7, shadow=True)
A["h_pct"] = {}
for n in range(0, 31):
    A["h_pct"][n] = Line(f"{n}%", mont(700, 250), WHITE, tracking=-4, silver=True, shadow=True)
A["h_pill_txt"] = Line("BLACK FRIDAY VIVENZA", mont(700, 25), INK, tracking=8)
# todas as joias
A["t_small"] = Line("30% OFF EM", mont(600, 31), WHITE, tracking=16, shadow=True)
A["t_big"] = Line("todas as joias", corm(500, 150, True), WHITE, shadow=True)
# dates
A["d_head"] = Line("BLACK FRIDAY  ·  3 DIAS", mont(600, 30), WHITE, tracking=12, shadow=True)
A["d_nov"] = Line("NOV", mont(600, 26), WHITE, tracking=8)
A["d_num"] = {n: Line(str(n), corm(600, 150), INK) for n in (19, 20, 21)}
A["d_sub"] = Line("DE NOVEMBRO", mont(600, 26), WHITE, tracking=14, shadow=True)
# recap
A["r_big"] = Line("Prata 925", corm(500, 170, True), WHITE, shadow=True)
A["r_box1"] = Line("30% OFF  ·  TODAS AS JOIAS", mont(600, 32), WHITE, tracking=8, shadow=True)
A["r_box2"] = Line("19 · 20 · 21 DE NOVEMBRO", mont(600, 32), WHITE, tracking=8, shadow=True)
# transition panel
A["p_viv"] = Line("VIVENZA", mont(600, 44), WHITE, tracking=30)
# end card
A["e_viv"] = Line("VIVENZA", corm(500, 150), WHITE, tracking=30)
A["e_viv_s"] = Line("VIVENZA", corm(500, 150), WHITE, tracking=30, silver=True)
A["e_bf"] = Line("BLACK FRIDAY", mont(600, 40), WHITE, tracking=22, silver=True)
A["e_off"] = Line("30% OFF", mont(700, 160), WHITE, tracking=2)
A["e_all"] = Line("em todas as joias", corm(500, 78, True), WHITE)
A["e_dates"] = Line("19 · 20 · 21 DE NOVEMBRO", mont(500, 34), WHITE, tracking=8)
A["e_prata"] = Line("PRATA 925", mont(500, 28), WHITE, tracking=18, silver=True)

# bottom legibility gradient
g = np.zeros((H, W, 4), np.uint8)
ys = np.arange(H)
ramp = np.clip((ys - 1060) / (H - 1060), 0, 1) ** 1.35 * 0.70
g[:, :, 3] = (ramp * 255).astype(np.uint8)[:, None]
A["grad"] = Image.fromarray(g, "RGBA")

def make_seal(r, ring_text, ring_font, center_lines, ring_col, center_col, bg=None, edge=None):
    s = 2; R = r * s
    im = Image.new("RGBA", (2 * R, 2 * R))
    d = ImageDraw.Draw(im)
    if bg: d.ellipse((0, 0, 2 * R - 1, 2 * R - 1), fill=bg)
    if edge:
        d.ellipse((6, 6, 2 * R - 7, 2 * R - 7), outline=edge, width=3)
        d.ellipse((int(R * 0.30), int(R * 0.30), int(2 * R - R * 0.30), int(2 * R - R * 0.30)), outline=edge, width=2)
    f = ImageFont.truetype(ring_font.path, ring_font.size * s)
    total = sum(f.getlength(c) for c in ring_text)
    rad = R * 0.83
    circ = 2 * math.pi * rad
    spacing = (circ - total) / len(ring_text)
    ang = -90.0
    for ch in ring_text:
        cw = f.getlength(ch)
        a_mid = ang + math.degrees((cw / 2) / rad)
        if ch != " ":
            gl = Image.new("RGBA", (int(cw) + 20, int(f.size * 1.6)))
            ImageDraw.Draw(gl).text((10, 0), ch, font=f, fill=ring_col)
            gl = gl.rotate(-(a_mid + 90), resample=Image.BICUBIC, expand=True)
            px = R + rad * math.cos(math.radians(a_mid)); py = R + rad * math.sin(math.radians(a_mid))
            im.alpha_composite(gl, (int(px - gl.width / 2), int(py - gl.height / 2)))
        ang += math.degrees((cw + spacing) / rad)
    ring = im
    centre = Image.new("RGBA", (2 * R, 2 * R))
    cd = ImageDraw.Draw(centre)
    tot_h = sum(fn.size * s * 1.0 for _, fn in center_lines)
    y = R - tot_h / 2
    for txt, fn in center_lines:
        f2 = ImageFont.truetype(fn.path, fn.size * s)
        cd.text((R, y + f2.size * 0.5), txt, font=f2, fill=center_col, anchor="mm")
        y += f2.size * 1.0
    return ring.resize((2 * r, 2 * r), Image.LANCZOS), centre.resize((2 * r, 2 * r), Image.LANCZOS)

A["seal925"] = make_seal(118, "PRATA 925 • JOIAS • PRATA 925 • JOIAS • ", mont(600, 17),
                         [("925", corm(600, 76))], (40, 40, 44, 255), (30, 30, 34, 255),
                         bg=(250, 249, 247, 215), edge=(60, 60, 66, 255))
A["seal_off"] = make_seal(112, "BLACK FRIDAY • BLACK FRIDAY • ", mont(600, 17),
                          [("30%", mont(700, 56)), ("OFF", mont(600, 26))], (225, 228, 233, 255),
                          WHITE, bg=(14, 14, 16, 235), edge=(200, 204, 210, 255))

def make_tape(segments, font, fg, bg, h, sep_col, border=None):
    """long horizontal strip (two periods) for marquee."""
    parts = []
    for txt in segments:
        L = Line(txt, font, fg, tracking=6)
        parts.append(L.full.crop((0, 0, L.full.width, L.full.height)))
    dm = diamond(int(h * 0.20), sep_col)
    gap = 46
    period_w = sum(p.width + gap + dm.width + gap for p in parts)
    strip = Image.new("RGBA", (period_w * 3, h), bg)
    x = 0
    for _ in range(3):
        for p in parts:
            strip.alpha_composite(p, (x, int(h / 2 - p.height / 2 + font.size * 0.02)))
            x += p.width + gap
            strip.alpha_composite(dm, (x, int(h / 2 - dm.height / 2)))
            x += dm.width + gap
    if border:
        d = ImageDraw.Draw(strip)
        d.line((0, 5, strip.width, 5), fill=border, width=2)
        d.line((0, h - 6, strip.width, h - 6), fill=border, width=2)
    return strip, period_w

A["tape1"] = make_tape(["BLACK FRIDAY", "30% OFF", "PRATA 925", "19 · 20 · 21 NOV"],
                       mont(700, 40), WHITE, (14, 14, 16, 255), 98, (200, 204, 210, 255))
A["tape2"] = make_tape(["VIVENZA", "TODAS AS JOIAS COM 30% OFF"],
                       mont(600, 32), INK, (250, 250, 248, 255), 80, (90, 92, 98, 255), border=(30, 30, 34, 255))

cards = {}
for n in (19, 20, 21):
    cw, ch_ = 196, 232
    c = rrect(cw, ch_, 20, (250, 250, 248, 255))
    band = Image.new("RGBA", (cw, 58), (14, 14, 16, 255))
    mask = rrect(cw, ch_, 20, (255, 255, 255, 255)).getchannel("A").crop((0, 0, cw, 58))
    c.paste(band, (0, 0), mask)
    nov = A["d_nov"]; ox, oy = nov.origin(cw / 2, 30)
    c.alpha_composite(nov.full, (int(ox), int(oy)))
    num = A["d_num"][n]; ox, oy = num.origin(cw / 2, 58 + (ch_ - 58) / 2)
    c.alpha_composite(num.full, (int(ox), int(oy)))
    # little binder holes
    d = ImageDraw.Draw(c)
    for hx in (cw * 0.3, cw * 0.7):
        d.ellipse((hx - 6, 22, hx + 6, 34), fill=(70, 70, 76, 255))
    sh, pd = shadow_of(c, blur=14, a=0.45)
    cards[n] = (c, sh, pd)
A["cards"] = cards
A["pill"] = rrect(int(A["h_pill_txt"].w) + 64, 58, 29, (250, 250, 248, 255))
print("assets ok", flush=True)

# ---------------------------------------------------------------- camera
def camera(t):
    """returns (seg_index, src_time, zoom, cx, cy) ; cx,cy normalised focus."""
    if t >= END_FOOT: return None
    k = max(i for i, s in enumerate(STARTS) if s <= t + 1e-9)
    name, a, b = SEGS[k]
    u = t - STARTS[k]
    src_t = a + u
    cx, cy = 0.5, 0.42
    if k == 0:
        z = lerp(1.08, 1.0, eio(prog(u, 0.0, 2.2))) + 0.045 * prog(u, 2.2, 8.2)
        z += 0.20 * ei(prog(u, 8.32, 8.60))            # zoom-through into transition
    elif k == 1:
        z = lerp(1.20, 1.0, eo(prog(u, 0.0, 0.45))) + 0.05 * prog(u, 0.45, 8.0)
    elif k == 2:
        cy = 0.36
        z = 1.15 + 0.035 * prog(u, 0, 5.3)               # punch-in hides the jump cut
        z = lerp(z, 1.0, eio(prog(u, 5.3, 6.0)))
        cy = lerp(0.36, 0.42, eio(prog(u, 5.3, 6.0)))
        if u > 6.0: z = 1.0 + 0.05 * prog(u, 6.0, 12.1)
    else:
        z = 1.0 + 0.05 * prog(u, 0, 7.6)
    return k, src_t, z, cx, cy

def apply_camera(img, z, cx, cy):
    if z <= 1.0005: return img
    cw, ch = W / z, H / z
    x0 = min(max(cx * W - cw / 2, 0), W - cw)
    y0 = min(max(cy * H - ch / 2, 0), H - ch)
    return img.resize((W, H), Image.BICUBIC, box=(x0, y0, x0 + cw, y0 + ch))

# ---------------------------------------------------------------- overlays
LT_Y_SMALL, LT_Y_BIG = 1300, 1428   # lower-third baseline area (inside Reels safe zone)

def grad_alpha(t):
    spans = [(1.45, 4.85), (4.75, 8.45), (S1 + 0.15, S2 - 0.1), (S2 + 0.1, S3 - 0.2), (S3 + 0.3, END_IN + 0.2)]
    return max([env(t, a, b, 0.35, 0.35) for a, b in spans] + [0])

def overlays(t, base):
    ov = Image.new("RGBA", (W, H))
    od = ImageDraw.Draw(ov)

    # bottom gradient for white type
    ga = grad_alpha(t)
    if ga > 0: put(base, A["grad"], 0, 0, ga)

    # ---------------- INTRO (over the empty curtain) ----------------
    if t < 1.6:
        ex = prog(t, 1.02, 1.42)
        a_all = 1 - eo(ex)
        # thin inset frame drawing in
        fr = eo(prog(t, 0.0, 0.55)) * a_all
        if fr > 0:
            col = (20, 20, 22, int(150 * a_all))
            m = 46
            L = (W - 2 * m) * fr; Hh = (H - 2 * m) * fr
            od.line((m, m, m + L, m), fill=col, width=2)
            od.line((W - m, H - m, W - m - L, H - m), fill=col, width=2)
            od.line((m, H - m, m, H - m - Hh), fill=col, width=2)
            od.line((W - m, m, W - m, m + Hh), fill=col, width=2)
        up = -70 * ei(ex)
        A["i_viv"].draw_chars(base, W / 2, 610 + up, t, 0.02, stagger=0.035, dur=0.45, mode="fade", rise=18, a_mul=a_all)
        hline(od, W / 2, 668 + up, 340 * eo(prog(t, 0.12, 0.6)), (20, 20, 22, int(200 * a_all)), 2)
        if ex <= 0:
            A["i_black"].draw_chars(base, W / 2, 805, t, 0.10, stagger=0.045, dur=0.5)
            A["i_friday"].draw_chars(base, W / 2, 985, t, 0.26, stagger=0.045, dur=0.55)
        else:
            A["i_black"].exit_chars(base, W / 2, 805, t, 1.02, stagger=0.03, dur=0.32)
            A["i_friday"].exit_chars(base, W / 2, 985, t, 1.08, stagger=0.03, dur=0.32)
        A["i_sub"].draw(base, W / 2, 1150 + up + 14 * (1 - eo(prog(t, 0.5, 0.9))), a=eo(prog(t, 0.5, 0.9)) * a_all)

    # ---------------- LOWER THIRD 1: BLACK FRIDAY / Vivenza ----------------
    a0, a1 = 1.55, 4.75
    if a0 <= t <= a1 + 0.05:
        out = eo(prog(t, a1 - 0.35, a1))
        a = 1 - out; dy = 26 * out
        L = A["l1_small"]
        L.draw(base, W / 2, LT_Y_SMALL + dy, a=a * eo(prog(t, a0, a0 + 0.35)))
        lw = 120 * eo(prog(t, a0 + 0.1, a0 + 0.6))
        if lw > 1:
            half = L.w / 2 + 26
            od.line((W / 2 - half - lw, LT_Y_SMALL + 2 + dy, W / 2 - half, LT_Y_SMALL + 2 + dy), fill=(235, 236, 240, int(230 * a)), width=2)
            od.line((W / 2 + half, LT_Y_SMALL + 2 + dy, W / 2 + half + lw, LT_Y_SMALL + 2 + dy), fill=(235, 236, 240, int(230 * a)), width=2)
        A["l1_big"].draw_chars(base, W / 2, LT_Y_BIG + 18 + dy, t, a0 + 0.12, stagger=0.05, dur=0.55, a_mul=a)

    # ---------------- LOWER THIRD 2 + seal: Prata 925 ----------------
    a0, a1 = 4.85, 8.42
    if a0 <= t <= a1 + 0.05:
        out = eo(prog(t, a1 - 0.3, a1)); a = 1 - out; dy = 26 * out
        L = A["l2_small"]
        p = eo(prog(t, a0, a0 + 0.45))
        L.draw(base, W / 2 - 40 * (1 - p), LT_Y_SMALL + dy, a=a * p)
        A["l2_big"].draw_chars(base, W / 2, LT_Y_BIG + 14 + dy, t, a0 + 0.1, stagger=0.045, dur=0.55, a_mul=a)
        # silver underline with diamond
        uw = 300 * eo(prog(t, a0 + 0.5, a0 + 1.0))
        if uw > 1:
            yy = LT_Y_BIG + 112 + dy
            od.line((W / 2 - uw, yy, W / 2 - 14, yy), fill=(214, 218, 224, int(235 * a)), width=2)
            od.line((W / 2 + 14, yy, W / 2 + uw, yy), fill=(214, 218, 224, int(235 * a)), width=2)
            put(base, diamond(14, (230, 232, 236, 255)), W / 2 - 7, yy - 7, a * eo(prog(t, a0 + 0.6, a0 + 0.9)))
    seal_spans = [(5.0, 8.40), (S3 + 0.55, END_IN + 0.15)]
    for s0, s1 in seal_spans:
        if s0 <= t <= s1:
            p = prog(t, s0, s0 + 0.6); a = env(t, s0, s1, 0.3, 0.3)
            sc = lerp(0.4, 1.0, eback(p, 2.0))
            ring, centre = A["seal925"]
            putc(base, ring, 186, 392, a=a, s=sc, rot=-(t - s0) * 24)
            putc(base, centre, 186, 392, a=a, s=sc)

    # ---------------- TRANSITION 1 flash ----------------
    # handled in frame() (white flash) ; light streak here
    if S1 - 0.12 <= t <= S1 + 0.18:
        p = prog(t, S1 - 0.12, S1 + 0.18)
        x = lerp(-300, W + 300, eio(p))
        streak = Image.new("RGBA", (420, H), (255, 255, 255, 0))
        arr = np.zeros((H, 420, 4), np.uint8); arr[:, :, :3] = 255
        prof = np.clip(1 - np.abs(np.linspace(-1, 1, 420)), 0, 1) ** 2.2
        arr[:, :, 3] = (prof * 150)[None, :].astype(np.uint8)
        streak = Image.fromarray(arr, "RGBA")
        put(base, streak, x - 210, 0, 1.0)

    # ---------------- HERO 30% OFF ----------------
    a0, a1 = S1 + 0.32, S1 + 4.3
    if a0 <= t <= a1 + 0.05:
        out = eo(prog(t, a1 - 0.35, a1)); a = 1 - out; dy = 30 * out
        n = int(round(30 * eo(prog(t, a0 + 0.05, a0 + 0.75))))
        P = A["h_pct"][n]
        P30 = A["h_pct"][30]
        right_w = max(A["h_off"].full.width, A["h_l1"].full.width) - 2 * A["h_off"].pad
        gap = 52
        total = P30.w + gap + right_w
        lx = W / 2 - total / 2
        cy = 1395 + dy
        p_in = eo(prog(t, a0, a0 + 0.5))
        # number right-aligned to fixed edge so the counter does not jitter
        num_right = lx + P30.w
        img = P.full
        sh_t = prog(t, a0 + 1.0, a0 + 1.7)
        sh_t2 = prog(t, a0 + 2.6, a0 + 3.3)
        if 0 < sh_t < 1: img = shimmer(img, sh_t)
        elif 0 < sh_t2 < 1: img = shimmer(img, sh_t2)
        sc = lerp(0.82, 1.0, eback(prog(t, a0, a0 + 0.55), 1.4))
        ncx = num_right - P.w / 2
        if P.sh is not None:
            sh, pd = P.sh
            ox, oy = P.origin(ncx, cy)
            put(base, sh, ox - pd, oy - pd + 5, a * p_in)
        putc(base, img, ncx, cy - (P.vtop + P.vbot) / 2 + P.full.height / 2, a=a * p_in, s=sc)
        # divider
        dvx = lx + P30.w + gap / 2
        dl = 170 * eo(prog(t, a0 + 0.3, a0 + 0.8))
        if dl > 1:
            od.line((dvx, cy - dl / 2, dvx, cy + dl / 2), fill=(210, 214, 220, int(230 * a)), width=2)
        rx = lx + P30.w + gap + right_w / 2
        A["h_off"].draw_chars(base, rx, cy - 44, t, a0 + 0.45, stagger=0.06, dur=0.45, a_mul=a)
        pr = eo(prog(t, a0 + 0.7, a0 + 1.1))
        A["h_l1"].draw(base, rx + 30 * (1 - pr), cy + 36, a=a * pr)
        pr2 = eo(prog(t, a0 + 0.8, a0 + 1.2))
        A["h_l2"].draw(base, rx + 30 * (1 - pr2), cy + 80, a=a * pr2)
        # pill
        pp = prog(t, a0 + 1.1, a0 + 1.55)
        if pp > 0:
            pill = A["pill"].copy()
            tx = A["h_pill_txt"]; ox, oy = tx.origin(pill.width / 2, pill.height / 2)
            pill.alpha_composite(tx.full, (int(ox), int(oy)))
            putc(base, pill, W / 2, 1556 + dy, a=a * min(1, pp * 2), s=lerp(0.6, 1, eback(pp, 2.2)))

    # ---------------- todas as joias + sticker ----------------
    a0, a1 = S1 + 4.5, S2 - 0.22
    if a0 <= t <= a1 + 0.05:
        out = eo(prog(t, a1 - 0.3, a1)); a = 1 - out; dy = 26 * out
        p = eo(prog(t, a0, a0 + 0.4))
        A["t_small"].draw(base, W / 2, LT_Y_SMALL - 6 + dy + 16 * (1 - p), a=a * p)
        A["t_big"].draw_chars(base, W / 2, LT_Y_BIG + 10 + dy, t, a0 + 0.12, stagger=0.035, dur=0.5, a_mul=a)
        # hand-drawn feel underline sweeping left -> right
        u = eo(prog(t, a0 + 0.7, a0 + 1.3))
        if u > 0:
            Lw = A["t_big"].w + 30
            x0 = W / 2 - Lw / 2
            yy = LT_Y_BIG + 92 + dy
            od.line((x0, yy, x0 + Lw * u, yy), fill=(218, 221, 227, int(240 * a)), width=3)
        # sticker top-right
        sp = prog(t, a0 + 0.5, a0 + 1.1)
        if sp > 0:
            ring, centre = A["seal_off"]
            sc = lerp(0.3, 1.0, eback(sp, 2.2))
            putc(base, ring, 888, 420, a=a * min(1, sp * 2), s=sc, rot=(t - a0) * 28)
            putc(base, centre, 888, 420, a=a * min(1, sp * 2), s=sc, rot=-8 * (1 - eo(sp)) + 6)

    # ---------------- DATES (calendar cards) ----------------
    a0, a1 = S2 + 0.28, S2 + 5.25
    if a0 <= t <= a1 + 0.1:
        p = eo(prog(t, a0, a0 + 0.4))
        aout = 1 - eo(prog(t, a1 - 0.3, a1))
        A["d_head"].draw(base, W / 2, 1170 + 20 * (1 - p), a=p * aout)
        cw = 196; gap = 34
        xs = [W / 2 + (i - 1) * (cw + gap) for i in range(3)]
        tilts = [-7, 5, -4]
        for i, n in enumerate((19, 20, 21)):
            st = a0 + 0.22 + i * 0.16
            q = prog(t, st, st + 0.55)
            if q <= 0: continue
            qo = prog(t, a1 - 0.42 + i * 0.07, a1 - 0.1 + i * 0.07)
            sc = lerp(0.5, 1.0, eback(q, 2.0)) * (1 - 0.15 * ei(qo))
            yy = 1355 + 60 * (1 - eo(q)) + 120 * ei(qo)
            rot = tilts[i] * (1 - eo(q)) + (math.sin((t - st) * 2.2 + i) * 0.8 if q >= 1 else 0)
            al = min(1, q * 2.5) * (1 - ei(qo))
            c, sh, pd = A["cards"][n]
            putc(base, sh, xs[i], yy + 10, a=al, s=sc, rot=rot)
            putc(base, c, xs[i], yy, a=al, s=sc, rot=rot)
        sp = eo(prog(t, a0 + 0.85, a0 + 1.25))
        A["d_sub"].draw(base, W / 2, 1520 + 14 * (1 - sp), a=sp * aout)

    # ---------------- RECAP: Prata 925 + swapping framed box ----------------
    a0, a1 = S2 + 5.75, S3 - 0.3
    if a0 <= t <= a1 + 0.05:
        out = eo(prog(t, a1 - 0.3, a1)); a = 1 - out; dy = 26 * out
        A["r_big"].draw_chars(base, W / 2, 1300 + dy, t, a0, stagger=0.05, dur=0.55, a_mul=a)
        bw = max(A["r_box1"].w, A["r_box2"].w) + 80; bh = 76
        by = 1452 + dy
        f = eo(prog(t, a0 + 0.45, a0 + 1.15))
        if f > 0:
            col = (232, 234, 238, int(235 * a))
            x0, x1 = W / 2 - bw / 2, W / 2 + bw / 2
            y0, y1 = by - bh / 2, by + bh / 2
            # border draws from top-centre around both sides
            per = bw / 2 + bh + bw / 2
            dist = per * f
            def seg_draw(sign):
                d_ = dist
                cxs = W / 2
                l1 = min(d_, bw / 2); od.line((cxs, y0, cxs + sign * l1, y0), fill=col, width=2); d_ -= l1
                if d_ > 0:
                    l2 = min(d_, bh); xe = cxs + sign * bw / 2
                    od.line((xe, y0, xe, y0 + l2), fill=col, width=2); d_ -= l2
                if d_ > 0:
                    l3 = min(d_, bw / 2); xe = cxs + sign * bw / 2
                    od.line((xe, y1, xe - sign * l3, y1), fill=col, width=2)
            seg_draw(1); seg_draw(-1)
        # text swaps every ~2.4 s with a vertical slide inside the box
        clip = (0, int(by - bh / 2 + 3), W, int(by + bh / 2 - 2))
        k0 = a0 + 0.8
        cyc = 2.4
        if t >= k0:
            idx = int((t - k0) // cyc); ph = (t - k0) - idx * cyc
            cur = [A["r_box1"], A["r_box2"]][idx % 2]
            nxt = [A["r_box1"], A["r_box2"]][(idx + 1) % 2]
            if idx == 0 and ph < 0.4:
                cur.draw(base, W / 2, by + 40 * (1 - eo(ph / 0.4)), a=a * eo(ph / 0.4), clip=clip)
            elif ph > cyc - 0.4 and t + (cyc - ph) < a1 - 0.3:
                q = eio((ph - (cyc - 0.4)) / 0.4)
                cur.draw(base, W / 2, by - 60 * q, a=a, clip=clip)
                nxt.draw(base, W / 2, by + 60 * (1 - q), a=a, clip=clip)
            else:
                cur.draw(base, W / 2, by, a=a, clip=clip)

    # ---------------- TAPES (marquee) ----------------
    a0, a1 = S3 + 0.35, END_IN + 0.1
    if a0 - 0.01 <= t <= a1 + 0.3:
        pin = eo5(prog(t, a0, a0 + 0.6)); pout = ei(prog(t, a1 - 0.35, a1 + 0.1))
        for key, cy, ang, speed, dirn, delay in (("tape2", 1500, 3.2, 70, 1, 0.12), ("tape1", 1418, -4.0, 95, -1, 0.0)):
            strip, per = A[key]
            pi = eo5(prog(t, a0 + delay, a0 + delay + 0.6))
            off = ((t - a0) * speed) % per
            if dirn < 0: x = off
            else: x = per - off
            crop = strip.crop((int(x), 0, int(x) + 1400, strip.height))
            rot = crop.rotate(ang, resample=Image.BICUBIC, expand=True)
            slide = (1 - pi) * 1500 * dirn + pout * 1500 * -dirn
            sh, pd = shadow_of(crop, blur=18, a=0.55)
            putc(base, sh.rotate(ang, resample=Image.BICUBIC, expand=True), W / 2 + slide, cy + 12)
            putc(base, rot, W / 2 + slide, cy)

    # ---------------- TRANSITION 2: black panel wipe ----------------
    if S3 - 0.26 <= t <= S3 + 0.26:
        if t < S3:
            top = lerp(H, 0, eio(prog(t, S3 - 0.26, S3))); bot = H
        else:
            top = 0; bot = lerp(H, 0, eio(prog(t, S3, S3 + 0.26)))
        if bot > top:
            od.rectangle((0, top, W, bot), fill=(12, 12, 14, 255))
            edge = top if t < S3 else bot
            od.line((0, edge, W, edge), fill=(210, 214, 220, 255), width=3)
    base.alpha_composite(ov)
    if S3 - 0.26 <= t <= S3 + 0.26:
        if t < S3: top, bot = lerp(H, 0, eio(prog(t, S3 - 0.26, S3))), H
        else: top, bot = 0, lerp(H, 0, eio(prog(t, S3, S3 + 0.26)))
        A["p_viv"].draw(base, W / 2, H / 2, a=1.0, clip=(0, int(top) + 3, W, int(bot) - 3))

    # ---------------- END CARD ----------------
    if t >= END_IN:
        top = lerp(H, 0, eio(prog(t, END_IN, END_IN + 0.5)))
        ov2 = Image.new("RGBA", (W, H)); d2 = ImageDraw.Draw(ov2)
        d2.rectangle((0, top, W, H), fill=(12, 12, 14, 255))
        if top > 0: d2.line((0, top, W, top), fill=(210, 214, 220, 255), width=3)
        e0 = END_IN + 0.38
        fr = eo(prog(t, e0, e0 + 0.7))
        if fr > 0:
            m = 56; col = (220, 223, 228, 120)
            L = (W - 2 * m) * fr; Hh = (H - 2 * m) * fr
            d2.line((m, m, m + L, m), fill=col, width=2)
            d2.line((W - m, H - m, W - m - L, H - m), fill=col, width=2)
            d2.line((m, H - m, m, H - m - Hh), fill=col, width=2)
            d2.line((W - m, m, W - m, m + Hh), fill=col, width=2)
        lw = 300 * eo(prog(t, e0 + 0.35, e0 + 0.8))
        hline(d2, W / 2, 805, lw, (205, 209, 216, 255), 2)
        base.alpha_composite(ov2)
        # VIVENZA (white -> silver shimmer)
        vv = A["e_viv"]
        if t < e0 + 0.9:
            vv.draw_chars(base, W / 2, 690, t, e0, stagger=0.05, dur=0.6)
        else:
            sp = prog(t, e0 + 1.0, e0 + 1.7)
            img = A["e_viv_s"].full
            if 0 < sp < 1: img = shimmer(img, sp, width=0.18)
            mix = eo(prog(t, e0 + 0.9, e0 + 1.2))
            vv.draw(base, W / 2, 690, a=1 - mix)
            A["e_viv_s"].draw(base, W / 2, 690, a=mix, img=img)
        A["e_bf"].draw_chars(base, W / 2, 872, t, e0 + 0.35, stagger=0.025, dur=0.4, mode="fade", rise=14)
        q = prog(t, e0 + 0.55, e0 + 1.05)
        if q > 0:
            putc(base, A["e_off"].full, W / 2, 1040 - (A["e_off"].vtop + A["e_off"].vbot) / 2 + A["e_off"].full.height / 2,
                 a=min(1, q * 2), s=lerp(0.7, 1.0, eback(q, 1.8)))
        A["e_all"].draw_chars(base, W / 2, 1172, t, e0 + 0.75, stagger=0.025, dur=0.45)
        bx = eo(prog(t, e0 + 0.95, e0 + 1.4))
        if bx > 0:
            ov3 = Image.new("RGBA", (W, H)); d3 = ImageDraw.Draw(ov3)
            bw = A["e_dates"].w + 70
            d3.rounded_rectangle((W / 2 - bw / 2 * bx, 1268, W / 2 + bw / 2 * bx, 1344), 38,
                                 outline=(220, 223, 228, 230), width=2)
            base.alpha_composite(ov3)
            A["e_dates"].draw(base, W / 2, 1306, a=eo(prog(t, e0 + 1.15, e0 + 1.5)))
        A["e_prata"].draw(base, W / 2, 1430 + 12 * (1 - eo(prog(t, e0 + 1.25, e0 + 1.6))),
                          a=eo(prog(t, e0 + 1.25, e0 + 1.6)))
        dm = diamond(12, (215, 218, 224, 255))
        put(base, dm, W / 2 - 6, 1495, a=eo(prog(t, e0 + 1.4, e0 + 1.7)))
    return base

def flash_amount(t):
    return 0.85 * max(0.0, 1 - abs(t - S1) / 0.11)

# ---------------------------------------------------------------- IO
class Reader:
    def __init__(self, name, a, b):
        n = int(round((b - a) * FPS)) + 2
        self.p = subprocess.Popen(
            ["ffmpeg", "-v", "error", "-ss", f"{a:.3f}", "-i", f"{SRC}/{name}.mov", "-frames:v", str(n), "-an",
             "-vf", "scale=in_color_matrix=bt709:in_range=tv:flags=accurate_rnd+full_chroma_int,format=rgb24",
             "-f", "rawvideo", "-"], stdout=subprocess.PIPE)
        self.last = None
    def get(self):
        buf = self.p.stdout.read(W * H * 3)
        if len(buf) == W * H * 3:
            self.last = Image.frombuffer("RGB", (W, H), buf, "raw", "RGB", 0, 1)
        return self.last
    def close(self):
        try: self.p.stdout.close(); self.p.kill()
        except Exception: pass

def grab(name, ts):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{ts:.3f}", "-i", f"{SRC}/{name}.mov", "-frames:v", "1",
                          "-vf", "scale=in_color_matrix=bt709:in_range=tv,format=rgb24", "-f", "rawvideo", "-"],
                         capture_output=True).stdout
    return Image.frombuffer("RGB", (W, H), raw, "raw", "RGB", 0, 1)

def compose(t, src_img):
    cam = camera(t)
    if cam is None or src_img is None:
        img = Image.new("RGB", (W, H), (12, 12, 14))
    else:
        _, _, z, cx, cy = cam
        img = apply_camera(src_img, z, cx, cy)
    fa = flash_amount(t)
    if fa > 0: img = Image.blend(img, Image.new("RGB", (W, H), (255, 255, 255)), fa)
    base = img.convert("RGBA")
    base = overlays(t, base)
    return base.convert("RGB")

def preview(times, out):
    tiles = []
    for t in times:
        cam = camera(t)
        src = grab(SEGS[cam[0]][0], cam[1]) if cam else None
        im = compose(t, src).resize((360, 640), Image.LANCZOS)
        ImageDraw.Draw(im).text((8, 8), f"{t:.2f}s", fill=(255, 0, 0))
        tiles.append(im)
    cols = min(6, len(tiles)); rows = math.ceil(len(tiles) / cols)
    sheet = Image.new("RGB", (cols * 360, rows * 640), (0, 0, 0))
    for i, im in enumerate(tiles): sheet.paste(im, ((i % cols) * 360, (i // cols) * 640))
    sheet.save(out)

def render(out_path):
    enc = subprocess.Popen(
        ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
         "-i", "-", "-an",
         "-vf", "scale=out_color_matrix=bt709:out_range=tv:flags=accurate_rnd+full_chroma_int,format=yuv420p",
         "-c:v", "libx264", "-preset", "slow", "-crf", "16", "-profile:v", "high", "-level", "4.2",
         "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", "-color_range", "tv",
         "-movflags", "+faststart", out_path], stdin=subprocess.PIPE)
    reader = None; cur = -1
    for f in range(NFRAMES):
        t = f / FPS
        cam = camera(t)
        src = None
        if cam is not None:
            k = cam[0]
            if k != cur:
                if reader: reader.close()
                reader = Reader(*SEGS[k]); cur = k
            src = reader.get()
        elif reader is not None:
            reader.close(); reader = None
        enc.stdin.write(compose(t, src).tobytes())
        if f % 60 == 0: print(f"frame {f}/{NFRAMES}", flush=True)
    if reader: reader.close()
    enc.stdin.close(); enc.wait()
    print("done", out_path, f"{TOTAL:.2f}s")

if __name__ == "__main__":
    print(f"segments start at {STARTS}, footage ends {END_FOOT:.2f}, total {TOTAL:.2f}s")
    if sys.argv[1] == "preview":
        times = [float(x) for x in sys.argv[3].split(",")]
        preview(times, sys.argv[2])
    else:
        render(sys.argv[2])
