# FOMC Dashboard 聯準會利率會議儀表板

Glassmorphism-style FOMC dashboard deployed on Vercel. Displays Fed dot plot, rate path projections, economic projections, global central bank rates, and central bank news.

## Live Demo

https://fomc-eight.vercel.app

## Structure

```
api/index.py          — Flask API (6 endpoints: meetings, current-rate, sep, global-rates, news, meetings/csv)
static/index.html     — Single-page frontend (vanilla JS, CSS glassmorphism)
vercel.json           — Vercel deployment config
requirements.txt      — Python dependencies
```

## API Endpoints

- `/api/meetings` — FOMC meeting schedule
- `/api/current-rate` — Current Fed funds rate range
- `/api/sep` — Dot plot + economic projections
- `/api/global-rates` — Global central bank rates
- `/api/news` — Recent central bank news (RSS)

## Deploy Your Own

```bash
vercel --prod
```

## Local Dev (for code changes)

```bash
pip install -r requirements.txt
python api/index.py
```
