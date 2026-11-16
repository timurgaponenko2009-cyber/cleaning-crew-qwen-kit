# build_EXAMPLE.py — эталон уровня детализации для Qwen (Claude, 16.11.2026).
# Приёмы: слои формы (база → вторичные формы → мелочь), фаски на всех видимых рёбрах,
# помощники для повторов, износ геометрией (потёки, ржавые края, наклейки), Rng с seed,
# детали врезаны в основу на 0.02–0.04 (нет копланарных граней), коллайдер отдельно.
from cc_kit import *

R = Rng(1611)


# ------------------------------------------------------------ помощники
def bolt(bm, p, axis="y", r=0.045, head=0.03):
    """Шестигранная головка болта на поверхности; axis — нормаль поверхности (знак = наружу)."""
    x, y, z = p
    sgn = -1 if axis.startswith("-") else 1
    a = axis[-1]
    if a == "y":
        return cyl(bm, (x, y, z), (x, y + sgn * head, z), r, r, 6)
    if a == "x":
        return cyl(bm, (x, y, z), (x + sgn * head, y, z), r, r, 6)
    return cyl(bm, (x, y, z), (x, y, z + sgn * head), r, r, 6)


def streaks(bm, x0, x1, y, z_top, n, length=(0.3, 1.1), w=(0.05, 0.12)):
    """Потёки ржавчины/грязи вниз по вертикальной грани (плоскость y, лицо −Y)."""
    for _ in range(n):
        x = R(x0, x1)
        ln = R(*length)
        box(bm, (x, y, z_top - ln / 2), (R(*w), 0.02, ln), r=0.008)
    return bm


def hazard_band(B, part, cx, y, z, width, height, stripes=9):
    """Оранжевая полоса с тёмными диагоналями (лицо −Y)."""
    B.add(part, "SafetyOrange", box(bm_new(), (cx, y, z), (width, 0.05, height), r=0.015))
    dk = bm_new()
    step = width / stripes
    for i in range(stripes):
        x = cx - width / 2 + step * (i + 0.5)
        box(dk, (x, y - 0.03, z), (step * 0.34, 0.02, height * 1.25), rot=(0, 45, 0))
    # диагонали обрезаем по высоте полосы: короткие бруски уже не выходят за край
    B.add(part + "Stripes", "DarkPlastic", dk)


