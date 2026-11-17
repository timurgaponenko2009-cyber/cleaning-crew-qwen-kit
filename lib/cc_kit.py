"""cc_kit — общая библиотека моделей CLEANING CREW для Blender 5.2 (headless).

Скрипт пакета (его пишет Qwen) выглядит так:

    from cc_kit import *

    @asset("HB_Bollard")
    def bollard(B):
        B.add("Body", "Concrete", box(bm_new(), (0, 0, 1.15), (0.7, 0.7, 2.3), r=0.06))
        B.add("Cap", "NeonOrange", cyl(bm_new(), (0, 0, 2.3), (0, 0, 2.4), 0.3))

    run("V1")

Запуск: python run_qwen.py <скрипт.py>  (Blender в фоне, результат в out/<пакет>/).
run() строит все ассеты, делает PBR-текстуры только для использованных материалов,
проверяет стандарт, пишет FBX, превью, report.txt и печатает строки REPORT/CHECK.
Функции геометрии и материалов взяты из art/blender/build_office_kit.py (формат уже в игре).
"""

import math
import os
import time

import bmesh
import bpy
import numpy as np
from mathutils import Euler, Matrix, Vector

T0 = time.time()
OUT = os.environ.get("CC_OUT", os.path.join(os.getcwd(), "out"))
TEX_DIR = os.path.join(OUT, "tex")
RES = int(os.environ.get("CC_RES", "1600"))
MAX_OBJECTS = 60
TILE = 4.0  # studs per texture repeat
TEX = int(os.environ.get("CC_TEX", "512"))
PREFIXES = ("HB_", "OF_", "TK_", "TR_", "FX_", "UI_", "CC_", "FH_", "Crew")

def srgb(r, g, b):
    def lin(c):
        c /= 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    return (lin(r), lin(g), lin(b), 1.0)


# ------------------------------------------------------------------ materials
# name: (rgb, metallic, roughness, pattern, extra)
MAT_DEF = {
    "WornWood": ((118, 86, 58), 0.0, 0.62, "wood", {}),
    "DarkWood": ((66, 44, 31), 0.0, 0.5, "wood", {}),
    "OldMetal": ((104, 108, 112), 0.8, 0.46, "metal", {}),
    "SteelMetal": ((150, 154, 156), 0.9, 0.34, "metal", {}),
    "RustMetal": ((104, 64, 42), 0.35, 0.86, "rust", {}),
    "Chrome": ((196, 200, 204), 1.0, 0.2, "metal", {}),
    "Brass": ((146, 114, 68), 0.9, 0.36, "metal", {}),
    "OldPlastic": ((178, 170, 152), 0.0, 0.56, "plastic", {}),  # yellowed office beige
    "DarkPlastic": ((38, 40, 44), 0.0, 0.5, "plastic", {}),
    "Laminate": ((168, 162, 150), 0.0, 0.5, "speckle", {}),
    "Enamel": ((192, 188, 178), 0.0, 0.42, "plastic", {}),
    "OldLeather": ((58, 38, 29), 0.0, 0.52, "leather", {}),
    "OfficeFabric": ((56, 62, 72), 0.0, 0.95, "fabric", {}),
    "DustyGlass": ((140, 156, 160), 0.0, 0.22, "glass", {"alpha": 0.45}),
    "BoardGlass": ((196, 210, 210), 0.0, 0.16, "glass", {"alpha": 0.35}),
    "Mirror": ((186, 192, 196), 1.0, 0.1, "glass", {}),
    "Screen": ((16, 20, 22), 0.0, 0.26, "screen", {}),
    "Paper": ((210, 202, 182), 0.0, 0.86, "paper", {}),
    "Cardboard": ((146, 112, 76), 0.0, 0.9, "cardboard", {}),
    "PackTape": ((160, 128, 84), 0.0, 0.4, "plastic", {}),
    "Rubber": ((30, 30, 32), 0.0, 0.9, "rubber", {}),
    "Ceramic": ((206, 202, 192), 0.0, 0.3, "ceramic", {}),
    "Concrete": ((128, 126, 120), 0.0, 0.92, "concrete", {}),
    "LightEmit": ((255, 214, 160), 0.0, 0.3, "flat", {"emit": 2.5}),  # warm interior light
    "Soil": ((48, 38, 30), 0.0, 0.96, "concrete", {}),
    "DryLeaf": ((104, 88, 54), 0.0, 0.9, "leaf", {}),
    "Bark": ((86, 64, 48), 0.0, 0.9, "bark", {}),  # tree trunks, roots, boughs: grooves run up the trunk
    "CarPaint": ((56, 68, 60), 0.2, 0.7, "paint", {}),
    "SignPaint": ((176, 140, 40), 0.1, 0.62, "paint", {}),
    "BookRed": ((92, 36, 32), 0.0, 0.8, "fabric", {}),
    "BookBlue": ((36, 48, 72), 0.0, 0.8, "fabric", {}),
}

MATS = {}


def mat(name, label=None):
    """Material `name`; `label` ("Paint~2") is its own copy for a per-part wear level."""
    label = label or name
    if label in MATS:
        return MATS[label]
    rgb, metal, rough, _pattern, extra = MAT_DEF[name]
    col = srgb(*rgb)
    m = bpy.data.materials.new(label)
    m.use_nodes = True
    m.diffuse_color = col
    nt = m.node_tree
    b = nt.nodes.get("Principled BSDF")
    b.inputs["Base Color"].default_value = col
    b.inputs["Metallic"].default_value = metal
    b.inputs["Roughness"].default_value = rough
    if "emit" in extra:
        b.inputs["Emission Color"].default_value = col
        b.inputs["Emission Strength"].default_value = extra["emit"]
    if "alpha" in extra:
        b.inputs["Alpha"].default_value = extra["alpha"]
        try:
            m.surface_render_method = "BLENDED"
        except Exception:
            pass
    MATS[label] = m
    return m


# ------------------------------------------------------------------ textures
RNG_TEX = np.random.default_rng(1207)


def blur(a, sigma):
    """Tileable gaussian blur through the FFT."""
    n = a.shape[0]
    f = np.fft.fftfreq(n)
    k = np.exp(-2 * (math.pi * sigma) ** 2 * (f[:, None] ** 2 + f[None, :] ** 2))
    return np.real(np.fft.ifft2(np.fft.fft2(a) * k))


def norm01(a):
    lo, hi = a.min(), a.max()
    return (a - lo) / (hi - lo + 1e-9)


def fbm(sigmas=(64, 32, 16, 8, 4, 2), weights=None):
    weights = weights or [1.0 / (i + 1) ** 0.9 for i in range(len(sigmas))]
    out = np.zeros((TEX, TEX))
    for s, w in zip(sigmas, weights):
        out += w * norm01(blur(RNG_TEX.standard_normal((TEX, TEX)), s))
    return norm01(out)


def scratches(count, length=(20, 160), width=1, along=None):
    img = np.zeros((TEX, TEX))
    for _ in range(count):
        x, y = RNG_TEX.uniform(0, TEX, 2)
        ang = along + RNG_TEX.normal(0, 0.25) if along is not None else RNG_TEX.uniform(0, math.pi)
        ln = RNG_TEX.uniform(*length)
        t = np.linspace(0, ln, int(ln * 2))
        xs = ((x + np.cos(ang) * t) % TEX).astype(int)
        ys = ((y + np.sin(ang) * t) % TEX).astype(int)
        val = RNG_TEX.uniform(0.4, 1.0)
        for dx in range(width):
            img[ys, (xs + dx) % TEX] = np.maximum(img[ys, (xs + dx) % TEX], val)
    return img


def specks(count, size=1.5):
    img = np.zeros((TEX, TEX))
    idx = RNG_TEX.integers(0, TEX, (count, 2))
    img[idx[:, 0], idx[:, 1]] = RNG_TEX.uniform(0.5, 1.0, count)
    return np.clip(blur(img, size) * size * 6, 0, 1)


# How worn the pack looks (owner 17.11: the HUB is a new, clean, premium
# company; wear and dirt belong to the missions). run(pack, wear=...) sets it.
WEAR_LEVELS = {"clean": 0.12, "used": 0.5, "worn": 1.0}
WEAR = 1.0


def blur2(a, sx, sy):
    """Tileable anisotropic gaussian blur: sx across the columns, sy along the rows."""
    n = a.shape[0]
    f = np.fft.fftfreq(n)
    k = np.exp(-2 * math.pi ** 2 * ((sx * f[None, :]) ** 2 + (sy * f[:, None]) ** 2))
    return np.real(np.fft.ifft2(np.fft.fft2(a) * k))


def grime_map():
    """Dirt that reads as weathering, not camouflage: thin streaks run down the
    walls (rows = height on the box-projected sides), soft patches stay faint."""
    streaks = norm01(blur2(RNG_TEX.standard_normal((TEX, TEX)), 2.5, 80))
    streaks = np.clip((streaks - 0.56) * 2.4, 0, 1)
    patches = fbm((96, 48, 24)) ** 2.8
    return np.clip(streaks * 0.75 + patches * 0.4, 0, 1) * WEAR


def pattern(kind):
    """Returns (shade multiplier ~1, height 0..1, roughness offset, grime 0..1)."""
    grime = grime_map()
    if kind == "wood":
        warp = fbm((48, 24, 12)) * 18
        yy = np.arange(TEX)[:, None] + warp
        grain = 0.5 + 0.5 * np.sin(yy * 0.35 + fbm((128, 64)) * 9)
        fine = fbm((2, 1))
        shade = 0.78 + 0.22 * grain + 0.08 * (fine - 0.5)
        sc = scratches(60, (10, 60))
        shade -= sc * 0.12
        height = grain * 0.6 + fine * 0.2 - sc * 0.4
        return shade, height, sc * 0.15 + grime * 0.1, grime
    if kind == "bark":
        # Deep furrows along the trunk (columns = across, so they run vertically
        # on the box-projected sides), plates between them, lichen-ish grime.
        warp = fbm((64, 32, 16)) * 14
        xx = np.arange(TEX)[None, :] + warp
        ridge = np.abs(np.sin(xx * 0.11 + fbm((96, 48)) * 6))
        plates = fbm((12, 6, 3))
        furrow = ridge ** 0.45
        shade = 0.62 + 0.3 * furrow + 0.14 * (plates - 0.5)
        height = furrow * 0.8 + plates * 0.25
        return shade, height, (1 - furrow) * 0.08 + grime * 0.05, grime * 0.7
    if kind == "metal":
        brushed = norm01(blur(RNG_TEX.standard_normal((TEX, TEX)), 0.6) +
                         np.repeat(blur(RNG_TEX.standard_normal((1, TEX)), 0.8), TEX, 0) * 3)
        sc = scratches(140, (20, 200), along=0.0) + scratches(40, (10, 80))
        sc = np.clip(sc, 0, 1)
        shade = 0.88 + 0.1 * brushed + 0.12 * sc
        return shade, brushed * 0.3 - sc * 0.5, -sc * 0.2 + grime * 0.25, grime
    if kind == "rust":
        b = fbm((48, 24, 12, 6, 3))
        pits = specks(1400, 1.2)
        shade = 0.7 + 0.5 * b - pits * 0.25
        return shade, b * 0.8 - pits, 0.05 * b, grime * 0.5
    if kind == "plastic":
        n = fbm((32, 16, 8, 4))
        sc = scratches(50, (6, 40))
        shade = 0.92 + 0.08 * n - sc * 0.08
        return shade, n * 0.15 - sc * 0.3, grime * 0.2, grime
    if kind == "speckle":
        sp = specks(9000, 0.8)
        n = fbm((24, 8))
        shade = 0.9 + 0.1 * n - sp * 0.12
        return shade, sp * 0.2, grime * 0.2, grime
    if kind == "leather":
        cells = norm01(blur(RNG_TEX.standard_normal((TEX, TEX)), 3))
        cracks = np.clip(1 - np.abs(cells - 0.5) * 28, 0, 1)
        n = fbm((40, 20, 10))
        shade = 0.82 + 0.25 * n + 0.15 * cracks
        return shade, cells * 0.5 - cracks * 0.6, cracks * 0.25, grime
    if kind == "fabric":
        x = np.arange(TEX)
        weave = (np.sin(x[:, None] * 1.6) * np.sin(x[None, :] * 1.6)) * 0.5 + 0.5
        n = fbm((16, 8, 4, 2))
        shade = 0.85 + 0.15 * n + 0.06 * weave
        return shade, weave * 0.4 + n * 0.3, 0.0, grime
    if kind == "glass":
        dust = fbm((64, 16, 4)) ** 1.6
        smear = np.clip(scratches(20, (40, 220), width=6) * 0.4, 0, 1)
        shade = 0.9 + 0.2 * dust
        return shade, dust * 0.1, dust * 0.35 + smear * 0.2, dust
    if kind == "screen":
        dust = fbm((32, 8, 2)) ** 2
        return 0.9 + 0.5 * dust, dust * 0.05, dust * 0.4, dust
    if kind == "paper":
        fib = fbm((3, 1.5, 0.8))
        stain = fbm((80, 40)) ** 3
        shade = 0.95 + 0.06 * fib - stain * 0.25
        return shade, fib * 0.2, stain * 0.1, stain
    if kind == "cardboard":
        x = np.arange(TEX)
        corr = 0.5 + 0.5 * np.sin(x[None, :] * 0.9)
        fib = fbm((4, 2, 1))
        shade = 0.88 + 0.06 * corr + 0.08 * fib
        return shade, corr * 0.3 + fib * 0.2, 0.0, grime
    if kind == "rubber":
        n = fbm((8, 4, 2))
        return 0.9 + 0.12 * n, n * 0.3, 0.0, grime * 0.3
    if kind == "ceramic":
        craze = np.clip(1 - np.abs(norm01(blur(RNG_TEX.standard_normal((TEX, TEX)), 6)) - 0.5) * 60, 0, 1)
        stain = fbm((64, 32)) ** 3
        shade = 0.97 - craze * 0.08 - stain * 0.18
        return shade, -craze * 0.3, stain * 0.3, stain
    if kind == "concrete":
        n = fbm((48, 16, 6, 2, 1))
        pits = specks(2600, 0.9)
        shade = 0.8 + 0.28 * n - pits * 0.2
        return shade, n * 0.6 - pits * 0.5, 0.0, grime
    if kind == "leaf":
        veins = np.clip(1 - np.abs(np.sin(np.arange(TEX)[None, :] * 0.08 + fbm((24,)) * 4)) * 8, 0, 1)
        n = fbm((16, 8))
        shade = 0.75 + 0.35 * n - veins * 0.1
        return shade, veins * 0.3, 0.0, grime
    if kind == "paint":
        chips = np.clip((fbm((24, 12, 6, 3)) - 0.72) * 6, 0, 1) * min(1.0, WEAR * 1.2)
        n = fbm((32, 12))
        shade = 0.88 + 0.12 * n
        return shade, -chips * 0.5 + n * 0.1, chips * 0.3, grime
    return np.ones((TEX, TEX)), np.zeros((TEX, TEX)), np.zeros((TEX, TEX)), np.zeros((TEX, TEX)) * 0


