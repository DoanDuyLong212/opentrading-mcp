FROM python:3.12-slim

# Pinned (#98): a moving :latest can change resolution or break the build.
COPY --from=ghcr.io/astral-sh/uv:0.13.7 /uv /uvbin/uv

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
# gen 6 core has no matplotlib; telemetry opt-out per vnstock 6 (0 = off).
ENV VNSTOCK_TELEMETRY=0
ENV VIRTUAL_ENV=/app/.venv PATH="/app/.venv/bin:$PATH"
WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
COPY src/ src/
RUN /uvbin/uv sync --frozen --no-dev --no-editable --compile-bytecode && chmod -R a+rX /app/.venv

RUN useradd --create-home --shell /usr/sbin/nologin appuser
USER appuser

EXPOSE 8102
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
  CMD python -c "import os,sys,urllib.request; \
p=os.environ.get('PORT','8102'); \
sys.exit(0 if urllib.request.urlopen(f'http://127.0.0.1:{p}/healthz',timeout=8).read() else 1)"
CMD ["sh", "-c", "opentrading-mcp serve --preset all --http --port ${PORT:-8102}"]
