FROM python:3.12-slim

ENV PYTHONUNBUFFERED 1

WORKDIR /app

COPY req.txt .
RUN --mount=type=cache,target=/root/.cache/pip,sharing=locked \
    pip install -U pip wheel && \
    pip install -r req.txt

COPY . .
CMD ["./run.py", "api"]
