# Stage 1: immutable Swiss Ephemeris data. The human-readable tag documents
# the selected line; the manifest-list digest is the actual build input.
FROM python:3.12-slim@sha256:229a2c5bfa27522db7815ea81f9bed70af17ccb9de9fc7ad142b1877b5830d36 AS ephe

WORKDIR /lock
COPY ephemeris.lock.json ./ephemeris.lock.json
COPY scripts/fetch_ephemeris.py ./fetch_ephemeris.py
RUN python fetch_ephemeris.py \
      --lock ephemeris.lock.json \
      --destination /usr/local/share/swisseph \
      --print-lock-id && \
    python fetch_ephemeris.py \
      --lock ephemeris.lock.json \
      --destination /usr/local/share/swisseph \
      --verify-only

# Stage 2: build and verify the same wheel that will enter the runtime image.
FROM python:3.12-slim@sha256:229a2c5bfa27522db7815ea81f9bed70af17ccb9de9fc7ad142b1877b5830d36 AS builder

WORKDIR /build
ENV CC=gcc
ENV CXX=g++
# pyswisseph does not publish a CPython 3.12 Linux wheel for the locked
# 2.10.3.2 release, so the immutable sdist must be compiled in the builder.
# None of these packages enter the final runtime stage.
RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential \
      gcc \
      g++ \
      python3-dev \
      libffi-dev \
    && rm -rf /var/lib/apt/lists/*

RUN python -m pip install --no-cache-dir --no-deps \
      pip==26.1.2 \
      uv==0.11.29 \
      setuptools==80.9.0 \
      wheel==0.47.0 \
      build==1.3.0 \
      packaging==26.0 \
      pyproject-hooks==1.2.0

COPY pyproject.toml uv.lock ./
RUN uv export \
      --frozen \
      --no-emit-project \
      --format requirements-txt \
      --output-file /build/runtime.requirements.txt && \
    python -m pip install \
      --no-cache-dir \
      --ignore-installed \
      --require-hashes \
      --prefix=/install \
      -r /build/runtime.requirements.txt

COPY pyproject.toml README.md LICENSE ./
COPY bazi_engine/ ./bazi_engine/
COPY scripts/verify_distribution.py ./scripts/verify_distribution.py
RUN python -m build --wheel --no-isolation --outdir /dist && \
    python scripts/verify_distribution.py /dist/*.whl && \
    python -m pip install --no-cache-dir --prefix=/install --no-deps /dist/*.whl

# Stage 3: source-free, non-root runtime. Keep this aligned with the approved
# Python line in scripts/assert_toolchain_versions.py and project metadata.
FROM python:3.12-slim@sha256:229a2c5bfa27522db7815ea81f9bed70af17ccb9de9fc7ad142b1877b5830d36 AS runtime

WORKDIR /app
RUN groupadd --gid 10001 fufire \
    && useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin fufire

COPY --from=ephe /usr/local/share/swisseph /usr/local/share/swisseph
COPY --from=builder /install /usr/local
COPY ephemeris.lock.json ./ephemeris.lock.json
COPY start.py ./start.py

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1
ENV PIP_DISABLE_PIP_VERSION_CHECK=1
ENV SE_EPHE_PATH=/usr/local/share/swisseph
ENV FUFIRE_REQUIRE_EXPLICIT_ENV=1

USER 10001:10001
EXPOSE 8080
CMD ["python", "start.py"]
