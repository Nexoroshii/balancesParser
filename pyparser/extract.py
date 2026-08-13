# -*- coding: utf-8 -*-
"""Извлечение из инвойса: поставщик, сумма(ы), дата, валюта."""
from __future__ import annotations
import re
import datetime as dt
from dataclasses import dataclass, field
from typing import List, Optional

from .aliases import FARM_ALIASES, FREIGHT_ALIASES, FILENAME_RULES
from .readers import Doc


# ----------------------------- поставщик -----------------------------------

def detect_supplier(doc: Doc, is_freight: bool):
    """Возвращает (canonical|None, matched_key|None, source)."""
    up_name = doc.basename.upper()
    for pat, canon in FILENAME_RULES:
        if re.search(pat, up_name):
            return canon, pat, "filename"
    table = FREIGHT_ALIASES if is_freight else FARM_ALIASES
    up_text = doc.text.upper()
    up_nospace = up_text.replace(" ", "")            # OCR склеивает слова
    hits = []
    for key, canon in table.items():
        if not canon:
            continue
        if key in up_text or key.replace(" ", "") in up_nospace:
            hits.append((len(key), key, canon))
    if hits:
        hits.sort(reverse=True)          # самый длинный (специфичный) ключ
        _, key, canon = hits[0]
        return canon, key, "text"
    return None, None, "none"


# ------------------------------- сумма -------------------------------------

_NUM = r"([0-9][0-9.,\s]*[0-9]|[0-9])"
_DEC = r"([0-9][0-9.,]*[.,][0-9]{2})"     # число с 2 знаками после разделителя

# (метка, regex, приоритет). Первым берём кандидата с макс. приоритетом.
AMOUNT_PATTERNS = [
    ("GROSS AMOUNT USD",  r"GROSS\s+AMOUNT\s*:?\s*USD\s*" + _NUM, 100),
    ("TOTAL NET AMOUNT USD", r"TOTAL\s+NET\s+AMOUNT\s*:?\s*USD\s*" + _NUM, 100),
    ("NET AMOUNT USD",    r"(?<!GROSS )NET\s+AMOUNT\s*:?\s*USD\s*" + _NUM, 95),
    ("INVOICE TOTAL",     r"INVOICE\s+TOTAL\s*[:\-]?\s*\$?\s*" + _NUM, 90),
    ("TOTAL INVOICE",     r"TOTAL\s+INVOICE\s*[:\-]?\s*\$?\s*" + _NUM, 90),
    ("INVOICE AMOUNT",    r"INVOICE\s+AMOUNT\s*\$?\s*" + _NUM, 88),
    ("AMOUNT DUE",        r"AMOUNT\s+DUE\s*\$?\s*" + _NUM, 85),
    ("TOTAL (INCL) $",    r"TOTAL\s*\(INCL\)\s*\$\s*" + _NUM, 85),
    ("GROSS AMOUNT EUR",  r"GROSS\s+AMOUNT\s*:?\s*EUR\s*" + _NUM, 100),
    ("NET AMOUNT EUR",    r"(?<!GROSS )NET\s+AMOUNT\s*:?\s*EUR\s*" + _NUM, 95),
    ("TOTAL: USD",        r"TOTAL\s*[:\-]\s*USD\s*" + _NUM, 80),
    ("TOTAL EUR",         r"TOTAL\s*[:\-]?\s*EUR\s*" + _NUM, 80),
    ("TOTAL USD",         r"TOTAL\s+USD\s*" + _NUM, 78),
    ("USD decimal",       r"\bUSD\s*\$?\s*" + _DEC, 70),
    ("SUB TOTAL",         r"SUB\s*TOTAL\s*[:\-]?\s*\$?\s*" + _NUM, 60),
    ("GRAND TOTAL",       r"GRAND\s+TOTAL\s*[:\-]?\s*\$?\s*" + _NUM, 55),
    ("TOTAL generic",     r"\bTOTAL\b([^0-9\n]{0,12})\$?\s*" + _NUM, 30),
]

# слова, указывающие что «TOTAL» — не деньги (боксы/стебли/вес)
_NON_MONEY = re.compile(r"BOX|STEM|PIECE|BUNCH|FULL|WEIGHT|KGS?|PCS|TALLOS|BOUNCH|STEAM|RAMO|CAJA")


def parse_number(raw: str) -> Optional[float]:
    s = raw.strip().replace(" ", "")
    if not s:
        return None
    has_c, has_d = "," in s, "." in s
    if has_c and has_d:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif has_c:
        if re.search(r",\d{2}$", s):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    try:
        return round(float(s), 2)
    except ValueError:
        return None


