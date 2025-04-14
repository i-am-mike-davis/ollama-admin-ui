FROM python:3.11-slim-bookworm

# Install uv
COPY --from=ghcr.io/astral-sh/uv:0.6.6 /uv /uvx /bin/

# Copy the project into the image
ADD . /ollama-admin-ui/

# Sync the project into a new environment, using the frozen lockfile
WORKDIR /ollama-admin-ui/app
RUN uv sync --frozen

EXPOSE 8000

CMD ["uv", "run", "python", "main.py"]
