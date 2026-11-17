# build_R1.py — рабочая основа магазина 2.0 (Claude, 17.11): собирается без ошибок.
# Оси: X — ширина, Y — глубина (лицо в −Y), Z — высота. box(bm, центр, (X, Y, Z), r=фаска).
from cc_kit import *


def emb(B, c, d, depth=0.08, badge="BrandNavy"):
    """Эмблема бренда; одинаковые имена деталей -> склеиваются в один объект."""
    E = emblem(c, d, depth, face="-Y")
    B.add("Emblem_badge", badge, E["badge"])
    B.add("Emblem_drop", "BrandTeal", E["drop"])
    B.add("Emblem_bubble", "SafetyOrange", E["bubble"])
    B.add("Emblem_spark", "NeonWhite", E["spark"])


# ------------------------------------------------------------------ фасад
# Плоскость стены y = 0 (внутренняя сторона), пилоны выступают до y = -2.1,
# козырёк выносом до y = -6.3.
@asset("HB_Store_Front", size=(28, 6.4, 17.2))
def store_front(B):
    B.add("Plinth", "LightConcrete", box(bm_new(), (0, -1.3, 0.6), (28, 1.6, 1.2), r=0.06))
    for x in (-13.5, -4.6, 4.6, 13.5):
        B.add("Pillar", "Facade", box(bm_new(), (x, -1.3, 7.0), (1.0, 1.6, 14.0), r=0.1))

    # витрины: нижняя панель, стекло, импосты, транец, эмблема на уровне глаз
    for s in (-1, 1):
        x = s * 9.05
        B.add("WinPanel", "BrandNavy", box(bm_new(), (x, -1.3, 0.9), (7.9, 0.3, 0.6)))
        B.add("WinGlass", "ClearGlass", box(bm_new(), (x, -1.0, 5.6), (7.9, 0.12, 8.8)))
        B.add("Impost", "Facade", box(bm_new(), (x, -1.05, 8.0), (7.9, 0.3, 0.18)))
        emb(B, (x, -1.07, 5.0), 1.4)
    for x in (-13.0, -5.1, 5.1, 13.0):
        B.add("Impost", "Facade", box(bm_new(), (x, -1.05, 5.6), (0.18, 0.3, 8.8)))

    # портал из трёх брусьев: проём 8.2 × 9.4 открыт
    for x in (-4.5, 4.5):
        B.add("Portal", "BrandNavy", box(bm_new(), (x, -1.65, 4.7), (0.8, 0.9, 9.4), r=0.08))
    B.add("Portal", "BrandNavy", box(bm_new(), (0, -1.65, 9.8), (9.8, 0.9, 0.8), r=0.08))

    # раздвижные двери
    for s, name in ((-1, "L"), (1, "R")):
        x = s * 2.05
        B.add("DoorSlide" + name, "Facade", box(bm_new(), (x, -1.3, 4.5), (4.1, 0.25, 9.0), r=0.05),
              anim="slide", axis="X", dist=s * 3.8)
        B.add("DoorGlass" + name, "ClearGlass", box(bm_new(), (x, -1.3, 4.6), (3.6, 0.27, 8.4)),
              anim="slide", axis="X", dist=s * 3.8)
        B.add("DoorBar" + name, "Chrome", cyl(bm_new(), (s * 0.4, -1.5, 2.6), (s * 0.4, -1.5, 6.1), 0.08),
              anim="slide", axis="X", dist=s * 3.8)
    B.add("Gadget", "DarkPlastic", box(bm_new(), (0, -2.15, 9.2), (0.8, 0.3, 0.4), r=0.04))
    B.add("SensorLed", "NeonWhite", box(bm_new(), (0, -2.33, 9.2), (0.1, 0.05, 0.1)), anim="blink")
    B.add("EntryRug", "DarkPlastic", box(bm_new(), (0, -3.4, 0.015), (7, 2.4, 0.03), r=0.01))

    # козырёк 14 × 4.2 × 0.7, низ на z 10.6, вынос от пилонов
    B.add("Canopy", "BrandWhite", box(bm_new(), (0, -4.2, 10.95), (14, 4.2, 0.7), r=0.2))
    for i in range(24):
        B.add("SoffitSlat", "Cedar", box(bm_new(), (-6.33 + i * 0.55, -4.2, 10.56), (0.3, 4.0, 0.08)))
    for i in range(6):
        x = -5.25 + i * 2.1
        B.add("Downlight", "LightEmit", cyl(bm_new(), (x, -4.2, 10.5), (x, -4.2, 10.54), 0.25))
    B.add("CanopyNeon", "NeonOrange", box(bm_new(), (0, -6.28, 10.66), (13.6, 0.08, 0.08)))
    for x in (-5, 5):
        B.add("TieRod", "Chrome", sweep(bm_new(), [(x, -6.0, 11.3), (x, -2.1, 15.0)], 0.06))

    # венец вывески 20 × 0.8 × 3.6 на z 12.4–16.0, эмблема и панель под название
    B.add("SignCrown", "BrandNavy", prism(bm_new(), rrect(20, 3.6, 0.3, cz=14.2), -2.1, -1.3))
    emb(B, (-7.0, -2.11, 14.2), 3.0, depth=0.3, badge="BrandWhite")
    B.add("SignBand", "BrandWhite", box(bm_new(), (3.0, -2.15, 14.2), (12, 0.08, 1.4), r=0.04))
    tube = [(x, -1.95, z) for x, z in rrect(20.2, 3.8, 0.3, cz=14.2)]
    B.add("CrownNeon", "NeonOrange", sweep(bm_new(), tube + [tube[0]], 0.06), anim="blink")
    B.mark("StoreSign", (3.0, -2.2, 14.2), dir=(0, -1, 0))

    # стена над витринами: подложка и плиты с зазором
    B.add("WallBacking", "Powder", box(bm_new(), (0, -0.6, 11.2), (26.0, 0.4, 5.6)))
    for row in range(2):
        for col in range(7):
            B.add("WallPanel", "BrandWhite",
                  box(bm_new(), (-10.2 + col * 3.4, -0.85, 9.4 + row * 2.06), (3.34, 0.12, 2.0), r=0.06))

    B.add("Parapet", "Facade", box(bm_new(), (0, -1.0, 16.4), (28.0, 2.0, 0.8), r=0.05))
    B.add("DripEdge", "SteelMetal", box(bm_new(), (0, -2.05, 16.75), (28.0, 0.15, 0.3), r=0.02))

    # вазоны с гранёными кустами у входа
    for s in (-1, 1):
        x = s * 6.6
        B.add("PlanterBox", "LightConcrete", box(bm_new(), (x, -2.9, 0.7), (3.0, 1.4, 1.4), r=0.08))
        for k, mat in enumerate(("Leaf", "LeafDark", "LeafLight")):
            B.add("Leaves", mat, ball(bm_new(), (x + (k - 1) * 0.8, -2.9, 1.7 + k * 0.15), 0.6 - k * 0.1,
                                      subd=1, sx=1.2, sy=1.0, sz=0.8),
                  flat=True, anim="sway", pivot=(x, -2.9, 1.4), axis="Z")

    # мелочь
    for s in (-1, 1):
        B.add("Sconce", "Facade", cyl(bm_new(), (s * 13.5, -2.2, 11.6), (s * 13.5, -2.2, 12.4), 0.18))
        B.add("SconceGlow", "LightEmit", cyl(bm_new(), (s * 13.5, -2.2, 12.4), (s * 13.5, -2.2, 12.5), 0.14))
    B.add("Gadget", "DarkPlastic", ball(bm_new(), (-4.0, -2.25, 9.2), 0.2, subd=2))
    B.add("Gadget", "DarkPlastic", box(bm_new(), (5.4, -2.15, 3.5), (0.3, 0.1, 0.5), r=0.02))
    B.add("Sconce", "Facade", box(bm_new(), (-5.4, -2.15, 3.5), (0.8, 0.1, 0.4), r=0.02))

    # коллайдер: цоколь, пилоны, венец, стёкла; проём входа свободен
    B.add("Collider", "Plastic", box(bm_new(), (0, -1.3, 0.6), (28, 1.6, 1.2)))
    for x in (-13.5, -4.6, 4.6, 13.5):
        B.add("Collider", "Plastic", box(bm_new(), (x, -1.3, 7.0), (1.0, 1.6, 14.0)))
    B.add("Collider", "Plastic", box(bm_new(), (0, -1.7, 14.2), (20, 0.8, 3.6)))
    for s in (-1, 1):
        B.add("Collider", "Plastic", box(bm_new(), (s * 9.05, -1.0, 5.6), (7.9, 0.12, 8.8)))
    B.mark("DoorCenter", (0, -1.3, 0))