@dataclass
class AmountHit:
    label: str
    raw: str
    value: Optional[float]


_NUM_TOKEN = r"\d[\d.,]*\d|\d"
_KES = re.compile(r"KES|KSH")


def _fmt(x: float) -> str:
    return str(int(x)) if float(x).is_integer() else str(round(x, 2))


def _line_numbers(line: str) -> List[float]:
    out = []
    for tok in re.findall(_NUM_TOKEN, line):
        v = parse_number(tok)
        if v is not None:
            out.append(v)
    return out


def _parse_ec(s: str) -> Optional[float]:
    """Эквадорский формат: запятая — десятичный разделитель, точка — тысячи."""
    s = s.strip().replace(" ", "")
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        return round(float(s), 2)
    except ValueError:
        return None


def _detect(doc: Doc):
    """Возвращает (AmountHit|None, components:list[float]).

    Уровни (строго по приоритету, следующий — только если предыдущий пуст):
      1) сильные метки (INVOICE TOTAL, AMOUNT DUE, TOTAL: USD, NET AMOUNT ...);
      2) число перед «$» в строке TOTAL (эквадорский формат «1460,00$»);
      3) сумма табличных строк «TOTALS» / одиночная строка TOTAL (последнее число).
    """
    up = doc.text.upper()

    # --- уровень 1: метки ---
    tier1 = []
    for label, pat, prio in AMOUNT_PATTERNS:
        if label == "TOTAL generic":
            continue
        m = re.search(pat, up)
        if not m:
            continue
        pre = up[max(0, m.start()):m.start(m.lastindex)]
        if "KES" in pre:
            continue
        v = parse_number(m.group(m.lastindex))
        if v and v > 0:
            tier1.append((prio, v, label))

    # компоненты табличных TOTALS (для многоинвойсовых файлов и формулы)
    components = []
    for line in up.splitlines():
        s = line.strip()
        if re.match(r"TOTALS\b", s) and not _NON_MONEY.search(s) and not _KES.search(s):
            nums = [n for n in _line_numbers(s) if n > 0]
            if nums:
                components.append(nums[-1])
    components = components if len(components) >= 2 else []
    # многоинвойсовый упаковочный лист: сумма компонент — авторитетна,
    # но ниже настоящих итоговых меток (INVOICE TOTAL=90, AMOUNT DUE=85, ...)
    if components:
        tier1.append((82, round(sum(components), 2), "сумма TOTALS"))

    # --- уровень 2: число перед $ в строке TOTAL ---
    tier2 = []
    for line in up.splitlines():
        s = line.strip()
        if not re.match(r"TOTAL\b", s) or _NON_MONEY.search(s) or _KES.search(s):
            continue
        md = re.search(r"([\d][\d.,]*)\s*\$", s)
        if md:
            v = _parse_ec(md.group(1))
            if v and v > 0:
                tier2.append(v)

    # --- уровень 3: последнее число одиночной строки TOTAL (напр. Subati «Total 499.2») ---
    tier3 = []
    for line in up.splitlines():
        s = line.strip()
        if not re.match(r"TOTAL\b", s) or _NON_MONEY.search(s) or _KES.search(s):
            continue
        nums = [n for n in _line_numbers(s) if n > 0]
        if nums:
            tier3.append(nums[-1])

    if tier1:
        best = max(tier1, key=lambda c: (c[0], c[1]))
        # компоненты (разбивку по инвойсам) отдаём только если сумма — это сумма TOTALS
        comps = components if best[2] == "сумма TOTALS" else []
        return AmountHit(best[2], "", best[1]), comps
    if tier2:
        return AmountHit("строка TOTAL $", "", max(tier2)), []
    if tier3:
        return AmountHit("TOTALS/строка TOTAL", "", max(tier3)), []

    # --- уровень 4 (последний): макс. число с РОВНО 2 десятичными (деньги),
    #     когда явного итога нет (напр. итоговая строка без метки) ---
    money2 = []
    for line in up.splitlines():
        if _KES.search(line):
            continue
        for tok in re.findall(r"\d[\d.,]*[.,]\d{2}(?!\d)", line):
            v = parse_number(tok)
            if v and v > 0:
                money2.append(v)
    if money2:
        return AmountHit("макс. 2-знач.", "", max(money2)), []
    return None, []


def detect_amount(doc: Doc) -> Optional[AmountHit]:
    return _detect(doc)[0]