def save_png(path, rgba):
    img = bpy.data.images.new(os.path.basename(path), TEX, TEX, alpha=True)
    img.pixels.foreach_set(np.ascontiguousarray(rgba[::-1], dtype=np.float32).ravel())
    img.filepath_raw = path
    img.file_format = "PNG"
    img.save()
    return img


GRIME_COL = np.array([0.18, 0.15, 0.12])


def make_textures(name, label=None, wear=None):
    """Textures of material `name`, saved as <label>_*.png; `wear` 0..1 overrides the pack level."""
    global WEAR
    label = label or name
    keep = WEAR
    if wear is not None:
        WEAR = wear
    try:
        return _make_textures(name, label)
    finally:
        WEAR = keep


def _make_textures(name, label):
    rgb, metal, rough, kind, extra = MAT_DEF[name]
    base = np.array(rgb) / 255.0
    shade, height, rough_off, grime = pattern(kind)
    shade = np.asarray(shade, dtype=float) * np.ones((TEX, TEX))
    grime = np.asarray(grime, dtype=float) * np.ones((TEX, TEX))
    col = base[None, None, :] * shade[:, :, None]
    if kind not in ("flat",):
        # Concrete gets light grime: on a 80-stud facade heavy grime reads as camouflage.
        k = 0.2 if kind == "concrete" else 0.55
        g = np.clip(grime * k, 0, k)[:, :, None]
        col = col * (1 - g) + GRIME_COL[None, None, :] * g
    col = np.clip(col, 0, 1) ** 2.2  # stored as sRGB below
    alpha = np.full((TEX, TEX, 1), 1.0)
    if "alpha" in extra:
        alpha[:] = extra["alpha"]
        alpha[:, :, 0] = np.clip(extra["alpha"] + grime * 0.35, 0, 1)
    albedo = np.concatenate([col ** (1 / 2.2), alpha], axis=2)
    h = np.asarray(height, dtype=float) * np.ones((TEX, TEX))
    dx = (np.roll(h, -1, 1) - np.roll(h, 1, 1)) * 2.2
    dy = (np.roll(h, -1, 0) - np.roll(h, 1, 0)) * 2.2
    n = np.stack([-dx, dy, np.ones_like(h)], axis=2)
    n /= np.linalg.norm(n, axis=2, keepdims=True)
    normal = np.concatenate([n * 0.5 + 0.5, np.ones((TEX, TEX, 1))], axis=2)
    r = np.clip(rough + np.asarray(rough_off) * np.ones((TEX, TEX)) + grime * 0.15, 0.03, 1.0)
    rough_img = np.concatenate([np.repeat(r[:, :, None], 3, axis=2), np.ones((TEX, TEX, 1))], axis=2)
    os.makedirs(TEX_DIR, exist_ok=True)
    out = {}
    for tag, arr in (("albedo", albedo), ("normal", normal), ("rough", rough_img)):
        out[tag] = save_png(os.path.join(TEX_DIR, f"{label}_{tag}.png"), arr)
    return out


def hook_textures(name, imgs, label=None):
    m = mat(name, label)
    nt = m.node_tree
    b = nt.nodes.get("Principled BSDF")
    ta = nt.nodes.new("ShaderNodeTexImage")
    ta.image = imgs["albedo"]
    nt.links.new(ta.outputs["Color"], b.inputs["Base Color"])
    if "alpha" in MAT_DEF[name][4]:
        nt.links.new(ta.outputs["Alpha"], b.inputs["Alpha"])
    tr = nt.nodes.new("ShaderNodeTexImage")
    tr.image = imgs["rough"]
    tr.image.colorspace_settings.name = "Non-Color"
    nt.links.new(tr.outputs["Color"], b.inputs["Roughness"])
    tn = nt.nodes.new("ShaderNodeTexImage")
    tn.image = imgs["normal"]
    tn.image.colorspace_settings.name = "Non-Color"
    nm = nt.nodes.new("ShaderNodeNormalMap")
    nt.links.new(tn.outputs["Color"], nm.inputs["Color"])
    nt.links.new(nm.outputs["Normal"], b.inputs["Normal"])


# ------------------------------------------------------------------ geometry
def T(x=0.0, y=0.0, z=0.0):
    return Matrix.Translation(Vector((x, y, z)))


def euler(rx=0, ry=0, rz=0):
    return Euler((math.radians(rx), math.radians(ry), math.radians(rz))).to_matrix().to_4x4()


def bm_new():
    return bmesh.new()


def merge(dst, src):
    vmap = {v: dst.verts.new(v.co) for v in src.verts}
    for f in src.faces:
        try:
            dst.faces.new([vmap[v] for v in f.verts])
        except ValueError:
            pass
    src.free()
    return dst


def xf(bm, M):
    bmesh.ops.transform(bm, matrix=M, verts=bm.verts)
    return bm


def box(bm, c, s, r=0.0, seg=2, rot=(0, 0, 0)):
    tmp = bmesh.new()
    bmesh.ops.create_cube(tmp, size=1.0, matrix=Matrix.Diagonal((s[0], s[1], s[2], 1.0)))
    if r > 0:
        bmesh.ops.bevel(tmp, geom=list(tmp.edges), offset=min(r, min(s) * 0.49), offset_type="OFFSET",
                        segments=seg, profile=0.5, affect="EDGES", clamp_overlap=True)
    xf(tmp, T(*c) @ euler(*rot))
    return merge(bm, tmp)


def cyl(bm, a, b, r0, r1=None, segs=16):
    r1 = r0 if r1 is None else r1
    a, b = Vector(a), Vector(b)
    d = b - a
    rot = d.to_track_quat("Z", "Y").to_matrix().to_4x4()
    tmp = bmesh.new()
    bmesh.ops.create_cone(tmp, cap_ends=True, segments=segs, radius1=r0, radius2=r1, depth=d.length,
                          matrix=Matrix.Translation((a + b) / 2) @ rot)
    return merge(bm, tmp)


def ball(bm, c, r, subd=2, sx=1.0, sy=1.0, sz=1.0):
    tmp = bmesh.new()
    bmesh.ops.create_icosphere(tmp, subdivisions=subd, radius=r,
                               matrix=T(*c) @ Matrix.Diagonal((sx, sy, sz, 1.0)))
    return merge(bm, tmp)


def lathe(bm, prof, segs, m=Matrix(), cap=True):
    """Revolve an open profile [(r, h)] (bottom to top) about local Z."""
    tmp = bmesh.new()
    rings = []
    for i in range(segs):
        a = 2 * math.pi * i / segs
        rings.append([tmp.verts.new(m @ Vector((r * math.cos(a), r * math.sin(a), h))) for r, h in prof])
    k = len(prof)
    for i in range(segs):
        A, B = rings[i], rings[(i + 1) % segs]
        for j in range(k - 1):
            q = [A[j], B[j], B[j + 1], A[j + 1]]
            uniq = []
            for v in q:
                if all((v.co - u.co).length > 1e-6 for u in uniq):
                    uniq.append(v)
            if len(uniq) >= 3:
                try:
                    tmp.faces.new(uniq)
                except ValueError:
                    pass
    if cap and prof[0][0] > 1e-6:
        try:
            tmp.faces.new([r[0] for r in reversed(rings)])
        except ValueError:
            pass
    return merge(bm, tmp)


def torus(bm, c, major, minor, m=Matrix(), segs=24, ring=8):
    prof = [(major + minor * math.cos(2 * math.pi * j / ring), minor * math.sin(2 * math.pi * j / ring))
            for j in range(ring + 1)]
    return lathe(bm, prof, segs, T(*c) @ m, cap=False)


def sweep(bm, pts, rad, segs=8):
    """Open tube of radius rad along points, capped."""
    pts = [Vector(p) for p in pts]
    n = len(pts)
    tmp = bmesh.new()
    tan = [(pts[min(i + 1, n - 1)] - pts[max(i - 1, 0)]).normalized() for i in range(n)]
    ref = Vector((0, 0, 1)) if abs(tan[0].z) < 0.9 else Vector((1, 0, 0))
    nrm = tan[0].cross(ref).normalized()
    rings = []
    for i in range(n):
        t = tan[i]
        nrm = (nrm - t * nrm.dot(t)).normalized()
        bi = t.cross(nrm)
        rings.append([tmp.verts.new(pts[i] + (nrm * math.cos(2 * math.pi * k / segs) +
                                              bi * math.sin(2 * math.pi * k / segs)) * rad) for k in range(segs)])
    for i in range(n - 1):
        A, B = rings[i], rings[i + 1]
        for k in range(segs):
            tmp.faces.new((A[k], A[(k + 1) % segs], B[(k + 1) % segs], B[k]))
    tmp.faces.new(rings[0][::-1])
    tmp.faces.new(rings[-1])
    return merge(bm, tmp)


def prism(bm, pts, y0, y1, r=0.0, seg=2):
    """Extrude a 2D outline [(x, z)] (counter-clockwise seen from -Y) between y0 and y1."""
    tmp = bmesh.new()
    f = [tmp.verts.new((x, y0, z)) for x, z in pts]
    b = [tmp.verts.new((x, y1, z)) for x, z in pts]
    n = len(pts)
    tmp.faces.new(f)
    tmp.faces.new(b[::-1])
    for i in range(n):
        j = (i + 1) % n
        tmp.faces.new((f[j], f[i], b[i], b[j]))
    bmesh.ops.recalc_face_normals(tmp, faces=tmp.faces)
    if r > 0:
        bmesh.ops.bevel(tmp, geom=list(tmp.edges), offset=r, offset_type="OFFSET", segments=seg,
                        profile=0.5, affect="EDGES", clamp_overlap=True)
    return merge(bm, tmp)


def leg(bm, x, y, h, rt=0.09, rb=0.07, z0=0.0, segs=10):
    return cyl(bm, (x, y, z0), (x, y, z0 + h), rb, rt, segs)


