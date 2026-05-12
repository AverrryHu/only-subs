FROM python:3.11-slim

WORKDIR /app

# Install yt-dlp and other dependencies
RUN pip install --no-cache-dir yt-dlp feedparser beautifulsoup4 lxml python-dotenv supabase fastapi uvicorn[standard] python-multipart

COPY app /app

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]