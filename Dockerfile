# Selenium news-scraping API (Ars Technica) - FA23-BDS-057
# Development environment: Python 3.12 + Selenium + Flask/Gunicorn
# Browser: Google Chrome (stable)   Driver: matching ChromeDriver
FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive \
    REGISTRATION=FA23-BDS-057 \
    NEWS_SOURCE="Ars Technica" \
    CHROME_BIN=/usr/bin/google-chrome \
    CHROMEDRIVER=/usr/local/bin/chromedriver

# Base tools
RUN apt-get update && apt-get install -y --no-install-recommends \
        wget curl gnupg ca-certificates unzip jq fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

# Google Chrome (stable) from Google's apt repository (linux/amd64)
RUN wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | gpg --dearmor -o /usr/share/keyrings/google-chrome.gpg \
    && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome.gpg] http://dl.google.com/linux/chrome/deb/ stable main" \
        > /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

# ChromeDriver that matches the installed Chrome version
RUN CHROME_VER=$(google-chrome --version | awk '{print $3}') \
    && BUILD=${CHROME_VER%.*} \
    && URL=$(curl -fsSL https://googlechromelabs.github.io/chrome-for-testing/latest-patch-versions-per-build-with-downloads.json \
        | jq -r --arg b "$BUILD" '.builds[$b].downloads.chromedriver[]? | select(.platform=="linux64") | .url') \
    && if [ -z "$URL" ]; then \
         MS=${CHROME_VER%%.*}; \
         URL=$(curl -fsSL https://googlechromelabs.github.io/chrome-for-testing/latest-versions-per-milestone-with-downloads.json \
           | jq -r --arg m "$MS" '.milestones[$m].downloads.chromedriver[]? | select(.platform=="linux64") | .url'); \
       fi \
    && echo "Chrome $CHROME_VER -> $URL" && test -n "$URL" \
    && wget -q "$URL" -O /tmp/chromedriver.zip \
    && unzip -j /tmp/chromedriver.zip '*/chromedriver' -d /usr/local/bin/ \
    && chmod +x /usr/local/bin/chromedriver \
    && rm /tmp/chromedriver.zip \
    && google-chrome --version && chromedriver --version

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

# REST API on port 7000 - starts automatically when the container runs
EXPOSE 7000
CMD ["gunicorn", "-b", "0.0.0.0:7000", "-w", "1", "--threads", "4", "--timeout", "180", "app:app"]
