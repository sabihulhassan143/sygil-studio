"""Mood-matched synth score + few soft SFX on the video's key moments (cues), written as a 48k stereo wav.
usage: python3 score.py out.wav mood seconds cues.json
Rules: music picked by project mood, music never overpowers, SFX are subtle accents 8-12 dB under the music peak,
only on 3-5 key moments, final loudness is normalized later by ffmpeg (-14 LUFS, TP -1.5)."""
import json, sys, wave
import numpy as np

SR = 48000
out, mood, DUR, cues = sys.argv[1], sys.argv[2], float(sys.argv[3]), json.load(open(sys.argv[4]))
N = int(SR * DUR)
L = np.zeros(N); R = np.zeros(N)
rng = np.random.default_rng(abs(hash(mood)) % 2**32)

def add(sig, at, g=1.0, pan=0.0, bus=None):
    i = int(at * SR)
    if i >= N or i < 0: return
    j = min(N, i + len(sig)); s = sig[:j - i] * g
    (bus or (L, R))[0][i:j] += s * (1 - max(pan, 0)); (bus or (L, R))[1][i:j] += s * (1 + min(pan, 0))
def env(n, a=.002, d=.3): t = np.arange(n) / SR; return np.minimum(t / a, 1) * np.exp(-t / d)
def lp(x, k):
    # fast one-pole lowpass via cumulative filter
    from scipy.signal import lfilter
    return lfilter([k], [1, k - 1], x)
def hp(x, k): return x - lp(x, k)
def note(m): return 440 * 2 ** ((m - 69) / 12)
def osc(f, n, kind='sine'):
    t = np.arange(n) / SR; ph = 2 * np.pi * f * t
    if kind == 'sine': return np.sin(ph)
    if kind == 'tri': return 2 / np.pi * np.arcsin(np.sin(ph))
    if kind == 'saw': return 2 * ((f * t) % 1) - 1
    if kind == 'sq': return np.sign(np.sin(ph)) * .6
def kick(g=1, tight=.16):
    n = int(.5 * SR); t = np.arange(n) / SR
    return np.sin(2 * np.pi * np.cumsum(45 + 120 * np.exp(-t * 30)) / SR) * env(n, .001, tight) * g
def snare(g=1):
    n = int(.3 * SR); nz = hp(rng.standard_normal(n), .2)
    return (nz * env(n, .001, .08) * .7 + np.sin(2 * np.pi * 185 * np.arange(n) / SR) * env(n, .001, .05) * .5) * g
def clap(g=1):
    n = int(.25 * SR); nz = hp(rng.standard_normal(n), .3); e = np.zeros(n)
    for o in (0, .01, .02): i = int(o * SR); e[i:] += env(n - i, .0005, .06)
    return nz * e * .5 * g
def hat(g=1, open_=False):
    n = int((.25 if open_ else .05) * SR); return hp(rng.standard_normal(n), .6) * env(n, .0005, .09 if open_ else .015) * .35 * g
def pluck(m, n_s=.35, kind='tri'):
    n = int(n_s * SR); return osc(note(m), n, kind) * env(n, .003, n_s / 3)
def pad(chord, length, kind='saw', cut=.02):
    n = int(length * SR); s = sum(osc(note(m) * (1 + d), n, kind) for m in chord for d in (-.003, .003))
    s = lp(s / (2 * len(chord)), cut); a = np.minimum(np.arange(n) / (.3 * SR), 1) * np.minimum((n - np.arange(n)) / (.3 * SR), 1)
    return s * a
def bass(m, length, kind='sine'):
    n = int(length * SR); return lp(osc(note(m), n, kind), .05 if kind != 'sine' else 1) * env(n, .005, length * .8)
def tom(f0=95): n = int(.5 * SR); t = np.arange(n) / SR; return np.sin(2 * np.pi * np.cumsum(f0 + 60 * np.exp(-t * 15)) / SR) * env(n, .001, .25)

