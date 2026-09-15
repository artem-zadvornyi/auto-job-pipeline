# Auto Job - job ads ETL pipeline

A small Python ETL pipeline I built for my own job search. Standard library only, no dependencies.

**Extract.** Collects job ads from 9 sources: Profesia.sk (HTML), LinkedIn public job search (HTML, no login), NoFluffJobs (JSON API) and 6 remote job boards (JSON APIs and RSS). A source that fails returns 0 rows and the others keep running.

**Transform.** Maps every source to one schema (source, title, company, location, salary, url), cleans the text and applies rules: location near Bratislava or remote, junior level (senior / head / architect are dropped unless the title also says junior) and a real IT role. Every ad gets a stable key (the ad id from the URL, otherwise company + title) and a score for ordering.

**Load.** Only new keys are added to `data/jobs.csv`, like a MERGE that inserts new rows.

**Use.** A small local web app (`app.py`) or the terminal flow (`auto_apply/apply.py`). Right before applying, the rules are checked again, plus at most 3 applications per company in 30 days and no duplicate positions. Applying itself is always done by hand.

## Run

```bash
python3 auto_apply/jobs.py          # collect new ads
python3 auto_apply/jobs.py --stats  # what is in the table
python3 app.py                      # local UI on http://127.0.0.1:8765
python3 auto_apply/test_jobs.py     # ~100 rule checks, no network needed
```

Personal settings: copy `profile.example.json` to `profile.json`.

## Notes

- Code comments are in Russian, my native language. Happy to walk through any part.
- Built with a lot of AI assistance. The requirements, the rules, testing and debugging were mine.
- A hosted version for other job seekers runs at https://getautojob.duckdns.org (the first list is free).
