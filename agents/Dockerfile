FROM python:3.11-slim

WORKDIR /app

# نسخ requirements أولاً (cache optimization)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# نسخ كل الملفات
COPY . .
# تحديث بسيط لإجبار إعادة البناء - 2026-08-07

CMD ["python", "main.py"]
