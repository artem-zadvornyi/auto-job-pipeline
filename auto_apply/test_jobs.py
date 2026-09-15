#!/usr/bin/env python3
"""Проверка фильтров и скоринга:  python3 auto_apply/test_jobs.py

Ломается, если правка config.py начнёт пропускать далёкие города,
не-IT мусор или вакансии, куда из Словакии не наймут."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jobs as J
import config as C


def job(title="Developer", loc="", src="profesia", company="X", salary=""):
    return dict(title=title, location=loc, source=src, company=company,
                salary=salary, url="http://x/" + title)


# --- гео: куда доедем ---------------------------------------------------
assert J.reachable(job(loc="Bratislava, Slovensko"))
assert J.reachable(job(loc="Trnava"))
assert J.reachable(job(loc="Práca z domu"))
assert J.reachable(job(loc="Remote work"))
assert not J.reachable(job(loc="Košice"))
assert not J.reachable(job(loc="Prešov, hybrid")), "гибрид в Прешове — это Прешов"
assert J.reachable(job(title="Žilina/Bratislava Academy", loc="Žilina, Bratislava")), \
    "если Братислава есть в списке — берём"
assert not J.reachable(job(loc="Banská Bystrica, home office 2 dni"))

# --- мировая удалёнка: регион и профиль ---------------------------------
assert J.region_ok(job(loc="Remote — Europe", src="remotive"))
assert J.region_ok(job(loc="Remote — anywhere", src="remoteok"))
assert J.region_ok(job(loc="Remote", src="remoteok")), "регион не указан — берём"
assert not J.region_ok(job(loc="Remote — USA", src="remotive"))
assert not J.region_ok(job(loc="Remote — Brisbane", src="remoteok"))
assert J.region_ok(job(loc="Košice", src="profesia")), "локальные — не этот фильтр"

assert J.it_job(job(title="Backend Engineer", src="remoteok"))
assert not J.it_job(job(title="Sales Advisor", src="remoteok"))
assert not J.it_job(job(title="Loss Prevention Officer", src="remotive"))
assert J.it_job(job(title="Sales Advisor", src="profesia")), "SK-борды не режем"

assert not J.not_it(job(title="Junior Actuarial Analyst")), "страхование — не IT"
assert not J.not_it(job(title="Junior manažér rozvoja územia - developér")), \
    "developér по-словацки = застройщик"
assert J.not_it(job(title="Junior Softvérový Inžinier")), "словацкие IT-названия оставляем"
assert J.not_it(job(title="Programátor/programátorka C++"))
assert J.not_it(job(title="IT technik junior"))

# --- уровень ------------------------------------------------------------
# Артём 13.09.2026: сеньоров больше не шлём — PROBS пригрозил чёрным списком.
for t in ("Senior Python Developer", "Enterprise Architect (IFS ERP)",
          "Seniorný dátový analytik", "Vedúci IT oddelenia", "Sr. Data Engineer",
          "Softvérový architekt", "Senior Developer, international team",
          "Sr Data Analytics, Maintenance & Reporting Analyst"):
    assert not J.worth_it(job(title=t)), f"должно резаться: {t}"
assert J.worth_it(job(title="Junior/Senior Python Developer")), "открыто и джуну"
assert J.worth_it(job(title="Senior Trainee Program")), "trainee — открыто джуну"
assert J.worth_it(job(title="Python Developer"))
assert not J.worth_it(job(title="Head of Engineering"))
assert not J.worth_it(job(title="Vice President, Technology"))

# --- порядок очереди ----------------------------------------------------
jr = J.score(job(title="Junior Python Developer", loc="Bratislava"))
sr = J.score(job(title="Senior Python Developer", loc="Bratislava"))
tr = J.score(job(title="Trainee Developer", loc="Remote"))
assert jr > sr, "джуниор должен идти раньше сеньора"
assert tr > sr
assert J.score(job(title="Junior Python Developer", loc="Práca z domu")) > jr, \
    "удалёнка — приоритет"

# --- дедупликация -------------------------------------------------------
a = job(title="Junior Python Developer", company="ESET", src="profesia")
b = job(title="Junior Python Developer", company="ESET", src="linkedin")
assert J.job_id(a) == J.job_id(b), "одна вакансия на двух сайтах = одна строка"
assert J.job_id(a) != J.job_id(job(title="QA Tester", company="ESET"))

# --- чистка полей -------------------------------------------------------
assert J.clean(job(company="H&amp;M"))["company"] == "H&M"
assert J.clean(job(title="  A   B  "))["title"] == "A B"

# --- письмо -------------------------------------------------------------
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import apply as A
# словацкие двойные формы рода не должны попадать в английское письмо
assert A.clean_title("PL/SQL Developer/Developerka Junior") == "PL/SQL Developer Junior"
assert A.clean_title("Junior Softvérový Inžinier/ka") == "Junior Softvérový Inžinier"
assert A.clean_title("MES Špecialista junior m/ž") == "MES Špecialista junior"
assert A.clean_title("Junior Developer (F/M) - skvelý začiatok kariéry") == "Junior Developer"
assert A.clean_title("Bratislava - Pantheon Academy") == "Pantheon Academy", "город в начале"
assert "PL/SQL" in A.clean_title("PL/SQL Developer Junior"), "PL/SQL это не форма рода"
assert A.clean_company("I.S.D.D. plus, s.r.o.") == "I.S.D.D. plus"
assert A.clean_company("CODERAMA s. r. o.") == "CODERAMA"
assert A.clean_company("Canonical") == "Canonical"

subj, body = A.make_cl("ESET", "Junior Python Developer")
assert "SUBJECT" not in body, "тема не должна попадать в тело письма"
assert "ESET" in body and "Junior Python Developer" in body
assert "{company}" not in body and "{position}" not in body
assert subj.startswith("Application for")
assert "—" not in body, "длинные тире выдают машинный текст"
assert "'" in body, "живой текст пишут с сокращениями (I'm, I've)"

# --- удалённые источники ---------------------------------------------
# Список REMOTE_SOURCES раньше был зашит в трёх функциях порознь и разъезжался
# при добавлении источника: вакансия проходила reachable, но падала на it_job.
for src in J.REMOTE_SOURCES:
    j = job(title="Sandwich artist", loc="Remote — anywhere", src=src)
    assert J.reachable(j), f"{src}: удалёнка должна быть достижима"
    assert not J.it_job(j), f"{src}: не-IT мусор с удалённых досок надо резать"
    assert J.it_job(job(title="Backend Developer", loc="Remote — anywhere", src=src))

# Гео на удалёнке: пустой регион значит «откуда угодно», США — не наймут.
assert J.region_ok(job(loc="Remote —", src="himalayas")), "пустой регион = anywhere"
assert J.region_ok(job(loc="Remote — EMEA, LATAM", src="jobicy"))
assert J.region_ok(job(loc="Remote — Anywhere in the World", src="weworkremotely"))
assert not J.region_ok(job(loc="Remote — United States", src="himalayas"))
assert not J.region_ok(job(loc="Remote — USA, Canada", src="remotive"))

# WWR отдаёт заголовок как "Компания: Должность" — разбор не должен терять
# должность, если двоеточия нет вовсе.
head = "Gusto, Inc.: Staff Software Engineer"
company, _, title = head.partition(": ")
assert (company, title) == ("Gusto, Inc.", "Staff Software Engineer")
head2 = "Staff Software Engineer"
c2, _, t2 = head2.partition(": ")
assert (t2 or head2) == "Staff Software Engineer" and not t2

# --- фильтр --remote в отправлялке ------------------------------------
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import apply as A
assert A.is_remote(dict(source="jobicy", location=""))
assert A.is_remote(dict(source="profesia", location="Práca z domu"))
assert A.is_remote(dict(source="profesia", location="Bratislava, remote"))
assert not A.is_remote(dict(source="profesia", location="Bratislava, hybrid")), \
    "гибрид — это не удалёнка, даже если reachable() его пропускает"
assert not A.is_remote(dict(source="linkedin", location="Bratislava"))

# --- profile.json -----------------------------------------------------
# Личные данные вынесены в profile.json, чтобы программу можно было отдать
# другому человеку без правки кода. Без файла всё обязано работать по-старому.
import json, tempfile, importlib
assert C.ME.get("name") and C.ME.get("email"), "контакты не подхватились"
assert C.KEYWORDS and C.OK_PLACES and C.REGION_OK, "списки поиска пусты"
assert C.CV_FILE.endswith(".pdf") and C.COVER_LETTER.endswith(".txt")

root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if os.path.isdir(os.path.join(root, "CV")):
    assert os.path.exists(os.path.join(root, C.CV_FILE)), f"нет CV: {C.CV_FILE}"
assert os.path.exists(os.path.join(root, C.COVER_LETTER)), f"нет письма: {C.COVER_LETTER}"
assert os.path.exists(os.path.join(root, "profile.example.json")), "нет примера для покупателя"

# Пустой список в профиле — опечатка, а не «искать ничего»: берём умолчание.
_saved = C._P
C._P = {"keywords": ["a"]}
assert C._from_profile("keywords", ["x"]) == ["a"], "значение из профиля важнее умолчания"
C._P = _saved
assert C._from_profile("нет-такого-ключа", ["x"]) == ["x"]
_saved = C._P
C._P = {"keywords": []}
assert C._from_profile("keywords", ["x"]) == ["x"], "пустой список не должен обнулять поиск"
C._P = _saved

# --- язык вакансии ----------------------------------------------------
# Заголовок английский, а в требованиях "Poľsky" — по тайтлу не отличить.
def posting(*langs):
    return {"tiles": {"values": [{"value": l, "type": "jobLanguage"} for l in langs]}}

assert J.lang_ok(posting())                    # язык не указан = скорее всего en
assert J.lang_ok(posting("en"))
assert J.lang_ok(posting("pl", "en"))          # достаточно одного подходящего
assert J.lang_ok(posting("cs"))                # чешский со словацким понятен
assert not J.lang_ok(posting("pl")), "польский-only не должен проходить"
assert not J.lang_ok(posting("de")), "немецкий-only не должен проходить"

# Точная проверка ходит в сеть, поэтому проверяем только разбор ответа.
def musts(*codes):
    return {"requirements": {"languages": [{"type": "MUST", "code": c} for c in codes]}}

_orig = J.get
J.get = lambda url, **kw: json.dumps(_stub)
_stub = musts("pl"); assert not J.nfj_lang_ok("https://x/job/persooa")
_stub = musts("en"); assert J.nfj_lang_ok("https://x/job/ok")
_stub = musts("pl", "en"); assert J.nfj_lang_ok("https://x/job/either")
_stub = {"requirements": {"languages": [{"type": "NICE", "code": "pl"}]}}
assert J.nfj_lang_ok("https://x/job/nice"), "NICE — не требование"
_stub = {}; assert J.nfj_lang_ok("https://x/job/empty"), "нет данных — пропускаем"
J.get = _orig

# --- порог по score ---------------------------------------------------
assert C.MIN_SCORE == 0
assert J.score(job(title="Senior Java Developer")) < 0
assert J.score(job(title="Global Architect")) < 0, "архитектор без слова senior"
assert J.score(job(title="Head of Engineering")) < 0
assert J.score(job(title="Software Developer")) >= 0, "нормальная вакансия без ключевых слов"
assert J.score(job(title="AI Engineer")) >= 0

# --- не-IT, добравшееся до отправки в августе -------------------------
for t in ("Obchodník / obchodníčka pre samosprávy", "HR Generalista / HR špecialista",
          "Špecialista / špecialistka BOZP a PO", "Grafik / Web Editor",
          "Business Konzultant (m/ž) | ERP riešenia", "Sr. Data Tax Analyst"):
    assert not J.not_it(job(title=t)), f"должно резаться: {t}"

# --- лимит на компанию и дубли в очереди --------------------------------
from datetime import date, timedelta
def row(i, title, company, status="new", applied=""):
    return dict(id=f"id{i}", title=title, company=company, status=status,
                applied=applied, note="10", source="profesia", location="Bratislava",
                salary="", url=f"http://x/O{i}")
def ids(*rs):
    return [r["id"] for r in A.queue({r["id"]: r for r in rs})]

today = date.today().isoformat()
q = ids(row(1, "Tester", "SOFTEC, s.r.o.", "applied", today),
        row(2, "Analyst", "SOFTEC", "applied", today),
        row(3, "Developer", "SOFTEC a.s.", "pinged", today),
        row(4, "Support", "SOFTEC"),
        row(5, "Java Developer", "Asseco", "applied", today),
        row(6, "Java Developer", "Asseco"),
        row(7, "QA Engineer", "ESET"), row(8, "QA Engineer", "ESET"),
        row(9, "Developer", ""), row(10, "Tester", ""), row(11, "Support", ""),
        row(12, "Analyst", ""))
assert "id4" not in q, "4-я вакансия в одну компанию за 30 дней"
assert "id6" not in q, "репост той же должности с новым ID"
assert ("id7" in q) + ("id8" in q) == 1, "дубль внутри самой очереди"
assert {"id9", "id10", "id11", "id12"} <= set(q), "пустая компания — без лимита"
old = (date.today() - timedelta(days=31)).isoformat()
assert ids(row(1, "A", "X", "applied", old), row(2, "B", "X", "applied", old),
           row(3, "C", "X", "applied", old), row(4, "D", "X")) == ["id4"], \
    "старше 30 дней — лимит не держит"

# Одна фирма под разными написаниями — один ключ: лимит обходили через варианты.
for a, b in (("Zurich Insurance Company Ltd, organizačná zložka", "Zurich Insurance"),
             ("VOLKSWAGEN GROUP SERVICES, s.r.o.", "Volkswagen Group"),
             ("Synpulse Slovakia s.r.o.", "Synpulse"),
             ("Kanadevia Inova Slovensko s.r.o.", "Kanadevia Inova"),
             ("Multitude IT Labs (part of Multitude Group)", "Multitude"),
             ("MicroStep, spol. s r.o.", "MicroStep-MIS"),
             ("Ciklum", "Ciklum Czech Republic & Slovakia")):
    assert A.company_key(a) == A.company_key(b), f"должны склеиться: {a} / {b}"
for a, b in (("Slovenská sporiteľňa", "Slovenská národná galéria"),
             ("Pro HR", "PRO Business Solutions"),
             ("Pôdohospodárska platobná agentúra", "P.A.M.M."),
             ("Slovak Telekom", "Slovak Parcel Service"),
             ("Tatra banka", "Tatra Supercompute")):
    assert A.company_key(a) != A.company_key(b), f"не должны склеиться: {a} / {b}"
assert A.company_key("Slovak Telekom") == A.company_key("Slovak Telekom, a.s.")
assert A.company_key("") == ""
assert ids(row(1, "A", "Zurich Insurance Company Ltd, organizačná zložka", "applied", today),
           row(2, "B", "Zurich Insurance Company", "applied", today),
           row(3, "C", "Zurich Insurance Company", "applied", today),
           row(4, "D", "Zurich Insurance")) == [], "лимит не обходится другим написанием"
assert ids(row(1, "Java Developer", "Asseco Central Europe, a.s.", "applied", today),
           row(2, "Java Developer", "Asseco Central Europe")) == [], \
    "репост под другим написанием компании — дубль"

print("все проверки прошли")
