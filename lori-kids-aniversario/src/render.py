#!/usr/bin/env python3
"""Lôri Kids — 5 anos. Compositor do vídeo da campanha (1080x1920, 30 fps).

Uso:
  LK_WORK=<pasta de intermediários> python3 render.py frames 10 50 120   -> PNGs de prévia
  LK_WORK=... python3 render.py chunk <i> <n> <saida.mp4>               -> trecho de vídeo (sem áudio)
  LK_WORK=... python3 render.py audio <saida.wav>                       -> áudio editado (sincronizado)

Os intermediários (LK_WORK/raw/c*.rgb) são os clipes originais já com correção de cor,
decodificados em 30 fps (ver build.sh).
"""
import os, sys, json, math, random, subprocess
import numpy as np
import skia

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONTS = os.path.join(ROOT, "fontes")
WORK = os.environ.get("LK_WORK", "")
W, H, FPS = 1080, 1920, 30

# ------------------------------------------------------------------ paleta
ORANGE = "#F37032"; ORANGE_D = "#C9501A"; ORANGE_L = "#F89A5E"
YELLOW = "#FFC83D"; YELLOW_D = "#E9A419"; YELLOW_L = "#FFE3A1"
GREEN = "#3E8E4E"; GREEN_D = "#1F4D34"; GREEN_DD = "#0F2A1C"; SAGE = "#B9CBA3"
CREAM = "#FFF6E7"; WHITE = "#FFFFFF"


