"""Original synthesized soundtrack for the Aqualori Black Friday edit.
120 BPM, bar = 2.0 s. Timeline: hook 0-4, speech 4-14, POP at 14.0 (slow-mo 14-22), end card 22-26.
"""
import sys
import numpy as np
from scipy.signal import butter, sosfilt, fftconvolve
from scipy.io import wavfile

SR = 48000
DUR = 26.0
N = int(SR * DUR)
BEAT = 0.5
BAR = 2.0
POP = 14.0
rng = np.random.default_rng(7)


def t_arr(d):
    return np.arange(int(d * SR)) / SR


def place(buf, sig, t0, gain=1.0):
    i = int(round(t0 * SR))
    if i >= buf.shape[-1]:
        return
    j = min(buf.shape[-1], i + sig.shape[-1])
    buf[..., i:j] += gain * sig[..., : j - i]


def lp(x, f, order=2):
    return sosfilt(butter(order, f, "low", fs=SR, output="sos"), x)


def hp(x, f, order=2):
    return sosfilt(butter(order, f, "high", fs=SR, output="sos"), x)


def bp(x, lo, hi, order=2):
    return sosfilt(butter(order, [lo, hi], "band", fs=SR, output="sos"), x)


def reverb(x, secs=2.5, damp=4000, seed=1):
    r = np.random.default_rng(seed)
    n = int(secs * SR)
    tt = np.arange(n) / SR
    out = []
    for ch in range(2):
        ir = r.standard_normal(n) * np.exp(-tt * 6.9 / secs)
        ir = lp(ir, damp)
        ir[: int(0.012 * SR)] *= np.linspace(0, 1, int(0.012 * SR))
        ir /= np.sqrt(np.sum(ir ** 2))
        src = x[ch] if x.ndim == 2 else x
        out.append(fftconvolve(src, ir)[: src.shape[-1]])
    return np.array(out)


def midi(m):
    return 440.0 * 2 ** ((m - 69) / 12)


# ---------- instruments ----------
def kick(punch=1.0, d=0.45):
    t = t_arr(d)
    f = 45 + 95 * np.exp(-t * 28)
    ph = 2 * np.pi * np.cumsum(f) / SR
    s = np.sin(ph) * np.exp(-t * 7.5)
    click = hp(rng.standard_normal(len(t)), 3000) * np.exp(-t * 300) * 0.25 * punch
    return np.tanh(1.6 * (s + click)) * 0.9


def hat(d=0.06, open_=False):
    t = t_arr(0.25 if open_ else d)
    n = hp(rng.standard_normal(len(t)), 7500, 4)
    return n * np.exp(-t * (14 if open_ else 70)) * 0.35


def clap(d=0.35):
    t = t_arr(d)
    n = bp(rng.standard_normal(len(t)), 900, 5000)
    env = np.zeros_like(t)
    for o in (0, 0.009, 0.019, 0.03):
        env += (t >= o) * np.exp(-np.clip(t - o, 0, None) * (90 if o < 0.03 else 18))
    return n * env * 0.45


def pad_chord(notes, d, cutoff=1800, attack=0.6, release=0.8):
    t = t_arr(d)
    L = np.zeros_like(t)
    R = np.zeros_like(t)
    for m in notes:
        f = midi(m)
        for k, det in enumerate((-0.11, 0.0, 0.13)):
            ff = f * 2 ** (det / 12)
            ph0 = rng.uniform(0, 1)
            saw = 2 * ((ff * t + ph0) % 1.0) - 1
            if k == 0:
                L += saw
            elif k == 2:
                R += saw
            else:
                L += 0.7 * saw
                R += 0.7 * saw
    env = np.minimum(1, t / attack) * np.minimum(1, np.clip(d - t, 0, None) / release)
    st = np.array([lp(L, cutoff, 2), lp(R, cutoff, 2)]) * env
    return st / (len(notes) * 3) * 0.9


def bell(m, d=1.6, amp=0.25):
    t = t_arr(d)
    f = midi(m)
    mod = np.sin(2 * np.pi * f * 3.5 * t) * 2.2 * np.exp(-t * 5)
    s = np.sin(2 * np.pi * f * t + mod) * np.exp(-t * 2.6)
    s += 0.25 * np.sin(2 * np.pi * f * 2 * t) * np.exp(-t * 4)
    a = int(0.004 * SR)
    s[:a] *= np.linspace(0, 1, a)
    return s * amp


