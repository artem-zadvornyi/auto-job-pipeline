#!/usr/bin/env python3
"""Подача заявок по очереди из data/jobs.csv.

    python3 auto_apply/apply.py --next 20            # основной режим: гонит по очереди
    python3 auto_apply/apply.py --next 20 --remote   # только удалёнка
    python3 auto_apply/apply.py --followup  # что пора пинговать (7+ дней тишины)
    python3 auto_apply/apply.py --cl "Firma" "Position"   # только письмо в буфер

В режиме --next на каждую вакансию: письмо подставляется под компанию и
кладётся в буфер обмена, вакансия открывается в Chrome. Ты вставляешь и
жмёшь Submit. Enter — засчитать и дальше, s — пропустить, q — выход.
"""
import csv, os, re, subprocess, sys, unicodedata
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config as C
from jobs import CSV_PATH, FIELDS, REMOTE_SOURCES, it_job, not_it, load, save, worth_it

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CL_TEMPLATE = os.path.join(ROOT, C.COVER_LETTER)
CV_PDF = os.path.join(ROOT, C.CV_FILE)
FOLLOWUP_DAYS = 7

BOLD, DIM, GREEN, YELLOW, RESET = "\033[1m", "\033[2m", "\033[32m", "\033[33m", "\033[0m"


# Словацкие объявления пишут обе формы рода: "Developer/Developerka",
# "programátor/programátorka", "Inžinier/ka", "m/ž". В английское письмо
# это лезет дословно и выглядит дико.
GENDER = re.compile(r"\s*[\(\[]?\s*\b[mfwžMFWŽ]\s*/\s*[mfwžMFWŽ]\b\s*[\)\]]?", re.I)
SUFFIX = re.compile(r"\b(\w{3,})/(?:ka|ová|ova|á|a)\b", re.I)
LEGAL = re.compile(r"[,\s]+(s\.?\s*r\.?\s*o\.?|a\.?\s*s\.?|spol\.?\s*s\s*r\.?\s*o\.?"
                   r"|k\.?\s*s\.?|GmbH|AG|Ltd\.?|Inc\.?|LLC|s\.\s*p\.?)\s*$", re.I)


def clean_title(t):
    """'PL/SQL Developer/Developerka Junior' -> 'PL/SQL Developer Junior'."""
    t = GENDER.sub(" ", t)
    t = SUFFIX.sub(r"\1", t)                       # Inžinier/ka -> Inžinier
    # Word/Wordka -> Word. 'PL/SQL' не трогаем: SQL не начинается с PL.
    t = re.sub(r"\b(\w{4,})/(\w+)\b",
               lambda m: m.group(1) if m.group(2).lower().startswith(m.group(1).lower())
               else m.group(0), t)
    parts = re.split(r"\s+[-–—]\s+", t)
    if len(parts) > 1:
        head, tail = parts[0], " - ".join(parts[1:])
        if any(head.lower().startswith(p) for p in C.OK_PLACES + C.BAD_PLACES):
            t = tail          # "Bratislava - Pantheon Academy" -> "Pantheon Academy"
        elif len(head.split()) >= 2:
            t = head          # "Junior Developer - skvelý začiatok..." -> голова
                              # 1 слово в голове не режем: съело бы половину названия
    return re.sub(r"\s{2,}", " ", t).strip(" -–—,")


def clean_company(c):
    """'I.S.D.D. plus, s.r.o.' -> 'I.S.D.D. plus'."""
    return LEGAL.sub("", c).strip(" ,.") or c


def make_cl(company, position):
    """Подставляет компанию и должность -> (тема письма, текст).

    Тема отделена от тела: в форму на сайте вставляется только тело,
    иначе в поле сообщения попадает строка "SUBJECT:"."""
    with open(CL_TEMPLATE, encoding="utf-8") as f:
        text = f.read()
    text = (text.replace("{company}", clean_company(company) or "your company")
                .replace("{position}", clean_title(position) or "advertised"))
    subject, _, body = text.partition("\n")
    return subject.replace("SUBJECT:", "").strip(), body.strip()