def col(h, a=1.0):
    h = h.lstrip("#")
    return skia.ColorSetARGB(max(0, min(255, int(round(a * 255)))), int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


# ------------------------------------------------------------------ easing
def clamp(x, a=0.0, b=1.0):
    return a if x < a else b if x > b else x


def lin(t, t0, t1):
    if t1 <= t0:
        return 1.0 if t >= t0 else 0.0
    return clamp((t - t0) / (t1 - t0))


def eoc(x): return 1 - (1 - x) ** 3
def eic(x): return x ** 3
def eioc(x): return 4 * x ** 3 if x < .5 else 1 - (-2 * x + 2) ** 3 / 2
def eoq(x): return 1 - (1 - x) ** 5
def eoexpo(x): return 1.0 if x >= 1 else 1 - 2 ** (-10 * x)


def eoback(x, s=1.7):
    x -= 1
    return 1 + (s + 1) * x ** 3 + s * x ** 2


def spring(x, f=2.2, d=5.5):
    """x em segundos desde o início; termina em 1 com leve oscilação."""
    if x <= 0:
        return 0.0
    return 1 - math.exp(-d * x) * math.cos(f * 2 * math.pi * x)


def mix(a, b, p): return a + (b - a) * p


# ------------------------------------------------------------------ fontes
_TF = {}


def tf(fam, w):
    k = (fam, w)
    if k not in _TF:
        _TF[k] = skia.Typeface.MakeFromFile(os.path.join(FONTS, f"{fam}-{w}.ttf"))
    return _TF[k]


def font(fam, w, size):
    f = skia.Font(tf(fam, w), size)
    f.setEdging(skia.Font.Edging.kAntiAlias)
    f.setSubpixel(True)
    f.setHinting(skia.FontHinting.kNone)
    return f


def paint(c, a=1.0, stroke=None, shadow=None, blur=None, shader=None):
    p = skia.Paint(AntiAlias=True)
    p.setColor(col(c, a) if isinstance(c, str) else c)
    if stroke:
        p.setStyle(skia.Paint.kStroke_Style)
        p.setStrokeWidth(stroke)
        p.setStrokeCap(skia.Paint.kRound_Cap)
        p.setStrokeJoin(skia.Paint.kRound_Join)
    if shadow:
        dx, dy, s, sc, sa = shadow
        p.setImageFilter(skia.ImageFilters.DropShadow(dx, dy, s, s, col(sc, sa * a)))
    elif blur and blur > 0.05:
        p.setImageFilter(skia.ImageFilters.Blur(blur, blur))
    if shader is not None:
        p.setShader(shader)
    return p


SH_TEXT = (0, 5, 12, GREEN_DD, .55)      # sombra padrão para textos claros sobre vídeo
SH_SOFT = (0, 10, 22, GREEN_DD, .35)


def measure(f, s, track=0):
    if not track:
        return f.measureText(s)
    return sum(f.measureText(ch) for ch in s) + track * (len(s) - 1)


def text(c, s, fam, w, size, x, y, color, a=1.0, align="l", track=0, shadow=None, blur=None):
    if a <= 0.003:
        return 0
    f = font(fam, w, size)
    tw = measure(f, s, track)
    x0 = x - tw * {"l": 0, "c": .5, "r": 1}[align]
    p = paint(color, a, shadow=shadow, blur=blur)
    if not track:
        c.drawString(s, x0, y, f, p)
    else:
        cx = x0
        for ch in s:
            c.drawString(ch, cx, y, f, p)
            cx += f.measureText(ch) + track
    return tw


def text_chars(c, s, fam, w, size, x, y, color, fn, align="l", track=0, shadow=None):
    """Desenha caractere a caractere; fn(i, n) -> (dx, dy, escala, rot, alpha)."""
    f = font(fam, w, size)
    ws = [f.measureText(ch) for ch in s]
    tw = sum(ws) + track * (len(s) - 1)
    cx = x - tw * {"l": 0, "c": .5, "r": 1}[align]
    n = len(s)
    for i, ch in enumerate(s):
        dx, dy, sc, rot, al = fn(i, n)
        if al > 0.003 and ch != " ":
            c.save()
            px = cx + ws[i] / 2
            c.translate(px + dx, y + dy)
            if rot:
                c.rotate(rot)
            if sc != 1:
                c.scale(sc, sc)
            c.drawString(ch, -ws[i] / 2, 0, f, paint(color, al, shadow=shadow))
            c.restore()
        cx += ws[i] + track
    return tw


def rrect(x, y, w, h, r):
    return skia.RRect.MakeRectXY(skia.Rect.MakeXYWH(x, y, w, h), r, r)


# ------------------------------------------------------------------ vídeo
class Clip:
    def __init__(self, name, w, h):
        path = os.path.join(WORK, "raw", f"{name}.rgb")
        n = os.path.getsize(path) // (w * h * 3)
        self.mm = np.memmap(path, np.uint8, "r", shape=(n, h, w, 3))
        self.w, self.h, self.n = w, h, n
        self.buf = np.empty((h, w, 4), np.uint8)
        self.buf[:, :, 3] = 255
        self._idx, self._img = None, None

    def img(self, i):
        i = int(min(max(i, 0), self.n - 1))
        if i != self._idx:
            self.buf[:, :, :3] = self.mm[i]
            self._img = skia.Image.fromarray(self.buf, colorType=skia.kRGBA_8888_ColorType, copy=True)
            self._idx = i
        return self._img


CLIPS = {}


def clip(name):
    if name not in CLIPS:
        dims = {"c1": (1440, 2560), "c2": (1440, 2560), "c3": (1080, 1920), "c4": (1440, 2560)}[name]
        CLIPS[name] = Clip(name, *dims)
    return CLIPS[name]


SAMP = skia.SamplingOptions(skia.CubicResampler.Mitchell())


def cam(cl, z, cx, cy, rect=(0, 0, W, H)):
    rx, ry, rw, rh = rect
    s = max(rw / cl.w, rh / cl.h) * z
    hw, hh = rw / (2 * s), rh / (2 * s)
    cxp = min(max(cx * cl.w, hw), cl.w - hw)
    cyp = min(max(cy * cl.h, hh), cl.h - hh)
    m = skia.Matrix()
    m.setTranslate(rx + rw / 2, ry + rh / 2)
    m.preScale(s, s)
    m.preTranslate(-cxp, -cyp)
    return m, s


def draw_video(c, cl, idx, m, s, blur=0.0):
    c.save()
    c.concat(m)
    p = skia.Paint()
    if blur > 0.1:
        p.setImageFilter(skia.ImageFilters.Blur(blur / s, blur / s, skia.TileMode.kClamp))
    c.drawImage(cl.img(idx), 0, 0, SAMP, p)
    c.restore()


# ------------------------------------------------------------------ rosto (rastreamento)
FACES = {}


def load_faces():
    path = os.path.join(WORK, "faces.json")
    raw = json.load(open(path))
    for k, boxes in raw.items():
        n = len(boxes)
        cx = np.full(n, np.nan); cy = np.full(n, np.nan); fw = np.full(n, np.nan)
        for i, b in enumerate(boxes):
            if b:
                cx[i] = b[0] + b[2] / 2; cy[i] = b[1] + b[3] / 2; fw[i] = b[2]
        for arr in (cx, cy, fw):
            idx = np.arange(n); ok = ~np.isnan(arr)
            arr[:] = np.interp(idx, idx[ok], arr[ok])
        # rejeita detecções espúrias (mãos, roupa) comparando com a mediana móvel
        for arr in (cx, cy):
            med = np.array([np.median(arr[max(0, i - 12):i + 13]) for i in range(n)])
            bad = np.abs(arr - med) > 0.06
            arr[bad] = med[bad]
        k9 = np.ones(9) / 9
        FACES[k] = tuple(np.convolve(np.pad(a, 4, mode="edge"), k9, "valid") for a in (cx, cy, fw))


def face(name, idx):
    cx, cy, fw = FACES[name]
    i = int(min(max(idx, 0), len(cx) - 1))
    return float(cx[i]), float(cy[i]), float(fw[i])


# ------------------------------------------------------------------ linha do tempo
SEGS = [  # nome, clipe, quadro inicial na fonte, nº de quadros
    ("c1A", "c1", 13, 71), ("c1B", "c1", 94, 100),
    ("c2A", "c2", 11, 156), ("c2B", "c2", 182, 84),
    ("c3A", "c3", 13, 75), ("c3B", "c3", 102, 58), ("c3C", "c3", 168, 63), ("c3D", "c3", 240, 43), ("c3E", "c3", 293, 86),
    ("c4A", "c4", 21, 139), ("c4B", "c4", 177, 140),
    ("END", "c4", 316, 60),
]
STARTS = {}
_acc = 0
for _s in SEGS:
    STARTS[_s[0]] = _acc
    _acc += _s[3]
TOTAL = _acc


def seg_at(fi):
    for s in SEGS:
        st = STARTS[s[0]]
        if st <= fi < st + s[3]:
            return s, fi - st
    s = SEGS[-1]
    return s, s[3] - 1


def T(name):  # início do segmento em segundos
    return STARTS[name] / FPS


# ------------------------------------------------------------------ elementos gráficos
def confetti(c, t, t0, seed, cx, cy, n=26, spread=520, dur=1.5, colors=(YELLOW, CREAM, GREEN, ORANGE_L), scale=1.0, grav=220):
    lt = t - t0
    if lt < 0 or lt > dur:
        return
    rng = random.Random(seed)
    for i in range(n):
        ang = rng.uniform(0, 2 * math.pi); spd = rng.uniform(.4, 1.0) * spread
        kind = rng.choice(["dot", "pill", "ring", "dot"]); cc = rng.choice(colors)
        size = rng.uniform(9, 20) * scale; rot0 = rng.uniform(0, 360); vr = rng.uniform(-260, 260)
        delay = rng.uniform(0, .1)
        u = clamp((lt - delay) / (dur - delay))
        if u <= 0:
            continue
        d = eoexpo(u)
        x = cx + math.cos(ang) * spd * d
        y = cy + math.sin(ang) * spd * d + grav * u * u
        a = (1 - clamp((u - .5) / .5)) * clamp(u * 8)
        c.save(); c.translate(x, y); c.rotate(rot0 + vr * lt)
        if kind == "dot":
            c.drawCircle(0, 0, size * .5, paint(cc, a))
        elif kind == "pill":
            c.drawRRect(rrect(-size * .9, -size * .28, size * 1.8, size * .56, size * .28), paint(cc, a))
        else:
            c.drawCircle(0, 0, size * .55, paint(cc, a, stroke=size * .22))
        c.restore()


def drift_confetti(c, t, seed, n=22, alpha=.55, area=(0, 0, W, H)):
    rng = random.Random(seed)
    ax, ay, aw, ah = area
    for i in range(n):
        x0 = ax + rng.uniform(0, aw); y0 = ay + rng.uniform(0, ah)
        sp = rng.uniform(18, 46); ph = rng.uniform(0, 6.28)
        cc = rng.choice([YELLOW, ORANGE_L, SAGE, CREAM]); size = rng.uniform(8, 18)
        kind = rng.choice(["dot", "pill", "ring"])
        x = x0 + math.sin(t * .9 + ph) * 14
        y = ay + ((y0 - ay - sp * t) % ah)
        c.save(); c.translate(x, y); c.rotate(ph * 57 + t * 40 * (1 if i % 2 else -1))
        if kind == "dot":
            c.drawCircle(0, 0, size * .5, paint(cc, alpha))
        elif kind == "pill":
            c.drawRRect(rrect(-size * .9, -size * .28, size * 1.8, size * .56, size * .28), paint(cc, alpha))
        else:
            c.drawCircle(0, 0, size * .55, paint(cc, alpha, stroke=size * .22))
        c.restore()


def bottom_scrim(c, y0=980, a=.5):
    sh = skia.GradientShader.MakeLinear([skia.Point(0, y0), skia.Point(0, H)], [col(GREEN_DD, 0), col(GREEN_DD, a)])
    c.drawRect(skia.Rect(0, y0, W, H), paint(WHITE, shader=sh))


def top_scrim(c, a=.35, y1=720):
    sh = skia.GradientShader.MakeLinear([skia.Point(0, 0), skia.Point(0, y1)], [col(GREEN_DD, a), col(GREEN_DD, 0)])
    c.drawRect(skia.Rect(0, 0, W, y1), paint(WHITE, shader=sh))


def vignette(c, a=.20):
    sh = skia.GradientShader.MakeRadial(skia.Point(W / 2, H * .46), H * .72, [col("#000000", 0), col("#000000", 0), col("#000000", a)], [0, .62, 1])
    c.drawRect(skia.Rect(0, 0, W, H), paint(WHITE, shader=sh))


def hole_layer(c, color, cx, cy, r, a=1.0):
    """Preenche a tela com uma cor, deixando um furo circular de raio r."""
    pa = skia.Path(); pa.addRect(skia.Rect(-10, -10, W + 10, H + 10))
    if r > 0.5:
        pb = skia.Path(); pb.addCircle(cx, cy, r)
        pa = skia.Op(pa, pb, skia.PathOp.kDifference_PathOp)
    c.drawPath(pa, paint(color, a))


def pill(c, x, y, w, h, color, a=1.0, shadow=None):
    c.drawRRect(rrect(x, y, w, h, h / 2), paint(color, a, shadow=shadow))


def big_five(c, cx, base_y, size, fill=CREAM, ext=ORANGE_D, depth=1.0, a=1.0, layers=7):
    """Número 5 com volume (camadas deslocadas) — base_y é a linha de base."""
    f = font("Fredoka", 700, size)
    w5 = f.measureText("5")
    x0 = cx - w5 / 2
    step = size * 0.0095 * depth
    for k in range(layers, 0, -1):
        c.drawString("5", x0 + k * step, base_y + k * step, f, paint(ext, a))
    c.drawString("5", x0, base_y, f, paint(fill, a))
    return w5


def corner_brackets(c, x0, y0, x1, y1, L=64, sw=9, color=ORANGE, a=1.0):
    p = paint(color, a, stroke=sw)
    for (px, py, dx, dy) in ((x0, y0, 1, 1), (x1, y0, -1, 1), (x0, y1, 1, -1), (x1, y1, -1, -1)):
        path = skia.Path(); path.moveTo(px, py + dy * L); path.lineTo(px, py + dy * 14)
        path.quadTo(px, py, px + dx * 14, py); path.lineTo(px + dx * L, py)
        c.drawPath(path, p)


def scallop_path(y_top, y_bot, r=95, top=True, bottom=True):
    """Faixa de tela inteira com bordas recortadas em 'copa de árvore'."""
    n = int(math.ceil((W + 40) / (2 * r)))
    p = skia.Path()
    p.moveTo(-20, y_top)
    if top:
        x = -20
        for i in range(n):
            p.arcTo(skia.Rect(x, y_top - r, x + 2 * r, y_top + r), 180, 180, False)
            x += 2 * r
    p.lineTo(W + 20 + 2 * r, y_top)
    p.lineTo(W + 20 + 2 * r, y_bot)
    if bottom:
        x = -20 + n * 2 * r
        for i in range(n):
            p.arcTo(skia.Rect(x - 2 * r, y_bot - r, x, y_bot + r), 0, 180, False)
            x -= 2 * r
    p.lineTo(-20, y_bot)
    p.close()
    return p


# ------------------------------------------------------------------ cupom
def coupon_path(x, y, w, h, stub, r=34, nr=26):
    p = skia.Path(); p.addRRect(rrect(x, y, w, h, r))
    for cy in (y, y + h):
        q = skia.Path(); q.addCircle(x + stub, cy, nr)
        p = skia.Op(p, q, skia.PathOp.kDifference_PathOp)
    for cy in (y + h * .5,):
        for cx in (x, x + w):
            q = skia.Path(); q.addCircle(cx, cy, nr * .75)
            p = skia.Op(p, q, skia.PathOp.kDifference_PathOp)
    return p


def draw_coupon(c, t, cx, cy, sc, rot, p_one, p_para, shine_t=None):
    w, h, stub = 860, 300, 236
    x, y = -w / 2, -h / 2
    c.save(); c.translate(cx, cy); c.rotate(rot); c.scale(sc, sc)
    path = coupon_path(x, y, w, h, stub)
    # sombra
    c.drawPath(path, paint(GREEN_DD, .30, shadow=(0, 18, 26, GREEN_DD, .45)))
    sh = skia.GradientShader.MakeLinear([skia.Point(0, y), skia.Point(0, y + h)], [col("#F7843F"), col("#EC5F22")])
    c.drawPath(path, paint(WHITE, shader=sh))
    c.save(); c.clipPath(path, skia.ClipOp.kIntersect, True)
    c.drawRect(skia.Rect(x, y, x + stub, y + h), paint(YELLOW))
    # padrão sutil de círculos no corpo
    for i in range(7):
        c.drawCircle(x + stub + 120 + i * 120, y + h + 40, 90, paint(WHITE, .05))
    if shine_t is not None and 0 <= shine_t <= 1:
        bx = mix(x - 200, x + w + 200, eioc(shine_t))
        g = skia.GradientShader.MakeLinear([skia.Point(bx - 90, 0), skia.Point(bx + 90, 0)],
                                          [col(WHITE, 0), col(WHITE, .38), col(WHITE, 0)])
        c.save(); c.skew(-.35, 0); c.drawRect(skia.Rect(bx - 200, y - 50, bx + 200, y + h + 50), paint(WHITE, shader=g)); c.restore()
    c.restore()
    # picote
    pp = paint(CREAM, .9, stroke=5); pp.setPathEffect(skia.DashPathEffect.Make([4, 16], 0))
    c.drawLine(x + stub, y + 34, x + stub, y + h - 34, pp)
    # canhoto: 5 anos
    big_five(c, x + stub / 2, y + 190, 190, fill=GREEN_D, ext=ORANGE, layers=4, depth=.8)
    text(c, "ANOS", "Nunito", 900, 34, x + stub / 2, y + 250, GREEN_D, align="c", track=7)
    # corpo
    if p_one > 0:
        s1 = mix(1.45, 1.0, eoc(p_one)); a1 = clamp(p_one * 2.2)
        c.save(); c.translate(x + stub + 56, y + 158); c.scale(s1, s1)
        text(c, "1 CUPOM", "Fredoka", 700, 128, 0, 0, CREAM, a=a1)
        c.restore()
    if p_para > 0:
        c.save(); c.clipRect(skia.Rect(x + stub + 40, y + 170, x + stub + 40 + (w - stub) * eoc(p_para), y + h))
        text(c, "PARA CONCORRER", "Nunito", 900, 46, x + stub + 60, y + 236, YELLOW_L, track=3)
        c.restore()
    c.restore()


# ------------------------------------------------------------------ legendas
def caption(c, t, chunks, x, y, size=58, align="l", maxw=None):
    for (t0, t1, words, emph) in chunks:
        if not (t0 - .01 <= t <= t1 + .18):
            continue
        a_out = 1 - lin(t, t1, t1 + .16)
        f = font("Nunito", 800, size)
        sp = f.measureText(" ")
        ws = [f.measureText(wd) for wd in words]
        lines, cur, cw = [], [], 0
        for i, wd in enumerate(words):
            add = ws[i] + (sp if cur else 0)
            if maxw and cur and cw + add > maxw:
                lines.append(cur); cur, cw = [], 0; add = ws[i]
            cur.append(i); cw += add
        if cur:
            lines.append(cur)
        lh = size * 1.18
        for li, line in enumerate(lines):
            lw = sum(ws[i] for i in line) + sp * (len(line) - 1)
            xx = x - lw * {"l": 0, "c": .5}[align]
            yy = y + li * lh - (len(lines) - 1) * lh
            for i in line:
                u = lin(t, t0 + i * .045, t0 + i * .045 + .22)
                a = eoc(u) * a_out
                color = YELLOW if i in emph else WHITE
                ff = font("Nunito", 900, size) if i in emph else f
                c.drawString(words[i], xx, yy + (1 - eoc(u)) * 22, ff, paint(color, a, shadow=SH_TEXT))
                xx += ws[i] + sp


def cap(t0, t1, s, emph=()):
    words = s.split(" ")
    return (t0, t1, words, {i for i, wd in enumerate(words) if wd.strip(",.!").lower() in emph})


CAP_C2 = [cap(5.92, 6.92, "E para comemorar,"), cap(6.92, 8.70, "vamos repetir uma surpresa", {"surpresa"}),
          cap(8.72, 9.50, "que fez muito sucesso", {"sucesso"}),
          cap(9.52, 10.86, "no Dia das Crianças.", {"dia", "das", "crianças"})]
CAP_C4 = [cap(24.80, 26.73, "Estamos muito felizes", {"felizes"}), cap(26.73, 27.62, "em comemorar estes"),
          cap(28.43, 29.15, "com vocês."), cap(29.20, 30.45, "Preparem-se,", {"preparem-se"}),
          cap(30.49, 31.95, "porque esta semana")]


# ================================================================== quadro
def render_frame(fi, surf_arr):
    surf = skia.Surface(surf_arr, colorType=skia.kRGBA_8888_ColorType, alphaType=skia.kPremul_AlphaType)
    c = surf.getCanvas()
    c.clear(col(CREAM))
    t = fi / FPS
    (name, cname, src0, nfr), lf = seg_at(fi)
    lt = lf / FPS
    cl = clip(cname)
    idx = src0 + lf if name != "END" else src0
    fx, fy, fw = face(cname, idx)

    split = 0.0
    # ---------------------------------------------------------- câmera / base
    if name == "c1A":
        z = 1.0 + .20 * (1 - eoexpo(lin(lt, 0, 1.1))) + .03 * lin(lt, 0, 2.37)
        m, s = cam(cl, z, .5, .5)
        draw_video(c, cl, idx, m, s)
    elif name == "c1B":
        z = 1.13 + .05 * eioc(lin(lt, 0, 3.3))
        m, s = cam(cl, z, mix(.5, fx, .45), .45)
        draw_video(c, cl, idx, m, s)
    elif name == "c2A":
        z = 1.0 + .05 * eioc(lin(lt, 0, 5.2))
        m, s = cam(cl, z, .5, .5)
        draw_video(c, cl, idx, m, s)
    elif name == "c2B":
        p = eioc(lin(lt, 0, 2.2))
        m, s = cam(cl, mix(1.03, 1.08, p), mix(.5, .54, p), .5)
        draw_video(c, cl, idx, m, s)
    elif name.startswith("c3"):
        pB = eioc(lin(t, 16.20, 16.72)); pE = eioc(lin(t, 22.62, 23.22))
        split = pB * (1 - pE)
        full_cam = {"c3A": (1.0 + .04 * lin(lt, 0, 2.5), .5, .5),
                    "c3E": (1.0 + .07 * eioc(lin(t, 22.9, 24.5)), mix(.5, .58, eioc(lin(t, 22.9, 24.5))), .5)}.get(name, (1.0, .5, .5))
        win_cam = {"c3A": (1.12, .45, .30), "c3B": (1.12 + .03 * lin(lt, 0, 1.9), .45, .30),
                   "c3C": (1.24 + .03 * lin(lt, 0, 2.1), .43, .28), "c3D": (1.10 + .03 * lin(lt, 0, 1.4), .47, .31),
                   "c3E": (1.18, .50, .32)}[name]
        if split > 0.001:
            draw_panel_bg(c, t, split)
            tgt = (40, 196, 1000, 800)
            rect = tuple(mix(a, b, split) for a, b in zip((0, 0, W, H), tgt))
            rad = 46 * split
            zz, cx_, cy_ = (mix(a, b, split) for a, b in zip(full_cam, win_cam))
            m, s = cam(cl, zz, cx_, cy_, rect)
            rr = rrect(*rect, rad)
            c.drawRRect(rr, paint(GREEN_DD, .25 * split, shadow=(0, 16, 30, GREEN_DD, .35 * split)))
            c.save(); c.clipRRect(rr, skia.ClipOp.kIntersect, True)
            draw_video(c, cl, idx, m, s)
            c.restore()
            c.drawRRect(rr, paint(WHITE, .95 * split, stroke=7))
        else:
            m, s = cam(cl, *full_cam)
            draw_video(c, cl, idx, m, s)
    elif name == "c4A":
        z = 1.0 + .10 * eioc(lin(lt, 0, 4.6))
        m, s = cam(cl, z, .5, .46)
        draw_video(c, cl, idx, m, s)
    elif name in ("c4B", "END"):
        tt = t - T("c4B")
        z = 1.27 + .09 * lin(tt, 0, 6.66)
        blur = 26 * eioc(lin(t, 33.25, 33.95))
        m, s = cam(cl, z, mix(.5, fx, .5), .47)
        draw_video(c, cl, idx, m, s, blur=blur)
    else:
        m, s = cam(cl, 1, .5, .5)
        draw_video(c, cl, idx, m, s)

    # máscaras de leitura nos planos cheios
    if split < .999 and t < 33.9:
        a = (1 - split)
        vignette(c, .18 * a)
        bottom_scrim(c, 960, .52 * a)

    # ---------------------------------------------------------- camadas por cena
    if t < T("c2A") + .05:
        scene1(c, t, cl, idx, m)
    if T("c2A") - .05 <= t < T("c3A") + .05:
        scene2(c, t, cl, idx, m)
    if T("c3A") - .05 <= t < T("c4A") + .05:
        scene3(c, t, cl, idx, m, split)
    if t >= T("c4A") - .05:
        scene4(c, t, cl, idx, m)

    transitions(c, t, cl, idx, m)
    del surf


# ------------------------------------------------------------------ cena 1
def scene1(c, t, cl, idx, m):
    # abertura: "ESSA SEMANA É / MUITO / ESPECIAL"
    if t < 2.6:
        out = eic(lin(t, 2.18, 2.48))
        x0 = 72
        a1 = eoc(lin(t, .22, .55)) * (1 - out)
        c.save(); c.clipRect(skia.Rect(0, 1080, W, 1215))
        text(c, "ESSA SEMANA É", "Nunito", 900, 56, x0 - out * 160, 1190 + (1 - eoc(lin(t, .22, .6))) * 80, WHITE, a1, track=3, shadow=SH_TEXT)
        c.restore()
        u2 = lin(t, .78, 1.12)
        c.save(); c.clipRect(skia.Rect(0, 1215, W, 1330))
        text(c, "MUITO", "Fredoka", 600, 112, x0 - out * 220, 1318 + (1 - eoc(u2)) * 120, WHITE, (u2 > 0) * (1 - out), shadow=SH_TEXT)
        c.restore()

        def fn(i, n):
            u = lin(t, 1.26 + i * .04, 1.26 + i * .04 + .42)
            e = eoback(u, 2.2) if u > 0 else 0
            return (-out * 300, (1 - e) * 90 + out * 40, mix(.6, 1, clamp(e)), (1 - clamp(e)) * -14, clamp(u * 3) * (1 - out))
        text_chars(c, "ESPECIAL", "Fredoka", 700, 176, x0 - 4, 1500, YELLOW, fn, shadow=SH_TEXT)
        # traço sublinhado que acompanha
        ul = eoc(lin(t, 1.55, 1.95))
        if ul > 0 and out < 1:
            c.drawLine(x0, 1545, x0 + 520 * ul - out * 600, 1545, paint(ORANGE, 1 - out, stroke=12))

    # composição 5 ANOS / LÔRI KIDS
    if 2.40 <= t < 5.75:
        fxs = m.mapXY(face("c1", idx)[0] * cl.w, 0).fX
        lockX = 540 + clamp((fxs - 540) * .30, -45, 45)
        R5 = 232
        wAN = font("Fredoka", 700, 132).measureText("ANOS")
        totw = 2 * R5 + 34 + wAN
        diskC = (lockX - totw / 2 + R5, 1420)
        xRight = diskC[0] + R5 + 34
        zoom = 1 + 11 * eic(lin(t, 5.40, 5.72))   # mergulho no círculo (transição)
        c.save(); c.translate(*diskC); c.scale(zoom, zoom); c.translate(-diskC[0], -diskC[1])
        fade_all = 1 - lin(zoom, 1.6, 2.6)
        pm = eioc(lin(t, 4.38, 4.85))  # 'LÔRI KIDS' migra para o bloco final
        # A NOSSA
        a = eoc(lin(t, 2.42, 2.72)) * (1 - lin(t, 4.25, 4.45))
        text(c, "A NOSSA", "Nunito", 900, 50, lockX, 1262 + (1 - eoc(lin(t, 2.42, 2.8))) * 30, YELLOW, a, align="c", track=10, shadow=(0, 4, 9, GREEN_DD, .8))
        # LÔRI KIDS — entra com espaçamento largo que se fecha + desfoque
        u = lin(t, 2.98, 3.55)
        if u > 0:
            size = mix(138, 56, pm)
            trk = mix(mix(46, 4, eoq(u)), 7, pm)
            ff = font("Fredoka" if pm < .5 else "Nunito", 700 if pm < .5 else 900, size)
            tw = measure(ff, "LÔRI KIDS", trk)
            right_x = xRight + 4
            x = mix(lockX - tw / 2, right_x, pm)
            y = mix(1398, 1374, pm)
            colr = WHITE if pm < .5 else YELLOW
            al = clamp(u * 2.5) * fade_all
            c.save()
            fam, wg = ("Fredoka", 700) if pm < .5 else ("Nunito", 900)
            text(c, "LÔRI KIDS", fam, wg, size, x, y, colr, al, track=trk, shadow=(0, 4, 9, GREEN_DD, .8) if (1 - u) * 14 < .5 else None,
                 blur=(1 - eoc(u)) * 14)
            c.restore()
        # COMPLETA
        u = lin(t, 3.84, 4.15)
        if u > 0 and t < 4.5:
            a = 1 - lin(t, 4.28, 4.45)
            c.save(); c.clipRect(skia.Rect(0, 1410, lockX - 240 + 480 * eoc(u), 1530))
            text(c, "COMPLETA", "Nunito", 900, 50, lockX, 1488, YELLOW, a, align="c", track=10, shadow=SH_TEXT)
            c.restore()
        # disco + 5
        ud = lin(t, 4.42, 4.86)
        if ud > 0:
            r = R5 * eoback(ud, 1.6)
            c.drawCircle(*diskC, r, paint(ORANGE, 1, shadow=(0, 14, 26, GREEN_DD, .4)))
            # anel que se desenha
            ua = eoc(lin(t, 4.6, 5.25))
            if ua > 0:
                rr = skia.Rect(diskC[0] - R5 - 32, diskC[1] - R5 - 32, diskC[0] + R5 + 32, diskC[1] + R5 + 32)
                c.drawArc(rr, -90 + 120 * ua, 360 * ua, False, paint(YELLOW, fade_all, stroke=9))
            u5 = lin(t, 4.50, 4.98)
            if u5 > 0:
                e = eoback(u5, 2.0)
                c.save(); c.translate(diskC[0], diskC[1] + 168); c.rotate((1 - clamp(e)) * -18); c.scale(mix(.35, 1, e), mix(.35, 1, e))
                big_five(c, 0, 0, 480, fill=CREAM, ext=ORANGE_D, depth=eoc(lin(t, 4.62, 4.95)), a=clamp(u5 * 4))
                c.restore()
            confetti(c, t, 4.56, 7, diskC[0], diskC[1], n=30, spread=430, dur=1.3)
        # ANOS — revelado por máscara
        ua = lin(t, 4.98, 5.32)
        if ua > 0:
            xA = xRight
            c.save(); c.clipRect(skia.Rect(xA - 10, 1380, xA - 10 + 420 * eoc(ua), 1560))
            text(c, "ANOS", "Fredoka", 700, 132, xA - (1 - eoc(ua)) * 40, 1512, WHITE, fade_all, shadow=SH_TEXT)
            c.restore()
        c.restore()


# ------------------------------------------------------------------ cena 2
PRODUCT_C2 = [  # tempo na fonte (s), caixa normalizada x0,y0,x1,y1
    (6.07, (.40, .30, .91, .95)), (7.2, (.35, .25, .90, .95)), (8.0, (.32, .17, .90, .94)), (8.85, (.36, .13, .99, .93))]


def product_box(st):
    ks = PRODUCT_C2
    if st <= ks[0][0]:
        return ks[0][1]
    for (a, ba), (b, bb) in zip(ks, ks[1:]):
        if st <= b:
            p = (st - a) / (b - a)
            return tuple(mix(x, y, p) for x, y in zip(ba, bb))
    return ks[-1][1]


def scene2(c, t, cl, idx, m):
    caption(c, t, CAP_C2, 66, 1300, size=58, maxw=560)
    # parte B: sorteio + produto
    if t >= T("c2B"):
        out = lin(t, 13.42, 13.6)
        # cartão de fundo (verde, translúcido) para leitura sobre a camisa branca
        uc = eoc(lin(t, 11.28, 11.62))
        if uc > 0:
            cx0, cy0, cw, ch = 40, 742, 524, 400
            c.save(); c.translate(0, (1 - uc) * 40)
            c.drawRRect(rrect(cx0, cy0, cw * mix(.2, 1, eoexpo(lin(t, 11.28, 11.7))), ch, 40), paint(GREEN_D, .86 * uc * (1 - out), shadow=(0, 14, 28, GREEN_DD, .35 * uc)))
            c.restore()
        # SORTEIO ESPECIAL — selo amarelo que se abre
        up = lin(t, 11.38, 11.78)
        if up > 0:
            f = font("Nunito", 900, 42); tw = measure(f, "SORTEIO ESPECIAL", 3)
            pw = (tw + 64) * eoexpo(up)
            pill(c, 72, 782, pw, 82, YELLOW, 1 - out)
            c.save(); c.clipRect(skia.Rect(72, 782, 72 + pw, 864))
            text(c, "SORTEIO ESPECIAL", "Nunito", 900, 42, 104 - (1 - eoc(lin(t, 11.5, 11.85))) * 60, 838, GREEN_D, 1 - out, track=3)
            c.restore()
        # CONCORRA A UM
        u = lin(t, 11.92, 12.25)
        text(c, "CONCORRA A UM", "Nunito", 900, 46, 76, 946 + (1 - eoc(u)) * 26, CREAM, eoc(u) * (1 - out), track=3)

        # SKATENET — letras caem com mola
        def fn(i, n):
            lt0 = t - (12.36 + i * .05)
            if lt0 <= 0:
                return (0, 0, 1, 0, 0)
            e = spring(lt0, 2.0, 6.0)
            return (0, (1 - e) * -120, 1, (1 - e) * (12 if i % 2 else -12), clamp(lt0 * 7) * (1 - out))
        text_chars(c, "SKATENET", "Fredoka", 700, 104, 70, 1068, WHITE, fn)
        us = eoc(lin(t, 12.75, 13.1))
        if us > 0:
            path = skia.Path(); path.moveTo(78, 1100); path.quadTo(290, 1084, 78 + 440 * us, 1096 - 10 * us)
            c.drawPath(path, paint(ORANGE, 1 - out, stroke=11))
        # cantoneiras no produto (acompanham o produto)
        ub = lin(t, 12.42, 12.82)
        if ub > 0:
            st = (idx) / FPS
            bx0, by0, bx1, by1 = product_box(st)
            p0 = m.mapXY(bx0 * cl.w, by0 * cl.h); p1 = m.mapXY(bx1 * cl.w, by1 * cl.h)
            x0, y0, x1, y1 = p0.fX - 18, p0.fY - 18, min(p1.fX + 18, W - 30), min(p1.fY + 10, 1860)
            e = eoback(ub, 1.8); cxm, cym = (x0 + x1) / 2, (y0 + y1) / 2; k = mix(1.25, 1.0, e)
            corner_brackets(c, cxm + (x0 - cxm) * k, cym + (y0 - cym) * k, cxm + (x1 - cxm) * k, cym + (y1 - cym) * k,
                            L=70, sw=10, color=YELLOW, a=clamp(ub * 3) * (1 - out))
            # pequenos traços de brilho junto ao guidão
            us2 = lin(t, 12.6, 13.0)
            if us2 > 0:
                hx, hy = x1 - 10, y0 + 10
                for j, ang in enumerate((-60, -25, 10)):
                    ln = 46 * eoc(lin(t, 12.6 + j * .05, 12.95 + j * .05))
                    a = math.radians(ang); r0 = 34
                    c.drawLine(hx + math.cos(a) * r0, hy + math.sin(a) * r0, hx + math.cos(a) * (r0 + ln), hy + math.sin(a) * (r0 + ln),
                               paint(YELLOW, (1 - out), stroke=8))


# ------------------------------------------------------------------ cena 3
def draw_panel_bg(c, t, p):
    c.drawRect(skia.Rect(0, 0, W, H), paint(CREAM))
    # formas grandes e suaves em segundo plano
    c.drawCircle(980 + math.sin(t * .6) * 10, 1720, 330, paint(YELLOW, .35))
    c.drawCircle(80, 1830, 230, paint(SAGE, .45))
    c.drawCircle(1010, 140, 160, paint(ORANGE_L, .25))
    c.drawArc(skia.Rect(-140, 860, 200, 1200), 0, 360, False, paint(SAGE, .5, stroke=26))
    drift_confetti(c, t, 11, n=12, alpha=.45, area=(0, 1000, W, 900))


def scene3(c, t, cl, idx, m, split):
    # A: PARA PARTICIPAR / É MUITO / FÁCIL
    if t < 16.5:
        out = eic(lin(t, 16.10, 16.36))
        x0 = 70
        a = eoc(lin(t, 13.80, 14.15)) * (1 - out)
        trk = mix(26, 3, eoq(lin(t, 13.80, 14.4)))
        text(c, "PARA PARTICIPAR", "Nunito", 900, 50, x0, 1210 + out * 70, WHITE, a, track=trk, shadow=SH_TEXT)
        u = lin(t, 14.98, 15.3)
        c.save(); c.clipRect(skia.Rect(0, 1230, W, 1352 + out * 70))
        text(c, "É MUITO", "Fredoka", 700, 116, x0, 1340 + (1 - eoc(u)) * 130 + out * 70, WHITE, (u > 0) * (1 - out), shadow=SH_TEXT)
        c.restore()
        um = lin(t, 15.55, 15.85)
        if um > 0:
            f = font("Fredoka", 700, 150); tw = f.measureText("FÁCIL")
            c.save(); c.translate(0, out * 70)
            c.drawRRect(rrect(x0 - 16, 1372, (tw + 40) * eoexpo(um), 150, 30), paint(YELLOW, 1 - out, shadow=(0, 10, 22, GREEN_DD, .3)))
            ul = lin(t, 15.68, 16.0)

            def fn(i, n):
                uu = lin(t, 15.68 + i * .045, 15.68 + i * .045 + .3)
                e = eoback(uu, 2.4) if uu > 0 else 0
                return (0, (1 - clamp(e)) * 26, mix(.5, 1, e), 0, clamp(uu * 3) * (1 - out))
            if ul > 0:
                text_chars(c, "FÁCIL", "Fredoka", 700, 150, x0 + 4, 1496, GREEN_D, fn)
            c.restore()

    if split > .01:
        base_a = clamp(split * 1.6)
        # B: DE QUARTA A SÁBADO + dias
        if 16.3 <= t < 18.45:
            out = eic(lin(t, 18.10, 18.36))
            ox = -out * 260
            u1 = lin(t, 16.30, 16.62); u2 = lin(t, 17.10, 17.40)
            f = font("Fredoka", 600, 80)
            w1 = f.measureText("DE QUARTA "); w2 = f.measureText("A SÁBADO")
            x = 540 - (w1 + w2) / 2 + ox
            c.save(); c.clipRect(skia.Rect(0, 1030, W, 1122))
            text(c, "DE QUARTA ", "Fredoka", 600, 80, x, 1108 + (1 - eoc(u1)) * 90, GREEN_D, (u1 > 0) * (1 - out) * base_a)
            text(c, "A SÁBADO", "Fredoka", 600, 80, x + w1, 1108 + (1 - eoc(u2)) * 90, ORANGE, (u2 > 0) * (1 - out) * base_a)
            c.restore()
            days = [("QUA", "25", ORANGE, WHITE), ("QUI", "26", YELLOW, GREEN_D), ("SEX", "27", GREEN, WHITE), ("SÁB", "28", ORANGE, WHITE)]
            cw, gap, ch = 196, 22, 176
            x0 = 540 - (4 * cw + 3 * gap) / 2
            # linha de progresso
            ul = eioc(lin(t, 17.12, 17.78))
            if ul > 0:
                ya = 1158 + ch + 34
                xa = x0 + cw / 2; xb = x0 + 3 * (cw + gap) + cw / 2
                c.drawLine(xa + ox, ya, mix(xa, xb, ul) + ox, ya, paint(ORANGE, (1 - out) * base_a, stroke=8))
                for k in range(4):
                    if ul >= k / 3 - .001:
                        c.drawCircle(xa + k * (xb - xa) / 3 + ox, ya, 12, paint(ORANGE, (1 - out) * base_a))
                        c.drawCircle(xa + k * (xb - xa) / 3 + ox, ya, 5, paint(CREAM, (1 - out) * base_a))
            for k, (d, n, bg, fg) in enumerate(days):
                u = lin(t, 16.42 + k * .13, 16.42 + k * .13 + .42)
                if u <= 0:
                    continue
                e = eoback(u, 2.0)
                cx = x0 + k * (cw + gap) + cw / 2 + ox; cy = 1158 + ch / 2
                c.save(); c.translate(cx, cy + (1 - clamp(e)) * 50); c.scale(mix(.4, 1, e), mix(.4, 1, e))
                a = clamp(u * 3) * (1 - out) * base_a
                c.drawRRect(rrect(-cw / 2, -ch / 2, cw, ch, 32), paint(bg, a, shadow=(0, 10, 18, GREEN_DD, .22 * a)))
                text(c, d, "Nunito", 900, 38, 0, -ch / 2 + 54, fg, a * .92, align="c", track=4)
                text(c, n, "Fredoka", 700, 96, 0, ch / 2 - 22, fg, a, align="c")
                c.restore()
            u3 = lin(t, 17.55, 17.85)
            text(c, "25 A 28 DE NOVEMBRO", "Nunito", 800, 36, 540 + ox, 1430 + (1 - eoc(u3)) * 20, GREEN_D, eoc(u3) * (1 - out) * base_a, align="c", track=5)

        # C: A CADA R$ 50 EM COMPRAS
        if 18.10 <= t < 20.55:
            out = eic(lin(t, 20.18, 20.42))
            oy = -out * 120
            a_out = (1 - out) * base_a
            u = lin(t, 18.16, 18.5)
            trk = mix(30, 10, eoq(u))
            text(c, "A CADA", "Nunito", 900, 50, 540, 1094 + oy, GREEN_D, eoc(u) * a_out, align="c", track=trk)
            f50 = font("Fredoka", 700, 320); fR = font("Fredoka", 600, 116); fE = font("Nunito", 900, 58)
            w50 = f50.measureText("50"); wR = fR.measureText("R$"); wE = max(fE.measureText("EM"), fE.measureText("COMPRAS"))
            total = wR + 14 + w50 + 30 + wE
            xR = 540 - total / 2; x50 = xR + wR + 14; xE = x50 + w50 + 30
            base = 1392 + oy
            punch = 1 + .08 * math.sin(math.pi * lin(t, 19.30, 19.55))
            # R$
            ur = lin(t, 18.78, 19.05)
            text(c, "R$", "Fredoka", 600, 116, xR - (1 - eoc(ur)) * 50, base - 150, ORANGE, eoc(ur) * a_out)
            # 50 — números rolando
            ud = lin(t, 18.80, 19.30)
            if ud > 0:
                capH = 320 * .72
                c.save(); c.translate(x50 + w50 / 2, base - capH / 2); c.scale(punch, punch); c.translate(-(x50 + w50 / 2), -(base - capH / 2))
                c.save(); c.clipRect(skia.Rect(x50 - 20, base - capH - 40, x50 + w50 + 40, base + 40))
                dx = x50
                for j, dch in enumerate("50"):
                    dw = f50.measureText(dch)
                    uj = lin(t, 18.80 + j * .07, 19.25 + j * .07)
                    steps = 6
                    off = (1 - eoc(uj)) * steps
                    dval = int(dch)
                    step_h = capH + 80
                    for k in range(steps + 1):
                        digit = str((dval - k) % 10)
                        yy = base - (k - off) * step_h
                        if yy < base - capH - 60 - step_h or yy > base + step_h:
                            continue
                        for L in range(5, 0, -1):
                            c.drawString(digit, dx + L * 3.2, yy + L * 3.2, f50, paint(YELLOW_D, a_out))
                        c.drawString(digit, dx, yy, f50, paint(ORANGE, a_out))
                    dx += dw
                c.restore(); c.restore()
                # traços de destaque ao assentar
                ub = lin(t, 19.28, 19.75)
                if 0 < ub < 1:
                    cx, cy = x50 + w50 / 2, base - capH / 2
                    for k in range(10):
                        ang = math.radians(-90 + k * 36 + 18)
                        r0 = mix(170, 215, eoc(ub)); r1 = r0 + 34 * (1 - ub)
                        c.drawLine(cx + math.cos(ang) * r0, cy + math.sin(ang) * r0 * .9, cx + math.cos(ang) * r1, cy + math.sin(ang) * r1 * .9,
                                   paint(ORANGE_L, a_out * (1 - ub), stroke=7))
            # EM / COMPRAS
            ue = lin(t, 19.54, 19.85)
            c.save(); c.clipRect(skia.Rect(xE - 10, base - 200, xE + wE + 40, base + 30))
            text(c, "EM", "Nunito", 900, 58, xE + (1 - eoc(ue)) * 120, base - 78, GREEN_D, (ue > 0) * a_out)
            text(c, "COMPRAS", "Nunito", 900, 58, xE + (1 - eoc(lin(t, 19.6, 19.92))) * 160, base - 8, GREEN_D, (ue > 0) * a_out)
            c.restore()
            # válido para qualquer produto
            uv = lin(t, 19.82, 20.12)
            if uv > 0:
                fV = font("Nunito", 800, 32); tw = measure(fV, "VÁLIDO PARA QUALQUER PRODUTO", 3)
                pw = (tw + 56) * eoexpo(uv)
                pill(c, 540 - pw / 2, 1432 + oy, pw, 64, GREEN, a_out)
                c.save(); c.clipRect(skia.Rect(540 - pw / 2, 1432 + oy, 540 + pw / 2, 1500 + oy))
                text(c, "VÁLIDO PARA QUALQUER PRODUTO", "Nunito", 800, 32, 540, 1475 + oy, WHITE, a_out, align="c", track=3)
                c.restore()

    # D/E: cupom
    if 20.22 <= t < 24.45:
        ui = lin(t, 20.24, 20.80)
        e = eoback(ui, 1.5)
        pe = eioc(lin(t, 22.62, 23.22))        # cupom vira selo no canto ao voltar ao plano cheio
        cx = mix(540, 290, pe); cy = mix(1245 + (1 - clamp(e)) * 520, 1440, pe)
        sc = mix(mix(.76, .95, e), .50, pe); rot = mix(mix(-14, -3, e), -6, pe)
        p_one = lin(t, 20.92, 21.18); p_para = lin(t, 21.70, 22.10)
        a_end = 1 - lin(t, 24.25, 24.40)
        c.saveLayerAlpha(None, int(255 * clamp(ui * 4) * a_end))
        draw_coupon(c, t, cx, cy, sc, rot, p_one, p_para, shine_t=lin(t, 21.15, 21.75))
        c.restore()
        if 20.9 < t < 21.6:
            confetti(c, t, 20.95, 21, 540 + 120, 1150, n=18, spread=340, dur=.9)

    # E: "A ESTE PRESENTÃO"
    if 22.70 <= t < 24.45:
        out = lin(t, 24.22, 24.40)
        u = lin(t, 22.74, 23.05)
        text(c, "A ESTE", "Nunito", 900, 50, 70 + (1 - eoc(u)) * -40, 1124, WHITE, eoc(u) * (1 - out), track=4, shadow=SH_TEXT)

        def fn(i, n):
            uu = lin(t, 23.0 + i * .045, 23.0 + i * .045 + .35)
            ee = eoback(uu, 1.8) if uu > 0 else 0
            return (0, (1 - clamp(ee)) * 60, mix(.7, 1, ee), 0, clamp(uu * 3) * (1 - out))
        text_chars(c, "PRESENTÃO", "Fredoka", 700, 108, 66, 1240, YELLOW, fn, shadow=SH_TEXT)


# ------------------------------------------------------------------ cena 4
def scene4(c, t, cl, idx, m):
    if t < 32.0:
        caption(c, t, CAP_C4, 540, 1418, size=60, align="c")
    # destaque "5 ANOS" ao lado da apresentadora
    if 27.55 <= t < 29.2:
        fxx, fyy, _ = face("c4", idx)
        p = m.mapXY(fxx * cl.w, fyy * cl.h)
        cx, cy = p.fX - 300, p.fY + 40
        u = lin(t, 27.60, 28.0); out = eic(lin(t, 28.95, 29.15))
        e = eoback(u, 1.9)
        sc = mix(.2, 1, e) * (1 - out)
        if sc > 0.01:
            bob = math.sin((t - 27.6) * 4.2) * 6
            c.save(); c.translate(cx, cy + bob); c.scale(sc, sc); c.rotate((1 - clamp(e)) * -20 - 6)
            c.drawCircle(0, 0, 112, paint(ORANGE, 1, shadow=(0, 10, 20, GREEN_DD, .35)))
            c.drawCircle(0, 0, 126, paint(WHITE, .95, stroke=6))
            big_five(c, 0, 66, 190, fill=CREAM, ext=ORANGE_D, layers=4, depth=.7)
            text(c, "ANOS", "Nunito", 900, 34, 0, 182, GREEN_D, align="c", track=8)
            c.restore()
            confetti(c, t, 27.66, 41, cx, cy, n=16, spread=230, dur=1.0, scale=.8)
    # PREPAREM-SE — palavra-chave grande
    # reforço final + assinatura
    if t >= 31.95:
        ts = 33.30
        pm = eioc(lin(t, ts, ts + .62))           # texto desce para a assinatura
        tint = eioc(lin(t, 33.2, 33.9))
        if tint > 0:
            sh = skia.GradientShader.MakeLinear([skia.Point(0, 0), skia.Point(0, H)], [col(GREEN_D, .84 * tint), col("#2C6A44", .80 * tint)])
            c.drawRect(skia.Rect(0, 0, W, H), paint(WHITE, shader=sh))
            c.drawCircle(1010, 1760, 300 * eoc(tint), paint(YELLOW, .22 * tint))
            c.drawCircle(60, 220, 210 * eoc(tint), paint(ORANGE, .20 * tint))
            c.drawArc(skia.Rect(-150, 1450, 230, 1830), 0, 360, False, paint(SAGE, .30 * tint, stroke=26))
            drift_confetti(c, t, 5, n=24, alpha=.5 * tint)
        if pm < .5:
            top_scrim(c, .45 * (1 - tint) * eoc(lin(t, 31.95, 32.3)), 760)
        # 5 ANOS DE
        u1 = lin(t, 32.00, 32.40)
        y1 = mix(338, 942, pm)

        def fn(i, n):
            uu = lin(t, 32.0 + i * .03, 32.0 + i * .03 + .3)
            return (0, (1 - eoc(uu)) * 20, 1, 0, eoc(uu))
        text_chars(c, "5 ANOS DE", "Nunito", 900, mix(52, 56, pm), 540, y1, YELLOW, fn, align="c", track=10, shadow=SH_TEXT if pm < 1 else None)
        # LÔRI KIDS
        u2 = lin(t, 32.25, 32.75)
        if u2 > 0:
            s2 = mix(1.18, 1, eoc(u2)) * mix(1, 1.12, pm)
            y2 = mix(492, 1118, pm)
            c.save(); c.translate(540, y2); c.scale(s2, s2)
            text(c, "LÔRI KIDS", "Fredoka", 700, 150, 0, 0, WHITE, eoc(u2), align="c", track=2, shadow=SH_TEXT, blur=None)
            c.restore()
        # selo do 5 (assinatura)
        ub = lin(t, 33.62, 34.12)
        if ub > 0:
            e = eoback(ub, 1.7); bc = (540, 600)
            c.save(); c.translate(*bc); c.rotate((1 - clamp(e)) * -40); c.scale(mix(.3, 1, e), mix(.3, 1, e))
            c.drawCircle(0, 0, 190, paint(ORANGE, 1, shadow=(0, 16, 30, "#000000", .3)))
            ua = eoc(lin(t, 33.75, 34.45))
            c.drawArc(skia.Rect(-218, -218, 218, 218), -90, 360 * ua, False, paint(YELLOW, 1, stroke=9))
            big_five(c, 0, 130, 370, fill=CREAM, ext=ORANGE_D, layers=6, depth=eoc(lin(t, 33.8, 34.2)))
            c.restore()
            # pequenos arcos orbitando
            for k in range(3):
                ang = t * 40 + k * 120
                c.drawArc(skia.Rect(bc[0] - 252, bc[1] - 252, bc[0] + 252, bc[1] + 252), ang, 22, False,
                          paint([SAGE, YELLOW_L, ORANGE_L][k], .8 * clamp(ub * 2), stroke=6))
            confetti(c, t, 33.70, 77, bc[0], bc[1], n=34, spread=560, dur=1.6)
        # VENHA COMEMORAR COM A GENTE!
        uv = lin(t, 33.92, 34.40)
        if uv > 0:
            f = font("Nunito", 900, 41); tw = measure(f, "VENHA COMEMORAR COM A GENTE!", 1)
            pw = (tw + 84) * eoexpo(uv)
            pill(c, 540 - pw / 2, 1180, pw, 106, ORANGE, 1, shadow=(0, 12, 22, "#000000", .25))
            c.save(); c.clipRect(skia.Rect(540 - pw / 2, 1180, 540 + pw / 2, 1286))

            def fnv(i, n):
                uu = lin(t, 34.05 + i * .018, 34.05 + i * .018 + .25)
                return (0, (1 - eoc(uu)) * 30, 1, 0, eoc(uu))
            text_chars(c, "VENHA COMEMORAR COM A GENTE!", "Nunito", 900, 41, 540, 1247, WHITE, fnv, align="c", track=1)
            c.restore()
        ud = lin(t, 34.45, 34.85)
        if ud > 0:
            c.drawLine(540 - 60 * eoc(ud), 1352, 540 + 60 * eoc(ud), 1352, paint(YELLOW, .9, stroke=5))
            text(c, "DE QUARTA A SÁBADO", "Nunito", 800, 38, 540, 1424, CREAM, eoc(ud), align="c", track=5)
            text(c, "25 A 28 DE NOVEMBRO", "Fredoka", 600, 62, 540, 1498, YELLOW, eoc(lin(t, 34.6, 35.0)), align="c", track=2)


# ------------------------------------------------------------------ transições
def transitions(c, t, cl, idx, m):
    # abertura: anéis concêntricos se abrindo a partir do rosto
    if t < .75:
        fxx, fyy, _ = face("c1", idx)
        p = m.mapXY(fxx * cl.w, fyy * cl.h)
        R = 2300
        for k, colr in enumerate((GREEN, YELLOW, ORANGE)):
            delay = (2 - k) * .08
            u = lin(t, delay, delay + .52)
            hole_layer(c, colr, p.fX, p.fY, R * eic(u) ** .55 if u > 0 else 0)
    # 1 -> 2: o disco laranja cobre (cena 1) e abre um furo no rosto da cena 2
    if T("c2A") <= t < T("c2A") + .42:
        u = lin(t, T("c2A"), T("c2A") + .40)
        fxx, fyy, _ = face("c2", idx)
        p = m.mapXY(fxx * cl.w, fyy * cl.h)
        r = 2300 * eoc(u) ** 1.3
        c.save()
        hole_layer(c, ORANGE, p.fX, p.fY, r)
        if r > 1:
            c.drawCircle(p.fX, p.fY, r - 18, paint(YELLOW, 1, stroke=36))
        c.restore()
    # 2 -> 3: faixas diagonais nas cores da loja
    t0 = T("c3A")
    if t0 - .32 <= t < t0 + .32:
        for k, colr in enumerate((ORANGE, YELLOW, GREEN)):
            d = (2 - k) * .055
            u = lin(t, t0 - .30 - d, t0 + .30 - d)
            if u <= 0 or u >= 1:
                continue
            x = mix(W / 2 + 1700, W / 2 - 1700, eioc(u))
            c.save(); c.translate(x, H / 2); c.rotate(-14)
            c.drawRect(skia.Rect(-760, -1500, 760, 1500), paint(colr))
            c.restore()
    # 3 -> 4: copa de árvore (bordas recortadas) atravessa a tela
    t0 = T("c4A")
    if t0 - .34 <= t < t0 + .40:
        for k, (colr, off) in enumerate(((YELLOW, .06), (GREEN, 0.0))):
            u = lin(t, t0 - .32 - off, t0 + .38 - off)
            if u <= 0 or u >= 1:
                continue
            span = H + 2 * 260
            y = mix(-span - 140, H + 140, eioc(u))
            c.drawPath(scallop_path(y, y + span, r=96), paint(colr))
            if colr == GREEN:
                # lâmpadas na borda inferior, como no cenário
                for j in range(6):
                    bx = 90 + j * 180; by = y + span + 70
                    c.drawCircle(bx, by, 12, paint(YELLOW_L, .95))


# ================================================================== saídas
def write_frames(frames, outdir):
    os.makedirs(outdir, exist_ok=True)
    arr = np.zeros((H, W, 4), np.uint8)
    for fi in frames:
        render_frame(fi, arr)
        skia.Image.fromarray(arr, colorType=skia.kRGBA_8888_ColorType).save(os.path.join(outdir, f"f{fi:04d}.png"))


def write_chunk(i, n, out):
    a = TOTAL * i // n; b = TOTAL * (i + 1) // n
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
           "-vf", "scale=out_color_matrix=bt709:out_range=tv,format=yuv420p",
           "-c:v", "libx264", "-preset", "slow", "-crf", "15", "-profile:v", "high", "-g", "30", "-bf", "2",
           "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709", out]
    pr = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    arr = np.zeros((H, W, 4), np.uint8)
    for fi in range(a, b):
        render_frame(fi, arr)
        pr.stdin.write(arr.tobytes())
    pr.stdin.close(); pr.wait()