def rrect(w, h, r, n=6, cx=0.0, cz=0.0):
    """Rounded rectangle outline (counter-clockwise) for prism(): signs, panels, screens."""
    r = min(r, w / 2, h / 2)
    pts = []
    for qx, qz, a0 in ((1, 1, 0), (-1, 1, 90), (-1, -1, 180), (1, -1, 270)):
        ox, oz = cx + qx * (w / 2 - r), cz + qz * (h / 2 - r)
        for i in range(n + 1):
            a = math.radians(a0 + 90 * i / n)
            pts.append((ox + r * math.cos(a), oz + r * math.sin(a)))
    return pts


def arcpts(cx, cz, r, a0, a1, n=16):
    """Points on an arc (degrees, counter-clockwise): arches, livery waves, wheel sectors."""
    return [(cx + r * math.cos(math.radians(a0 + (a1 - a0) * i / n)),
             cz + r * math.sin(math.radians(a0 + (a1 - a0) * i / n))) for i in range(n + 1)]


def soften(bm, levels=1, smooth=0.6):
    """Subdivide and relax: cushions, bags, rags, mop strands, organic shapes."""
    for _ in range(levels):
        bmesh.ops.subdivide_edges(bm, edges=bm.edges[:], cuts=1, use_grid_fill=True)
        bmesh.ops.smooth_vert(bm, verts=bm.verts[:], factor=smooth, use_axis_x=True,
                              use_axis_y=True, use_axis_z=True)
    return bm


def displace(bm, amp=0.05, scale=0.5, seed=1):
    """Crumple: moves every vertex along its normal by smooth noise (fabric, paper, bags, foil)."""
    bm.normal_update()
    for v in bm.verts:
        p = v.co * (1.0 / max(scale, 1e-3))
        n = (math.sin(p.x * 1.7 + seed) * math.cos(p.y * 2.3 - seed) * math.sin(p.z * 1.9 + seed * 0.7)
             + 0.5 * math.sin(p.x * 4.1 - p.z * 3.3 + seed * 1.3))
        v.co += v.normal * (amp * n)
    return bm


def mirror_x(bm):
    """Mirror across X (left glove from the right one) with normals kept outward."""
    bmesh.ops.transform(bm, matrix=Matrix.Scale(-1, 4, (1, 0, 0)), verts=bm.verts[:])
    bmesh.ops.reverse_faces(bm, faces=bm.faces[:])
    return bm


def _drop_pts(cx, cz, r, n=14):
    """Teardrop outline (point up), counter-clockwise, seen from -Y."""
    pts = []
    for i in range(n + 1):
        a = math.radians(150 + 240 * i / n)  # round bottom: 150 -> 390 degrees
        pts.append((cx + r * math.cos(a), cz + r * math.sin(a) * 0.95))
    return pts + [(cx, cz + r * 1.9)]  # the tip on top


def _star_pts(cx, cz, r, inner=0.28, n=4, rot=45):
    pts = []
    for i in range(n * 2):
        rr = r if i % 2 == 0 else r * inner
        a = math.radians(rot + 90 + 180 * i / n)
        pts.append((cx + rr * math.cos(a), cz + rr * math.sin(a)))
    return pts


def emblem(c, d, depth=0.08, face="-Y"):
    """The CLEANING CREW emblem (one design everywhere): returns bmeshes
    {"badge": disc, "drop": water drop, "bubble": ring, "spark": four-point glint}.
    c = centre of the badge's back face, d = badge diameter; the emblem looks along
    -Y (face="-Y") or +Y ("+Y"); for walls along X turn it with xf(bm, ...).
    Suggested materials: badge BrandNavy or BrandWhite, drop BrandTeal,
    bubble BrandWhite, spark NeonWhite or BrandWhite."""
    x, y, z = c
    sgn = -1 if face == "-Y" else 1
    r = d / 2
    def slab(pts, layer):
        y0 = y + sgn * (depth * layer)
        y1 = y + sgn * (depth * (layer + 1))
        return prism(bm_new(), pts, min(y0, y1), max(y0, y1), r=min(0.02, depth * 0.3))
    circle = [(x + r * math.cos(math.radians(a)), z + r * math.sin(math.radians(a))) for a in range(0, 360, 10)]
    out = {"badge": slab(circle, 0)}
    out["drop"] = slab(_drop_pts(x - r * 0.08, z - r * 0.22, r * 0.36), 1)
    ring = bm_new()
    torus(ring, (x + r * 0.42, y + sgn * depth * 1.5, z + r * 0.36), r * 0.17, r * 0.035,
          m=euler(90, 0, 0), segs=24, ring=8)
    out["bubble"] = ring
    out["spark"] = slab(_star_pts(x - r * 0.4, z + r * 0.42, r * 0.16), 1)
    return out


class Rng:
    def __init__(self, seed):
        self.s = seed

    def __call__(self, a=0.0, b=1.0):
        self.s = (self.s * 1103515245 + 12345) & 0x7FFFFFFF
        return a + (b - a) * self.s / 0x7FFFFFFF


# ------------------------------------------------------------------ builder
class Builder:
    """Collects bmeshes per (part, material) of one asset."""

    def __init__(self, asset):
        self.asset = asset
        self.parts = {}
        self.flat = set()
        self.tile = {}
        self.wear = {}

    def mark(self, name, pos, dir=None):
        """A named point for the game: prompt, screen centre, wheel centre, shelf,
        steam or leaf emitter. Written to markers.json and a MARK line."""
        MARKS.setdefault(self.asset, {})[name] = {"pos": list(pos), "dir": list(dir) if dir else None}

    def light(self, name, kind, pos, dir=(0, -1, 0), color=(255, 236, 210), range=16,
              brightness=1.5, angle=60, shadows=False):
        """A Roblox light: kind "point" | "spot" | "surface". Written to lights.json."""
        LIGHTS.setdefault(self.asset, {})[name] = {
            "kind": kind, "pos": list(pos), "dir": list(dir), "color": list(color),
            "range": range, "brightness": brightness, "angle": angle, "shadows": shadows}

    def add(self, part, material, src, anim=None, pivot=None, axis="Z", speed=None,
            flat=False, tile=None, dist=None, angle=None, period=None, phase=None, wear=None):
        """anim: "spin" | "swing" | "slide" | "blink" | "sway" -- a moving part.
        pivot: rotation point / hinge in asset coordinates; axis: "X" | "Y" | "Z"
        (for slide: the direction); speed: turns per second or a period, optional.
        A moving part must be its OWN part name: the game moves it as a whole."""
        key = (part, material)
        if key not in self.parts:
            self.parts[key] = bm_new()
        merge(self.parts[key], src)
        if flat:  # faceted look: every edge hard (crystal foliage, low-poly rocks)
            self.flat.add(key)
        if tile:  # studs per texture repeat for this part (small tools: 0.5-1)
            self.tile[key] = tile
        if wear is not None:  # 0 = new, 1 = old; overrides run(wear=...) for this part
            self.wear[key] = max(0.0, min(1.0, float(wear)))
        if anim:
            info = {"anim": anim, "pivot": list(pivot) if pivot else None, "axis": axis, "speed": speed}
            for k, v in (("dist", dist), ("angle", angle), ("period", period), ("phase", phase)):
                if v is not None:
                    info[k] = v
            ANIM.setdefault(self.asset, {})[part] = info

    def build(self, coll):
        objs = []
        for (part, material), bm in self.parts.items():
            bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
            bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
            # Sharp corners keep hard normals, bevels shade smooth.
            limit = 0.0 if (part, material) in self.flat else math.radians(38)
            sharp = [e for e in bm.edges if len(e.link_faces) == 2 and
                     e.calc_face_angle(0) > limit]
            bmesh.ops.split_edges(bm, edges=sharp)
            uv = bm.loops.layers.uv.new("UVMap")
            tile = self.tile.get((part, material), TILE)
            for face in bm.faces:
                face.smooth = True
                nx, ny, nz = (abs(c) for c in face.normal)
                for loop in face.loops:
                    p = loop.vert.co
                    if nz >= nx and nz >= ny:
                        u, v = p.x, p.y
                    elif nx >= ny:
                        u, v = p.y, p.z
                    else:
                        u, v = p.x, p.z
                    loop[uv].uv = (u / tile, v / tile)
            name = f"{self.asset}__{part}__{material}"
            me = bpy.data.meshes.new(name)
            bm.to_mesh(me)
            bm.free()
            w = self.wear.get((part, material))
            me.materials.append(mat(material, None if w is None else f"{material}~{round(w * 10)}"))
            ob = bpy.data.objects.new(name, me)
            coll.objects.link(ob)
            objs.append(ob)
        return objs




# ------------------------------------------------------------------ Dark Realism materials
# Имена из промпта Qwen (п.4) поверх материалов офисного кита.
MAT_DEF.update({
    "WetConcrete": ((92, 92, 90), 0.0, 0.32, "concrete", {}),
    "Asphalt": ((46, 47, 50), 0.0, 0.78, "concrete", {}),
    "Metal": ((150, 154, 156), 0.9, 0.34, "metal", {}),
    "Wood": ((140, 100, 66), 0.0, 0.55, "wood", {}),
    "Glass": ((120, 136, 146), 0.0, 0.12, "glass", {"alpha": 0.4}),
    "DirtyGlass": ((120, 128, 124), 0.0, 0.3, "glass", {"alpha": 0.55}),
    "Tile": ((178, 176, 168), 0.0, 0.34, "ceramic", {}),
    "CeilingTile": ((190, 186, 172), 0.0, 0.9, "speckle", {}),
    "Linoleum": ((112, 110, 100), 0.0, 0.5, "speckle", {}),
    "Carpet": ((58, 60, 66), 0.0, 0.98, "fabric", {}),
    "Fabric": ((56, 62, 72), 0.0, 0.95, "fabric", {}),
    "Leather": ((58, 38, 29), 0.0, 0.52, "leather", {}),
    "Plastic": ((178, 170, 152), 0.0, 0.56, "plastic", {}),
    "Brick": ((112, 66, 52), 0.0, 0.88, "concrete", {}),
    "SafetyOrange": ((226, 122, 44), 0.1, 0.55, "paint", {}),
    "WarnRed": ((214, 64, 52), 0.1, 0.55, "paint", {}),
    "Paint": ((150, 153, 158), 0.1, 0.62, "paint", {}),
    "NeonOrange": ((255, 136, 32), 0.0, 0.3, "flat", {"emit": 6.0}),
    "Leaf": ((86, 112, 60), 0.0, 0.7, "leaf", {}),       # healthy foliage, muted green
    "LeafDark": ((52, 76, 44), 0.0, 0.75, "leaf", {}),   # conifers, hedges, shaded leaves
    "Grass": ((104, 124, 66), 0.0, 0.85, "leaf", {}),
    "Flower": ((214, 92, 70), 0.0, 0.6, "plastic", {}),  # warm flower heads
})

# ------------------------------------------------------------------ clean HUB and brand (17.11)
# The HUB is the crew's new, clean company campus: brand navy, turquoise and
# white, dark powder-coated frames, rendered facades, LED light; bright
# plastics for the products in the store.
MAT_DEF.update({
    "BrandWhite": ((236, 238, 236), 0.0, 0.32, "paint", {}),   # van body, fascias, kiosks
    "BrandNavy": ((30, 46, 70), 0.1, 0.4, "paint", {}),        # company navy (HQ, signs, uniforms)
    "BrandTeal": ((46, 160, 156), 0.1, 0.4, "paint", {}),      # company turquoise (livery, trims)
    "PowderCoat": ((58, 64, 72), 0.4, 0.45, "paint", {}),      # dark frames, posts, rails, benches
    "Stucco": ((222, 218, 210), 0.0, 0.88, "concrete", {}),    # clean rendered facade walls
    "Composite": ((206, 208, 210), 0.3, 0.38, "paint", {}),    # aluminium composite cladding panels
    "Acrylic": ((226, 236, 240), 0.0, 0.25, "glass", {"alpha": 0.7}),  # frosted light boxes, signs
    "NeonTeal": ((90, 235, 225), 0.0, 0.3, "flat", {"emit": 5.0}),     # brand neon, light lines
    "LightCool": ((235, 245, 255), 0.0, 0.3, "flat", {"emit": 3.0}),   # LED panels, cool light
    "BottleBlue": ((58, 128, 214), 0.0, 0.3, "plastic", {}),   # product bottles and canisters
    "BottleGreen": ((84, 176, 92), 0.0, 0.3, "plastic", {}),
    "BottleYellow": ((238, 198, 64), 0.0, 0.3, "plastic", {}),
    "BottlePink": ((228, 112, 160), 0.0, 0.3, "plastic", {}),
    "SpongeYellow": ((240, 208, 84), 0.0, 0.9, "speckle", {}), # sponges, foam pads
    "Microfiber": ((70, 140, 200), 0.0, 0.95, "fabric", {}),   # cloths, mop heads
})