def to_clipboard(text):
    # Без LC_CTYPE pbcopy калечит не-ASCII (тире, диакритику).
    subprocess.run(["pbcopy"], input=text.encode("utf-8"), check=False,
                   env=dict(os.environ, LC_CTYPE="UTF-8"))


def open_url(url):
    subprocess.run(["open", "-a", "Google Chrome", url], check=False)


def is_remote(r):
    """Настоящая удалёнка, а не 'hybrid'. REMOTE_WORDS содержит 'hybrid',
    потому что для reachable() гибрид в Братиславе — это достижимо; здесь
    же нужен именно дом, поэтому гибрид отбрасываем."""
    if r.get("source") in REMOTE_SOURCES:
        return True
    loc = (r.get("location") or "").lower()
    return any(w in loc for w in C.REMOTE_WORDS if w != "hybrid")


def sendable(r):
    """Проверка перед самой отправкой, а не только при сборе вакансий.

    Очередь копится днями и переживает правки фильтров: запись, добавленная
    старой версией кода, потом уходит на почту по правилам, которых уже нет.
    Так на Head of Engineering и Senior Azure Architect ушло 27 откликов от
    джуна без коммерческого опыта. Последний рубеж закрывает эту дыру."""
    if int(r.get("note") or 0) < C.MIN_SCORE:
        return False
    return worth_it(r) and not_it(r) and it_job(r)


# Юридические и общие слова: "Zurich Insurance Company Ltd, organizačná zložka"
# и "Zurich Insurance" — одна фирма. Лимит обходили через такие варианты.
_CO_STOP = set("sro s r o as a spol ltd gmbh inc llc ag company group organizacna "
               "zlozka slovakia slovensko czech republic cz sk part of the".split())
# Первое слово, по которому фирму не узнать: "Slovenská sporiteľňa" и
# "Slovenská národná galéria" — разные.
_CO_WEAK = set("slovenska slovensky slovenske narodna narodny narodne vseobecna pro it "
               "global digital international euro slovak tatra".split())


def company_key(s):
    """Один ключ компании для лимита и для дублей.
    ponytail: ключ = первое длинное слово, так что Swiss Re и Swiss Life
    склеятся. Это безопасная сторона (откликов меньше); если начнёт мешать —
    словарь алиасов."""
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    w = [x for x in re.findall(r"[a-z0-9]+", s) if x not in _CO_STOP]
    if not w:
        return ""
    return " ".join(w[:2]) if len(w[0]) < 5 or w[0] in _CO_WEAK else w[0]


def _co(r):
    return company_key(r.get("company"))


def queue(rows, remote_only=False):
    """Очередь на отправку. Сверх sendable(): не больше MAX_PER_COMPANY откликов
    в одну компанию за COMPANY_WINDOW_DAYS и без дублей — репост той же
    должности с новым ID это та же вакансия. 12.09 хедхантер PROBS назвал
    10 откликов от бота спамом. Пустую компанию не лимитируем: не знаем чья."""
    since = (date.today() - timedelta(days=C.COMPANY_WINDOW_DAYS)).isoformat()
    per_co, seen = {}, set()
    for r in rows.values():
        if r["status"] not in C.SENT or not _co(r):
            continue
        seen.add((_co(r), clean_title(r["title"]).lower()))
        if (r.get("applied") or since) >= since:        # без даты — считаем свежим
            per_co[_co(r)] = per_co.get(_co(r), 0) + 1

    q = [r for r in rows.values() if r["status"] == "new" and sendable(r)]
    if remote_only:
        q = [r for r in q if is_remote(r)]
    q.sort(key=lambda r: -int(r.get("note") or 0))
    out = []
    for r in q:
        co = _co(r)
        if co:
            key = (co, clean_title(r["title"]).lower())
            if key in seen or per_co.get(co, 0) >= C.MAX_PER_COMPANY:
                continue
            seen.add(key)
            per_co[co] = per_co.get(co, 0) + 1
        out.append(r)
    return out