# ------------------------------------------------------------ контейнер
@asset("HB_Dumpster")
def dumpster(B):
    W, D = 6.2, 3.4           # корпус
    z0, H = 1.05, 3.0         # низ корпуса, высота
    zc = z0 + H / 2
    fy = -D / 2               # передняя грань

    B.add("Body", "CarPaint", box(bm_new(), (0, 0, zc), (W, D, H), r=0.07, seg=3))
    # рёбра жёсткости спереди и сзади
    ribs = bm_new()
    for x in (-2.4, -1.2, 0.0, 1.2, 2.4):
        for s in (-1, 1):
            box(ribs, (x, s * (D / 2 + 0.03), zc), (0.2, 0.12, H - 0.25), r=0.04)
    for s in (-1, 1):  # горизонтальный пояс по бокам
        box(ribs, (s * (W / 2 + 0.03), 0, zc + 0.6), (0.12, D - 0.3, 0.22), r=0.04)
    B.add("Ribs", "CarPaint", ribs)
    # верхний обод и рама основания
    B.add("Rim", "OldMetal", box(bm_new(), (0, 0, z0 + H + 0.06), (W + 0.2, D + 0.2, 0.16), r=0.05))
    B.add("BaseFrame", "RustMetal", box(bm_new(), (0, 0, z0 - 0.1), (W - 0.2, D - 0.2, 0.24), r=0.04))
    # карманы под вилы погрузчика
    pk = bm_new()
    for s in (-1, 1):
        box(pk, (s * (W / 2 + 0.12), 0, zc + 0.15), (0.26, 1.0, 0.62), r=0.04)
    B.add("ForkPocket", "OldMetal", pk)
    holes = bm_new()
    for s in (-1, 1):
        box(holes, (s * (W / 2 + 0.24), 0, zc + 0.15), (0.04, 0.8, 0.44))
    B.add("ForkHole", "DarkPlastic", holes)
    # колёса на поворотных кронштейнах
    wh, br = bm_new(), bm_new()
    for sx in (-1, 1):
        for sy in (-1, 1):
            x, y = sx * (W / 2 - 0.55), sy * (D / 2 - 0.5)
            cyl(wh, (x - 0.1, y, 0.3), (x + 0.1, y, 0.3), 0.3, 0.3, 18)
            box(br, (x, y, 0.62), (0.34, 0.34, 0.06), r=0.015)
            for s in (-1, 1):
                box(br, (x + s * 0.15, y, 0.47), (0.04, 0.14, 0.36), r=0.01)
            cyl(br, (x - 0.17, y, 0.3), (x + 0.17, y, 0.3), 0.06, 0.06, 8)
            cyl(br, (x, y, 0.65), (x, y, 0.85), 0.07, 0.07, 10)
    B.add("Wheel", "Rubber", wh)
    B.add("Caster", "OldMetal", br)
    # крышки: левая закрыта, правая приоткрыта и подпирает мешок
    zt = z0 + H + 0.16
    B.add("LidL", "DarkPlastic", box(bm_new(), (-W / 4, 0.05, zt + 0.12), (W / 2 - 0.05, D + 0.3, 0.14),
                                      r=0.05, rot=(-4, 0, 0)))
    lid = bm_new()
    box(lid, (0, 0, 0), (W / 2 - 0.05, D + 0.3, 0.14), r=0.05)
    for x in (-0.9, 0.0, 0.9):
        box(lid, (x, 0, 0.09), (0.12, D + 0.1, 0.08), r=0.03)
    xf(lid, T(W / 4, D / 2 + 0.15, zt + 0.1) @ euler(-28, 0, 0) @ T(0, -(D + 0.3) / 2, 0))
    B.add("LidR", "DarkPlastic", lid)
    hinge = bm_new()
    for s in (-1, 1):
        cyl(hinge, (s * W / 2 - s * 0.2 - 0.6, D / 2 + 0.12, zt + 0.05),
            (s * W / 2 - s * 0.2 + 0.6, D / 2 + 0.12, zt + 0.05), 0.07, 0.07, 10)
    B.add("Hinge", "OldMetal", hinge)
    bag = bm_new()
    ball(bag, (W / 4, -0.3, zt + 0.35), 0.9, 2, 1.1, 0.9, 0.55)
    ball(bag, (W / 4 + 0.35, -0.55, zt + 0.75), 0.25, 1, 1.0, 0.8, 1.4)   # завязка
    B.add("TrashBag", "DarkPlastic", bag)
    # износ и разметка спереди
    hazard_band(B, "Hazard", 0, fy - 0.03, z0 + 0.45, W - 0.6, 0.34)
    B.add("RustEdge", "RustMetal", box(bm_new(), (0, fy - 0.005, z0 + 0.08), (W - 0.1, 0.04, 0.16), r=0.01))
    B.add("RustStreak", "RustMetal", streaks(bm_new(), -2.9, 2.9, fy - 0.02, z0 + H - 0.1, 11))
    B.add("Notice", "Paper", box(bm_new(), (-1.8, fy - 0.07, zc + 0.4), (0.8, 0.02, 0.56), r=0.01,
                                  rot=(0, 4, 0)))
    bl = bm_new()
    for x in (-2.95, 2.95):
        for z in (z0 + 0.3, z0 + H - 0.3):
            bolt(bl, (x, fy - 0.01, z), "-y")
    B.add("Bolts", "OldMetal", bl)
    B.add("DrainPlug", "Brass", cyl(bm_new(), (W / 2 - 0.01, 1.0, z0 + 0.2), (W / 2 + 0.1, 1.0, z0 + 0.2),
                                     0.09, 0.09, 8))
    B.add("Collider", "Plastic", box(bm_new(), (0, 0, (z0 + H + 0.3) / 2), (W + 0.4, D + 0.4, z0 + H + 0.3)))


