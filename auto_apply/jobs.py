#!/usr/bin/env python3
"""Собирает вакансии со всех источников -> data/jobs.csv (без дублей).

    python3 auto_apply/jobs.py            # собрать всё
    python3 auto_apply/jobs.py --stats    # что уже в базе
"""
import csv, gzip, html, json, os, re, sys, time, urllib.parse, urllib.request
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config as C

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV_PATH = os.path.join(ROOT, "data", "jobs.csv")
# "note" — это score (порядок очереди), historical name. "user_note" — заметки
# Артема. "reqs" — текст вакансии, забирается при подаче: через месяц позвонит
# рекрутёр, и надо вспомнить, какой там был стек.
FIELDS = ["id", "source", "title", "company", "location", "salary", "url",
          "found", "status", "applied", "note", "user_note", "reqs"]


# ---------------------------------------------------------------- сеть

def get(url, data=None, headers=None):
    """GET/POST -> текст. Пустая строка вместо исключения: один упавший
    источник не должен ронять весь сбор."""
    hdrs = {"User-Agent": C.USER_AGENT, "Accept-Language": "sk,en;q=0.9"}
    if headers:
        hdrs.update(headers)
    body = data.encode() if isinstance(data, str) else data
    req = urllib.request.Request(url, data=body, headers=hdrs)
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            raw = r.read()
            if r.headers.get("Content-Encoding") == "gzip":
                raw = gzip.decompress(raw)
            return raw.decode("utf-8", "replace")
    except Exception as e:
        print(f"    ! {type(e).__name__}: {str(e)[:70]}", file=sys.stderr)
        return ""


# Удалённые источники: сюда физически ехать не надо, но нужен фильтр по региону
# и по тому, что вакансия вообще про IT. Список один на все три проверки ниже —
# раньше он был зашит в каждую отдельно и разъезжался при добавлении источника.
REMOTE_SOURCES = ("remotive", "remoteok", "arbeitnow", "jobicy",
                  "himalayas", "weworkremotely")


def clean(job):
    """Один проход чистки для всех источников: сущности, пробелы, мусор."""
    for k in ("title", "company", "location", "salary"):
        job[k] = re.sub(r"\s+", " ", html.unescape(str(job.get(k) or ""))).strip()
    return job


def it_job(job):
    """Мировая удалёнка сыпет Sales Advisor и Loss Prevention — режем."""
    if job["source"] not in REMOTE_SOURCES:
        return True
    return any(w in job["title"].lower() for w in C.TECH_WORDS)


def not_it(job):
    """Режет не-IT, пролезшее по слову junior/developer. Работает на всех
    источниках — 'Junior manažér rozvoja územia - developér' это застройщик."""
    return not any(w in job["title"].lower() for w in C.NOT_IT)


def region_ok(job):
    """'Remote — USA' из Словакии не наймут: нужен явный европейский регион."""
    if job["source"] not in REMOTE_SOURCES:
        return True
    loc = job["location"].lower()
    return (not loc.replace("remote", "").strip(" —-,")
            or any(w in loc for w in C.REGION_OK))


def strip_tags(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s))).strip()


# ------------------------------------------------------------ источники

def profesia(kw):
    """Profesia.sk — главный словацкий борд."""
    out = []
    for page in range(1, C.PAGES_PER_KEYWORD + 1):
        url = ("https://www.profesia.sk/praca/?search_anywhere="
               + urllib.parse.quote(kw) + f"&page_num={page}")
        page_html = html.unescape(get(url))
        rows = re.findall(r'<li class="list-row"[^>]*>(.*?)</li>', page_html, re.S)
        if not rows:
            break
        for row in rows:
            m = re.search(r"<span class='title'>(.*?)</span>", row, re.S)
            # Первая ссылка в строке бывает на страницу компании (/C123), а не на
            # объявление (/O123) — такие строки потом не отправить. Берём /O.
            u = (re.search(r'href="(/praca/[^"?]*/O\d+)', row)
                 or re.search(r'href="(/praca/[^"?]+)', row))
            if not (m and u):
                continue
            emp = re.search(r"<span class='employer'>(.*?)</span>", row, re.S)
            loc = re.search(r"class='job-location'>(.*?)</span>", row, re.S)
            sal = re.search(r'label label-bordered green[^"]*">(.*?)</span>', row, re.S)
            out.append(dict(
                source="profesia", title=strip_tags(m.group(1)),
                company=strip_tags(emp.group(1)) if emp else "",
                location=strip_tags(loc.group(1)) if loc else "",
                salary=strip_tags(sal.group(1)) if sal else "",
                url="https://www.profesia.sk" + u.group(1)))
        time.sleep(C.DELAY)
    return out