def bass(m, d, amp=0.5):
    t = t_arr(d)
    f = midi(m)
    s = np.sin(2 * np.pi * f * t) + 0.3 * np.sin(2 * np.pi * 2 * f * t)
    s = np.tanh(1.4 * s)
    env = np.minimum(1, t / 0.01) * np.minimum(1, np.clip(d - t, 0, None) / 0.05)
    return lp(s * env, 900) * amp


def riser(d):
    t = t_arr(d)
    n = rng.standard_normal(len(t))
    out = np.zeros_like(t)
    seg = int(0.05 * SR)
    for i in range(0, len(t), seg):
        c = 400 + (7000 - 400) * (i / len(t)) ** 2
        blk = n[max(0, i - 2000): i + seg]
        out[i: i + seg] = bp(blk, c * 0.7, min(c * 1.4, 20000))[-len(out[i: i + seg]):]
    env = (t / d) ** 2.2
    return out * env * 0.5


def impact():
    t = t_arr(3.5)
    f = 30 + 40 * np.exp(-t * 6)
    boom = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 1.6)
    noise = lp(rng.standard_normal(len(t)), 6000) * np.exp(-t * 3.2) * 0.35
    return np.tanh(1.3 * boom) * 0.9 + noise


def whoosh(d=0.6, rev=False):
    t = t_arr(d)
    n = rng.standard_normal(len(t))
    env = np.sin(np.pi * t / d) ** 2
    s = bp(n, 1500, 8000) * env * 0.2
    return s[::-1] if rev else s


# ---------- arrangement ----------
L = np.zeros((2, N))   # music bus (stereo)
REVSEND = np.zeros((2, N))
DRUMS = np.zeros((2, N))

# chords per bar (bars 0..12): Am9 | Fmaj7 | C/G | Em7 ...
prog = [
    ([57, 60, 64, 67, 71], 45),   # Am9
    ([53, 57, 60, 64, 67], 41),   # Fmaj9
    ([55, 60, 64, 67, 71], 43),   # Cmaj7/G
    ([52, 55, 59, 62, 66], 40),   # Em9
]


def chord(bar):
    return prog[bar % 4]


def stereo(x, pan=0.0):
    return np.array([x * (1 - pan) ** 0.5, x * (1 + pan) ** 0.5]) / 1.0


# Pads: whole piece, filter opens in slow-mo section
for b in range(13):
    notes, root = chord(b)
    t0 = b * BAR
    if t0 < 4:
        cut, g = 900 + 400 * b, 0.55
    elif t0 < POP:
        cut, g = 1500, 0.45
    elif t0 < 22:
        cut, g = 3200, 0.75
    else:
        cut, g = 2600, 0.7
    d = BAR + 0.9 if b < 12 else 4.0
    p = pad_chord(notes, d, cutoff=cut, attack=0.5 if b else 1.5, release=0.9)
    place(L, p, t0, g)
    place(REVSEND, p, t0, g * 0.5)

# Bell arpeggio sparkles: hook, slow-mo, end card
arp_pat = [0, 2, 4, 3, 1, 3, 4, 2]
for b in range(13):
    t0 = b * BAR
    if 4 <= t0 < POP:
        continue
    notes, _ = chord(b)
    step = BEAT / 2 if t0 < 4 else BEAT
    amp = 0.13 if t0 < 4 else 0.16
    k = 0
    tt = t0
    while tt < t0 + BAR - 1e-6:
        m = notes[arp_pat[k % 8]] + 12
        s = bell(m, 1.4, amp)
        pan = 0.5 * np.sin(k * 1.7)
        place(L, stereo(s, pan), tt, 1.0)
        place(REVSEND, stereo(s, pan), tt, 1.2)
        k += 1
        tt += step
        if t0 >= 22 and tt > 24.5:
            break

# Hook (0-4): soft filtered kick on bar 1, riser into the cut, title whoosh
for i in range(4):
    place(DRUMS, stereo(lp(kick(0.3), 400)), 2.0 + i * BEAT, 0.35 + 0.1 * i)
place(L, stereo(whoosh(0.9)), 0.6, 0.7)
place(REVSEND, stereo(whoosh(0.9)), 0.6, 0.6)
r = riser(1.0)
place(L, stereo(r * 0.5), 3.0, 1.0)

