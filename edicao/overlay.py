"""Animated text layer (RGBA, 1080x1920 @30fps, 780 frames) written as raw frames to stdout,
or as PNG stills with: overlay.py FONTDIR --still t1,t2,... OUTDIR"""
import sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

W, H, FPS, NF = 1080, 1920, 30, 780
FD = sys.argv[1]
F = lambda name, size: ImageFont.truetype(f"{FD}/{name}.ttf", size)

IVORY = (248, 242, 230)
GOLD_TOP = np.array([246, 226, 168])
GOLD_BOT = np.array([184, 138, 62])

_cache = {}


def ease_out(x):
    x = min(max(x, 0.0), 1.0)
    return 1 - (1 - x) ** 3


def ramp(t, a, b):
    return min(max((t - a) / (b - a), 0.0), 1.0)


def text_layer(text, font, tracking, gold=False, color=IVORY):
    """Render text with letter tracking into an RGBA image (cached). Returns (img, letter_boxes)."""
    key = (text, font.path, font.size, tracking, gold, color)
    if key in _cache:
        return _cache[key]
    adv = []
    for ch in text:
        adv.append(font.getlength(ch))
    total = sum(adv) + tracking * (len(text) - 1)
    asc, desc = font.getmetrics()
    pad = 40
    w, h = int(total + 2 * pad), asc + desc + 2 * pad
    letters = []
    x = pad
    for ch, a in zip(text, adv):
        m = Image.new("L", (w, h), 0)
        ImageDraw.Draw(m).text((x, pad), ch, font=font, fill=255)
        letters.append(np.asarray(m, dtype=np.float32) / 255.0)
        x += a + tracking
    if gold:
        g = np.linspace(0, 1, h)[:, None, None]
        rgb = (GOLD_TOP * (1 - g) + GOLD_BOT * g) * np.ones((h, w, 3))
        # subtle sheen
    else:
        rgb = np.ones((h, w, 3)) * np.array(color)
    res = (rgb.astype(np.float32), letters, w, h)
    _cache[key] = res
    return res


def draw(canvas, text, font, cy, tracking=0, gold=False, color=IVORY, alpha=1.0,
         letter_alpha=None, dy=0.0, scale=1.0, shadow=0.55):
    """Composite text centred horizontally at vertical centre cy onto float canvas (H,W,4 premult)."""
    if alpha <= 0.001:
        return
    rgb, letters, w, h = text_layer(text, font, tracking, gold, color)
    a = np.zeros((h, w), np.float32)
    for i, m in enumerate(letters):
        la = 1.0 if letter_alpha is None else letter_alpha(i, len(letters))
        if la > 0:
            a = np.maximum(a, m * la)
    a *= alpha
    img = Image.fromarray(np.dstack([rgb, a * 255]).astype(np.uint8), "RGBA")
    if abs(scale - 1) > 1e-3:
        img = img.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.LANCZOS)
    iw, ih = img.size
    x0 = int(round(W / 2 - iw / 2))
    y0 = int(round(cy - ih / 2 + dy))
    arr = np.asarray(img, dtype=np.float32) / 255.0
    if shadow > 0:
        sh = img.split()[3].filter(ImageFilter.GaussianBlur(14))
        sa = np.asarray(sh, dtype=np.float32) / 255.0 * shadow
        comp(canvas, np.zeros((ih, iw, 3), np.float32), sa, x0, y0 + 4)
    comp(canvas, arr[..., :3], arr[..., 3], x0, y0)


def comp(canvas, rgb, a, x0, y0):
    h, w = a.shape
    xa, ya = max(0, x0), max(0, y0)
    xb, yb = min(W, x0 + w), min(H, y0 + h)
    if xa >= xb or ya >= yb:
        return
    sa = a[ya - y0:yb - y0, xa - x0:xb - x0, None]
    sr = rgb[ya - y0:yb - y0, xa - x0:xb - x0]
    dst = canvas[ya:yb, xa:xb]
    dst[..., :3] = sr * sa + dst[..., :3] * (1 - sa)
    dst[..., 3:] = sa + dst[..., 3:] * (1 - sa)


