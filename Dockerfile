FROM python:3.14-alpine AS builder

WORKDIR /build

RUN apk add --no-cache libxml2-dev libxslt-dev build-base
COPY requirements.txt .
RUN pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt

FROM python:3.14-alpine

WORKDIR /app

COPY requirements.txt .
COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir --only-binary :all: --find-links /wheels -r requirements.txt && \
    rm -rf /wheels requirements.txt

COPY app/ .
RUN chmod +x docker.sh && \
    mkdir -p /app/static/js && \
    wget -q -O /app/static/js/echarts.min.js \
    https://cdn.jsdelivr.net/npm/echarts@6.1.0/dist/echarts.min.js

EXPOSE 5000

HEALTHCHECK --interval=5s --start-period=30s --timeout=5s --retries=3 \
    CMD wget -qO - http://127.0.0.1:5000/health | grep -q healthy || exit 1

ENTRYPOINT ["/app/docker.sh"]
CMD ["gunicorn", "-c", "gunicorn_config.py", "app:application"]
