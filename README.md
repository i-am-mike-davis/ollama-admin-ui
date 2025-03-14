# ollama-admin-ui

<https://hub.docker.com/r/ollama/ollama>

## Prerequisites

- [uv](https://docs.astral.sh/uv/)
- tailwindcss cli

## Install Dependencies

```
uv sync
```

## Run

```
uv run main.py
```

## Styling

- Use Tailwindcss utility classes in html.
- Generate new css using tailwindcss cli.

```
tailwindcss --watch -i ./app/static/input.css -o ./app/static/output.css
```

## About

- FastAPI
- [pyproject.toml](https://packaging.python.org/en/latest/guides/writing-pyproject-toml/)
- uv<https://docs.astral.sh/uv/guides/integration/docker/>

```
