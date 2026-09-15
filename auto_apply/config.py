"""Технические словари фильтров — одинаковые для любого пользователя.

Личное (контакты, ожидания, ключевые слова, города, CV, письмо) лежит в
profile.json в корне проекта. Здесь оно остаётся значениями по умолчанию:
без profile.json программа обязана работать ровно как раньше, иначе правка
конфига ломает запущенный поиск на полпути."""
import json as _json, os as _os

_PATH = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))),
                      "profile.json")
try:
    with open(_PATH, encoding="utf-8") as _f:
        _P = _json.load(_f)
except (OSError, ValueError):
    _P = {}


def _from_profile(key, default):
    """Пустой список в профиле — это опечатка, а не «искать ничего»."""
    return _P.get(key) or default

# Что ищем. Каждое слово = отдельный поиск на каждом сайте.
KEYWORDS = _from_profile('keywords', [
    "python", "junior developer", "backend", "fastapi", "django",
    "junior programátor", "trainee developer", "graduate developer",
    "javascript", "react", "node.js", "java junior", "c# junior",
    "qa tester", "manual tester", "automation tester",
    "it support", "helpdesk", "service desk",
    "devops junior", "data analyst junior", "sql developer",
])

# Города/регионы, куда физически доедем (≤100 км от Братиславы).
OK_PLACES = _from_profile('home_places', [
    "bratislav", "trnav", "senec", "pezinok", "malacky", "modra",
    "nitra", "trenč", "trencin", "piešťan", "piestan", "sereď", "sered",
    "galant", "hlohovec", "dunajská streda", "dunajska streda", "šamorín", "samorin",
    "skalica", "senica", "hainburg", "wien", "vienna", "kittsee",
])
# Признаки удалёнки — их берём независимо от города.
REMOTE_WORDS = [
    "remote", "home office", "práca z domu", "praca z domu", "z domu",
    "homeoffice", "work from home", "anywhere", "fully remote", "hybrid",
]
# Явно далеко — выбрасываем, если не удалёнка.
BAD_PLACES = _from_profile('avoid_places', [
    "košic", "kosic", "prešov", "presov", "žilin", "zilin", "poprad",
    "banská bystric", "banska bystric", "martin", "zvolen", "michalovce",
    "humenné", "humenne", "liptovsk", "spišsk", "spissk", "lučenec", "lucenec",
    "trebišov", "trebisov", "vranov", "bardejov", "svidník", "svidnik", "rimavsk",
    "komárno", "komarno", "levice", "topoľčany", "topolcany", "považsk", "povazsk",
])

# Слова, из-за которых вакансию не показываем (реально бессмысленно подаваться).
HARD_SKIP = [
    "10+ years", "10 rokov", "head of", "chief ", "cto", "director",
    "vp of", "vice president", "principal engineer", "staff engineer",
    "architect with", "president",
]

# Артём 13.09.2026 отменил «сеньоров шлём тоже»: хедхантер PROBS пригрозил
# чёрным списком за рассылку CV ботом (Head of..., Enterprise Architect).
# Регэкспы, а не подстроки: "intern" не должно ловить "international".
SENIOR_RE = r"\b(senior|sr\b|head\b|architect|architekt|vedúc)"   # sr\b: и "Sr.", и "Sr Data"
JUNIOR_RE = r"\b(junior|trainee|intern\b|internship|graduate|absolvent|entry\b)"

# SOFTEC получил 22 отклика за неделю — это спам, а не поиск работы.
MAX_PER_COMPANY = 3
COMPANY_WINDOW_DAYS = 30
# Статусы, при которых отклик уже ушёл.
SENT = ("applied", "replied", "interview", "rejected", "offer", "pinged")