# Groove under speech (4-14)
for b in range(2, 7):
    t0 = b * BAR
    notes, root = chord(b)
    for q in range(4):
        tb = t0 + q * BEAT
        place(DRUMS, stereo(kick(0.8)), tb, 0.8)
        place(DRUMS, stereo(hat(), 0.3), tb + BEAT / 2, 0.55)
        place(DRUMS, stereo(hat(0.03), -0.3), tb + BEAT * 0.75, 0.25)
        if q in (1, 3):
            place(DRUMS, stereo(clap()), tb, 0.45)
            place(REVSEND, stereo(clap()), tb, 0.25)
        # offbeat bass
        place(L, stereo(bass(root, 0.22)), tb + BEAT / 2, 0.9)

# Build-up on the last bar before the pop (12-14): snare roll + riser
roll_t = 12.0
k = 0
while roll_t < POP - 0.01:
    prog_ = (roll_t - 12.0) / 2.0
    place(DRUMS, stereo(clap(0.12)), roll_t, 0.15 + 0.45 * prog_)
    roll_t += BEAT / 2 if prog_ < 0.5 else (BEAT / 4 if prog_ < 0.85 else BEAT / 8)
place(L, stereo(riser(2.0)), 12.0, 1.0)
place(L, stereo(whoosh(0.5, rev=True)), POP - 0.5, 1.2)

# POP: impact + crash into big reverb
imp = impact()
place(L, stereo(imp), POP, 1.1)
place(REVSEND, stereo(imp), POP, 0.6)
crash = hp(rng.standard_normal(int(2.5 * SR)), 4000) * np.exp(-t_arr(2.5) * 2.2) * 0.3
place(L, np.array([crash, np.roll(crash, 300)]), POP, 1.0)
place(REVSEND, np.array([crash, crash]), POP, 0.8)

# Slow-motion section (14-22): half-time, huge reverb claps, sustained sub
for b in range(7, 11):
    t0 = b * BAR
    notes, root = chord(b)
    place(DRUMS, stereo(kick(1.0, 0.7)), t0, 1.0)
    place(DRUMS, stereo(kick(0.6, 0.5)), t0 + 1.25, 0.55)
    c = clap(0.4)
    place(DRUMS, stereo(c), t0 + 1.0, 0.6)
    place(REVSEND, stereo(c), t0 + 1.0, 1.4)
    place(L, stereo(bass(root - 12, BAR - 0.05, 0.75)), t0, 1.0)
    for q in range(8):
        place(DRUMS, stereo(hat(0.04), 0.4 if q % 2 else -0.4), t0 + q * BEAT / 2 + 0.0, 0.12)
# text accents: "50% OFF" on 14.5, dates on 18.0
for ta, g in ((14.5, 0.9), (18.0, 0.8)):
    place(L, stereo(whoosh(0.45, rev=True)), ta - 0.45, 0.9)
    bl = bell(81, 2.5, 0.22)
    place(L, stereo(bl), ta, 1.0)
    place(REVSEND, stereo(bl), ta, 1.5)
place(L, stereo(whoosh(0.8, rev=True)), 22.0 - 0.8, 1.0)

# End card (22-26): final hit, chord rings out
place(DRUMS, stereo(kick(1.0, 0.8)), 22.0, 1.0)
fin = impact() * 0.6
place(L, stereo(fin), 22.0, 0.8)
place(REVSEND, stereo(fin), 22.0, 0.5)
place(L, stereo(bass(45 - 12, 3.4, 0.7)), 22.0, 1.0)

# ---------- mix ----------
wet = reverb(REVSEND, 3.2, 5000)
mix = L + DRUMS + 0.55 * wet

# sidechain pump under the 4/4 groove (pads/bass breathe with kick)
pump = np.ones(N)
for b in range(2, 7):
    for q in range(4):
        i = int((b * BAR + q * BEAT) * SR)
        n = int(0.3 * SR)
        pump[i:i + n] = np.minimum(pump[i:i + n], 0.55 + 0.45 * (np.arange(n) / n) ** 0.6)
mix = (L * pump + DRUMS + 0.55 * wet)

# master: gentle glue, fade out
mix = np.tanh(mix * 1.1) / 1.1
fade = np.ones(N)
fo = int(1.4 * SR)
fade[-fo:] = np.linspace(1, 0, fo) ** 1.5
mix *= fade
mix /= np.max(np.abs(mix)) + 1e-9
mix *= 0.89
wavfile.write(sys.argv[1], SR, (mix.T * 32767).astype(np.int16))
print("ok", mix.shape)