# ------------------------------------------------------------------ боковая стена
@asset("HB_Store_Side", size=(20, 2.5, 15.2))
def store_side(B):
    B.add("WallBase", "Powder", box(bm_new(), (0, 0, 7.0), (20, 0.6, 14.0)))
    for row in range(3):
        for col in range(5):
            if row == 2 and 1 <= col <= 3:
                continue  # здесь фрамуга
            B.add("WallPanel", "BrandWhite",
                  box(bm_new(), (-8.0 + col * 4.0, -0.38, 2.0 + row * 4.0), (3.94, 0.16, 3.94), r=0.06))
    B.add("Plinth", "LightConcrete", box(bm_new(), (0, -0.05, 0.3), (20, 0.7, 0.6), r=0.06))
    B.add("Parapet", "Facade", box(bm_new(), (0, 0, 14.8), (20, 0.8, 0.8), r=0.05))

    # каналы с неоновой линией на концах
    for s, name in ((-1, "StripeL"), (1, "StripeR")):
        B.add("Channel", "Facade", box(bm_new(), (s * 9.5, -0.45, 7.0), (1.0, 0.3, 13.6), r=0.05))
        B.add(name, "NeonOrange", box(bm_new(), (s * 9.5, -0.62, 7.0), (0.3, 0.06, 12.0)), anim="blink")

    # ленточная фрамуга в раме
    B.add("TransomFrame", "Facade", box(bm_new(), (0, -0.4, 10.0), (12.2, 0.2, 2.0), r=0.04))
    B.add("TransomGlass", "TintGlass", box(bm_new(), (0, -0.52, 10.0), (11.8, 0.08, 1.6)))
    for i in range(5):
        B.add("Mullion", "Facade", box(bm_new(), (-4.8 + i * 2.4, -0.6, 10.0), (0.12, 0.12, 1.6)))

    # служебная дверь
    B.add("ServiceFrame", "Facade", box(bm_new(), (-6.0, -0.4, 4.2), (4.4, 0.25, 8.4), r=0.05))
    B.add("ServiceDoor", "BrandNavy", box(bm_new(), (-6.0, -0.55, 4.0), (4.0, 0.12, 8.0), r=0.04))
    B.add("ServiceHandle", "Chrome", box(bm_new(), (-4.6, -0.65, 3.6), (0.1, 0.1, 1.0), r=0.03))
    B.add("ServiceCanopy", "BrandWhite", box(bm_new(), (-6.0, -1.1, 8.7), (5.0, 1.6, 0.3), r=0.04))
    B.add("ServiceBulb", "LightEmit", cyl(bm_new(), (-6.0, -1.1, 8.5), (-6.0, -1.1, 8.55), 0.15))

    # кондиционеры снаружи на площадках, вентиляторы крутятся
    for s, fan in ((-1, "FanA"), (1, "FanB")):
        x = 3.0 + s * 2.2
        B.add("ACPad", "LightConcrete", box(bm_new(), (x, -1.3, 0.2), (2.0, 1.6, 0.4), r=0.05))
        B.add("ACUnit", "BrandWhite", box(bm_new(), (x, -1.3, 1.3), (1.8, 1.2, 1.8), r=0.08))
        B.add("ACGrille", "DarkPlastic", torus(bm_new(), (x, -1.92, 1.3), 0.55, 0.05, m=euler(90, 0, 0)))
        B.add(fan, "SteelMetal", cyl(bm_new(), (x, -1.95, 1.3), (x, -1.9, 1.3), 0.5),
              anim="spin", axis="Y", pivot=(x, -1.92, 1.3))
        B.add("PipeInsul", "Rubber", sweep(bm_new(), [(x + 0.7, -0.7, 1.8), (x + 0.7, -0.5, 1.8), (x + 0.7, -0.5, 3.0)], 0.1))

    # водосток с отводом
    B.add("Downpipe", "Facade", cyl(bm_new(), (8.6, -0.5, 0.9), (8.6, -0.5, 14.6), 0.18))
    B.add("Downpipe", "Facade", sweep(bm_new(), [(8.6, -0.5, 0.9), (8.6, -0.8, 0.3)], 0.18))

    emb(B, (0, -0.47, 6.0), 3.0, depth=0.1)
    for x in (-2.0, 7.0):
        B.add("VentGrille", "Facade", box(bm_new(), (x, -0.4, 0.95), (1.0, 0.2, 0.5), r=0.02))
    B.add("Collider", "Plastic", box(bm_new(), (0, 0, 7.6), (20, 0.6, 15.2)))


