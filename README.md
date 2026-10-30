# Selenium News Summarizer API (Ars Technica)

Lab Assignment 4 - CSC418 DevOps for Cloud Computing, COMSATS University Islamabad  
Student: Hashim Nabi Sulehria - FA23-BDS-057 - news source: **Ars Technica**
(57 % 20 + 1 = 18)

A Docker image with Python, Google Chrome, ChromeDriver and a Selenium script. It searches
arstechnica.com for a keyword, opens the first result, summarizes the article and returns it
through a REST API on port 7000.

## API

`GET /get?keyword=<keyword>` (port 7000)

```json
{
  "registration": "FA23-BDS-057",
  "newssource": "Ars Technica",
  "keyword": "openai",
  "url": "https://arstechnica.com/...",
  "summary": "..."
}
```

`GET /` shows a web page with the registration number.

## Run

```bash
docker run -d --name news -p 7000:7000 hashimnabi/news-summarizer:1.0
curl "http://localhost:7000/get?keyword=openai"
```

## Files

| File | Purpose |
|---|---|
| `Dockerfile` | Python 3.12 + Chrome + ChromeDriver + app, starts the API automatically |
| `app.py` | Flask REST API (`/`, `/get`, `/health`) served by Gunicorn |
| `scraper.py` | Selenium (headless Chrome) search + article extraction |
| `summarizer.py` | Extractive summarization module (word-frequency scoring) |
| `requirements.txt` | selenium, flask, gunicorn |

Language used for the Selenium code: **Python**.
