# 候選映像；作者建置時保存實際 base digest、pip list 與最後映像 digest。
FROM python:3.13.5-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8080 OTEL_SDK_DISABLED=true GOOGLE_GENAI_USE_VERTEXAI=FALSE
WORKDIR /app
COPY examples/day12/requirements*.txt /app/examples/day12/
RUN python -m pip install --no-cache-dir -r examples/day12/requirements.txt && python -m pip check
COPY docs/day01/handoff-timeout-001.json /app/docs/day01/handoff-timeout-001.json
COPY examples/day05/catalog.py /app/examples/day05/catalog.py
COPY examples/day08/confirmation.py /app/examples/day08/confirmation.py
COPY examples/day09/*.py /app/examples/day09/
COPY examples/day09/fixtures.json /app/examples/day09/fixtures.json
COPY examples/day11/*.py /app/examples/day11/
COPY examples/day11/dependency-lock.json /app/examples/day11/dependency-lock.json
COPY examples/day12/*.py /app/examples/day12/
COPY SOURCE_MANIFEST.json /app/SOURCE_MANIFEST.json
COPY LICENSE /app/LICENSE
RUN useradd --uid 10001 --no-create-home appuser
USER 10001
EXPOSE 8080
CMD ["sh", "-c", "exec python -m uvicorn examples.day12.main:app --host 0.0.0.0 --port ${PORT:-8080} --workers 1 --no-access-log"]
