# -*- coding: utf-8 -*-
"""Фаза 2: агрегация распознанных инвойсов и запись в копию баланса.

Запуск:
  python -m pyparser.phase2 --folder excel/07.02 \
      --balance "excel/балансы актульные 0626.xlsx" [--out copy.xlsx]

- одна строка на поставщика за поставку;
- «отгрузка» = формула =инв1+инв2+...  (компоненты — отдельные инвойсы);
- дата = самая ранняя среди инвойсов поставщика;
- нераспознанное (manual) не пишется — попадает в отчёт.
"""
from __future__ import annotations
import argparse
import os
import io
import csv
import datetime as dt
from collections import defaultdict

from .readers import read_any
from .extract import extract
from .aliases import NEW_COLUMNS
from .balance import BalanceWriter
from .phase1 import find_files, is_freight_path, rel


def _setup_stdout():
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


def _log(msg=""):
    """Печать с немедленным сбросом буфера — чтобы прогресс был виден сразу."""
    import sys
    print(msg, flush=True)
    try:
        sys.stdout.flush()
    except Exception:
        pass


def _amounts_of(ex):
    if ex.all_totals:
        return list(ex.all_totals)
    if ex.amount:
        return [ex.amount.value]
    return []


def _manual_item(folder, p, ex, why):
    d = ex.date.value if (ex and ex.date and ex.date.value) else None
    amts = _amounts_of(ex) if ex else []
    hint = why
    if ex and ex.candidates:
        hint = "выберите Total Prepaid: " + ", ".join(
            (str(int(x)) if float(x).is_integer() else str(x)) for x in ex.candidates[:6])
        amts = []          # фрахт: сумму пусть выберет пользователь
    return {"file": rel(p, folder), "supplier": (ex.supplier if ex else "") or "",
            "date": d, "amounts": amts, "hint": hint}


def aggregate(folder):
    """Возвращает (per_supplier, manual)."""
    per = defaultdict(lambda: {"amounts": [], "dates": [], "files": []})
    manual = []
    seen_stems = set()          # один инвойс в двух форматах: GLOBAL.pdf == GLOBAL.xlsx
    files = list(find_files(folder))
    total = len(files)
    _log("Найдено файлов инвойсов: %d. Читаю..." % total)
    for i, p in enumerate(files, 1):
        _log("  [%d/%d] %s" % (i, total, rel(p, folder)))
        stem = os.path.splitext(os.path.basename(p))[0].strip().lower()
        if stem in seen_stems:
            continue
        try:
            doc = read_any(p)
            ex = extract(doc, is_freight=is_freight_path(p))
        except Exception as e:
            manual.append(_manual_item(folder, p, None, "ошибка чтения: " + repr(e)))
            continue
        if ex.status != "ok" or not ex.supplier:
            manual.append(_manual_item(folder, p, ex, "; ".join(ex.notes) or ex.status))
            continue
        amts = _amounts_of(ex)
        if not amts:
            manual.append(_manual_item(folder, p, ex, "нет суммы"))
            continue
        seen_stems.add(stem)
        d = ex.date.value if (ex.date and ex.date.value) else None
        rec = per[ex.supplier]
        rec["amounts"].extend(amts)
        if d:
            rec["dates"].append(d)
        rec["files"].append((p, amts, d))
    return per, manual


def run(folder, balance, out):
    per, manual = aggregate(folder)
    _log("")
    _log("Распознано поставщиков: %d, на ручную проверку: %d" % (len(per), len(manual)))
    _log("Открываю баланс и записываю суммы...")
    w = BalanceWriter(balance, out)
    written, skipped, failed = [], [], []
    for supplier, rec in sorted(per.items()):
        amounts = rec["amounts"]
        date = min(rec["dates"]) if rec["dates"] else dt.date.today()
        # создать блок, если поставщика ещё нет в балансе
        if w.find_block(supplier) is None and supplier.upper() in {s.upper() for s in NEW_COLUMNS}:
            w.create_block(supplier)
        status, msg = w.write_supplier(supplier, date, amounts)
        bucket = {"written": written, "skipped": skipped, "error": failed}[status]
        bucket.append((supplier, date, amounts, msg))
    w.save()
    return per, manual, written, skipped, failed