MOODS = {  # bpm, root, progression (semitones from root), kit, pad wave, lead wave
  'military': dict(bpm=110, root=45, prog=[[0, 3, 7], [-4, 0, 3], [-2, 2, 5], [-5, -2, 2]], kit='cine', padk='saw', lead=None),
  'playful':  dict(bpm=118, root=60, prog=[[0, 4, 7], [7, 11, 14], [9, 12, 16], [5, 9, 12]], kit='pop', padk='tri', lead='tri'),
  'spooky':   dict(bpm=92, root=50, prog=[[0, 3, 7], [1, 4, 8], [0, 3, 6], [-1, 3, 7]], kit='dark', padk='saw', lead='sine'),
  'luxury':   dict(bpm=120, root=53, prog=[[0, 4, 7, 11], [-1, 2, 7, 10], [-3, 0, 3, 7], [-5, -1, 2, 7]], kit='house', padk='tri', lead='sine'),
  'synthwave':dict(bpm=104, root=45, prog=[[0, 3, 7], [-4, 0, 3], [3, 7, 10], [-2, 2, 5]], kit='wave', padk='saw', lead='saw'),
  'jpop':     dict(bpm=128, root=62, prog=[[0, 4, 7], [-3, 0, 4], [5, 9, 12], [7, 11, 14]], kit='pop', padk='tri', lead='sq'),
  'trap':     dict(bpm=140, root=46, prog=[[0, 3, 7], [-4, 0, 3], [-2, 2, 5], [0, 3, 7]], kit='trap', padk='saw', lead='sq'),
}
M = MOODS.get(mood, MOODS['trap']); beat = 60 / M['bpm']; bar = beat * 4
start = 1.0  # music drop lands on the logo slam
mus = (np.zeros(N), np.zeros(N))
# intro (0-1s): soft riser into the drop
n0 = int(start * SR); tt = np.arange(n0) / SR
add(lp(rng.standard_normal(n0), .05) * (tt / start) ** 2 * .35, 0, 1, 0, mus)
t = start; bi = 0
end_music = DUR - 1.2
while t < end_music:
    ch = M['prog'][bi % 4]; r = M['root']
    add(pad([r + 12 + c for c in ch], bar + .05, M['padk']), t, .55, 0, mus)
    add(bass(r - 12 + ch[0], beat * 2, 'sine'), t, .9, 0, mus); add(bass(r - 12 + ch[0], beat * 2, 'sine'), t + beat * 2, .8, 0, mus)
    for b in range(4):
        bt = t + b * beat
        if bt >= end_music: break
        k = M['kit']
        if k in ('house', 'pop', 'wave'): add(kick(), bt, .9, 0, mus)
        elif k == 'trap':
            if b in (0, 2): add(kick(1, .35), bt + (beat * .75 if b == 2 and bi % 2 else 0), 1.0, 0, mus)
        elif k in ('cine', 'dark'):
            if b in (0, 2) or (k == 'cine' and b == 3): add(kick(1, .22), bt, .9, 0, mus)
            if k == 'cine' and b == 3: add(tom(110), bt + beat / 2, .35, .2, mus)
        if b in (1, 3): add(clap() if k in ('pop', 'trap', 'house') else snare(), bt, .45 if k != 'dark' else .25, 0, mus)
        steps = 4 if k == 'trap' else 2
        for h in range(steps): add(hat(1, k == 'house' and h == 1), bt + h * beat / steps, .5 if k != 'dark' else .2, .25 * ((h % 2) * 2 - 1), mus)
        if M['lead'] and bi >= 1:
            arp = [r + 24 + c for c in ch] + [r + 36 + ch[0]]
            for s8 in range(2): add(lp(pluck(arp[(b * 2 + s8) % len(arp)], .3, M['lead']), .3), bt + s8 * beat / 2, .22, .3 * (s8 * 2 - 1), mus)
    t += bar; bi += 1
# outro: last chord rings out
add(pad([M['root'] + 12 + c for c in M['prog'][0]], 1.6, M['padk']), end_music, .6, 0, mus)
# sidechain-ish pump + gentle duck while captions slam (keeps the bed under the visuals)
m = np.stack(mus, 1); peak = np.max(np.abs(m)) or 1; m = m / peak * .5
# ---------- SFX: few, soft (≈ -10 dB under the music peak)
fx = (np.zeros(N), np.zeros(N))
def whoosh(length=.45):
    n = int(length * SR); x = np.linspace(0, 1, n); return lp(rng.standard_normal(n), .08) * np.sin(np.pi * x) ** 2
def impact(): n = int(1.2 * SR); tt = np.arange(n) / SR; return np.sin(2 * np.pi * np.cumsum(38 + 70 * np.exp(-tt * 10)) / SR) * env(n, .001, .45) + lp(rng.standard_normal(n), .1) * env(n, .001, .08)
def ding(f=1568): n = int(1.0 * SR); tt = np.arange(n) / SR; return (np.sin(2 * np.pi * f * tt) + .35 * np.sin(2 * np.pi * f * 2.01 * tt)) * env(n, .002, .3)
def pop(): n = int(.12 * SR); tt = np.arange(n) / SR; return np.sin(2 * np.pi * (900 - 500 * tt / .12) * tt) * env(n, .001, .03)
def tick():
    s = np.zeros(int(1.2 * SR))
    for k in range(14): i = int(k * .075 * SR); c = hp(rng.standard_normal(int(.02 * SR)), .5) * env(int(.02 * SR), .0003, .004); s[i:i + len(c)] += c
    return s
SFX = {'impact': (impact, .32), 'whoosh': (whoosh, .22), 'flip': (lambda: whoosh(.3), .2), 'pop': (pop, .2), 'ding': (ding, .14), 'tick': (tick, .18)}
for c in cues:
    f, g = SFX.get(c['k'], (None, 0))
    if f: add(f(), c['t'], g, 0, fx)
mix = m + np.stack(fx, 1)
fade_in = np.minimum(np.arange(N) / (.05 * SR), 1); fade_out = np.clip((DUR - np.arange(N) / SR) / 1.2, 0, 1)
mix *= (fade_in * fade_out)[:, None]
mix = np.tanh(mix * 1.2) / np.tanh(1.2) * .9
with wave.open(out, 'wb') as w:
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes((mix * 32767).astype('<i2').tobytes())
print('score ok', mood, DUR)