# ------------------------------------------------------------ фонарь
@asset("HB_LampPost")
def lamp_post(B):
    # основание
    B.add("BasePlate", "RustMetal", box(bm_new(), (0, 0, 0.07), (1.5, 1.5, 0.14), r=0.04))
    nuts = bm_new()
    for sx in (-1, 1):
        for sy in (-1, 1):
            cyl(nuts, (sx * 0.55, sy * 0.55, 0.13), (sx * 0.55, sy * 0.55, 0.26), 0.09, 0.09, 6)
            cyl(nuts, (sx * 0.55, sy * 0.55, 0.26), (sx * 0.55, sy * 0.55, 0.36), 0.04, 0.04, 8)
    B.add("Nuts", "OldMetal", nuts)
    B.add("Flare", "Paint", lathe(bm_new(), [(0.52, 0.13), (0.5, 0.3), (0.42, 0.62), (0.32, 1.0),
                                              (0.3, 1.3)], 24))
    # ствол, сужение кверху
    B.add("Pole", "Paint", cyl(bm_new(), (0, 0, 1.28), (0, 0, 16.9), 0.3, 0.19, 24))
    B.add("RustBand", "RustMetal", cyl(bm_new(), (0, 0, 1.25), (0, 0, 1.6), 0.315, 0.31, 24))
    B.add("Reflector", "SafetyOrange", cyl(bm_new(), (0, 0, 2.6), (0, 0, 3.2), 0.31, 0.305, 24))
    # люк обслуживания с винтами
    B.add("Hatch", "Paint", box(bm_new(), (0, -0.3, 2.0), (0.32, 0.07, 0.8), r=0.03))
    sc = bm_new()
    for z in (1.68, 2.32):
        bolt(sc, (0, -0.335, z), "-y", r=0.03, head=0.02)
    B.add("HatchScrews", "Chrome", sc)
    # обрывки объявлений
    paper = bm_new()
    for z, rz in ((4.2, 0), (4.9, 12), (5.3, -20)):
        a = math.radians(rz)
        box(paper, (0.27 * math.sin(a), -0.27 * math.cos(a), z), (0.42, 0.015, R(0.3, 0.55)), r=0.005,
            rot=(0, R(-8, 8), rz))
    B.add("Flyers", "Paper", paper)
    # кабель-канал вдоль ствола и в фонарь
    B.add("Conduit", "OldMetal", sweep(bm_new(), [(0.33, 0, 0.14), (0.32, 0, 6.0), (0.26, 0, 12.0),
                                                 (0.22, 0, 16.4), (0.6, 0, 17.3)], 0.045, 8))
    clamps = bm_new()
    for z in (2.0, 5.0, 8.0, 11.0, 14.0):
        rr = 0.3 - (0.11 * (z - 1.28) / 15.6)
        torus(clamps, (0, 0, z), rr + 0.02, 0.03, segs=24, ring=6)
    B.add("Clamps", "OldMetal", clamps)
    # кронштейн с подкосом
    B.add("Arm", "Paint", sweep(bm_new(), [(0, 0, 16.6), (0.3, 0, 17.3), (1.2, 0, 17.8), (3.1, 0, 18.0)],
                                0.11, 12))
    B.add("Brace", "Paint", sweep(bm_new(), [(0, 0, 15.7), (0.8, 0, 16.6), (1.9, 0, 17.7)], 0.06, 8))
    B.add("Cap", "Paint", ball(bm_new(), (0, 0, 16.95), 0.21, 2, 1, 1, 0.6))
    # голова: корпус, рёбра охлаждения, рассеиватель
    head = bm_new()
    box(head, (3.5, 0, 17.95), (1.9, 0.82, 0.3), r=0.1, seg=3)
    box(head, (3.4, 0, 18.15), (1.5, 0.6, 0.14), r=0.06)
    B.add("Head", "DarkPlastic", head)
    fins = bm_new()
    for i in range(7):
        box(fins, (2.9 + i * 0.2, 0, 18.26), (0.05, 0.56, 0.1), r=0.01)
    B.add("Fins", "OldMetal", fins)
    B.add("Lens_Glow", "LightEmit", box(bm_new(), (3.55, 0, 17.79), (1.5, 0.58, 0.04), r=0.02))
    B.add("Collider", "Plastic", box(bm_new(), (0, 0, 8.5), (0.7, 0.7, 17)))


run("EXAMPLE")