# ------------------------------------------------------------------ 17.11 full list (all four briefs)
# Synonyms from the briefs (Powder = PowderCoat, CleanWhite = BrandWhite ...) keep their own names
# so every brief stays valid. Roblox look: tools/assemble_qwen_pack.luau PALETTE (same list).
MAT_DEF.update({
    "BrandBlue": ((29, 95, 208), 0.1, 0.4, "paint", {}),
    "BrandLime": ((181, 222, 58), 0.1, 0.45, "paint", {}),
    "BrandAqua": ((141, 235, 227), 0.1, 0.4, "paint", {}),
    "BrandMist": ((227, 234, 244), 0.0, 0.5, "paint", {}),
    "CleanWhite": ((236, 238, 236), 0.0, 0.32, "paint", {}),
    "Powder": ((58, 64, 72), 0.4, 0.45, "paint", {}),
    "PowderGraphite": ((54, 58, 64), 0.3, 0.55, "paint", {}),
    "Facade": ((214, 218, 220), 0.5, 0.32, "paint", {}),
    "Cedar": ((176, 116, 72), 0.0, 0.5, "wood", {}),
    "LightConcrete": ((206, 204, 198), 0.0, 0.85, "concrete", {}),
    "Plaster": ((230, 226, 218), 0.0, 0.9, "concrete", {}),
    "Stone": ((150, 148, 142), 0.0, 0.3, "speckle", {}),
    "Siding": ((220, 222, 216), 0.0, 0.6, "paint", {}),
    "PaintedWood": ((226, 222, 212), 0.0, 0.55, "paint", {}),
    "RoofShingle": ((70, 66, 64), 0.0, 0.9, "concrete", {}),
    "Terracotta": ((178, 96, 62), 0.0, 0.7, "ceramic", {}),
    "Gold": ((232, 186, 84), 0.9, 0.3, "metal", {}),
    "CoinGold": ((240, 196, 80), 0.9, 0.3, "metal", {}),
    "GlossPlastic": ((240, 240, 240), 0.0, 0.2, "plastic", {}),
    "Linen": ((214, 206, 190), 0.0, 0.95, "fabric", {}),
    "Velvet": ((96, 60, 90), 0.0, 0.95, "fabric", {}),
    "Cotton": ((232, 228, 218), 0.0, 0.95, "fabric", {}),
    "Bristle": ((40, 40, 44), 0.0, 0.8, "plastic", {}),
    "Nitrile": ((70, 110, 200), 0.0, 0.6, "rubber", {}),
    "Sponge": ((240, 208, 84), 0.0, 0.9, "speckle", {}),
    "SpongeFoam": ((240, 208, 84), 0.0, 0.9, "speckle", {}),
    "Scour": ((60, 140, 80), 0.0, 0.95, "fabric", {}),
    "ClearGlass": ((200, 220, 228), 0.0, 0.08, "glass", {'alpha': 0.25}),
    "TintGlass": ((60, 74, 84), 0.0, 0.1, "glass", {'alpha': 0.6}),
    "ClearPlastic": ((220, 232, 240), 0.0, 0.2, "glass", {'alpha': 0.5}),
    "GemCrystal": ((120, 230, 220), 0.0, 0.05, "glass", {'alpha': 0.85}),
    "Water": ((120, 170, 190), 0.0, 0.05, "glass", {'alpha': 0.5}),
    "WaterDirty": ((110, 104, 80), 0.0, 0.1, "glass", {'alpha': 0.75}),
    "Liquid": ((90, 170, 220), 0.0, 0.15, "plastic", {}),
    "LiquidDirty": ((100, 90, 60), 0.0, 0.2, "plastic", {}),
    "Opal": ((240, 242, 240), 0.0, 0.5, "glass", {'alpha': 0.85, 'emit': 0.6}),
    "NeonWhite": ((220, 240, 255), 0.0, 0.3, "flat", {'emit': 5.0}),
    "LightCold": ((214, 228, 255), 0.0, 0.3, "flat", {'emit': 3.0}),
    "CoolLED": ((214, 228, 255), 0.0, 0.3, "flat", {'emit': 3.0}),
    "WarmLED": ((255, 196, 140), 0.0, 0.3, "flat", {'emit': 3.0}),
    "LedGlow": ((120, 240, 200), 0.0, 0.3, "flat", {'emit': 4.0}),
    "NeonLime": ((200, 255, 80), 0.0, 0.3, "flat", {'emit': 5.0}),
    "NeonGold": ((255, 200, 90), 0.0, 0.3, "flat", {'emit': 5.0}),
    "NeonGreen": ((110, 240, 140), 0.0, 0.3, "flat", {'emit': 5.0}),
    "NeonBlue": ((90, 160, 255), 0.0, 0.3, "flat", {'emit': 5.0}),
    "NeonPurple": ((190, 120, 255), 0.0, 0.3, "flat", {'emit': 5.0}),
    "RarityGreen": ((72, 196, 104), 0.1, 0.4, "paint", {}),
    "RarityBlue": ((58, 132, 236), 0.1, 0.4, "paint", {}),
    "RarityPurple": ((156, 88, 228), 0.1, 0.4, "paint", {}),
    "LeafLight": ((128, 176, 84), 0.0, 0.7, "leaf", {}),
    "LeafAutumn": ((222, 120, 48), 0.0, 0.7, "leaf", {}),
    "LeafGold": ((232, 184, 64), 0.0, 0.7, "leaf", {}),
    "LeafRed": ((188, 64, 48), 0.0, 0.7, "leaf", {}),
    "FlowerPink": ((232, 120, 160), 0.0, 0.6, "plastic", {}),
    "FlowerWhite": ((240, 236, 226), 0.0, 0.6, "plastic", {}),
    "FlowerYellow": ((240, 200, 70), 0.0, 0.6, "plastic", {}),
    "FlowerViolet": ((140, 100, 200), 0.0, 0.6, "plastic", {}),
    "Birch": ((226, 222, 212), 0.0, 0.8, "bark", {}),
    "FarRock": ((104, 112, 128), 0.0, 0.9, "flat", {}),
    "FarRockLight": ((150, 156, 170), 0.0, 0.9, "flat", {}),
    "FarSnow": ((238, 242, 248), 0.0, 0.9, "flat", {}),
    "FarForest": ((52, 80, 70), 0.0, 0.9, "flat", {}),
    "FarHaze": ((170, 180, 196), 0.0, 0.9, "flat", {}),
    "FarBuild": ((120, 128, 140), 0.0, 0.9, "flat", {}),
    "FarWindow": ((255, 214, 160), 0.0, 0.3, "flat", {'emit': 1.5}),
})

# ------------------------------------------------------------------ assets
ASSETS = []
ANIM = {}  # asset -> part -> {anim, pivot, axis, speed, dist, angle, period, phase}; anim.json
MARKS = {}  # asset -> name -> {pos, dir}; markers.json
LIGHTS = {}  # asset -> name -> light; lights.json
SIZES = {}  # asset -> (w, d, h) given in @asset(size=...)
SHOTS = []  # shot() requests, rendered at the end of run()


def asset(name, size=None, render_only=False):
    """Декоратор: @asset("HB_Lamp") над функцией f(B), которая вызывает B.add(part, material, bmesh).
    size=(ширина X, глубина Y, высота Z) из ТЗ: отклонение больше 5 % по любой оси — CHECK ERROR.
    render_only=True: модель только для рендера иконок (UI_M_*): без FBX и проверок."""
    def wrap(fn):
        if size:
            SIZES[name] = tuple(size)
        if render_only:
            RENDER_ONLY.add(name)
        ASSETS.append((name, fn))
        return fn
    return wrap


def engine_id():
    ids = [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items]
    return "BLENDER_EEVEE_NEXT" if "BLENDER_EEVEE_NEXT" in ids else "BLENDER_EEVEE"


def bounds(objs):
    lo, hi = Vector((1e9, 1e9, 1e9)), Vector((-1e9, -1e9, -1e9))
    for ob in objs:
        for v in ob.data.vertices:
            p = ob.matrix_world @ v.co
            lo = Vector(map(min, lo, p))
            hi = Vector(map(max, hi, p))
    return lo, hi


def tris_of(ob):
    return sum(len(p.vertices) - 2 for p in ob.data.polygons)


# Real scale (owner 17.11: a 16x6 «store» passed review as a «micro booth»).
# The Roblox R15 character is ~5.3 studs; doors >= 7.5; a storey 12-14.
FIGURE_H = 5.3
FIGURE_MIN = 3.0  # closeups show the figure next to assets at least this big
SCALE_RULES = (
    (("Store", "Shop", "Kiosk", "Garage", "Warehouse", "House", "Building"), "z", 11.0,
     "здание ниже 11 студов: персонаж 5.3, дверь от 7.5, этаж 12–14"),
    (("Van", "Truck"), "xy", 15.0,
     "фургон короче 15 студов: при персонаже 5.3 настоящий фургон 17–19"),
    (("Door",), "z", 7.5, "дверь ниже 7.5 студа: персонаж 5.3 должен проходить"),
)


def check(per_asset):
    """Стандарт из промпта. ERROR = модель не принимается, WARN = посмотреть."""
    out = []
    for a, objs in per_asset.items():
        if not a.startswith(PREFIXES):
            out.append(("ERROR", a, f"префикс не из {PREFIXES}"))
        if not objs:
            out.append(("ERROR", a, "пустой ассет"))
            continue
        lo, hi = bounds(objs)
        size = hi - lo
        if abs(lo.z) > 0.05:
            out.append(("WARN", a, f"низ не на z=0 (min z={lo.z:.2f}): pivot = центр низа"))
        for i, (l, h) in enumerate(((lo.x, hi.x), (lo.y, hi.y))):
            c = (l + h) / 2
            if abs(c) > max(0.25, (h - l) * 0.15):
                out.append(("WARN", a, f"центр по {'XY'[i]} смещён на {c:.2f}: pivot должен быть в точке установки (норма для столба с рукой)"))
        for ob in objs:
            t = tris_of(ob)
            if len(ob.name.split("__")) != 3:
                out.append(("ERROR", ob.name, "имя не <Ассет>__<Деталь>__<Материал>"))
            if t > 20000:
                out.append(("ERROR", ob.name, f"{t} треугольников > 20000 (лимит Roblox)"))
            elif t > 10000:
                out.append(("WARN", ob.name, f"{t} треугольников > 10000"))
            bm = bmesh.new()
            bm.from_mesh(ob.data)
            zero = sum(1 for f in bm.faces if f.calc_area() < 1e-7)
            bm.free()
            if zero:
                out.append(("WARN", ob.name, f"{zero} вырожденных граней"))
        if max(size) > 2048:
            out.append(("ERROR", a, "размер > 2048 studs"))
        if a in SIZES:
            want = SIZES[a]
            for i, ax in enumerate("XYZ"):
                if want[i] and abs(size[i] - want[i]) > want[i] * 0.05:
                    out.append(("ERROR", a, f"габарит по {ax} {size[i]:.2f}, по ТЗ {want[i]:.2f} (допуск 5 %)"))
        for keys, axis, least, msg in SCALE_RULES:
            if any(k in a for k in keys) and not (axis == "z" and "Roof" in a):
                got = size.z if axis == "z" else max(size.x, size.y)
                if got < least:
                    out.append(("WARN", a, f"{msg} (сейчас {got:.1f})"))
    return out


