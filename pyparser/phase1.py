# -*- coding: utf-8 -*-
"""Фаза 1: обход папки поставки, извлечение и таблица распознавания.

Запуск:
  python -m pyparser.phase1 --folder excel/07.02

Выводит таблицу: файл -> поставщик -> дата -> сумма -> статус.
Пишет отчёт (csv, utf-8-sig) рядом или по --out.
"""
from __future__ import annotations
import argparse
import glob
import os
import sys
import io
import csv

from .readers import read_any
from .extract import extract, reconcile_dates
from .aliases import SKIP_FILE_PATTERNS
import re

SKIP_DIRS = ("ready",)                      # папки, которые не трогаем
FREIGHT_DIR = "t_common"                     # фрахтовые AWB
EXTS = (".pdf", ".xls", ".xlsx")

_SKIP_RE = [re.compile(p) for p in SKIP_FILE_PATTERNS]


def is_freight_path(p: str) -> bool:
    return ("/" + FREIGHT_DIR + "/") in p.replace("\\", "/").lower()


def is_skip_file(p: str) -> bool:
    name = os.path.basename(p).upper()
    return any(r.search(name) for r in _SKIP_RE)


def find_files(folder: str):
    out = []
    for p in glob.glob(os.path.join(folder, "**", "*"), recursive=True):
        if not os.path.isfile(p):
            continue
        low = p.replace("\\", "/").lower()
        if any(("/" + s) in low for s in SKIP_DIRS):
            continue
        if os.path.splitext(p)[1].lower() not in EXTS:
            continue
        if is_skip_file(p):
            continue
        out.append(p)
    return sorted(out)


def rel(p, folder):
    try:
        return os.path.relpath(p, folder).replace("\\", "/")
    except ValueError:
        return p


def run(folder: str, out_csv: str):
    files = find_files(folder)
    results = []
    for p in files:
        try:
            doc = read_any(p)
            ex = extract(doc, is_freight=is_freight_path(p))
        except Exception as e:
            results.append((p, None, "ERROR: " + repr(e)))
            continue
        results.append((p, ex, None))

    # сверка дат dd/mm vs mm/dd по всей поставке (см. reconcile_dates)
    reconcile_dates([ex for _, ex, err in results if ex])

    # --- отчёт csv ---
    with io.open(out_csv, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["файл", "тип", "поставщик", "источник", "валюта",
                    "дата", "дата_raw", "сумма", "метка_суммы", "сумма_raw",
                    "все_тоталы", "статус", "примечания"])
        for p, ex, err in results:
            if err:
                w.writerow([rel(p, folder), "", "", "", "", "", "", "", "", "", "", "error", err])
                continue
            d = ex.date
            a = ex.amount
            w.writerow([
                rel(p, folder), ex.kind, ex.supplier or "", ex.supplier_src,
                ex.currency,
                (d.value.isoformat() if d and d.value else ""),
                (d.raw if d else ""),
                (a.value if a else ""),
                (a.label if a else ""),
                (a.raw if a else ""),
                "+".join(str(x) for x in ex.all_totals),
                ex.status,
                "; ".join(ex.notes),
            ])

    return results


def print_table(results, folder):
    def cut(s, n):
        s = str(s)
        return s if len(s) <= n else s[: n - 1] + "…"

    ok = manual = err = 0
    lines = []
    lines.append("%-42s | %-26s | %-10s | %10s | %-7s" %
                 ("файл", "поставщик", "дата", "сумма", "статус"))
    lines.append("-" * 108)
    for p, ex, e in results:
        name = rel(p, folder)
        if e:
            err += 1
            lines.append("%-42s | %-26s | %-10s | %10s | %-7s" %
                         (cut(name, 42), "", "", "", "ERROR"))
            continue
        if ex.status == "ok":
            ok += 1
        elif ex.status == "manual":
            manual += 1
        dd = ex.date.value.isoformat() if (ex.date and ex.date.value) else "?"
        amt = ("%.2f %s" % (ex.amount.value, ex.currency)) if ex.amount else "?"
        lines.append("%-42s | %-26s | %-10s | %10s | %-7s" %
                     (cut(name, 42), cut(ex.supplier or "—", 26), dd,
                      cut(amt, 10), ex.status))
    lines.append("-" * 108)
    lines.append("ИТОГО: %d файлов | ok=%d | manual=%d | error=%d" %
                 (len(results), ok, manual, err))
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--folder", required=True, help="папка поставки, напр. excel/07.02")
    ap.add_argument("--out", default=None, help="куда писать csv-отчёт")
    ap.add_argument("--report-file", default=None,
                    help="если задан — таблица пишется в этот файл (utf-8), а не в stdout")
    args = ap.parse_args(argv)

    out_csv = args.out or os.path.join(args.folder, "_recognition_report.csv")
    results = run(args.folder, out_csv)
    table = print_table(results, args.folder)
    if args.report_file:
        with io.open(args.report_file, "w", encoding="utf-8") as f:
            f.write(table + "\n\nCSV: " + out_csv + "\n")
    else:
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
        print(table)
        print("\nCSV-отчёт:", out_csv)


if __name__ == "__main__":
    main()