def linkedin(kw):
    """LinkedIn — публичный guest-эндпоинт, без логина."""
    out = []
    for start in range(0, C.PAGES_PER_KEYWORD * 25, 25):
        url = ("https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
               f"?keywords={urllib.parse.quote(kw)}&location=Slovakia&start={start}")
        page_html = get(url)
        cards = re.split(r'<li>\s*<div class="base-card', page_html)[1:]
        if not cards:
            break
        for card in cards:
            t = re.search(r'<span class="sr-only">\s*(.*?)\s*</span>', card, re.S)
            u = re.search(r'href="(https://[a-z]{2}\.linkedin\.com/jobs/view/[^"?]+)', card)
            if not (t and u):
                continue
            comp = re.search(r'hidden-nested-link"[^>]*>\s*(.*?)\s*</a>', card, re.S)
            loc = re.search(r'job-search-card__location">\s*(.*?)\s*</span>', card, re.S)
            out.append(dict(
                source="linkedin", title=strip_tags(t.group(1)),
                company=strip_tags(comp.group(1)) if comp else "",
                location=strip_tags(loc.group(1)) if loc else "", salary="",
                url=html.unescape(u.group(1))))
        time.sleep(C.DELAY)
    return out


def lang_ok(posting):
    """Дешёвая проверка языка по выдаче поиска.

    Ловит только явно объявленные языки и потому пропускает почти всё:
    настоящее требование лежит в карточке вакансии, а не в результатах
    поиска. Точную проверку делает nfj_lang_ok() — она стоит запроса."""
    vals = (posting.get("tiles") or {}).get("values") or []
    langs = [v.get("value") for v in vals if v.get("type") == "jobLanguage"]
    return not langs or any(l in C.MY_LANGUAGES for l in langs)


def nfj_lang_ok(url):
    """Точная проверка: язык из карточки вакансии NoFluffJobs.

    У Persooa заголовок английский, requirements.musts — сплошной HTML и
    JavaScript, а в requirements.languages стоит {"type": "MUST", "code": "pl"}.
    По выдаче поиска это не видно вообще: тайлы там пустые. Отсюда и взялась
    оценка "127 из 130 англоязычные", которая оказалась неверной.

    Нет данных — пропускаем: молчание не повод выбрасывать вакансию."""
    slug = url.rstrip("/").rsplit("/", 1)[-1]
    try:
        d = json.loads(get(f"https://nofluffjobs.com/api/posting/{slug}"))
    except Exception:
        return True
    musts = [l.get("code") for l in ((d.get("requirements") or {}).get("languages") or [])
             if l.get("type") == "MUST"]
    return not musts or any(code in C.MY_LANGUAGES for code in musts)


def nofluff(kw):
    """NoFluffJobs — IT-борд, отдаёт JSON."""
    url = ("https://nofluffjobs.com/api/search/posting?pageSize=60&region=sk"
           "&salaryCurrency=EUR&salaryPeriod=month")
    raw = get(url, data=json.dumps({"rawSearch": kw}),
              headers={"Content-Type": "application/json"})
    out = []
    try:
        postings = json.loads(raw).get("postings", [])
    except Exception:
        return out
    for p in postings:
        loc = p.get("location") or {}
        places = loc.get("places") or []
        remote = loc.get("fullyRemote")
        # NoFluff отдаёт всю Центральную Европу — оставляем SK и полную удалёнку
        if not remote and not any(
                (pl.get("country") or {}).get("code") == "SVK" for pl in places):
            continue
        if not lang_ok(p):
            continue                    # "Poľsky" в обязательных требованиях
        sal = p.get("salary") or {}
        out.append(dict(
            source="nofluff", title=p.get("title", ""), company=p.get("name", ""),
            location="Remote" if remote else ", ".join(
                pl.get("city", "") for pl in places[:3]),
            salary=(f"{sal.get('from','')}-{sal.get('to','')} "
                    f"{sal.get('currency','')}" if sal.get("from") else ""),
            url="https://nofluffjobs.com/sk/job/" + p.get("url", p.get("id", ""))))
    time.sleep(C.DELAY)
    return out


def remotive():
    """Remotive — мировая удалёнка, JSON."""
    out = []
    for cat in ("software-dev", "qa", "devops"):
        raw = get(f"https://remotive.com/api/remote-jobs?category={cat}&limit=100")
        try:
            for j in json.loads(raw).get("jobs", []):
                out.append(dict(
                    source="remotive", title=j.get("title", ""),
                    company=j.get("company_name", ""),
                    location="Remote — " + (j.get("candidate_required_location") or ""),
                    salary=j.get("salary", ""), url=j.get("url", "")))
        except Exception:
            pass
        time.sleep(C.DELAY)
    return out


