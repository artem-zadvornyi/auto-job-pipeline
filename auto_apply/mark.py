#!/usr/bin/env python3
"""Отметить вакансию поданной — когда подаёшь не через очередь (LinkedIn, вручную).

    python3 auto_apply/mark.py "Mindrift" "Chatbot Developer" https://...
    python3 auto_apply/mark.py "ESET" "QA Tester" --status skipped --note "нужен C#"

Если вакансии нет в базе — добавит. Текст вакансии подтянет сам, чтобы потом
можно было найти по стеку.
"""
import os, sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jobs as J


def mark(company, title, url="", status="applied", note="", fetch=True):
    rows = J.load()
    jid = J.job_id({"company": company, "title": title, "url": url})
    row = rows.get(jid)
    new = row is None
    if new:
        row = {"id": jid, "source": "linkedin", "title": title, "company": company,
               "location": "", "salary": "", "url": url, "note": "0",
               "found": date.today().isoformat(), "user_note": "", "reqs": ""}
        rows[jid] = row

    row["status"] = status
    row["applied"] = date.today().isoformat() if status != "new" else ""
    if note:
        row["user_note"] = note
    if url and not row.get("url"):
        row["url"] = url
    # текст вакансии — то, по чему потом искать «кто мне звонит»
    if fetch and url and not row.get("reqs"):
        row["reqs"] = J.fetch_reqs(url)

    J.save(rows)
    return "добавлено" if new else "обновлено"


def main():
    a = [x for x in sys.argv[1:] if not x.startswith("--")]
    if len(a) < 2:
        return print(__doc__)
    flags = sys.argv[1:]

    def flag(name, default=""):
        return flags[flags.index(name) + 1] if name in flags else default

    what = mark(a[0], a[1], a[2] if len(a) > 2 else "",
                status=flag("--status", "applied"), note=flag("--note"))
    print(f"{what}: {a[1]} — {a[0]}")


if __name__ == "__main__":
    main()