# ------------------------------------------------------------------ задняя стена с погрузкой
@asset("HB_Store_Back", size=(28, 3.0, 15.2))
def store_back(B):
    B.add("WallBase", "Powder", box(bm_new(), (0, 0, 7.0), (28, 0.6, 14.0)))
    for row in range(3):
        for col in range(7):
            if col == 3 and row < 2:
                continue  # здесь ворота
            B.add("WallPanel", "BrandWhite",
                  box(bm_new(), (-12.0 + col * 4.0, -0.38, 2.0 + row * 4.0), (3.94, 0.16, 3.94), r=0.06))
    B.add("Plinth", "LightConcrete", box(bm_new(), (0, -0.05, 0.3), (28, 0.7, 0.6), r=0.06))
    B.add("Parapet", "Facade", box(bm_new(), (0, 0, 14.8), (28, 0.8, 0.8), r=0.05))

    # роллета 9 × 9 (ламели внутри одной детали), направляющие, короб
    sh = bm_new()
    for i in range(26):
        box(sh, (0, -0.45, 0.6 + i * 0.34), (9.0, 0.12, 0.3), r=0.03)
    B.add("Shutter", "BrandWhite", sh, anim="slide", axis="Z", dist=8)
    for s in (-1, 1):
        B.add("ShutterGuide", "Facade", box(bm_new(), (s * 4.65, -0.5, 4.75), (0.3, 0.3, 9.3)))
    B.add("ShutterBox", "Facade", box(bm_new(), (0, -0.6, 9.75), (9.6, 0.6, 0.8), r=0.05))

    # погрузочная зона
    B.add("LoadRamp", "LightConcrete", box(bm_new(), (0, -1.4, 0.15), (9.6, 2.2, 0.3), r=0.04))
    B.add("RampEdge", "SafetyOrange", box(bm_new(), (0, -2.45, 0.32), (9.6, 0.15, 0.05)))
    for s in (-1, 1):
        B.add("Bumper", "Rubber", box(bm_new(), (s * 4.0, -0.65, 1.0), (0.6, 0.3, 1.2), r=0.05))
        B.add("Post", "PowderCoat", cyl(bm_new(), (s * 5.4, -2.2, 0.0), (s * 5.4, -2.2, 3.5), 0.15))
        B.add("PostBand", "SafetyOrange", cyl(bm_new(), (s * 5.4, -2.2, 2.85), (s * 5.4, -2.2, 3.15), 0.16))
        B.add("GateLamp", "Facade", box(bm_new(), (s * 3.0, -0.6, 10.6), (0.6, 0.5, 0.4), r=0.05))
        B.add("GateLampGlow", "LightEmit", box(bm_new(), (s * 3.0, -0.7, 10.38), (0.5, 0.3, 0.06)))
    for i, x in enumerate((-9.0, 9.0, 13.0)):
        B.add("WallLampA", "Facade", box(bm_new(), (x, -0.45, 10.0), (0.5, 0.3, 1.0), r=0.05))
        B.add("LampGlowA", "LightEmit", box(bm_new(), (x, -0.62, 10.0), (0.36, 0.06, 0.8)), anim="blink")

    # служебная дверь, водостоки, щит с молнией, решётки
    B.add("ServiceFrame", "Facade", box(bm_new(), (-10.0, -0.4, 4.2), (4.4, 0.25, 8.4), r=0.05))
    B.add("ServiceDoor", "BrandNavy", box(bm_new(), (-10.0, -0.55, 4.0), (4.0, 0.12, 8.0), r=0.04))
    for x in (-13.0, 13.0):
        B.add("Downpipe", "Facade", cyl(bm_new(), (x, -0.5, 0.0), (x, -0.5, 14.6), 0.18))
    B.add("ElecBox", "BrandWhite", box(bm_new(), (10.0, -0.5, 3.0), (2.0, 0.3, 3.0), r=0.05))
    bolt = [(10.1, 3.9), (9.6, 2.9), (10.0, 2.9), (9.8, 2.1), (10.4, 3.1), (10.0, 3.1)]
    B.add("LightningPicto", "BrandNavy", prism(bm_new(), bolt, -0.72, -0.65))
    for x in (-5.5, 6.0):
        B.add("VentGrille", "Facade", box(bm_new(), (x, -0.4, 0.95), (1.0, 0.2, 0.5), r=0.02))
    B.add("Collider", "Plastic", box(bm_new(), (0, 0, 7.6), (28, 0.6, 15.2)))
    B.add("Collider", "Plastic", box(bm_new(), (0, -1.4, 0.15), (9.6, 2.2, 0.3)))


