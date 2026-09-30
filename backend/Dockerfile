FROM python:3.11-slim
WORKDIR /app/backend
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ /app/backend/
COPY data/reference/ /app/data/reference/
ENV WP_DATA_DIR=/app/data
ENV WP_CORS_ORIGINS=http://localhost:3000
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