def remoteok():
    """RemoteOK — мировая удалёнка, JSON."""
    raw = get("https://remoteok.com/api")
    out = []
    try:
        for j in json.loads(raw):
            if not j.get("position"):
                continue          # первый элемент — юридическая заглушка
            out.append(dict(
                source="remoteok", title=j.get("position", ""),
                company=j.get("company", ""),
                location="Remote — " + (j.get("location") or "anywhere"),
                salary=(f"{j.get('salary_min','')}-{j.get('salary_max','')} USD/y"
                        if j.get("salary_min") else ""),
                url=j.get("url", "")))
    except Exception:
        pass
    return out


def arbeitnow():
    """Arbeitnow — немецкая биржа с открытым API. Берём только удалёнку:
    в штутгартский офис из Братиславы не наездишься."""
    out = []
    try:
        for j in json.loads(get("https://www.arbeitnow.com/api/job-board-api")).get("data", []):
            if not j.get("remote"):
                continue
            out.append(dict(
                source="arbeitnow", title=j.get("title", ""),
                company=j.get("company_name", ""),
                location="Remote — Germany, " + (j.get("location") or ""),
                salary="", url=j.get("url", "")))
    except Exception:
        pass
    return out


def jobicy():
    """Jobicy — удалёнка с фильтром по региону прямо в запросе."""
    out = []
    for ind in ("engineering", "dev", "data-science", "supporting"):
        try:
            raw = get(f"https://jobicy.com/api/v2/remote-jobs?count=50&geo=europe&industry={ind}")
            for j in json.loads(raw).get("jobs", []):
                lo, hi = j.get("annualSalaryMin"), j.get("annualSalaryMax")
                out.append(dict(
                    source="jobicy", title=j.get("jobTitle", ""),
                    company=j.get("companyName", ""),
                    location="Remote — " + (j.get("jobGeo") or ""),
                    salary=(f"{lo}-{hi} {j.get('salaryCurrency','')}/y" if lo and hi else ""),
                    url=j.get("url", "")))
        except Exception:
            pass
        time.sleep(C.DELAY)
    return out


def himalayas():
    """Himalayas — удалёнка. Доска общая и в основном американская: из сотни
    вакансий по гео и профилю проходит одна-две, поэтому один запрос без
    пагинации — дальше идёт тот же мусор, только дольше."""
    out = []
    try:
        for j in json.loads(get("https://himalayas.app/jobs/api?limit=100")).get("jobs", []):
            hi = j.get("maxSalary")
            out.append(dict(
                source="himalayas", title=j.get("title", ""),
                company=j.get("companyName", ""),
                location="Remote — " + ", ".join(j.get("locationRestrictions") or []),
                # minSalary у части вакансий почасовой — годовым считаем только
                # явно крупные числа, иначе в CSV поедет мусор
                salary=(f"{j.get('minSalary')}-{hi} USD/y" if hi and hi > 1000 else ""),
                url=j.get("applicationLink") or j.get("url", "")))
    except Exception:
        pass
    return out


def weworkremotely():
    """We Work Remotely — RSS. Заголовок вида 'Компания: Должность'."""
    out = []
    for cat in ("remote-programming-jobs", "remote-devops-sysadmin-jobs",
                "remote-back-end-programming-jobs", "remote-full-stack-programming-jobs"):
        try:
            raw = get(f"https://weworkremotely.com/categories/{cat}.rss")
            for item in re.findall(r"<item>(.*?)</item>", raw, re.S):
                def tag(name):
                    m = re.search(rf"<{name}>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</{name}>", item, re.S)
                    return strip_tags(m.group(1)) if m else ""
                head = tag("title")
                company, _, title = head.partition(": ")
                out.append(dict(
                    source="weworkremotely", title=(title or head),
                    company=(company if title else ""),
                    location="Remote — " + (tag("region") or "anywhere"),
                    salary="", url=tag("link")))
        except Exception:
            pass
        time.sleep(C.DELAY)
    return out


def fetch_reqs(url, limit=1500):
    """Текст вакансии для поиска задним числом. Пустая строка при неудаче —
    подача важнее, чем эта справка."""
    page = get(url)
    if not page:
        return ""
    body = re.sub(r"(?is)<(script|style|nav|footer|header|svg)[^>]*>.*?</\1>", " ", page)
    return strip_tags(body)[:limit]


# ------------------------------------------------------------- фильтр

def reachable(job):
    """Доедем ли туда физически (или это удалёнка)."""
    if job["source"] in REMOTE_SOURCES:
        return True                     # по определению удалёнка
    blob = f"{job['location']} {job['title']}".lower()
    if any(w in blob for w in C.OK_PLACES):
        return True                     # Братислава/Трнава указана явно
    if any(w in blob for w in C.BAD_PLACES):
        return False                    # далёкий город, и близкого нет:
                                        # "hybrid v Žiline" — это всё равно Žilina
    return any(w in blob for w in C.REMOTE_WORDS)


