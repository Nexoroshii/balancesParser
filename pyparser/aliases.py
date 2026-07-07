# -*- coding: utf-8 -*-
"""Справочник сопоставления «имя поставщика в инвойсе» -> «колонка (имя) в балансе».

Ключ — подстрока (в ВЕРХНЕМ регистре), которая встречается в тексте инвойса.
Значение — каноническое имя = заголовок блока в Лист1 «балансы актуальные».

FARM_ALIASES  ищем в папках co/ec/ke (инвойсы ферм).
FREIGHT_ALIASES ищем ТОЛЬКО в t_common (фрахтовые AWB). Их имена (PACIFIC, IFC,
AIRFLO) встречаются и в farm-инвойсах как «карго-агент», поэтому для ферм НЕ
применяются — иначе ложные срабатывания.

Список пополняемый.
"""

FARM_ALIASES = {
    "TESSA": "TESSA( ECUANROS ECUADORIAN NEW\xa0ROSES\xa0S.A. )",
    "TESSACORPORATION": "TESSA( ECUANROS ECUADORIAN NEW\xa0ROSES\xa0S.A. )",
    "PLAZOLETA": "plazoletta",
    "ALANUCA YANEZ": "ALANUCA YANEZ DIANA ( SISA)",
    "SISA GREEN FLOWERS": "ALANUCA YANEZ DIANA ( SISA)",
    "QUALISA": "QUALISSA   Quality Service S.A.",
    "QUALITY SERVICE QUALISA": "QUALISSA   Quality Service S.A.",
    "EL CAMPANARIO DE SANTA ANITA": "Santa Anita(Star roses) el campanario de santa anita/  EC BLOOMS S.A.S",
    "STAROSES": "Santa Anita(Star roses) el campanario de santa anita/  EC BLOOMS S.A.S",
    "EC BLOOMS": "Santa Anita(Star roses) el campanario de santa anita/  EC BLOOMS S.A.S",
    "DALE FLORA": "DALE FLORA(euro)",
    "VALENCIA PUJOTA JAIME": "VALENT ROSES",
    "VALENTROSES": "VALENT ROSES",
    "VALENT ROSAS": "VALENT ROSES",
    "SUBATI": "Subati + Транспорт ",
    "WARIDI": "WARIDI(euro)",
    "FLORES MENDEZ": "FLORES  MENDEZ",
    "FLORES-MENDEZ": "FLORES  MENDEZ",
    # добавлено по итогам Фазы 1:
    "BELLARO": "Bellaro S.A.",
    "BELLAROSA": "Bellaro S.A.",
    "BELEN'S COMPANY": "Belen's Company",
    "BELENCOMPANIAROSES": "Belen's Company",
    "CAIZALUISA": "CAIZALUISA (ANTHONELA FARMS)",
    "ANTHONELA FARMS": "CAIZALUISA (ANTHONELA FARMS)",
    "LUCY ROSES": "Lucy Roses Cia. Ltda.",
    "ROSAL S FLOWERS": "ROSAL S FLOWERS",
    "ROSALES GAONA": "ROSAL S FLOWERS",
    "MERAKI": "MERAKI   (EMERSON Michael Arequipa)",
    "AREQUIPA AIMACANA EMERSON": "MERAKI   (EMERSON Michael Arequipa)",
    "MERAKIFARMS": "MERAKI   (EMERSON Michael Arequipa)",
    "SHALIMAR": "SHALIMAR",
    "BLISS FLORA": "BLISS FLORA",
    "YARINA": "YARINA  FLOWERS ",
    "INFOYARINA": "YARINA  FLOWERS ",
    "POZO DIAZ RICHART": "YARINA  FLOWERS ",
    "P.J. DAVE FLORA": "PJ DAVE FLORA(euro)",
    "PJ DAVE FLORA": "PJ DAVE FLORA(euro)",
    "PJDAVEFLORA": "PJ DAVE FLORA(euro)",
    # FAUSTO BAYARDO VALENCIA POZO (fausto_valencia2811@hotmail.com, RUC 1713225868001)
    # — это ферма DOMENICA FLOWERS, НЕ VALENT. VALENT — другой человек (VALENCIA PUJOTA
    # JAIME / valentroses.com). Инвойсы «Invoice_GLOBAL GREEN DECO_*» с «Roses grown by:
    # FAUSTO BAYARDO VALENCIA POZO» пишем в колонку DOMENICA FLOWERS.
    "VALENCIA POZO": "DOMENICA FLOWERS",
    "FAUSTO BAYARDO VALENCIA": "DOMENICA FLOWERS",
    "DOMENICA FLOWERS": "DOMENICA FLOWERS",
    "DOMENICAFLOWERS": "DOMENICA FLOWERS",
    "1792059232001": "NOVELFARM (FLORSANI S.A., )",   # NOVELFARM, ключ по RUC (имени в тексте нет)
    "NOVELFARM": "NOVELFARM (FLORSANI S.A., )",
    "FLORSANI": "NOVELFARM (FLORSANI S.A., )",
    # BLESS FLOWER — колонки в балансе ещё нет, создаётся в конце (см. NEW_COLUMNS)
    "BLESS FLOWER": "BLESS FLOWER",
    "BESSFLOWER": "BLESS FLOWER",
    "LANCHIMBA TUTILLO": "BLESS FLOWER",
    "FLORALCHAIN": "GREENDEAL",   # инвойсы Floralchain («Реализация товаров и услуг») пишем в колонку GREENDEAL
    "BUDS AND BLOOMS": "BUDS BLOOMS",
    "BUDSANDBLOOMS": "BUDS BLOOMS",     # из email/сайта, устойчиво к OCR-склейке
    "BUDS&BLOOM": "BUDS BLOOMS",
    "BUDS BLOOM": "BUDS BLOOMS",
    "NL813909867B01": "AIRFLO",         # NL-форвардер (INVOICE 536647 и др.) — по VAT, в колонку AIRFLO
}

