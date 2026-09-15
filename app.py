#!/usr/bin/env python3
"""Auto Job — окно приложения.

    python3 app.py

Поднимает локальный сервер и открывает окно Chrome без адресной строки.
Данные — тот же data/jobs.csv, что и у терминальных скриптов.
"""
import json, os, subprocess, sys, threading, webbrowser
from datetime import date, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "auto_apply"))
import jobs as J
import apply as A

PORT = 8765
DEADLINE = date(2026, 9, 30)
UI = os.path.join(ROOT, "ui.html")
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

_collecting = {"running": False, "log": ""}
_lock = threading.Lock()      # ponytail: один процесс — хватит; если запустишь
                              # апку и apply.py разом, последний save победит


# ------------------------------------------------------------------ данные

def stats(rows):
    today = date.today()
    applied = [r for r in rows if r["status"] in
               ("applied", "replied", "interview", "rejected", "offer")]
    done_today = sum(1 for r in applied if r.get("applied") == today.isoformat())
    days_left = max((DEADLINE - today).days, 0)
    return {
        "total": len(rows),
        "queue": sum(1 for r in rows if r["status"] == "new"),
        "applied": len(applied),
        "today": done_today,
        "replied": sum(1 for r in rows if r["status"] in
                       ("replied", "interview", "offer")),
        "interview": sum(1 for r in rows if r["status"] == "interview"),
        "offer": sum(1 for r in rows if r["status"] == "offer"),
        "rejected": sum(1 for r in rows if r["status"] == "rejected"),
        "days_left": days_left,
        "deadline": DEADLINE.isoformat(),
        "followups": sum(1 for r in rows if needs_followup(r)),
        "collecting": _collecting["running"],
    }


def needs_followup(r):
    """Молчат 7+ дней. То, чего не было с Iron Mountain."""
    if r["status"] != "applied" or not r.get("applied"):
        return False
    try:
        return (date.today() - datetime.fromisoformat(r["applied"]).date()).days >= 7
    except ValueError:
        return False


def payload():
    everything = J.load()
    # В очереди только то, что прошло бы отправку: иначе кнопка в приложении
    # обходит фильтры и лимит на компанию.
    ok = {r["id"] for r in A.queue(everything)}
    rows = [r for r in everything.values() if r["status"] != "new" or r["id"] in ok]
    for r in rows:
        r["followup"] = needs_followup(r)
        r["score"] = int(r.get("note") or 0)
    rows.sort(key=lambda r: (r["status"] != "new", -r["score"]))
    return {"jobs": rows, "stats": stats(rows)}


def grab_reqs(job_id, url):
    """Текст вакансии в фоне — чтобы кнопка не подвисала."""
    text = J.fetch_reqs(url)
    if not text:
        return
    with _lock:
        rows = J.load()
        if job_id in rows:
            rows[job_id]["reqs"] = text
            J.save(rows)


# -------------------------------------------------------------------- сбор

def collect():
    _collecting["running"] = True
    try:
        p = subprocess.run([sys.executable, os.path.join(ROOT, "auto_apply", "jobs.py")],
                           capture_output=True, text=True, timeout=1800)
        _collecting["log"] = (p.stdout or p.stderr)[-600:]
    except Exception as e:
        _collecting["log"] = f"Ошибка: {e}"
    finally:
        _collecting["running"] = False


# ------------------------------------------------------------------ сервер

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass                                    # без спама в терминал

    def _send(self, code, body, ctype="application/json"):
        raw = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", f"{ctype}; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if self.path.startswith("/api/state"):
            return self._send(200, json.dumps(payload(), ensure_ascii=False))
        if self.path.startswith("/api/collect-log"):
            return self._send(200, json.dumps(_collecting))
        with open(UI, "rb") as f:
            return self._send(200, f.read(), "text/html")

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        req = json.loads(self.rfile.read(n) or "{}")

        if self.path == "/api/collect":
            if not _collecting["running"]:
                threading.Thread(target=collect, daemon=True).start()
            return self._send(200, json.dumps({"ok": True}))

        jid = req.get("id")
        with _lock:
            rows = J.load()
            job = rows.get(jid)
            if not job:
                return self._send(404, json.dumps({"error": "нет такой вакансии"}))

            if self.path == "/api/open":
                subject, body = A.make_cl(job["company"], job["title"])
                A.to_clipboard(body)
                subprocess.run(["open", "-a", "Google Chrome", job["url"]], check=False)
                return self._send(200, json.dumps({"subject": subject}))

            if self.path == "/api/update":
                if "status" in req:
                    job["status"] = req["status"]
                    if req["status"] == "applied" and not job.get("applied"):
                        job["applied"] = date.today().isoformat()
                        if not job.get("reqs"):
                            threading.Thread(target=grab_reqs,
                                             args=(jid, job["url"]), daemon=True).start()
                if "user_note" in req:
                    job["user_note"] = req["user_note"]
                J.save(rows)
                return self._send(200, json.dumps({"ok": True}))

        self._send(404, json.dumps({"error": "нет такого метода"}))


def main():
    url = f"http://127.0.0.1:{PORT}"
    try:
        srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    except OSError as e:
        if e.errno != 48:                  # 48 = порт занят
            raise
        # Апка уже запущена — не падаем, просто отдаём окно живому серверу.
        print(f"Auto Job уже работает: {url}")
        if "--no-window" not in sys.argv:
            webbrowser.open(url)
        return
    print(f"Auto Job работает: {url}\nЗакрыть — Ctrl+C\n")

    if "--no-window" in sys.argv:          # для проверок без открытия окна
        return srv.serve_forever()

    profile = os.path.join(ROOT, ".appwindow")
    try:
        subprocess.Popen([CHROME, f"--app={url}", f"--user-data-dir={profile}",
                          "--window-size=1180,860", "--no-first-run"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except FileNotFoundError:
        webbrowser.open(url)                    # Chrome не найден — обычный браузер

    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("Остановлено.")


if __name__ == "__main__":
    main()