# ------------------------------------------------------------------ крыша (pivot — низ потолка, ставится на 13.4)
@asset("HB_Store_Roof", size=(28, 20, 4.6))
def store_roof(B):
    B.add("CeilingSlab", "BrandWhite", box(bm_new(), (0, 0, 0.3), (27.4, 19.4, 0.6), r=0.05))
    # светильники вровень с потолком (видны изнутри)
    for i in range(3):
        y = -6.0 + i * 6.0
        B.add("LightBox", "Facade", box(bm_new(), (0, y, 0.0), (22, 0.6, 0.08), r=0.02))
        B.add("LightStrip", "LightEmit", box(bm_new(), (0, y, -0.03), (21.6, 0.3, 0.04)))
    for i in range(6):
        x = -10.0 + i * 4.0
        B.add("Downlight", "LightEmit", cyl(bm_new(), (x, -8.0, -0.04), (x, -8.0, 0.0), 0.25))
    for i in range(4):
        x = -6.0 + i * 4.0
        B.add("Diffuser", "Facade", box(bm_new(), (x, 4.0, 0.0), (1.5, 1.5, 0.08), r=0.03))
        B.add("DiffuserCore", "LightEmit", box(bm_new(), (x, 4.0, -0.03), (1.1, 1.1, 0.04)))
    for i in range(8):  # акустические рейки над кассой
        B.add("AcousticSlat", "Cedar", box(bm_new(), (9.0, 2.0 + i * 0.6, -0.02), (6.0, 0.2, 0.04)))

    # кровля
    B.add("RoofMembrane", "LightConcrete", box(bm_new(), (0, 0, 1.2), (27.4, 19.4, 1.2), r=0.1))
    for fan, x, y in (("FanA", -6.0, -4.0), ("FanB", 6.0, 4.0)):
        B.add("HVACUnit", "BrandWhite", box(bm_new(), (x, y, 2.9), (4, 3, 2.2), r=0.08))
        B.add("HVACGrille", "DarkPlastic", torus(bm_new(), (x, y, 4.02), 0.7, 0.06))
        B.add(fan, "SteelMetal", cyl(bm_new(), (x, y, 3.98), (x, y, 4.04), 0.65),
              anim="spin", axis="Z", pivot=(x, y, 4.0))
    B.add("DuctRun", "Facade", box(bm_new(), (0, 0, 2.3), (10, 1.0, 1.0), r=0.05))
    B.add("SkylightFrame", "Facade", box(bm_new(), (0, 6.0, 1.9), (6.2, 4.2, 0.2), r=0.05))
    B.add("SkylightGlass", "ClearGlass", lathe(bm_new(), [(2.6, 0.0), (0.05, 1.2)], 4,
                                                m=T(0, 6.0, 2.0) @ euler(0, 0, 45)))
    for i in range(8):
        x = -10.5 + (i % 4) * 3.6
        y = -8.0 + (i // 4) * 2.4
        B.add("SunPanel", "TintGlass", xf(box(bm_new(), (0, 0, 0), (3.2, 1.8, 0.1), r=0.02),
                                         T(x, y, 2.6) @ euler(15, 0, 0)))
        B.add("PanelStand", "PowderCoat", box(bm_new(), (x, y, 2.15), (0.2, 0.2, 0.7)))
    B.add("CableTray", "Facade", box(bm_new(), (0, 8.5, 1.95), (20, 0.5, 0.3), r=0.02))
    B.add("RoofHatch", "BrandWhite", box(bm_new(), (10.0, 8.0, 1.9), (2.0, 2.0, 0.2), r=0.05))
    B.add("LightningRod", "Chrome", cyl(bm_new(), (12.0, 8.0, 1.8), (12.0, 8.0, 4.5), 0.05))
    B.add("Collider", "Plastic", box(bm_new(), (0, 0, 0.9), (27.4, 19.4, 1.8)))


run("R1", wear="clean")