def detect_all_totals(doc: Doc) -> List[float]:
    return _detect(doc)[1]


# --------------------------- фрахт: Total Prepaid --------------------------
# В форме AWB метка «Total Prepaid» стоит НАД значением, поэтому первое денежное
# число (с 2 знаками) ПОСЛЕ метки и есть сумма фрахта. Устойчиво к OCR-опечаткам:
# «Total Prepaid», «Totat Prepa'd», «Totat Prepaid», склейке «TotalPrepaid».
_FREIGHT_LABEL = re.compile(r"TOT\w*\s*PREPA")
_MONEY2 = re.compile(r"[0-9][0-9.,]*[.,][0-9]{2}")
_FREIGHT_DATE = re.compile(r"(\d{1,2}[-/]\d{1,2}[-/]\d{4})")


def detect_freight_prepaid(up: str):
    """Из AWB (текст в ВЕРХНЕМ регистре) достаёт (сумма Total Prepaid, дата)."""
    m = _FREIGHT_LABEL.search(up)
    if not m:
        return None, None
    win = up[m.end(): m.end() + 220]
    amount = None
    for tok in _MONEY2.findall(win):
        v = parse_number(tok)
        if v and v > 0:
            amount = v
            break
    date = None
    dm = _FREIGHT_DATE.search(win)
    if dm:
        date = _to_date(dm.group(1))
    return amount, date


# ------------------------------- дата --------------------------------------

_DATE_LABELS = r"(?:INVOICE\s+DATE|\bDATE\b|FECHA|EMISION|EMISI[ÓO]N|F\.?\s*EMISION)"
# буквенные месяцы (формат AIRFLO/форвардеров: «02-Jul-26», «02 JUL 2026»)
_MONTHS = {
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
}
_DATE_ALPHA = r"(\d{1,2}(?:ST|ND|RD|TH)?[/\-.\s]*(?:JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)[A-Z]*[/\-.\s]*\d{2,4})"
_DATE_RE = r"(\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4}|\d{4}[/\-.]\d{1,2}[/\-.]\d{1,2})"


def _to_date(raw: str) -> Optional[dt.date]:
    # буквенный месяц: «02-JUL-26», «02 JUL 2026», «11th Aug 2026»
    ma = re.match(r"(\d{1,2})(?:ST|ND|RD|TH)?[/\-.\s]*([A-Z]{3})[A-Z]*[/\-.\s]*(\d{2,4})", raw.upper())
    if ma and ma.group(2) in _MONTHS:
        d, mo, y = int(ma.group(1)), _MONTHS[ma.group(2)], int(ma.group(3))
        if y < 100:
            y += 2000
        try:
            return dt.date(y, mo, d)
        except ValueError:
            return None
    m = re.match(r"(\d{4})[/\-.](\d{1,2})[/\-.](\d{1,2})", raw)
    if m:
        y, a, b = map(int, m.groups())
        try:
            return dt.date(y, a, b)
        except ValueError:
            return None
    m = re.match(r"(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2,4})", raw)
    if m:
        a, b, y = map(int, m.groups())
        if y < 100:
            y += 2000
        if a > 12 and b <= 12:
            d, mo = a, b
        elif b > 12 and a <= 12:
            d, mo = b, a
        else:
            d, mo = a, b   # предполагаем dd/mm
        try:
            return dt.date(y, mo, d)
        except ValueError:
            return None
    return None


@dataclass
class DateHit:
    raw: str
    value: Optional[dt.date]
    ambiguous: bool = False
    source: str = ""


def _serial_to_date(serial: int) -> Optional[dt.date]:
    if 40000 <= serial <= 50000:            # 2009..2036
        return dt.date(1899, 12, 30) + dt.timedelta(days=serial)
    return None


