# ------------------------------------------------------------------------------
# Stage 1: Build virtual environment with uv
# ------------------------------------------------------------------------------
FROM python:3.12-slim-bookworm AS builder

# Install uv from official distroless image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Enable bytecode compilation and copy link mode for clean container layers
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

# Install dependencies first for optimal Docker layer caching
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

# Copy source files and install the package (non-editable for standalone runtime)
COPY src/ ./src/
RUN uv sync --frozen --no-dev --no-editable

# ------------------------------------------------------------------------------
# Stage 2: Minimal runtime image
# ------------------------------------------------------------------------------
FROM python:3.12-slim-bookworm AS runtime

LABEL org.opencontainers.image.title="openstax-md" \
      org.opencontainers.image.description="High-fidelity compiler transforming OpenStax CNXML/COLLXML textbooks into GitHub Flavored Markdown" \
      org.opencontainers.image.source="https://github.com/michaelnavazhylau/openstax-md" \
      org.opencontainers.image.licenses="MIT"

# Install git (required for remote catalog sparse checkout) and ca-certificates
RUN apt-get update && \
    apt-get install -y --no-install-recommends git ca-certificates && \
    git config --system --add safe.directory '*' && \
    rm -rf /var/lib/apt/lists/*

# Create dedicated non-root user and directories for cache and working data
RUN groupadd -g 1000 openstax && \
    useradd -u 1000 -g openstax -m -s /bin/bash openstax && \
    mkdir -p /cache /data && \
    chown -R openstax:openstax /cache /data && \
    chmod 777 /cache /data

# Copy isolated virtual environment from builder stage
COPY --from=builder --chown=openstax:openstax /app/.venv /app/.venv

# Configure runtime environment
ENV PATH="/app/.venv/bin:$PATH" \
    OPENSTAX_MD_CACHE="/cache" \
    PYTHONUNBUFFERED=1

WORKDIR /data

USER openstax

ENTRYPOINT ["openstax-md"]
CMD ["--help"]
