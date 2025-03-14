# standard library imports
from typing import Union
from dotenv import load_dotenv
from pathlib import Path
import os

# third-party imports
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from ollama import Client

# local imports
# import app.lib as lib

# Get environment variables
dotenv_path = Path("./.env")
load_dotenv(dotenv_path=dotenv_path)
OLLAMA_ADDRESS = os.getenv("OLLAMA_ADDRESS")

# Initialize ollama client
oclient = Client(host=OLLAMA_ADDRESS)

# Initialize jinja2 html templates
templates = Jinja2Templates(directory="templates")

# Initialize the fastapi application server
app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")


# @app.get("/")
# def read_root():
#     return {"Hello": "World"}
@app.get("/")
def get_root(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")


@app.get("/items/{id}", response_class=HTMLResponse)
async def read_item(request: Request, id: str):
    return templates.TemplateResponse(
        request=request, name="item.html", context={"id": id}
    )


#
# @app.get("/items/{item_id}")
# def read_item(item_id: int, q: Union[str, None] = None):
#     return {"item_id": item_id, "q": q}
#

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
