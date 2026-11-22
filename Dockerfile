FROM python:3.12-slim
WORKDIR /code
COPY pyproject.toml /code/
COPY backend /code/backend
COPY frontend /code/frontend
RUN pip install --no-cache-dir .
ENV DB_PATH=/data/portfolio.sqlite3
ENV FRONTEND_PATH=/code/frontend/index.html
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