def render_preview(per_asset, path):
    scn = bpy.context.scene
    scn.render.engine = engine_id()
    for attr, val in (("taa_render_samples", 32), ("use_raytracing", True), ("use_shadows", True)):
        try:
            setattr(scn.eevee, attr, val)
        except Exception:
            pass
    scn.render.resolution_x, scn.render.resolution_y = RES, int(RES * 0.62)
    try:
        scn.view_settings.view_transform = "AgX"
        scn.view_settings.look = "AgX - Medium High Contrast"
    except Exception:
        pass
    world = bpy.data.worlds.new("Stage")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.22, 0.25, 0.3, 1)
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.7
    scn.world = world
    st = bpy.data.collections.new("_Stage")
    scn.collection.children.link(st)
    sun_d = bpy.data.lights.new("Key", "SUN")
    sun_d.energy, sun_d.angle, sun_d.color = 3.0, math.radians(8), (0.86, 0.92, 1.0)
    sun = bpy.data.objects.new("Key", sun_d)
    sun.rotation_euler = (math.radians(52), math.radians(8), math.radians(-35))
    st.objects.link(sun)
    gb = bmesh.new()
    bmesh.ops.create_grid(gb, x_segments=1, y_segments=1, size=4000)
    gme = bpy.data.meshes.new("Ground")
    gb.to_mesh(gme)
    gm = bpy.data.materials.new("StageGround")
    gm.use_nodes = True
    gm.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.1, 0.1, 0.11, 1)
    gme.materials.append(gm)
    g = bpy.data.objects.new("Ground", gme)
    g.location.z = -0.01
    st.objects.link(g)
    lm = bpy.data.materials.new("Label")
    lm.use_nodes = True
    lm.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.9, 0.9, 0.9, 1)
    names = [a for a, _ in ASSETS]
    per_row = max(1, math.ceil(math.sqrt(len(names) * 1.6)))
    rows = [names[i:i + per_row] for i in range(0, len(names), per_row)]
    pts = []
    y = 0.0
    for row in rows:
        bn = [bounds(per_asset[a]) for a in row]
        depth = max(hi.y - lo.y for lo, hi in bn)
        gap = max(2.5, max(hi.x - lo.x for lo, hi in bn) * 0.15)
        x = 0.0
        for a, (lo, hi) in zip(row, bn):
            off = Vector((x - lo.x, y - lo.y, 0))
            for ob in per_asset[a]:
                ob.location = off
                ob.hide_render = "__Collider__" in ob.name
            for cx in (lo.x, hi.x):
                for cy in (lo.y, hi.y):
                    for cz in (0.0, hi.z):
                        pts.append(Vector((cx, cy, cz)) + off)
            tc = bpy.data.curves.new("L_" + a, "FONT")
            tc.body = a
            tc.size = max(0.8, (hi.x - lo.x) * 0.08)
            tc.align_x = "CENTER"
            tc.materials.append(lm)
            to = bpy.data.objects.new("L_" + a, tc)
            to.location = (off.x + (lo.x + hi.x) / 2, y - tc.size * 1.8, 0.02)
            st.objects.link(to)
            pts.append(Vector(to.location))
            x += (hi.x - lo.x) + gap
        y += depth + gap * 2
    d = Vector((0.45, 1.0, -0.72)).normalized()
    rot = d.to_track_quat("-Z", "Y")
    cd = bpy.data.cameras.new("Cam")
    cd.type = "ORTHO"
    cam = bpy.data.objects.new("Cam", cd)
    st.objects.link(cam)
    scn.camera = cam
    cam.rotation_euler = rot.to_euler()
    R = rot.to_matrix()
    right, up = R @ Vector((1, 0, 0)), R @ Vector((0, 1, 0))
    xs = [p.dot(right) for p in pts]
    ys = [p.dot(up) for p in pts]
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    w, h = max(xs) - min(xs), max(ys) - min(ys)
    cd.ortho_scale = max(w, h * scn.render.resolution_x / scn.render.resolution_y) * 1.06
    cd.clip_end = 20000
    cam.location = right * cx + up * cy - d * 3000
    scn.render.filepath = path
    bpy.ops.render.render(write_still=True)
    for a in names:
        for ob in per_asset[a]:
            ob.location = (0, 0, 0)
    for ob in list(st.objects):
        bpy.data.objects.remove(ob)
    bpy.data.collections.remove(st)


def _scale_figure(coll):
    """A plain 5.3-stud person (R15 height) for the closeups: the asset's real scale."""
    bm = bm_new()
    for sx in (-0.32, 0.32):
        cyl(bm, (sx, 0, 0.0), (sx, 0, 2.5), 0.3, 0.26, 10)          # legs
    box(bm, (0, 0, 3.55), (1.7, 0.85, 2.1), r=0.25)                 # torso
    for sx in (-1.12, 1.12):
        cyl(bm, (sx, 0, 4.45), (sx, 0, 2.55), 0.25, 0.22, 10)       # arms
    ball(bm, (0, 0, FIGURE_H - 0.42), 0.42, 2)                      # head, top at 5.3
    me = bpy.data.meshes.new("_ScaleFigure")
    bm.to_mesh(me)
    bm.free()
    m = bpy.data.materials.new("_ScaleFigure")
    m.use_nodes = True
    b = m.node_tree.nodes.get("Principled BSDF")
    b.inputs["Base Color"].default_value = (0.9, 0.9, 0.92, 1)
    b.inputs["Roughness"].default_value = 0.6
    me.materials.append(m)
    for poly in me.polygons:
        poly.use_smooth = True
    ob = bpy.data.objects.new("_ScaleFigure", me)
    coll.objects.link(ob)
    return ob


def render_closeups(per_asset, path, cell=560, cols=4):
    """Каждый ассет крупно (вид 3/4 спереди-сверху, ключ + контровой свет) — лист снимков для оценки детализации."""
    scn = bpy.context.scene
    bpy.context.view_layer.update()  # the overview moved everything; refresh matrix_world
    scn.render.engine = engine_id()
    scn.render.resolution_x = scn.render.resolution_y = cell
    scn.render.film_transparent = False
    world = bpy.data.worlds.new("Close")
    world.use_nodes = True
    bg = (0.36, 0.40, 0.46, 1) if WEAR < 0.3 else (0.16, 0.18, 0.21, 1)  # clean HUB packs: daylight grey
    world.node_tree.nodes["Background"].inputs["Color"].default_value = bg
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.6
    scn.world = world
    st = bpy.data.collections.new("_Close")
    scn.collection.children.link(st)
    lights = []
    for name, kind, energy, col, rot in (
        ("Key", "SUN", 3.2, (1.0, 0.86, 0.68), (52, 8, -35)),      # тёплый, как натриевый фонарь
        ("Rim", "SUN", 2.2, (0.62, 0.74, 1.0), (60, 0, 150)),      # холодный контровой, как небо в дождь
    ):
        d = bpy.data.lights.new(name, kind)
        d.energy, d.color, d.angle = energy, col, math.radians(6)
        ob = bpy.data.objects.new(name, d)
        ob.rotation_euler = tuple(math.radians(a) for a in rot)
        st.objects.link(ob)
        lights.append(ob)
    cd = bpy.data.cameras.new("CloseCam")
    cd.type = "ORTHO"
    cam = bpy.data.objects.new("CloseCam", cd)
    st.objects.link(cam)
    scn.camera = cam
    fig = _scale_figure(st)  # a 5.3-stud person beside every asset of 3+ studs
    names = [a for a, _ in ASSETS]
    tiles = []
    for a in names:
        for b in names:
            for ob in per_asset[b]:
                ob.hide_render = (b != a) or ("__Collider__" in ob.name)
        lo, hi = bounds([ob for ob in per_asset[a] if "__Collider__" not in ob.name] or per_asset[a])
        fig.hide_render = max(hi - lo) < FIGURE_MIN
        if not fig.hide_render:
            fig.location = (hi.x + 1.4, lo.y - 0.9, 0.0)  # front-right corner, never hidden
            bpy.context.view_layer.update()
            flo, fhi = bounds([fig])
            lo, hi = Vector(map(min, lo, flo)), Vector(map(max, hi, fhi))
        d = Vector((0.55, 1.0, -0.5)).normalized()
        rot = d.to_track_quat("-Z", "Y")
        Rm = rot.to_matrix()
        right, up = Rm @ Vector((1, 0, 0)), Rm @ Vector((0, 1, 0))
        corners = [Vector((x, y, z)) for x in (lo.x, hi.x) for y in (lo.y, hi.y) for z in (lo.z, hi.z)]
        xs = [p.dot(right) for p in corners]
        ys = [p.dot(up) for p in corners]
        cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
        cd.ortho_scale = max(max(xs) - min(xs), max(ys) - min(ys)) * 1.1
        radius = (hi - lo).length
        cam.location = right * cx + up * cy - d * (radius * 3 + 10)
        cam.rotation_euler = rot.to_euler()
        cd.clip_start, cd.clip_end = 0.1, radius * 8 + 40
        tmp = os.path.join(OUT, f"_close_{a}.png")
        scn.render.filepath = tmp
        bpy.ops.render.render(write_still=True)
        img = bpy.data.images.load(tmp)
        px = np.array(img.pixels[:], dtype=np.float32).reshape(cell, cell, 4)[::-1]
        bpy.data.images.remove(img)
        os.remove(tmp)
        tiles.append(px)
    for b in names:
        for ob in per_asset[b]:
            ob.hide_render = False
    rows = math.ceil(len(tiles) / cols)
    sheet = np.zeros((rows * cell, min(cols, len(tiles)) * cell, 4), dtype=np.float32)
    sheet[..., 3] = 1
    for i, t in enumerate(tiles):
        r, k = divmod(i, cols)
        sheet[r * cell:(r + 1) * cell, k * cell:(k + 1) * cell] = t
    for ob in list(st.objects):
        bpy.data.objects.remove(ob)
    bpy.data.collections.remove(st)
    h, w = sheet.shape[:2]
    out = bpy.data.images.new("closeups", w, h, alpha=True)
    out.pixels.foreach_set(np.ascontiguousarray(sheet[::-1]).ravel())
    out.filepath_raw = path
    out.file_format = "PNG"
    out.save()
    return names


def export_fbx(per_asset, pack):
    chunks, cur = [], []
    for a, _ in ASSETS:
        if a not in per_asset:
            continue
        objs = per_asset[a]
        if cur and len(cur) + len(objs) > MAX_OBJECTS:
            chunks.append(cur)
            cur = []
        cur = cur + objs
    if cur:
        chunks.append(cur)
    files = []
    for i, objs in enumerate(chunks):
        bpy.ops.object.select_all(action="DESELECT")
        for ob in objs:
            ob.select_set(True)
        bpy.context.view_layer.objects.active = objs[0]
        suffix = chr(65 + i) if len(chunks) > 1 else ""
        path = os.path.join(OUT, f"{pack}{suffix}.fbx")
        bpy.ops.export_scene.fbx(
            filepath=path, use_selection=True, object_types={"MESH"}, use_mesh_modifiers=True,
            mesh_smooth_type="FACE", bake_anim=False, embed_textures=False, path_mode="STRIP",
            axis_forward="-Z", axis_up="Y")
        files.append((path, len(objs)))
    return files


