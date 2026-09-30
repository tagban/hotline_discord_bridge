FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt && useradd -r -u 1000 bridge
COPY hl_bridge.py hotline.py ./
USER bridge
ENV PYTHONUNBUFFERED=1
CMD ["python", "hl_bridge.py", "/config/config.json"]
