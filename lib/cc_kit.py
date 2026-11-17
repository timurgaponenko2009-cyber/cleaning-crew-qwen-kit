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


def asset(name, size=None):
    """Декоратор: @asset("HB_Lamp") над функцией f(B), которая вызывает B.add(part, material, bmesh).
    size=(ширина X, глубина Y, высота Z) из ТЗ: отклонение больше 5 % по любой оси — CHECK ERROR."""
    def wrap(fn):
        if size:
            SIZES[name] = tuple(size)
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
            if any(k in a for k in keys):
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
    for level, who, msg in check(per_asset):
        lines.append(f"CHECK {level} {who}: {msg}")
    if wear not in WEAR_LEVELS:
        lines.append(f"CHECK ERROR {pack}: wear={wear!r}, нужно clean, used или worn")
    lines.append(f"WEAR {wear}")
    for path, n in (export_fbx(per_asset, pack) if per_asset else []):
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
    errors = sum(1 for line in lines if line.startswith(("ERROR", "CHECK ERROR")))
    lines.append(f"DONE {pack} assets={len(per_asset)} failed={len(failed)} errors={errors} "
                 f"time={time.time() - T0:.0f}s")
    text = "\n".join(lines)
    with open(os.path.join(OUT, "report.txt"), "w", encoding="utf-8") as fh:
        fh.write(text + "\n")
    print(text, flush=True)


def shot(name, items, cam, look, size=(1920, 1080), sun=(6, 235), lens=35, ground="Concrete",
         ground_size=400, haze=0.35):
    """A rendered scene (loading screen, menu background), drawn at the end of run().
    items: [(asset, (x, y, z), yaw_degrees), ...]; asset is from this script or
    "V1a/HB_LampPost" (pack/asset of an already built pack). cam, look: camera and target
    points (studs). sun: (elevation, azimuth) in degrees. Saved as out/<pack>/<name>.png."""
    SHOTS.append(dict(name=name, items=items, cam=cam, look=look, size=size, sun=sun, lens=lens,
                      ground=ground, ground_size=ground_size, haze=haze))


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


def _render_shot(per_asset, name, items, cam, look, size, sun, lens, ground, ground_size, haze):
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
    so = bpy.data.objects.new("Sun", sd)
    so.rotation_euler = (math.radians(90 - sun[0]), 0, math.radians(sun[1]))
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
    gme.materials.append(mat(ground if ground in MAT_DEF else "Concrete"))
    st.objects.link(bpy.data.objects.new("ShotGround", gme))
    for (ref, pos, yaw), coll in zip(items, sources):
        inst = bpy.data.objects.new("I_" + ref.replace("/", "_"), None)
        inst.instance_type = "COLLECTION"
        inst.instance_collection = coll
        inst.location = pos
        inst.rotation_euler = (0, 0, math.radians(yaw))
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
    for a in per_asset:
        lc = bpy.context.view_layer.layer_collection.children.get(a)
        if lc is not None:
            lc.exclude = False
    for ob in list(st.objects):
        bpy.data.objects.remove(ob)
    bpy.data.collections.remove(st)
    return f"SHOT {path} {size[0]}x{size[1]} items={len(items)}"


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


__all__ = ["box", "cyl", "ball", "lathe", "torus", "sweep", "prism", "leg", "T", "euler", "bm_new",
           "merge", "xf", "Rng", "asset", "run", "png", "shot", "fbm", "blur", "norm01", "scratches", "specks",
           "MAT_DEF", "Matrix", "Vector", "math", "np",
           "rrect", "arcpts", "soften", "displace", "mirror_x", "blur2", "emblem"]