# Мировая удалёнка (remotive/remoteok) сыпет не-IT мусором и вакансиями
# "Remote — USA", куда из Словакии не наймут. Два фильтра ниже режут это.
TECH_WORDS = [
    "developer", "engineer", "programmer", "python", "java", "javascript",
    "typescript", "react", "node", "backend", "frontend", "fullstack",
    "full stack", "full-stack", "devops", "sre", "qa", "tester", "testing",
    "software", "api", "sql", "database", "data analyst", "data engineer",
    "web", "cloud", "automation", "it support", "helpdesk", "technical support",
    "django", "fastapi", "php", "ruby", "golang", " go ", "c#", ".net", "scrum",
]
# Явно не-IT, хотя в названии есть "junior"/"developer". Словацкое
# "developér" = застройщик недвижимости, а не разработчик — классика.
NOT_IT = [
    "actuarial", "aktuár", "poisťov", "rozvoja územia", "nehnuteľnost",
    "real estate", "reality", "key account", "fúzie", "akvizíc",
    "account manager", "sales manager", "obchodný zástupca", "obchodná zástupkyňa",
    "predajca", "predavač", "účtovní", "mzdov", "recruiter", "náborov",
    "marketing manager", "brand manager", "kuchár", "vodič", "skladník",
    "upratov", "čašník", "operátor výroby", "montážn", "zvárač",
    # Добралось до отправки в августе 2026 и потребовало ручной чистки:
    "obchodník", "obchodníčka", "telefonický predaj", "hr generalist",
    "hr špecialist", "hr manager", "personalist", "bozp", "požiarn",
    "grafik", "grafick", "business konzultant", "business consultant",
    "tax analyst", "daňov", "learning experience", "bezpečnostný technik",
]

# Минимальный score для отправки. Ниже нуля опускают только штрафы за
# сеньорность — джуну без коммерческого опыта там делать нечего.
# 0, а не выше: "Software Developer" и "AI Engineer" тоже дают ровно 0,
# и это нормальные для него вакансии.
MIN_SCORE = _P.get("min_score", 0)

# Языки, на которых кандидат реально работает. NoFluffJobs объявляет требуемый
# язык отдельным полем: из вакансий уровня junior там половина польские или
# немецкие, и по заголовку это не видно — заголовок английский, а в "Musí mať"
# стоит "Poľsky". Чешский оставлен: со словацким взаимно понятен.
MY_LANGUAGES = _P.get("languages", ["en", "sk", "cs", "uk", "ru"])

# Регионы, откуда реально возьмут человека из Словакии.
REGION_OK = _from_profile('region_ok', [
    "europe", "emea", "worldwide", "anywhere", "global", "slovak", "czech",
    "eu ", "eu,", "(eu", "cet", "gmt", "germany", "poland", "austria",
    "united kingdom", "uk,", "netherlands", "international",
])

# Сколько страниц листать на каждый запрос (20 вакансий на страницу).
PAGES_PER_KEYWORD = 2

# Сеть
USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")
DELAY = 1.2          # пауза между запросами, секунд — не злим сайты

# Твои данные (подставляются в письма)
_ME_DEFAULT = {
    "name":  "Artem Zadvornyi",
    "email": "zadvornyiartem1@gmail.com",
    "phone": "+421 917 860 112",
}
ME = _from_profile('me', _ME_DEFAULT)

# Ожидания по условиям — ответ на вопрос "Aká je Vaša očakávaná hrubá mzda?"
# Не фильтр для поиска: многие джуновые вакансии в SK стартуют с 1200-1600,
# и подаваться туда всё равно имеет смысл. Это то, что пишем, когда спрашивают.
_EXPECTED_DEFAULT = {
    "salary_eur":  1700,                       # brutto/мес - ЦЕЛЬ, не фильтр
    "salary_floor_fulltime": 1300,             # brutto, полная ставка - ниже не идём
    "salary_floor_parttime": 800,              # ЧИСТЫМИ, только для пол ставки
    "salary_text": "1700 € brutto, dohodou",
    "hours":       "plný úväzok, 8-9 h denne",
    "work_mode":   "preferujem home office, ale office aj hybrid su OK",
    "start":       "ihneď",
}
EXPECTED = _from_profile('expected', _EXPECTED_DEFAULT)


# Файлы кандидата. Пути относительно корня проекта.
CV_FILE = _P.get("cv_file", "CV/Artem_Zadvornyi_CV.pdf")
COVER_LETTER = _P.get("cover_letter", "CL/cover_letter.txt")

# Не подаваться на бесплатное: волонтёрство, "оплата долей", неоплачиваемые стажировки.
# Артём 01.09.2026: работать без денег он не будет. Оплачиваемые стажировки - можно.
UNPAID = (
    "volunteer", "voluntary", "unpaid", "no salary", "equity only", "equity-only",
    "equity based", "equity-based", "(equity)", "co-founder", "cofounder",
    "bez odmeny", "dobrovoľn", "neplaten",
)