def run(pack, preview=True, textures=True, wear="worn"):
    """Строит всё из @asset, проверяет, экспортирует. pack — имя пакета (V1, V2...).
    wear: "clean" (HUB: новое и чистое), "used" (лёгкий износ), "worn" (миссии: грязь, подтёки)."""
    global TEX_DIR, WEAR
    WEAR = WEAR_LEVELS.get(wear, 1.0)
    os.makedirs(OUT, exist_ok=True)
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    for c in list(bpy.data.collections):
        bpy.data.collections.remove(c)
    scn = bpy.context.scene
    per_asset, lines, failed = {}, [], []
    seen = set()
    for name, fn in ASSETS:
        if name in seen:
            lines.append(f"ERROR {name}: имя ассета повторяется")
            continue
        seen.add(name)
        coll = bpy.data.collections.new(name)
        scn.collection.children.link(coll)
        B = Builder(name)
        try:
            fn(B)
            bad = sorted({m for (_p, m) in B.parts if m not in MAT_DEF})
            if bad:
                raise ValueError(f"материалы не из списка: {bad}")
            per_asset[name] = B.build(coll)
        except Exception as e:  # один сломанный ассет не роняет пакет
            import traceback
            failed.append(name)
            lines.append(f"ERROR {name} build: {e!r}")
            traceback.print_exc()
    ASSETS[:] = [(a, f) for a, f in ASSETS if per_asset.get(a)]
    bpy.context.view_layer.update()
    used = sorted({ob.name.split("__")[-1] for objs in per_asset.values() for ob in objs})
    if textures:
        TEX_DIR = os.path.join(OUT, "tex")
        labels = sorted({ob.data.materials[0].name for objs in per_asset.values() for ob in objs})
        for label in labels:
            base, _, lvl = label.partition("~")
            hook_textures(base, make_textures(base, label, int(lvl) / 10 if lvl else None), label)
    for a, objs in per_asset.items():
        lo, hi = bounds(objs)
        s = hi - lo
        tris = sum(tris_of(ob) for ob in objs)
        mats = sorted({ob.name.split("__")[-1] for ob in objs})
        coll = any("__Collider__" in ob.name for ob in objs)
        lines.append(f"REPORT {a} tris={tris} size={s.x:.2f}x{s.y:.2f}x{s.z:.2f} objects={len(objs)} "
                     f"mats={','.join(mats)} collider={'yes' if coll else 'no'}")
    game_assets = {a: o for a, o in per_asset.items() if a not in RENDER_ONLY}
    for level, who, msg in check(game_assets):
        lines.append(f"CHECK {level} {who}: {msg}")
    if wear not in WEAR_LEVELS:
        lines.append(f"CHECK ERROR {pack}: wear={wear!r}, нужно clean, used или worn")
    lines.append(f"WEAR {wear}")
    for path, n in (export_fbx(game_assets, pack) if game_assets else []):
        lines.append(f"FBX {path} objects={n}")
    if textures and used:
        lines.append(f"TEX {TEX_DIR} materials={','.join(used)}")
    if preview and per_asset:
        p = os.path.join(OUT, "preview.png")
        render_preview(per_asset, p)
        lines.append(f"PREVIEW {p}")
        cp = os.path.join(OUT, "closeups.png")
        order = render_closeups(per_asset, cp)
        lines.append(f"CLOSEUPS {cp} order={','.join(order)}")
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT, f"{pack}.blend"))
    if ANIM:
        import json
        for a, parts in ANIM.items():
            for part, info in parts.items():
                if info["anim"] in ("spin", "swing") and not info["pivot"]:
                    lines.append(f"CHECK ERROR {a}__{part}: anim {info['anim']} needs a pivot")
                extra = "".join(f" {k}={info[k]}" for k in ("dist", "angle", "period", "phase") if k in info)
                lines.append(f"ANIM {a}__{part} {info['anim']} pivot={info['pivot']} axis={info['axis']}{extra}")
        with open(os.path.join(OUT, "anim.json"), "w", encoding="utf-8") as fh:
            json.dump(ANIM, fh, ensure_ascii=False, indent=1)
    import json as _json
    for fname, data, tag in (("markers.json", MARKS, "MARK"), ("lights.json", LIGHTS, "LIGHT")):
        if data:
            for a, items in data.items():
                for n, info in items.items():
                    kind = f" kind={info['kind']}" if "kind" in info else ""
                    lines.append(f"{tag} {a}.{n} pos={info['pos']}{kind}")
            with open(os.path.join(OUT, fname), "w", encoding="utf-8") as fh:
                _json.dump(data, fh, ensure_ascii=False, indent=1)
    for req in SHOTS:
        try:
            lines.append(_render_shot(per_asset, **req))
        except Exception as e:  # a failed shot never fails the pack
            import traceback
            tb = traceback.format_exc().strip().splitlines()
            lines.append(f"ERROR shot {req.get('name')}: {e!r} at {tb[-3].strip() if len(tb) > 2 else ''}")
    lines.extend(UI_LINES)
    if UI_PNGS:
        sheet = os.path.join(OUT, "ui_sheet.png")
        try:
            _ui_sheet(sheet)
            lines.append(f"UISHEET {sheet} pngs={len(UI_PNGS)}")
        except Exception as e:
            lines.append(f"ERROR ui_sheet: {e!r}")
    errors = sum(1 for line in lines if line.startswith(("ERROR", "CHECK ERROR")))
    lines.append(f"DONE {pack} assets={len(per_asset)} failed={len(failed)} errors={errors} "
                 f"time={time.time() - T0:.0f}s")
    text = "\n".join(lines)
    with open(os.path.join(OUT, "report.txt"), "w", encoding="utf-8") as fh:
        fh.write(text + "\n")
    print(text, flush=True)


def shot(name, items, cam, look, size=(1920, 1080), sun=(6, 235), lens=35, ground="Concrete",
         ground_size=400, haze=0.35, transparent=False, only=None, sky="golden", dof=None,
         tiles=None, bleed=8):
    """A rendered scene (loading screen, menu background), drawn at the end of run().
    items: [(asset, (x, y, z), yaw_degrees), ...]; asset is from this script or
    "V1a/HB_LampPost" (pack/asset of an already built pack). cam, look: camera and target
    points (studs). sun: (elevation, azimuth) in degrees. Saved as out/<pack>/<name>.png."""
    # transparent: no sky and ground (front parallax layers); only: refs of `items` to draw;
    # sky: "golden" (warm evening) | "rain_dusk" (blue rainy dusk, wet mirror ground);
    # dof: (focus distance, f-stop); tiles: (cols, rows) -> <name>_r<R>c<C>.png, each <= 1024.
    SHOTS.append(dict(name=name, items=items, cam=cam, look=look, size=size, sun=sun, lens=lens,
                      ground=ground, ground_size=ground_size, haze=haze, transparent=transparent,
                      only=only, sky=sky, dof=dof, tiles=tiles, bleed=bleed))


def _collection_for(ref):
    """'V1a/HB_LampPost' -> that asset's collection from out/V1a/V1a.blend (loaded once);
    'HB_Bench' -> this script's own asset."""
    if "/" not in ref:
        coll = bpy.data.collections.get(ref)
        if coll is None:
            raise KeyError(f"no asset {ref}")
        return coll
    pack, a = ref.split("/", 1)
    have = bpy.data.collections.get(a)
    if have:
        return have
    path = os.path.join(os.path.dirname(OUT), pack, pack + ".blend")
    if not os.path.exists(path):
        raise FileNotFoundError(f"pack {pack} not built ({path})")
    with bpy.data.libraries.load(path, link=False) as (src, dst):
        if a not in src.collections:
            raise KeyError(f"pack {pack} has no {a}")
        dst.collections = [a]
    return bpy.data.collections[a]


def _render_shot(per_asset, name, items, cam, look, size, sun, lens, ground, ground_size, haze,
                 transparent=False, only=None, sky="golden", dof=None, tiles=None, bleed=8):
    sky_mode = sky
    rain = sky_mode == "rain_dusk"
    scn = bpy.context.scene
    scn.render.engine = engine_id()
    for attr, val in (("taa_render_samples", 64), ("use_raytracing", True), ("use_shadows", True)):
        try:
            setattr(scn.eevee, attr, val)
        except Exception:
            pass
    scn.render.resolution_x, scn.render.resolution_y = size
    try:
        scn.view_settings.view_transform = "AgX"
        scn.view_settings.look = "AgX - Medium High Contrast"
    except Exception:
        pass
    # Sources stay at the origin, out of the render; instances place them.
    sources = [_collection_for(ref) for ref, _, _ in items]
    for a in per_asset:
        lc = bpy.context.view_layer.layer_collection.children.get(a)
        if lc is not None:
            lc.exclude = True
    for coll in sources:
        for ob in coll.all_objects:
            if ob is not None:
                ob.hide_render = "__Collider__" in ob.name
    st = bpy.data.collections.new("_Shot_" + name)
    scn.collection.children.link(st)
    world = bpy.data.worlds.new("Sunset")
    world.use_nodes = True
    nt = world.node_tree
    bg = nt.nodes["Background"]
    try:
        sky = nt.nodes.new("ShaderNodeTexSky")
        for kind in ("NISHITA", "MULTIPLE_SCATTERING", "SINGLE_SCATTERING"):
            try:
                sky.sky_type = kind
                break
            except Exception:
                continue
        for attr, val in (("sun_elevation", math.radians(sun[0])), ("sun_rotation", math.radians(sun[1])),
                          ("air_density", 1.0 + haze * 2), ("dust_density", 1.0 + haze * 6)):
            try:
                setattr(sky, attr, val)
            except Exception:
                pass
        nt.links.new(sky.outputs["Color"], bg.inputs["Color"])
        bg.inputs["Strength"].default_value = 0.22
    except Exception:
        bg.inputs["Color"].default_value = (0.9, 0.62, 0.38, 1)
        bg.inputs["Strength"].default_value = 0.6
    scn.world = world
    sd = bpy.data.lights.new("Sun", "SUN")
    sd.energy, sd.angle, sd.color = 6.5, math.radians(2.5), (1.0, 0.66, 0.38)  # golden hour
    so_rot = None
    if rain:  # blue rainy dusk: cool sky fill, a soft moon key; lamps and neon glow on top
        for link in list(bg.inputs["Color"].links):
            nt.links.remove(link)
        bg.inputs["Color"].default_value = (0.07, 0.1, 0.19, 1)
        bg.inputs["Strength"].default_value = 1.4
        sd.energy, sd.color, sd.angle = 1.6, (0.6, 0.7, 1.0), math.radians(8)
        so_rot = (math.radians(58), 0, math.radians(sun[1]))
    so = bpy.data.objects.new("Sun", sd)
    so.rotation_euler = so_rot or (math.radians(90 - sun[0]), 0, math.radians(sun[1]))
    st.objects.link(so)
    gb = bmesh.new()
    bmesh.ops.create_grid(gb, x_segments=1, y_segments=1, size=ground_size / 2)
    gme = bpy.data.meshes.new("ShotGround")
    gb.to_mesh(gme)
    gb.free()
    uv = gme.uv_layers.new(name="UVMap")
    for poly in gme.polygons:
        for li in poly.loop_indices:
            co = gme.vertices[gme.loops[li].vertex_index].co
            uv.data[li].uv = (co.x / TILE, co.y / TILE)
    if rain:  # wet street: dark mirror that picks up every lamp
        gm = bpy.data.materials.new("WetShotGround")
        gm.use_nodes = True
        gpb = gm.node_tree.nodes.get("Principled BSDF")
        gpb.inputs["Base Color"].default_value = (0.03, 0.032, 0.038, 1)
        gpb.inputs["Roughness"].default_value = 0.07
        gme.materials.append(gm)
    else:
        gme.materials.append(mat(ground if ground in MAT_DEF else "Concrete"))
    gob = bpy.data.objects.new("ShotGround", gme)
    gob.hide_render = bool(transparent)
    st.objects.link(gob)
    for (ref, pos, yaw), coll in zip(items, sources):
        inst = bpy.data.objects.new("I_" + ref.replace("/", "_"), None)
        inst.instance_type = "COLLECTION"
        inst.instance_collection = coll
        inst.location = pos
        inst.rotation_euler = (0, 0, math.radians(yaw))
        inst.hide_render = bool(only) and ref not in only
        st.objects.link(inst)
    # loaded pack collections are not in the scene; instancing works without linking them
    cd = bpy.data.cameras.new("ShotCam")
    cd.lens = lens
    cd.clip_end = 5000
    camo = bpy.data.objects.new("ShotCam", cd)
    camo.location = cam
    camo.rotation_euler = (Vector(look) - Vector(cam)).to_track_quat("-Z", "Y").to_euler()
    st.objects.link(camo)
    scn.camera = camo
    if dof:
        cd.dof.use_dof = True
        cd.dof.focus_distance, cd.dof.aperture_fstop = float(dof[0]), float(dof[1])
    scn.render.film_transparent = bool(transparent)
    # Hero glass: dark and reflective (the closeup dust pattern reads as a wall from afar).
    for m in bpy.data.materials:
        if m.name.split(".")[0] in ("Glass", "DirtyGlass", "DustyGlass", "BoardGlass") and m.use_nodes:
            b = m.node_tree.nodes.get("Principled BSDF")
            if b:
                for link in list(b.inputs["Base Color"].links):
                    m.node_tree.links.remove(link)
                b.inputs["Base Color"].default_value = (0.02, 0.03, 0.04, 1)
                for link in list(b.inputs["Roughness"].links):
                    m.node_tree.links.remove(link)
                b.inputs["Roughness"].default_value = 0.06
                for link in list(b.inputs["Alpha"].links):
                    m.node_tree.links.remove(link)
                b.inputs["Alpha"].default_value = 1.0
                try:
                    m.surface_render_method = "DITHERED"
                except Exception:
                    pass
    path = os.path.join(OUT, name + ".png")
    scn.render.filepath = path
    bpy.ops.render.render(write_still=True)
    scn.render.film_transparent = False
    for a in per_asset:
        lc = bpy.context.view_layer.layer_collection.children.get(a)
        if lc is not None:
            lc.exclude = False
    for ob in list(st.objects):
        bpy.data.objects.remove(ob)
    bpy.data.collections.remove(st)
    line = f"SHOT {path} {size[0]}x{size[1]} items={len(items)} sky={sky_mode}"
    if tiles:
        img = bpy.data.images.load(path)
        W, H = size
        px = np.array(img.pixels[:], dtype=np.float32).reshape(H, W, 4)[::-1]
        bpy.data.images.remove(img)
        cols, rows = tiles
        tw, th = W // cols, H // rows
        for r in range(rows):
            for c in range(cols):
                x0, y0 = max(0, c * tw - bleed), max(0, r * th - bleed)
                x1, y1 = min(W, (c + 1) * tw + bleed), min(H, (r + 1) * th + bleed)
                _ui_save(f"{name}_r{r}c{c}", px[y0:y1, x0:x1].copy(), kind="TILE")
        line += f" tiles={cols}x{rows} bleed={bleed}"
    elif max(size) > 1024:
        line += " (CHECK WARN: больше 1024 — для игры нужен tiles=(3, 2))"
    return line