def detect_date(doc: Doc) -> Optional[DateHit]:
    up = doc.text.upper()
    m = re.search(_DATE_LABELS + r"[^\d\n]{0,15}" + _DATE_RE, up)
    src = "label"
    # буквенный месяц у метки (AIRFLO/форвардеры: «INVOICE DATE:02-Jul-26»)
    if not m:
        ma = re.search(_DATE_LABELS + r"\D{0,15}" + _DATE_ALPHA, up)
        if ma:
            raw = ma.group(1)
            return DateHit(raw, _to_date(raw), False, "label-alpha")
    if not m:
        m = re.search(_DATE_RE, up)
        src = "any"
    if not m:
        ma = re.search(_DATE_ALPHA, up)
        if ma:
            raw = ma.group(1)
            return DateHit(raw, _to_date(raw), False, "alpha")
    # Excel-серийник рядом с меткой DATE (xls, где дата в тексте как «46203.0»)
    ms = re.search(r"(?:INVOICE\s+DATE|\bDATE\b|FECHA|EMISION|F\.?\s*EMISION)\D{0,8}(\d{5})(?:\.0)?\b", up)
    if ms:
        d = _serial_to_date(int(ms.group(1)))
        if d:
            return DateHit(d.isoformat(), d, False, "serial")
    if m:
        raw = m.group(1)
        parts = re.split(r"[/\-.]", raw)
        ambiguous = False
        if len(parts) == 3 and len(parts[0]) <= 2:
            try:
                ambiguous = int(parts[0]) <= 12 and int(parts[1]) <= 12
            except ValueError:
                ambiguous = False
        return DateHit(raw, _to_date(raw), ambiguous, src)
    # фолбэк — даты из ячеек .xls/.xlsx (берём самую раннюю правдоподобную)
    cds = doc.meta.get("cell_dates") or []
    if cds:
        d = min(cds)
        return DateHit(d.isoformat(), d, False, "cell")
    return None


# -------------------- сверка дат по всей поставке --------------------------
# В одной поставке даты кучкуются в несколько дней. Числовая дата, где одно
# число > 12, ориентируется ОДНОЗНАЧНО (напр. «07/13» = 13 июля при любом
# соглашении) — это «якорь». Разные поставщики в одной поставке пишут по-разному
# (06/07 = dd/mm = 6 июля, а 07/06 = mm/dd = тоже 6 июля), поэтому фиксированное
# правило dd/mm ошибается на половине. Решение: для каждой неоднозначной даты
# (оба числа ≤ 12) берём ту из двух трактовок, что ближе к окну якорей.

_AMBIG_NOTE = "дата неоднозначна dd/mm vs mm/dd"


def _swap_dm(d: dt.date) -> Optional[dt.date]:
    """Меняет местами день и месяц (обе трактовки dd/mm ↔ mm/dd)."""
    if d.day <= 12 and d.month <= 12:
        try:
            return dt.date(d.year, d.day, d.month)
        except ValueError:
            return None
    return None