def line(canvas, cy, half_w, alpha, thick=2):
    if alpha <= 0 or half_w < 1:
        return
    x0, x1 = int(W / 2 - half_w), int(W / 2 + half_w)
    seg = canvas[int(cy):int(cy) + thick, x0:x1]
    col = np.array([214, 178, 105], np.float32) / 255
    seg[..., :3] = col * alpha + seg[..., :3] * (1 - alpha)
    seg[..., 3] = alpha + seg[..., 3] * (1 - alpha)


def vgrad(canvas, y0, y1, amax, alpha):
    """Dark vertical gradient for legibility (premultiplied black)."""
    if alpha <= 0:
        return
    ys = np.arange(y0, y1)
    g = np.sin(np.pi * (ys - y0) / (y1 - y0)) ** 1.2 * amax * alpha
    a = g[:, None, None]
    canvas[y0:y1, :, :3] *= (1 - a)
    canvas[y0:y1, :, 3:] = a + canvas[y0:y1, :, 3:] * (1 - a)


def stagger(t, start, per=0.045, dur=0.35):
    return lambda i, n: ease_out(ramp(t, start + i * per, start + i * per + dur))


# fonts
SANS = F("montserrat-latin-500-normal", 42)
SANS_SM = F("montserrat-latin-500-normal", 30)
SANS_B = F("montserrat-latin-600-normal", 56)
SANS_MD = F("montserrat-latin-500-normal", 50)
SANS_END1 = F("montserrat-latin-600-normal", 58)
SANS_END2 = F("montserrat-latin-400-normal", 38)
SERIF_XL = F("bodoni-moda-latin-500-normal", 104)
SERIF_HUGE = F("bodoni-moda-latin-600-normal", 186)
SERIF_DATE = F("bodoni-moda-latin-500-normal", 150)
SERIF_END = F("bodoni-moda-latin-500-normal", 96)

POP = 14.0


