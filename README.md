# ollama-admin-ui

<https://hub.docker.com/r/ollama/ollama>

Access at:

- <http://localhost:8000/>

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
- [heroicons](https://heroicons.com/)

```
tailwindcss --watch -i ./app/static/css/input.css -o ./app/static/css/output.css
```

## About

- <https://hypermedia.systems/extending-html-as-hypermedia/>
Other user interfaces for ollama:

- <https://itsfoss.com/ollama-web-ui-tools/>

- FastAPI
- [pyproject.toml](https://packaging.python.org/en/latest/guides/writing-pyproject-toml/)
- uv<https://docs.astral.sh/uv/guides/integration/docker/>

```
