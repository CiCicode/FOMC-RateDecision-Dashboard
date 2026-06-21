<img width="607" height="281" alt="Screenshot 2026-06-21 165059" src="https://github.com/user-attachments/assets/0feb790d-3fd2-42be-880e-d16e0d2cbbad" /># FOMC Dashboard 聯準會利率會議儀表板

FOMC dashboard deployed on Vercel. Displays Fed dot plot, rate path projections, economic projections, global central bank rates, and central bank news.

<img width="608" height="119" alt="Screenshot 2026-06-21 165119" src="https://github.com/user-attachments/assets/c9811d3c-bae9-48bd-86f0-462562889893" />
<img width="607" height="281" alt="Screenshot 2026-06-21 165059" src="https://github.com/user-attachments/assets/77f8f94d-a6d4-4e72-8cca-1d7f7d72b8ea" />
<img width="608" height="275" alt="Screenshot 2026-06-21 165146" src="https://github.com/user-attachments/assets/1bb550e7-3a45-424c-b775-0271887e08f3" />

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