def reconcile_dates(extractions, extra_anchors=None) -> int:
    """Разворачивает неоднозначные даты (dd/mm vs mm/dd) по всей поставке.

    Якоря — все однозначные даты партии (+ extra_anchors, напр. дата из имени
    папки). Для каждой неоднозначной даты выбираем трактовку, ближайшую к окну
    якорей [min..max]; при равенстве — ближе к медиане. Возвращает число
    фактически изменённых дат. Мутирует DateHit на месте.
    """
    exs = [e for e in extractions if e is not None]
    anchors = [a for a in (extra_anchors or []) if a]
    for e in exs:
        d = e.date
        if d and d.value and not d.ambiguous:
            anchors.append(d.value)
    if not anchors:
        return 0                     # не на что опереться — оставляем как есть
    anchors.sort()
    lo, hi, med = anchors[0], anchors[-1], anchors[len(anchors) // 2]

    def dist(x: dt.date) -> int:
        if x < lo:
            return (lo - x).days
        if x > hi:
            return (x - hi).days
        return 0

    fixed = 0
    for e in exs:
        d = e.date
        if not (d and d.value and d.ambiguous):
            continue
        cur = d.value
        alt = _swap_dm(cur)
        cands = [cur] if (alt is None or alt == cur) else [cur, alt]
        best = min(cands, key=lambda x: (dist(x), abs((x - med).days)))
        if best != cur:
            d.value = best
            d.source = (d.source + "+reconciled").strip("+")
            e.notes.append("дата развёрнута по поставке → " + best.isoformat())
            fixed += 1
        d.ambiguous = False          # трактовка выбрана по контексту поставки
        if _AMBIG_NOTE in e.notes:
            e.notes.remove(_AMBIG_NOTE)
    return fixed


# ------------------------------ валюта -------------------------------------

def detect_currency(doc: Doc, amount_label: str = "") -> str:
    up = doc.text.upper()
    m = re.search(r"CURRENCY\s*:?\s*(US\s*DOLLAR|USD|EUR|EURO)", up)
    if m:
        return "EUR" if m.group(1).startswith("EUR") else "USD"
    if "EUR" in amount_label:
        return "EUR"
    if "USD" in amount_label:
        return "USD"
    if re.search(r"\bUSD\b|\$", up):
        return "USD"
    if re.search(r"\bEUR\b|€", up):
        return "EUR"
    return "?"


# ------------------------------ агрегат ------------------------------------

@dataclass
class Extraction:
    path: str
    kind: str
    supplier: Optional[str]
    supplier_key: Optional[str]
    supplier_src: str
    amount: Optional[AmountHit]
    all_totals: List[float] = field(default_factory=list)
    date: Optional[DateHit] = None
    currency: str = "?"
    status: str = "ok"
    notes: List[str] = field(default_factory=list)
    candidates: List[float] = field(default_factory=list)   # варианты суммы (фрахт OCR)


def extract(doc: Doc, is_freight: bool = False) -> Extraction:
    canon, key, src = detect_supplier(doc, is_freight)
    amt, totals = _detect(doc)

    # фрахтовый AWB: сумма = «Total Prepaid» (устойчиво даже по OCR); плюс собираем
    # все USD-суммы как запасных кандидатов, если метку разъело OCR.
    freight_usd = []
    freight_total = None
    freight_date = None
    freight_by_label = False
    if is_freight:
        up = doc.text.upper()
        is_ocr = bool(doc.meta.get("ocr"))
        freight_total, freight_date = detect_freight_prepaid(up)
        freight_by_label = freight_total is not None
        freight_usd = sorted({parse_number(x) for x in
                              re.findall(r"USD\s*\$?\s*([0-9][0-9.,]*[.,][0-9]{2})", up)
                              if parse_number(x)}, reverse=True)
        # метку «Total Prepaid» разъело OCR (напр. «TOALPRAPALD») — берём макс. USD-сумму:
        # в AWB Total Prepaid = вес + прочие сборы, т.е. ВСЕГДА наибольшая USD-сумма.
        if freight_total is None and freight_usd:
            freight_total = freight_usd[0]
        # дата исполнения на OCR-сканах (метка-дата не читается) — последняя полная
        # дата в документе (стоит внизу бланка AWB, рядом с Total Prepaid).
        if freight_date is None and is_ocr:
            ds = re.findall(r"\d{1,2}[-/]\d{1,2}[-/]\d{4}", up)
            if ds:
                freight_date = _to_date(ds[-1])
        # если метки не было (фолбэк «макс. USD») и обычный детектор уже нашёл
        # надёжную сумму по явной метке (TOTAL EUR/USD, INVOICE TOTAL...) —
        # не затираем её угадайкой: фолбэк нужен только когда сказать нечего.
        if freight_total is not None and (freight_by_label or amt is None):
            lbl = "Total Prepaid (фрахт)" if freight_by_label else "фрахт USD (макс.)"
            amt = AmountHit(lbl, "", freight_total)

    date = detect_date(doc)
    if is_freight and freight_date is not None:
        date = DateHit(freight_date.isoformat(), freight_date, False, "freight")
    cur = detect_currency(doc, amt.label if amt else "")
    if cur == "?" and amt is not None:
        cur = "USD"                          # по умолчанию: подавляющее большинство в USD

    notes = []
    status = "ok"
    if doc.meta.get("ocr"):
        notes.append("распознано через OCR — сверьте сумму")
    # фрахт из OCR: если нашли явную метку «Total Prepaid» — пишем автоматически
    # (но просим сверить). Если метки нет — не угадываем (путается с TRM-курсом),
    # выводим USD-кандидатов на ручной выбор.
    if is_freight and doc.meta.get("ocr"):
        if freight_total is not None:
            notes.append("OCR-фрахт: сумма = Total Prepaid (сверьте с AWB)"
                         if freight_by_label else
                         "OCR-фрахт: метка не читается, взята макс. USD-сумма (сверьте)")
        else:
            status = "manual"
            cand = ", ".join(_fmt(x) for x in freight_usd[:6]) or "—"
            notes.append("OCR-фрахт: выберите Total Prepaid из USD-сумм: " + cand)
    if not doc.meta.get("has_text", True):
        status = "manual"; notes.append("нет текста (скан) — нужен OCR")
    if canon is None:
        status = "manual"; notes.append("поставщик не распознан")
    if amt is None:
        status = "manual"; notes.append("сумма не найдена")
    if date is None:
        notes.append("дата не найдена")
    elif date.ambiguous:
        notes.append("дата неоднозначна dd/mm vs mm/dd")

    return Extraction(doc.path, doc.kind, canon, key, src, amt, totals,
                      date, cur, status, notes, freight_usd)
