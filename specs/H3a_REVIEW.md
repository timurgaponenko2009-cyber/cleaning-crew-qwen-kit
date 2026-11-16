Отчёт запуска H3a: DONE H3a assets=4 failed=0 errors=0
REPORT HB_Pergola tris=2980 size=34.00x6.40x9.60 objects=20
REPORT HB_Bench tris=1520 size=6.00x1.61x2.90 objects=7
REPORT HB_InfoBoard tris=832 size=4.00x1.15x4.50 objects=13
REPORT HB_VendingMachine tris=2084 size=3.00x2.80x6.50 objects=18
CHECK WARN HB_InfoBoard: центр по Y смещён на −0.28 (козырёк — принято)

Принято: HB_InfoBoard. HB_Bench — принят после переименования (п.2).

1. HB_Pergola — ламели (24 шт. шириной 0.35 с шагом 0.24) легли внахлёст и выглядят сплошной крышей. Сделай настоящие жалюзи: 18 ламелей 0.12×0.45, шаг 0.6, наклон 35°, между ними видно небо. УБЕРИ anim у Louver (все ламели одной деталью раскачиваются как крышка). Вьюны почти не видны: по 2 стойкам и вдоль одной балки — густые группы `Leaf`/`LeafDark` (30–40 шаров-кластеров разного размера, свисающие плети `sweep`), anim sway оставь. Подвесные лампы опусти ниже балок (на 1.2), чтобы их было видно снизу.
2. HB_Bench — переименуй детали: «Seat» → `Slats`, «Rest» → `BackBoards` нельзя (слово Back) → `RestBoards`. Слова Seat/Back/Mat/Tap/Wall в именах деталей игра трактует особо.
3. HB_VendingMachine — сейчас серая коробка. Витрина: стекло `Glass` (не DirtyGlass, HUB чистый), за ним ярко подсвеченные полки (`LightEmit` полосы сверху каждой полки), бутылки 3–4 цветов (материалы `Glass` + крышки `SafetyOrange`/`WarnRed`/`Flower`), боковая панель с крупной рамкой под рекламу (`SignPanel` пустая), козырёк сверху с подсветкой. Корпус — `Paint` тёмно-графитовый с оранжевой полосой.

Пришли исправленные @asset HB_Pergola, HB_Bench, HB_VendingMachine, затем H3b.