def png(name, rgba):
    """Сохраняет картинку numpy (H, W, 4), значения 0..1, строка 0 = верх, в out/<пакет>/<name>.png."""
    rgba = np.asarray(rgba, dtype=np.float32)
    h, w = rgba.shape[:2]
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, name + ".png")
    img = bpy.data.images.new(name, w, h, alpha=True)
    img.pixels.foreach_set(np.ascontiguousarray(rgba[::-1]).ravel())
    img.filepath_raw = path
    img.file_format = "PNG"
    img.save()
    print(f"PNG {path} {w}x{h}", flush=True)
    return path



# ================================================================== UI (17.11)
# 2D canvas with signed distance fields, 3D -> PNG icons, text3d, a UI sheet.
# Brief: 3_UI_HUD_МЕНЮ.md §3. Coordinates are pixels of the FINAL image, y down;
# drawing happens at ss x resolution and is averaged down in C.png().

UI_LINES = []  # PNG / CHECK lines for report.txt
UI_PNGS = []  # (name, rgba) for ui_sheet.png
RENDER_ONLY = set()  # @asset(render_only=True): no FBX, no checks


def _col(c):
    """'#RRGGBB' | '#RRGGBBAA' | (r, g, b) | (r, g, b, a), 0..255 -> float RGBA 0..1."""
    if isinstance(c, str):
        h = c.lstrip("#")
        v = [int(h[i:i + 2], 16) for i in range(0, len(h), 2)]
    else:
        v = list(c)
    if len(v) == 3:
        v.append(255)
    return np.array(v, dtype=np.float32) / 255.0


def _box_blur_1d(a, r, axis):
    if r < 1:
        return a
    pad = [(0, 0)] * a.ndim
    pad[axis] = (r + 1, r)
    c = np.cumsum(np.pad(a, pad, mode="edge"), axis=axis)
    hi = np.take(c, range(2 * r + 1, c.shape[axis]), axis=axis)
    lo = np.take(c, range(0, c.shape[axis] - 2 * r - 1), axis=axis)
    return (hi - lo) / (2 * r + 1)


def _gauss(a, sigma):
    """Fast gaussian-like blur (three box passes) of a 2D or 3D (H, W, C) array."""
    if sigma <= 0.3:
        return a
    r = max(1, int(round(sigma * 0.87)))
    for _ in range(3):
        a = _box_blur_1d(_box_blur_1d(a, r, 0), r, 1)
    return a


def _down(a, k):
    if k == 1:
        return a
    h, w = a.shape[0] // k, a.shape[1] // k
    return a[:h * k, :w * k].reshape(h, k, w, k, *a.shape[2:]).mean(axis=(1, 3))


def _up(a, k):
    return a if k == 1 else np.repeat(np.repeat(a, k, axis=0), k, axis=1)


class Canvas:
    """C = canvas(w, h, ss=4). C.x, C.y: pixel-centre coordinate grids (final pixels)."""

    def __init__(self, w, h, ss=4):
        self.w, self.h, self.ss = int(w), int(h), int(ss)
        H, W = self.h * self.ss, self.w * self.ss
        self.x = (np.arange(W, dtype=np.float32)[None, :] + 0.5) / self.ss
        self.y = (np.arange(H, dtype=np.float32)[:, None] + 0.5) / self.ss
        self.x = np.broadcast_to(self.x, (H, W))
        self.y = np.broadcast_to(self.y, (H, W))
        self.buf = np.zeros((H, W, 4), dtype=np.float32)  # premultiplied

    def _src(self, col):
        if isinstance(col, np.ndarray) and col.ndim == 3:
            return col.astype(np.float32)
        return _col(col)[None, None, :]

    def over(self, col, mask, alpha=1.0):
        """Paints colour or gradient `col` through mask 0..1 on top."""
        src = self._src(col)
        a = np.clip(mask, 0, 1)[..., None] * float(alpha) * src[..., 3:4]
        pre = np.concatenate([src[..., :3] * a, a], axis=-1)
        self.buf = pre + self.buf * (1 - a)
        return self

    def under(self, col, mask, alpha=1.0):
        """Paints behind what is already there (outlines, backplates)."""
        src = self._src(col)
        a = np.clip(mask, 0, 1)[..., None] * float(alpha) * src[..., 3:4]
        pre = np.concatenate([src[..., :3] * a, a], axis=-1)
        self.buf = self.buf + pre * (1 - self.buf[..., 3:4])
        return self

    def _soft(self, mask, blur, dx=0.0, dy=0.0):
        m = _down(np.clip(mask, 0, 1), self.ss)
        if dx or dy:
            m = np.roll(m, (int(round(dy)), int(round(dx))), axis=(0, 1))
        return np.clip(_up(_gauss(m, blur), self.ss), 0, 1)

    def shadow(self, mask, blur=8, dx=0, dy=4, col="#12284A", alpha=0.25):
        """Soft drop shadow of `mask` (draw it before the shape)."""
        return self.over(col, self._soft(mask, blur, dx, dy), alpha)

    def glow(self, mask, blur=10, col="#8DEBE3", alpha=0.5):
        """Soft halo around `mask`."""
        return self.over(col, self._soft(mask, blur), alpha)

    def paste(self, img, x, y, scale=1.0):
        """Pastes a straight-alpha numpy image (h, w, 4) with its top-left at (x, y)."""
        img = np.asarray(img, dtype=np.float32)
        if scale != 1.0:
            h, w = img.shape[:2]
            nh, nw = max(1, int(round(h * scale))), max(1, int(round(w * scale)))
            ys = np.clip(((np.arange(nh) + 0.5) / scale).astype(int), 0, h - 1)
            xs = np.clip(((np.arange(nw) + 0.5) / scale).astype(int), 0, w - 1)
            img = img[ys][:, xs]
        big = _up(img, self.ss)
        H, W = self.buf.shape[:2]
        x0, y0 = int(round(x * self.ss)), int(round(y * self.ss))
        sx0, sy0 = max(0, -x0), max(0, -y0)
        x1, y1 = min(W, x0 + big.shape[1]), min(H, y0 + big.shape[0])
        if x1 <= max(x0, 0) or y1 <= max(y0, 0):
            return self
        part = big[sy0:sy0 + (y1 - max(y0, 0)), sx0:sx0 + (x1 - max(x0, 0))]
        a = part[..., 3:4]
        region = self.buf[max(y0, 0):y1, max(x0, 0):x1]
        self.buf[max(y0, 0):y1, max(x0, 0):x1] = np.concatenate([part[..., :3] * a, a], -1) + region * (1 - a)
        return self

    def image(self):
        """The final straight-alpha image (h, w, 4), colour bled under transparent pixels."""
        pre = _down(self.buf, self.ss)
        a = pre[..., 3:4]
        rgb = np.where(a > 1e-4, pre[..., :3] / np.maximum(a, 1e-4), 0)
        # Bleed colour into transparent pixels: no dark fringes when the game scales it.
        known = (a[..., 0] > 0.01).astype(np.float32)
        if known.any() and known.min() == 0:
            col, wgt = rgb * known[..., None], known
            for s in (1, 2, 4, 8, 16, 32):
                bc, bw = _gauss(col, s), _gauss(wgt, s)
                fillc = bc / np.maximum(bw, 1e-6)[..., None]
                miss = (known < 0.5) & (bw > 1e-4)
                rgb = np.where(miss[..., None], fillc, rgb)
                known = np.maximum(known, miss.astype(np.float32))
        return np.concatenate([np.clip(rgb, 0, 1), np.clip(a, 0, 1)], -1)

    def png(self, name, slice=None):
        img = self.image()
        _ui_save(name, img, slice)
        return img


def canvas(w, h, ss=4):
    return Canvas(w, h, ss)


def _ui_save(name, img, slice=None, kind="PNG"):
    h, w = img.shape[:2]
    a = img[..., 3]
    cover = float((a > 0.02).mean())
    edge = max(a[0].max(), a[-1].max(), a[:, 0].max(), a[:, -1].max())
    png(name, img)
    UI_PNGS.append((name, img))
    sl = f" slice={tuple(slice)}" if slice else ""
    UI_LINES.append(f"{kind} {name} {w}x{h} alpha={cover:.2f}{sl}")
    if max(w, h) > 1024:
        UI_LINES.append(f"CHECK ERROR {name}: сторона {max(w, h)} > 1024 (лимит Roblox)")
    if edge > 0.03 and cover < 0.98:
        UI_LINES.append(f"CHECK WARN {name}: непрозрачные пиксели у края ({edge:.2f}) — свечение или обводка обрезаны")
    if slice:
        l, t, r, b = slice
        if not (0 < l < r < w and 0 < t < b < h):
            UI_LINES.append(f"CHECK ERROR {name}: slice {slice} вне картинки {w}x{h}")


# --- signed distances (pixels; negative inside)
def sd_circle(C, cx, cy, r):
    return np.hypot(C.x - cx, C.y - cy) - r


def sd_rrect(C, cx, cy, w, h, r):
    r = min(r, w / 2, h / 2)
    qx = np.abs(C.x - cx) - (w / 2 - r)
    qy = np.abs(C.y - cy) - (h / 2 - r)
    out = np.hypot(np.maximum(qx, 0), np.maximum(qy, 0))
    return out + np.minimum(np.maximum(qx, qy), 0) - r


def sd_seg(C, x0, y0, x1, y1):
    px, py = C.x - x0, C.y - y0
    dx, dy = x1 - x0, y1 - y0
    t = np.clip((px * dx + py * dy) / max(dx * dx + dy * dy, 1e-9), 0, 1)
    return np.hypot(px - dx * t, py - dy * t)


def sd_arc(C, cx, cy, r, a0, a1):
    """Distance to an arc; degrees, 0 = right, counter-clockwise (screen up)."""
    ang = np.degrees(np.arctan2(-(C.y - cy), C.x - cx)) % 360
    lo, span = a0 % 360, (a1 - a0) % 360 or 360
    inside = ((ang - lo) % 360) <= span
    d_ring = np.abs(np.hypot(C.x - cx, C.y - cy) - r)
    ends = []
    for a in (a0, a1):
        ex, ey = cx + r * math.cos(math.radians(a)), cy - r * math.sin(math.radians(a))
        ends.append(np.hypot(C.x - ex, C.y - ey))
    return np.where(inside, d_ring, np.minimum(*ends))


def sd_poly(C, pts):
    pts = [(float(x), float(y)) for x, y in pts]
    d = None
    sign = np.ones_like(C.x)
    n = len(pts)
    for i in range(n):
        x0, y0 = pts[i]
        x1, y1 = pts[(i + 1) % n]
        seg = sd_seg(C, x0, y0, x1, y1)
        d = seg if d is None else np.minimum(d, seg)
        cond = ((C.y >= y0) != (C.y >= y1)) & (C.x < (x1 - x0) * (C.y - y0) / ((y1 - y0) or 1e-9) + x0)
        sign = np.where(cond, -sign, sign)
    return d * sign


def sd_union(a, b):
    return np.minimum(a, b)


def sd_sub(a, b):
    return np.maximum(a, -b)


def sd_round(d, r):
    return d - r


def fill(C, d):
    """Antialiased 0..1 mask of the inside of d."""
    return np.clip(0.5 - d * C.ss, 0, 1)


def stroke(C, d, w):
    """Antialiased line of width w px along the contour of d."""
    return np.clip(0.5 - (np.abs(d) - w / 2) * C.ss, 0, 1)


def lin_grad(C, p0, p1, c0, c1):
    (x0, y0), (x1, y1) = p0, p1
    dx, dy = x1 - x0, y1 - y0
    t = np.clip(((C.x - x0) * dx + (C.y - y0) * dy) / max(dx * dx + dy * dy, 1e-9), 0, 1)[..., None]
    return _col(c0)[None, None] * (1 - t) + _col(c1)[None, None] * t


def rad_grad(C, cx, cy, r, c0, c1):
    t = np.clip(np.hypot(C.x - cx, C.y - cy) / max(r, 1e-9), 0, 1)[..., None]
    return _col(c0)[None, None] * (1 - t) + _col(c1)[None, None] * t


