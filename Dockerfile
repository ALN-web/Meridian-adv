# Playwright image: Python + Chromium + its system libraries. Pin matches requirements (playwright>=1.47).
FROM mcr.microsoft.com/playwright/python:v1.47.0-jammy
# Tesseract reads scanned invoices and delivery proofs locally (documents never leave the container).
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV PYTHONPATH=/app/src PYTHONUNBUFFERED=1
EXPOSE 8510
CMD ["streamlit", "run", "src/meridian/ui/app.py", "--server.port=8510", "--server.address=0.0.0.0", "--server.headless=true"]
