Отчёт запуска V1a: DONE V1a assets=12 failed=0 errors=0 time=30s

REPORT HB_LampPost tris=5444 size=5.20x1.51x18.01 objects=30 collider=yes
REPORT HB_LampPostDouble tris=6696 size=7.90x1.51x18.06 objects=33 collider=yes
REPORT HB_Bollard tris=678 size=0.70x0.70x2.30 objects=10 collider=yes
REPORT HB_SteamGrate tris=1892 size=4.00x4.00x0.93 objects=9 collider=yes
REPORT HB_DrainCover tris=1130 size=2.00x2.00x0.17 objects=9 collider=yes
REPORT HB_Barrier tris=1640 size=6.00x1.60x2.60 objects=14 collider=yes
REPORT HB_TrafficCone tris=530 size=0.90x0.90x1.60 objects=6 collider=yes
REPORT HB_PowerPole tris=3464 size=7.00x2.38x25.95 objects=22 collider=yes
REPORT HB_CrateStack tris=2544 size=4.10x4.00x4.00 objects=15 collider=yes
REPORT HB_HazardSign tris=1100 size=1.96x0.30x3.21 objects=15 collider=yes
REPORT HB_ACUnit tris=2840 size=3.01x1.57x2.40 objects=19 collider=yes
REPORT HB_ElectricBox tris=1708 size=1.96x0.86x3.00 objects=16 collider=yes
CHECK WARN HB_LampPost: центр по X смещён на 1.85 (норма для столба с рукой — принято)
CHECK WARN HB_SteamGrate: низ не на z=0 (min z=-0.60) — яма под решёткой, принято (уйдёт в землю)

Замечания Claude (closeups.png приложен):
Уровень хороший. Приняты без правок: HB_LampPost, HB_LampPostDouble, HB_PowerPole, HB_HazardSign, HB_ElectricBox, HB_ACUnit (кроме общего п.1), HB_SteamGrate.

1. ОБЩЕЕ — потёки (`streaks`, `streaks_x`) выглядят как приклеенные палочки: толщина 0.04 по центру грани = выступ 0.02 + видимые торцы. Сделай потёк плоским и сужающимся: выступ над гранью 0.008–0.012, ширина 0.03–0.07, из 2–3 сегментов, каждый ниже — уже (верх широкий, низ тонкий), длины разные. Касается Bollard, Barrier, ACUnit, PowerPole, LampPost (PoleRust), ElectricBox.
2. HB_DrainCover — «ромбы» рассыпаны хаотично и читаются как белые бумажки, ржавые пятна перекрывают их. Нужен регулярный рельеф: решётка ромбов/рёбер на диске (рядами, одинаковый шаг, выступ 0.03, тот же материал OldMetal), 2 кольца рельефа оставить, ржавчина только по кромке и вокруг петли (плоско, выступ 0.01).
3. HB_TrafficCone — чёрные потёртости (Scuff) торчат из конуса под углом: они не лежат на поверхности. Поставь их по образующей конуса (повернуть на угол наклона стенки, центр точно на радиусе с учётом высоты и наклона lean), выступ ≤ 0.01, либо убери Scuff и сделай потёртости светлыми полосами на кольцах.
4. HB_CrateStack — Strap сейчас сплошные чёрные листы 2.76×1.84 на гранях ящика (выглядит как чёрная стена). Стяжная лента — это узкие полосы 0.06–0.08 шириной, 2 штуки вертикально через ящик + 1 горизонтально, выступ 0.01, с пряжкой.
5. HB_Bollard (и Chip в HB_Barrier, Dent в HB_ACUnit) — чёрные квадраты читаются как наклейки, а не сколы. Убери их. Скол делай светлым: 2 маленьких бокса `Concrete` (на металле — `OldMetal`) неправильной формы на ребре, выступ 0.005, повёрнуты на 10–30°.

Пришли исправленные @asset целиком (HB_DrainCover, HB_TrafficCone, HB_CrateStack, HB_Bollard) и новые функции `streaks`/`streaks_x` — только их. После приёмки V1a — сразу V1b (штаб) по packs/V1.md.

## Повторный прогон 16.11 (после правок Qwen) — ПРИНЯТ
12/12, 0 ошибок, 26 с. SteamGrate min z = 0 (исправлено). Накладок-плашек нет, износ материалом. Читаются: столбик, люк, барьер, ящики (без «лица»), кондиционер, электрощит, знак, столбы.
Мелочи (не блокируют):
1. HB_TrafficCone — верхнее белое кольцо шире конуса (ступенька). Радиусы кольца = радиус конуса на той же высоте + 0.004, с тем же наклоном lean.
2. Полосатое дерево на ящике — текстура WornWood в cc_kit (правит Claude, не Qwen).
Дальше: V1b (штаб из 4 модулей) по packs\V1.md.
