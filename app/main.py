# standard library imports
from typing import Union
from dotenv import load_dotenv
from pathlib import Path
import os

# third-party imports
import uvicorn
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from ollama import Client, AsyncClient, ResponseError, ProgressResponse
from log2d import Log

# local imports
# import app. as lib

from wollama.wollama import (
    Catalog,
    ModelTag,
    ModelTagCollection,
    OllamaManager,
    OllamaInfo,
    OllamaRegistry,
)

# TODO:
# - [-] Setup logging.
# - [ ] Setup error handling.
# - [ ] Clean up comments.
# - [ ] Make reading the environment variable more reliable.

# Get environment variables
dotenv_path = Path("../.env")
load_dotenv(dotenv_path=dotenv_path)

OLLAMA_ADDRESS = os.getenv("OLLAMA_ADDRESS")

# Initialize logger.
log = Log(Path(__file__).stem).logger
LOG_LEVEL = "WARNING"
log.setLevel(level=f"{LOG_LEVEL}")

try:
    LOG_LEVEL = os.getenv("LOG_LEVEL")
    log.setLevel(level=f"{LOG_LEVEL}")
    log.info(f"Set log level to: {LOG_LEVEL}")
except Exception as e:
    log.info(
        f"Did not detect a log level specified in the environment file, using default: {LOG_LEVEL}"
    )
    log.warning(e)

# Initialize the ollama client
oclient = Client(host=OLLAMA_ADDRESS)
aclient = AsyncClient(host=OLLAMA_ADDRESS)

# Initialize the OllamaManager to handle downloading and deleting models...
omanager = OllamaManager(client=oclient)

# Initialize the OllamaRegistry client to read the remote ollama library.
oregistry = OllamaRegistry()

if oregistry:
    try:
        oregistry.load_from_cache()
    except Exception as e:
        print(f"Could not load oregistry catalog from cache...:\n{e}")
        try:
            oregistry.refresh()
        except:
            print("Could not refresh the remote catalog from the web!")


# Initialize jinja2 html templates
templates = Jinja2Templates(directory="templates")

# Initialize the fastapi application server
app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")


@app.put("/download/{model_name}")
def put_download(request: Request, model_name: str, tag: str):
    try:
        # oclient.pull(model=f"{model_name}:{tag}")
        log.info(f"Downloading {model_name}:{tag}")
        omanager.pull(model=model_name, tag=tag)
        log.info(f"Finished downloading... {model_name}:{tag}")
    except Exception as e:
        print(e)
        # raise HTTPException(status_code=500, detail=f"{e}")
        # return templates.TemplateResponse(
        #     request=request,
        #     name="button-downloaded.html",
        #     context={"url": f"/delete/{model_name}={tag}"},
        # )
        # html = f"""
        #     <button id="error-bar" class="visible bg-[#991b1b]">{e}</button>
        #     """
        return templates.TemplateResponse(
            request=request,
            name="error-bar.html",
            context={"error_message": f"{e}"},
            status_code=500,
        )

    return templates.TemplateResponse(
        request=request,
        name="button-downloaded.html",
        context={
            "tag_name": f"{tag}",
            "url": f"/delete/{model_name}?tag={tag}",
            "model_name": f"{model_name}",
        },
    )


@app.post("/delete/{model_name}")
def put_download(request: Request, model_name: str, tag: str):
    try:
        log.info(f"Deleting {model_name}:{tag}")
        omanager.delete(model=model_name, tag=tag)
        log.info(f"Finished deleting {model_name}:{tag}")
    except Exception as e:
        print(e)
        return templates.TemplateResponse(
            request=request,
            name="error-bar.html",
            context={"error_message": f"{e}"},
            status_code=500,
        )

    return templates.TemplateResponse(
        request=request,
        name="button-download.html",
        context={
            "tag_name": f"{tag}",
            "url": f"/download/{model_name}?tag={tag}",
            "model_name": f"{model_name}",
        },
    )


@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="library.html",
        context={"remote": oregistry.catalog, "local": omanager.catalog},
    )


#
# @app.get("/local", response_class=HTMLResponse)
# async def read_root(request: Request):
#     return templates.TemplateResponse(
#         request=request,
#         name="library.html",
#         context={"remote": oregistry.catalog, "local": omanager.catalog},
#     )
#

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)
