FROM python:3.12-slim
WORKDIR /srv
ENV PYTHONUNBUFFERED=1 DEEPEVAL_TELEMETRY_OPT_OUT=YES GAUNTLET_DB=/data/gauntlet.db
COPY requirements.txt requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements-dev.txt
COPY . .
VOLUME /data
EXPOSE 8000
CMD ["uvicorn", "app.api:app", "--host", "0.0.0.0", "--port", "8000"]