def worth_it(job):
    t = job["title"].lower()
    if any(w in t for w in C.HARD_SKIP):
        return False
    # Сеньорское режем, если вакансия не открыта и джуну: "Junior/Senior Python".
    return not re.search(C.SENIOR_RE, t) or bool(re.search(C.JUNIOR_RE, t))


def score(job):
    """Чем выше, тем раньше подаваться. Не фильтр — только порядок."""
    t = job["title"].lower()
    s = 0
    for w, p in (("junior", 40), ("trainee", 40), ("intern", 35), ("graduate", 35),
                 ("entry", 30), ("začiatočník", 30), ("absolvent", 30)):
        if w in t:
            s += p
    for w, p in (("python", 25), ("fastapi", 20), ("backend", 15), ("django", 15),
                 ("api", 8), ("qa", 10), ("tester", 10), ("support", 8),
                 ("javascript", 8), ("react", 8), ("sql", 6)):
        if w in t:
            s += p
    for w, p in (("senior", -30), ("lead", -25), ("manager", -20),
                 ("expert", -15), ("medior", -8),
                 # "Global Architect" и "Vedúci oddelenia" не содержат senior
                 # и раньше набирали ровно 0, то есть проходили как обычные.
                 ("architect", -25), ("principal", -30), ("head of", -40),
                 ("vedúci", -25), ("manažér", -20), ("staff ", -20)):
        if w in t:
            s += p
    if any(w in f"{job['location']}".lower() for w in C.REMOTE_WORDS):
        s += 12
    if job["salary"]:
        s += 5
    return s


def job_id(job):
    """Стабильный ключ. Если в ссылке есть id объявления — берём его: он не зависит
    от того, как записали название компании, и не плодит дубли."""
    m = re.search(r"/O(\d+)|/jobs/view/(\d+)|(\d{10})", job.get("url", "") or "")
    if m:
        return "id" + (m.group(1) or m.group(2) or m.group(3))
    key = re.sub(r"[^a-z0-9]", "",
                 (job["company"] + job["title"]).lower())[:60]
    return key or re.sub(r"[^a-z0-9]", "", job["url"].lower())[-40:]


# ------------------------------------------------------------ хранилище

def load():
    if not os.path.exists(CSV_PATH):
        return {}
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        return {r["id"]: r for r in csv.DictReader(f)}


def save(rows):
    os.makedirs(os.path.dirname(CSV_PATH), exist_ok=True)
    ordered = sorted(rows.values(),
                     key=lambda r: (r["status"] != "new", -int(r.get("note") or 0)))
    with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows({k: r.get(k, "") for k in FIELDS} for r in ordered)


def stats():
    rows = load()
    if not rows:
        return print("База пуста. Запусти: python3 auto_apply/jobs.py")
    by = {}
    for r in rows.values():
        by[r["status"]] = by.get(r["status"], 0) + 1
    print(f"\nВсего вакансий: {len(rows)}")
    for k, v in sorted(by.items(), key=lambda x: -x[1]):
        print(f"  {k:10} {v}")
    print("\nТоп-15 в очереди:\n")
    queue = [r for r in rows.values() if r["status"] == "new"]
    queue.sort(key=lambda r: -int(r.get("note") or 0))
    for r in queue[:15]:
        print(f"  [{r['note']:>3}] {r['title'][:52]:52} | {r['company'][:22]:22} "
              f"| {r['source']}")
    print()


# ---------------------------------------------------------------- main

def main():
    if "--stats" in sys.argv:
        return stats()

    known = load()
    before = len(known)
    found = []

    for kw in C.KEYWORDS:
        print(f"  поиск: {kw}", flush=True)
        for fn in (profesia, linkedin, nofluff):
            found += fn(kw)

    print("  поиск: мировая удалёнка", flush=True)
    for fn in (remotive, remoteok, arbeitnow, jobicy, himalayas, weworkremotely):
        got = fn()
        print(f"    {fn.__name__}: {len(got)}", flush=True)
        found += got

    added = skipped = 0
    for j in found:
        if not j.get("title") or not j.get("url"):
            continue
        j = clean(j)
        if not (worth_it(j) and reachable(j) and it_job(j)
                and region_ok(j) and not_it(j)):
            skipped += 1
            continue
        jid = job_id(j)
        if jid in known:
            continue
        known[jid] = dict(j, id=jid, found=date.today().isoformat(),
                          status="new", applied="", note=str(score(j)))
        added += 1

    save(known)
    print(f"\nНайдено сырых: {len(found)}   отсеяно по гео/уровню: {skipped}")
    print(f"Новых в очереди: {added}   всего в базе: {len(known)} (было {before})")
    print(f"\n{CSV_PATH}")
    print("Дальше:  python3 auto_apply/apply.py --next 20")


if __name__ == "__main__":
    main()