def noise(w, h, sigmas=(32, 16, 8, 4), seed=7):
    """Seamless fbm 0..1 of any size."""
    rng = np.random.default_rng(seed)
    fy, fx = np.fft.fftfreq(h)[:, None], np.fft.fftfreq(w)[None, :]
    out = np.zeros((h, w))
    for i, s in enumerate(sigmas):
        k = np.exp(-2 * (math.pi * s) ** 2 * (fy ** 2 + fx ** 2))
        layer = np.real(np.fft.ifft2(np.fft.fft2(rng.standard_normal((h, w))) * k))
        out += norm01(layer) / (i + 1) ** 0.9
    return norm01(out).astype(np.float32)


# --- 3D -> PNG
def _temp_asset(ref):
    """(collection, objects, cleanup) for an asset of this script or 'Pack/Asset'."""
    if "/" in ref:
        coll = _collection_for(ref)
        objs = [o for o in coll.all_objects if "__Collider__" not in o.name]
        return coll, objs, lambda: None
    fns = dict(ASSETS)
    if ref not in fns:
        raise KeyError(f"нет ассета {ref}: объяви @asset выше вызова icon()")
    coll = bpy.data.collections.new("_icon_" + ref)
    bpy.context.scene.collection.children.link(coll)
    B = Builder(ref)
    fns[ref](B)
    objs = [o for o in B.build(coll) if "__Collider__" not in o.name]

    def cleanup():
        for o in list(coll.objects):
            bpy.data.objects.remove(o)
        bpy.data.collections.remove(coll)
    return coll, objs, cleanup


def _icon_render(src, size, view, fill_, style, tilt):
    scn = bpy.context.scene
    coll, objs, cleanup = _temp_asset(src)
    hidden = []
    for ob in bpy.data.objects:
        if ob not in objs and not ob.hide_render and ob.type in ("MESH", "EMPTY", "CURVE", "FONT"):
            ob.hide_render = True
            hidden.append(ob)
    st = bpy.data.collections.new("_iconrig")
    scn.collection.children.link(st)
    try:
        if view == "icon":
            yaw, pitch = -35.0, 22.0
        elif view == "front":
            yaw, pitch = 0.0, 0.0
        else:
            yaw, pitch = view
        # Camera looks along d (from front-left-above towards the model, face -Y).
        d = (Matrix.Rotation(math.radians(yaw), 3, "Z") @ Matrix.Rotation(math.radians(-pitch), 3, "X")
             @ Vector((0, 1, 0))).normalized()
        rot = d.to_track_quat("-Z", "Y")
        if tilt:
            rot = rot @ Euler((0, 0, math.radians(tilt))).to_quaternion()
        Rm = rot.to_matrix()
        right, up = Rm @ Vector((1, 0, 0)), Rm @ Vector((0, 1, 0))
        pts = [ob.matrix_world @ Vector(c) for ob in objs for c in ob.bound_box]
        xs, ys = [p.dot(right) for p in pts], [p.dot(up) for p in pts]
        cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
        extent = max(max(xs) - min(xs), max(ys) - min(ys))
        lo, hi = bounds(objs)
        radius = (hi - lo).length + 1
        cd = bpy.data.cameras.new("IconCam")
        cd.type = "ORTHO"
        cd.ortho_scale = extent / max(fill_, 0.1)
        cam = bpy.data.objects.new("IconCam", cd)
        cam.location = right * cx + up * cy - d * radius * 3
        cam.rotation_euler = rot.to_euler()
        cd.clip_start, cd.clip_end = 0.01, radius * 8
        st.objects.link(cam)
        scn.camera = cam
        world = bpy.data.worlds.new("IconWorld")
        world.use_nodes = True
        wb = world.node_tree.nodes["Background"]
        wb.inputs["Color"].default_value = (0.8, 0.84, 0.9, 1)
        wb.inputs["Strength"].default_value = 0.55 if style != "flat" else 1.0
        scn.world = world
        scn.render.film_transparent = True
        scn.render.resolution_x = scn.render.resolution_y = size * 2
        try:
            scn.view_settings.view_transform = "Standard"
            scn.view_settings.look = "None"
        except Exception:
            pass
        if style == "flat":
            scn.render.engine = "BLENDER_WORKBENCH"
            scn.display.shading.light = "FLAT"
            scn.display.shading.color_type = "MATERIAL"
        else:
            scn.render.engine = engine_id()
            for attr, val in (("taa_render_samples", 48), ("use_shadows", True)):
                try:
                    setattr(scn.eevee, attr, val)
                except Exception:
                    pass
            # Studio: warm key upper left, cool fill right, white rim from behind.
            for nm, energy, col, ang in (("Key", 4.0, (1.0, 0.93, 0.84), (50, 0, -40)),
                                         ("Fill", 1.6, (0.78, 0.86, 1.0), (60, 0, 70)),
                                         ("Rim", 3.0, (1.0, 1.0, 1.0), (-55, 0, 180))):
                ld = bpy.data.lights.new(nm, "SUN")
                ld.energy, ld.color, ld.angle = energy, col, math.radians(8)
                lo_ = bpy.data.objects.new(nm, ld)
                lo_.rotation_euler = tuple(math.radians(a) for a in ang)
                st.objects.link(lo_)
        tmp = os.path.join(OUT, "_icon_tmp.png")
        scn.render.filepath = tmp
        os.makedirs(OUT, exist_ok=True)
        bpy.ops.render.render(write_still=True)
        img = bpy.data.images.load(tmp)
        n = size * 2
        px = np.array(img.pixels[:], dtype=np.float32).reshape(n, n, 4)[::-1].copy()
        bpy.data.images.remove(img)
        os.remove(tmp)
        return px
    finally:
        for ob in hidden:
            ob.hide_render = False
        for ob in list(st.objects):
            bpy.data.objects.remove(ob)
        bpy.data.collections.remove(st)
        cleanup()
        scn.render.film_transparent = False


def _dilate(a, r):
    out = a.copy()
    rr = int(math.ceil(r))
    for dy in range(-rr, rr + 1):
        for dx in range(-rr, rr + 1):
            if dx * dx + dy * dy <= r * r:
                out = np.maximum(out, np.roll(a, (dy, dx), axis=(0, 1)))
    return out


def icon_img(name, src=None, size=256, view="icon", outline=6, fill=0.78, style="studio",
             glow=None, tilt=0, outline_col="#12284A"):
    """Renders 3D asset `src` (this script or 'Pack/Asset') to a straight-alpha numpy icon."""
    src = src or name
    px = _icon_render(src, size, view, fill, style, tilt)  # 2x
    a = px[..., 3]
    rgba = px
    if outline:
        ring = _gauss(_dilate((a > 0.5).astype(np.float32), outline * 2), 1.0)
        oc = _col(outline_col)
        base = np.zeros_like(px)
        base[..., :3] = oc[:3]
        base[..., 3] = np.clip(ring, 0, 1) * oc[3]
        # render over the outline
        pa = px[..., 3:4]
        rgb = px[..., :3] * pa + base[..., :3] * base[..., 3:4] * (1 - pa)
        aa = pa + base[..., 3:4] * (1 - pa)
        rgba = np.concatenate([rgb / np.maximum(aa, 1e-4), aa], -1)
    if glow:
        gc = _col(glow)
        halo = _gauss(rgba[..., 3], size * 0.06) * 0.6 * gc[3]
        pa = rgba[..., 3:4]
        rgb = rgba[..., :3] * pa + gc[:3][None, None] * halo[..., None] * (1 - pa)
        aa = pa + halo[..., None] * (1 - pa)
        rgba = np.concatenate([rgb / np.maximum(aa, 1e-4), aa], -1)
    pre = np.concatenate([rgba[..., :3] * rgba[..., 3:4], rgba[..., 3:4]], -1)
    pre = _down(pre, 2)
    a = pre[..., 3:4]
    rgb = np.where(a > 1e-4, pre[..., :3] / np.maximum(a, 1e-4), 0)
    return np.concatenate([np.clip(rgb, 0, 1), np.clip(a, 0, 1)], -1).astype(np.float32)


def icon(name, src=None, size=256, view="icon", outline=6, fill=0.78, style="studio", glow=None,
         tilt=0, outline_col="#12284A"):
    """Renders 3D asset `src` to PNG `name` (size x size, transparent)."""
    try:
        img = icon_img(name, src, size, view, outline, fill, style, glow, tilt, outline_col)
    except Exception as e:  # one broken icon never stops the pack
        UI_LINES.append(f"ERROR icon {name}: {e!r}")
        return None
    C = Canvas(size, size, 1)
    C.paste(img, 0, 0)
    _ui_save(name, C.image())
    return img


def text3d(bm, text, size=1.0, depth=0.3, bevel=0.03, weight=0.0, track=0.0, align="CENTER",
           at=(0, 0, 0)):
    """Letters in the XZ plane, face -Y, baseline on z = at.z, depth along Y. Merged into bm."""
    cu = bpy.data.curves.new("_txt", "FONT")
    cu.body = text
    font_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Inter-Bold.ttf")
    if os.path.exists(font_path):
        try:
            cu.font = bpy.data.fonts.load(font_path, check_existing=True)
        except Exception:
            pass
    cu.size = size
    cu.extrude = depth / 2
    cu.bevel_depth = bevel
    cu.offset = weight
    cu.space_character = 1.0 + track
    cu.align_x = align
    ob = bpy.data.objects.new("_txt", cu)
    bpy.context.scene.collection.objects.link(ob)
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
    tmp = bmesh.new()
    tmp.from_mesh(me)
    M = T(*at) @ Matrix.Rotation(math.radians(90), 4, "X")
    bmesh.ops.transform(tmp, matrix=M, verts=tmp.verts)
    bpy.data.objects.remove(ob)
    bpy.data.curves.remove(cu)
    bpy.data.meshes.remove(me)
    return merge(bm, tmp)


def _ui_sheet(path):
    """Every PNG of the pack on light glass, dark glass and a checker, plus a 32 px copy."""
    if not UI_PNGS:
        return
    cell = 160
    rows = len(UI_PNGS)
    sheet = np.ones((rows * cell, cell * 4, 4), dtype=np.float32)
    bgs = [np.array([0.90, 0.93, 0.97]), np.array([0.10, 0.14, 0.20])]
    yy, xx = np.mgrid[0:cell, 0:cell]
    checker = np.where(((yy // 10) + (xx // 10)) % 2 == 0, 0.75, 0.55)[..., None] * np.ones(3)
    for i, (_n, img) in enumerate(UI_PNGS):
        h, w = img.shape[:2]
        k = min((cell - 16) / w, (cell - 16) / h)
        ys = np.clip(((np.arange(int(h * k)) + 0.5) / k).astype(int), 0, h - 1)
        xs = np.clip(((np.arange(int(w * k)) + 0.5) / k).astype(int), 0, w - 1)
        small = img[ys][:, xs]
        sh, sw = small.shape[:2]
        tiny_k = 32 / max(w, h)
        ty = np.clip(((np.arange(max(1, int(h * tiny_k))) + 0.5) / tiny_k).astype(int), 0, h - 1)
        tx = np.clip(((np.arange(max(1, int(w * tiny_k))) + 0.5) / tiny_k).astype(int), 0, w - 1)
        tiny = img[ty][:, tx]
        for j, bg in enumerate([bgs[0], bgs[1], None, bgs[0]]):
            tile = np.zeros((cell, cell, 3)) + (checker if bg is None else bg)
            src = tiny if j == 3 else small
            ph, pw = src.shape[:2]
            oy, ox = (cell - ph) // 2, (cell - pw) // 2
            a = src[..., 3:4]
            tile[oy:oy + ph, ox:ox + pw] = src[..., :3] * a + tile[oy:oy + ph, ox:ox + pw] * (1 - a)
            sheet[i * cell:(i + 1) * cell, j * cell:(j + 1) * cell, :3] = tile
    h, w = sheet.shape[:2]
    out = bpy.data.images.new("ui_sheet", w, h, alpha=True)
    out.pixels.foreach_set(np.ascontiguousarray(sheet[::-1]).ravel())
    out.filepath_raw = path
    out.file_format = "PNG"
    out.save()


__all__ = ["box", "cyl", "ball", "lathe", "torus", "sweep", "prism", "leg", "T", "euler", "bm_new",
           "merge", "xf", "Rng", "asset", "run", "png", "shot", "fbm", "blur", "norm01", "scratches", "specks",
           "MAT_DEF", "Matrix", "Vector", "math", "np",
           "rrect", "arcpts", "soften", "displace", "mirror_x", "blur2", "emblem",
           "canvas", "Canvas", "sd_circle", "sd_rrect", "sd_seg", "sd_arc", "sd_poly", "sd_union",
           "sd_sub", "sd_round", "fill", "stroke", "lin_grad", "rad_grad", "noise", "icon", "icon_img",
           "text3d"]