# Поставщики, которых ещё нет в балансе — их блок создаётся в конце Лист1.
NEW_COLUMNS = {"BLESS FLOWER"}

FREIGHT_ALIASES = {
    "INTERNATIONAL FLOWER CARGO": "IFC(разбивка колумбия)",
    "INTERNATIONAL FLOWERS CARGO": "IFC(разбивка колумбия)",
    "IFC": "IFC(разбивка колумбия)",
    "PACIFIC AIR CARGO": "PACIFIC (разбивка)",
    "PACIFIC": "PACIFIC (разбивка)",
    "AIRFLO": "AIRFLO",
    "ATLAS AIR": "PACIFIC (разбивка)",       # эквадорский борт (OneTeamCargo/Atlas) относим к PACIFIC
    "ONETEAMCARGO": "PACIFIC (разбивка)",
}

# Правила по имени файла (приоритетнее поиска по тексту).
# (regex по basename в верхнем регистре) -> каноническое имя поставщика.
FILENAME_RULES = [
    (r"^INV-\d+", "IMPEX(NOVPEC)"),   # инвойсы IMPEX
]

# Файлы, которые НЕ являются инвойсами (манифесты/развесовки/сводники) — пропускаем.
SKIP_FILE_PATTERNS = [
    r"^REPORTE",
    r"^MANIFEST",
    r"\d+\s*BXS",           # развесовки «... 182 BXS / 211bxs / 223 bxs»
    r"^KE\d+\.XLSX$",       # KE0702.xlsx — сводный рабочий файл
    r"GRD-GGD.*\.XLSX$",    # манифест боксов AIRFLO (.xlsx, без сумм)
    r"^GLOBAL-FFG,",        # сводник-манифест «GLOBAL-FFG, GLOBAL-IA <дата>.xlsx»
]
