# FOMC Dashboard 聯準會利率會議儀表板

### 解決問題： 提供聯準會 FOMC 利率決策的即時總覽——會議時程、利率路徑（SEP 點陣圖中位數）、市場降息預期（利率機率長條圖）、全球主要央行利率比較、以及各國央行重大新聞，讓 macro 交易員／分析師不用在多個網站之間切換。(FOMC dashboard deployed on Vercel. Displays Fed dot plot, rate path projections, economic projections, global central bank rates, and central bank news.)

<img width="608" height="119" alt="Screenshot 2026-06-21 165119" src="https://github.com/user-attachments/assets/c9811d3c-bae9-48bd-86f0-462562889893" />
<img width="607" height="281" alt="Screenshot 2026-06-21 165059" src="https://github.com/user-attachments/assets/77f8f94d-a6d4-4e72-8cca-1d7f7d72b8ea" />
<img width="608" height="275" alt="Screenshot 2026-06-21 165146" src="https://github.com/user-attachments/assets/1bb550e7-3a45-424c-b775-0271887e08f3" />

https://fomc-eight.vercel.app

## Structure

```
api/index.py          — Flask API (6 endpoints: meetings, current-rate, sep, global-rates, news, meetings/csv)
static/index.html     — Single-page frontend (vanilla JS, CSS glassmorphism)
vercel.json           — Vercel deployment config
requirements.txt      — Python dependencies
```

## API Endpoints

### 資料來源：Fed 官方 JSON 日曆（federalreserve.gov）、FOMC 聲明網頁（正則抓取當前利率）、SEP 經濟預測表格（HTML 解析點陣圖 + GDP/失業率/PCE 中位數）、全球央行：ECB 官網表格（存款利率）、BOE 官網、TradingEconomics（BOJ/AU/KR/TW）、
RSS：Fed、ECB、BOE、BOJ、BOK 共 5 家央行即時消息

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