def run_next(limit, remote_only=False):
    rows = load()
    q = queue(rows, remote_only)
    if not q:
        return print("Очередь пуста. Собери вакансии: python3 auto_apply/jobs.py")

    print(f"\n{BOLD}В очереди {len(q)}. Прогоняем {min(limit, len(q))}.{RESET}")
    print(f"{DIM}CV для загрузки: {CV_PDF}{RESET}")
    print(f"{DIM}Enter — подал  |  s — пропустить  |  q — выход{RESET}\n")

    done = skipped = 0
    for n, job in enumerate(q[:limit], 1):
        subject, body = make_cl(job["company"], job["title"])
        to_clipboard(body)
        with open(os.path.join(ROOT, "data", "last_cl.txt"), "w", encoding="utf-8") as f:
            f.write(f"{subject}\n\n{body}")

        print(f"{BOLD}[{n}/{min(limit, len(q))}] {job['title']}{RESET}")
        print(f"      {job['company']}  ·  {job['location'][:55]}")
        if job["salary"]:
            print(f"      {GREEN}{job['salary']}{RESET}")
        print(f"      {DIM}{job['source']} · score {job['note']}{RESET}")
        print(f"      {job['url']}")
        print(f"      {DIM}тема письма: {subject}{RESET}")
        print(f"      {GREEN}письмо в буфере — Cmd+V{RESET}")
        open_url(job["url"])

        try:
            ans = input(f"      {YELLOW}>{RESET} ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\nПрервано.")
            break

        if ans == "q":
            break
        if ans == "s":
            rows[job["id"]]["status"] = "skipped"
            skipped += 1
        else:
            rows[job["id"]]["status"] = "applied"
            rows[job["id"]]["applied"] = date.today().isoformat()
            done += 1
        save(rows)
        print()

    total = sum(1 for r in load().values() if r["status"] == "applied")
    print(f"\n{GREEN}Подано за сессию: {done}{RESET}   пропущено: {skipped}")
    print(f"Всего подано: {BOLD}{total}{RESET}")


def run_followup():
    """Кто молчит 7+ дней. Ошибка с Iron Mountain — молча ждать."""
    rows = load()
    today = date.today()
    due = []
    for r in rows.values():
        if r["status"] != "applied" or not r["applied"]:
            continue
        try:
            days = (today - datetime.fromisoformat(r["applied"]).date()).days
        except ValueError:
            continue
        if days >= FOLLOWUP_DAYS:
            due.append((days, r))

    if not due:
        return print(f"Нечего пинговать (порог {FOLLOWUP_DAYS} дней).")

    due.sort(reverse=True, key=lambda x: x[0])
    print(f"\n{BOLD}Молчат {FOLLOWUP_DAYS}+ дней: {len(due)}{RESET}\n")
    for days, r in due:
        print(f"  {days:>3}д  {r['title'][:45]:45} | {r['company'][:25]:25}")
        print(f"        {DIM}{r['url']}{RESET}")
    print(f"\n{DIM}Пингуй ответом в переписке или через форму. "
          f"Пометил как pinged:{RESET}")
    if input("  Пометить все как pinged? [y/N] ").strip().lower() == "y":
        for _, r in due:
            rows[r["id"]]["status"] = "pinged"
        save(rows)
        print(f"{GREEN}Готово.{RESET}")


def main():
    a = sys.argv[1:]
    if not a or a[0] in ("-h", "--help"):
        return print(__doc__)
    if a[0] == "--next":
        remote_only = "--remote" in a
        nums = [x for x in a[1:] if x.isdigit()]
        return run_next(int(nums[0]) if nums else 20, remote_only)
    if a[0] == "--followup":
        return run_followup()
    if a[0] == "--cl":
        subject, body = make_cl(a[1] if len(a) > 1 else "",
                                a[2] if len(a) > 2 else "")
        to_clipboard(body)
        return print(f"Письмо в буфере.\nТема: {subject}")
    print(__doc__)


if __name__ == "__main__":
    main()