def frame(t):
    c = np.zeros((H, W, 4), np.float32)

    # ---- A: hook 0-4 ----
    if t < 4.2:
        out = 1 - ramp(t, 3.55, 3.95)
        vgrad(c, 560, 1260, 0.45, ramp(t, 0.0, 0.8) * out)
        a1 = ease_out(ramp(t, 0.35, 1.2)) * out
        trk = 18 + 10 * ease_out(ramp(t, 0.35, 2.5))
        draw(c, "AQUALÔRI", SANS, 790, tracking=trk, alpha=a1)
        line(c, 838, 150 * ease_out(ramp(t, 0.9, 1.7)), 0.9 * out)
        draw(c, "BLACK FRIDAY", SERIF_XL, 925, tracking=3, alpha=out,
             letter_alpha=stagger(t, 1.0, 0.05, 0.45),
             dy=14 * (1 - ease_out(ramp(t, 1.0, 2.0))), shadow=0.6)

    # ---- B/C: discreet tag while they speak ----
    if 4.2 < t < 14.0:
        a = ease_out(ramp(t, 4.4, 5.0)) * (1 - ramp(t, 13.4, 13.85))
        draw(c, "BLACK FRIDAY  ·  AQUALÔRI", SANS_SM, 262, tracking=9, alpha=a * 0.95, shadow=0.7)

    # ---- D: slow motion 14-22 ----
    if 13.9 < t < 22.2:
        # gentle legibility gradient behind the lower text block
        gA = ramp(t, 14.3, 15.0) * (1 - ramp(t, 21.6, 22.0))
        vgrad(c, 1000, 1640, 0.5, gA)
        # 50% OFF  (lands on beat 2 after the pop: 14.5)
        s0 = 14.5
        out = 1 - ramp(t, 17.45, 17.85)
        if t >= s0 - 0.05 and out > 0:
            p = ease_out(ramp(t, s0, s0 + 0.55))
            draw(c, "ATÉ", SANS_B, 1135, tracking=22, gold=True, alpha=ease_out(ramp(t, s0, s0 + 0.35)) * out,
                 dy=-18 * (1 - p) - 20 * ramp(t, 17.45, 17.85))
            draw(c, "50% OFF", SERIF_HUGE, 1300, tracking=4, gold=True, alpha=ease_out(ramp(t, s0, s0 + 0.3)) * out,
                 scale=1.08 - 0.08 * p + 0.012 * ramp(t, s0 + 0.55, 17.45),
                 dy=-20 * ramp(t, 17.45, 17.85), shadow=0.65)
            line(c, 1440, 170 * ease_out(ramp(t, s0 + 0.3, s0 + 1.0)), 0.9 * out)
        # 19, 20 E 21 DE NOVEMBRO  (lands on bar downbeat: 18.0)
        d0 = 18.0
        out2 = 1 - ramp(t, 21.55, 21.95)
        if t >= d0 - 0.05 and out2 > 0:
            p = ease_out(ramp(t, d0, d0 + 0.7))
            draw(c, "19, 20 E 21", SERIF_DATE, 1225, tracking=4, gold=True, alpha=out2,
                 letter_alpha=stagger(t, d0, 0.06, 0.4), dy=16 * (1 - p), shadow=0.65)
            line(c, 1352, 150 * ease_out(ramp(t, d0 + 0.4, d0 + 1.1)), 0.9 * out2)
            draw(c, "DE NOVEMBRO", SANS_MD, 1420, tracking=20, alpha=ease_out(ramp(t, d0 + 0.5, d0 + 1.1)) * out2,
                 dy=12 * (1 - ease_out(ramp(t, d0 + 0.5, d0 + 1.2))))
        # white flash on the pop
        fl = 0.55 * np.exp(-max(t - POP, 0) / 0.09) if t >= POP else 0.0
        if fl > 0.01:
            c[..., :3] = 1 * fl + c[..., :3] * (1 - fl)
            c[..., 3] = fl + c[..., 3] * (1 - fl)

    # ---- E: end card 22-26 ----
    if t >= 21.95:
        dark = 0.5 * ease_out(ramp(t, 21.95, 22.4))
        c[..., :3] *= (1 - dark)
        c[..., 3] = dark + c[..., 3] * (1 - dark)
        e = 22.0
        draw(c, "AQUALÔRI", SANS_END1, 700, tracking=30, alpha=ease_out(ramp(t, e + 0.05, e + 0.6)),
             dy=10 * (1 - ease_out(ramp(t, e, e + 0.7))))
        line(c, 760, 130 * ease_out(ramp(t, e + 0.3, e + 0.9)), 0.9)
        draw(c, "BLACK FRIDAY", SERIF_END, 850, tracking=3, gold=True,
             letter_alpha=stagger(t, e + 0.25, 0.04, 0.4), shadow=0.6)
        draw(c, "ATÉ 50% OFF", SANS_END1, 1010, tracking=14, alpha=ease_out(ramp(t, e + 0.75, e + 1.25)),
             dy=10 * (1 - ease_out(ramp(t, e + 0.75, e + 1.35))))
        draw(c, "19, 20 E 21 DE NOVEMBRO", SANS_END2, 1085, tracking=10,
             alpha=0.92 * ease_out(ramp(t, e + 1.0, e + 1.5)),
             dy=10 * (1 - ease_out(ramp(t, e + 1.0, e + 1.6))))
        fb = ramp(t, 25.35, 25.98)
        if fb > 0:
            c[..., :3] *= (1 - fb)
            c[..., 3] = fb + c[..., 3] * (1 - fb)
    return c


def to_rgba8(c):
    a = c[..., 3:4]
    rgb = np.where(a > 1e-4, c[..., :3] / np.maximum(a, 1e-4), 0)
    return (np.dstack([rgb, a]).clip(0, 1) * 255 + 0.5).astype(np.uint8)


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[2] == "--still":
        for ts in sys.argv[3].split(","):
            Image.fromarray(to_rgba8(frame(float(ts))), "RGBA").save(f"{sys.argv[4]}/ov_{ts}.png")
    else:
        out = sys.stdout.buffer
        for n in range(NF):
            out.write(to_rgba8(frame(n / FPS)).tobytes())