def _report(folder, out, per, manual, written, skipped, failed, report_path):
    csv_path = os.path.splitext(out)[0] + "_report.csv"
    with io.open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        wr = csv.writer(f, delimiter=";")
        wr.writerow(["поставщик", "дата", "кол-во инвойсов", "сумма", "формула/статус"])
        for s, d, a, m in written:
            wr.writerow([s, d.isoformat(), len(a), round(sum(a), 2), m])
        for s, d, a, m in skipped:
            wr.writerow([s, d.isoformat(), len(a), round(sum(a), 2), "ПРОПУЩЕНО: " + m])
        for s, d, a, m in failed:
            wr.writerow([s, d.isoformat(), len(a), round(sum(a), 2), "НЕ ЗАПИСАНО: " + m])
        wr.writerow([])
        wr.writerow(["--- НА РУЧНУЮ ПРОВЕРКУ ---"])
        for it in manual:
            wr.writerow([it["file"], it.get("supplier", ""), "", "", it["hint"]])

    lines = []
    lines.append("ЗАПИСАНО в баланс (%d поставщиков):" % len(written))
    for s, d, a, m in written:
        lines.append("  %-34s %s  %2d инв.  = %9.2f | %s" %
                     (s[:34], d.isoformat(), len(a), sum(a), m))
    if skipped:
        lines.append("\nПРОПУЩЕНО (уже записано ранее, %d):" % len(skipped))
        for s, d, a, m in skipped:
            lines.append("  %-34s | %s" % (s[:34], m))
    if failed:
        lines.append("\nНЕ УДАЛОСЬ записать (%d):" % len(failed))
        for s, d, a, m in failed:
            lines.append("  %-34s | %s" % (s[:34], m))
    lines.append("\nНА РУЧНУЮ ПРОВЕРКУ (%d файлов):" % len(manual))
    for it in manual:
        lines.append("  %-46s | %s" % (it["file"][:46], it["hint"]))
    lines.append("\nКопия баланса: " + out)
    lines.append("CSV-отчёт: " + csv_path)
    text = "\n".join(lines)
    if report_path:
        with io.open(report_path, "w", encoding="utf-8") as f:
            f.write(text + "\n")
    return text


def _auto_balance(excel_dir="excel"):
    import glob
    cands = [p for p in glob.glob(os.path.join(excel_dir, "*.xlsx"))
             if "баланс" in os.path.basename(p).lower()
             and "_auto" not in os.path.basename(p).lower()]
    return max(cands, key=os.path.getmtime) if cands else None


def _auto_folder(excel_dir="excel"):
    subs = [os.path.join(excel_dir, d) for d in os.listdir(excel_dir)
            if os.path.isdir(os.path.join(excel_dir, d))]
    # поставка = папка с подпапками co/ec/ke
    good = [d for d in subs if any(os.path.isdir(os.path.join(d, x))
                                   for x in ("co", "ec", "ke"))]
    pool = good or subs
    return max(pool, key=os.path.getmtime) if pool else None


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--folder", default=None, help="папка поставки (по умолч. — свежая в excel/)")
    ap.add_argument("--balance", default=None, help="файл баланса (по умолч. — свежий баланс* в excel/)")
    ap.add_argument("--out", default=None)
    ap.add_argument("--report-file", default=None)
    args = ap.parse_args(argv)

    if not args.report_file:
        _setup_stdout()
    _log("=" * 60)
    _log("ОБРАБОТКА БАЛАНСА — старт")
    _log("=" * 60)

    args.folder = args.folder or _auto_folder()
    args.balance = args.balance or _auto_balance()
    if not args.folder or not args.balance:
        raise SystemExit("Не найдена папка поставки или файл баланса в excel/. "
                         "Укажите --folder и --balance явно.")

    _log("Папка поставки: " + args.folder)
    _log("Файл баланса:   " + args.balance)
    _log("")

    out = args.out or os.path.join(
        os.path.dirname(args.balance),
        os.path.splitext(os.path.basename(args.balance))[0] + "_auto.xlsx")
    per, manual, written, skipped, failed = run(args.folder, args.balance, out)

    # редактируемая очередь ручной проверки
    queue_path = os.path.splitext(out)[0] + "_очередь.xlsx"
    from .review import export_queue
    export_queue(manual, queue_path)

    text = _report(args.folder, out, per, manual, written, skipped, failed, args.report_file)
    text += "\nОчередь для заполнения: " + queue_path
    text += ("\n(заполните колонку/сумму/дату, поставьте «да», затем: "
             "python -m pyparser.review --balance \"%s\" --queue \"%s\")" % (out, queue_path))
    if args.report_file:
        with io.open(args.report_file, "w", encoding="utf-8") as f:
            f.write(text + "\n")
    if not args.report_file:
        import sys
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
        print(text)


if __name__ == "__main__":
    main()