def write_audio(out):
    import soundfile as sf
    SR = 48000; SPF = SR // FPS
    gains = {"c1": -1.1, "c2": -0.5, "c3": +0.3, "c4": -0.9}   # nivelamento por clipe (alvo ~ -14 LUFS)
    data = {k: sf.read(os.path.join(WORK, "raw", f"{k}.wav"), dtype="float32")[0] for k in gains}
    parts = []
    fade = int(SR * .008)
    for (name, cname, src0, nfr) in SEGS:
        n = nfr * SPF
        if name == "END":
            parts.append(np.zeros(n, np.float32)); continue
        a = data[cname][src0 * SPF: src0 * SPF + n].copy()
        if len(a) < n:
            a = np.pad(a, (0, n - len(a)))
        if name == "c4B":   # finaliza suavemente o ambiente após a última fala
            tail = int(SR * .35); a[-tail:] *= np.linspace(1, 0, tail) ** 2
        a[:fade] *= np.linspace(0, 1, fade); a[-fade:] *= np.linspace(1, 0, fade)
        parts.append(a * 10 ** (gains[cname] / 20))
    sf.write(out, np.concatenate(parts), SR, subtype="FLOAT")


if __name__ == "__main__":
    load_faces()
    mode = sys.argv[1]
    if mode == "frames":
        write_frames([int(x) for x in sys.argv[2:]], os.path.join(WORK, "preview"))
    elif mode == "chunk":
        write_chunk(int(sys.argv[2]), int(sys.argv[3]), sys.argv[4])
    elif mode == "audio":
        write_audio(sys.argv[2])
    print("total frames", TOTAL)
