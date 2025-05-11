# standard library imports
from typing import Union
from dotenv import load_dotenv
from pathlib import Path
import os

# third-party imports
import uvicorn
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from ollama import Client, AsyncClient, ResponseError, ProgressResponse
from log2d import Log
from typing import List

# local imports
# import app. as lib
import string
from wollama.wollama import (
    Catalog,
    ModelTag,
    ModelTagCollection,
    OllamaManager,
    OllamaInfo,
    OllamaRegistry,
    mock_job_stack,
    mock_do_work,
    mock_initiate_work,
)

import asyncio
import uuid

context = {"jobs": {}}

# TODO:
# - [ ] Clean up comments.

# Get environment variables
dotenv_path = Path("../.env")
load_dotenv(dotenv_path=dotenv_path)

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

OLLAMA_ADDRESS = os.getenv("OLLAMA_ADDRESS")

MOCK_REMOTE_TRAFFIC = os.getenv("MOCK_REMOTE_TRAFFIC")

if MOCK_REMOTE_TRAFFIC is not None:
    if MOCK_REMOTE_TRAFFIC.upper() == "TRUE":
        log.debug("Mocking remote traffic!")
        log.warning("Mocking remote traffic!")
        MOCK_REMOTE_TRAFFIC = True
    else:
        MOCK_REMOTE_TRAFFIC = False
else:
    MOCK_REMOTE_TRAFFIC = False


# Initialize the ollama client
try:
    oclient = Client(host=OLLAMA_ADDRESS)
    aclient = AsyncClient(host=OLLAMA_ADDRESS)
except Exception as e:
    log.error("Could not connect to ollama!")
    log.error(f"{e}")

# Initialize the OllamaManager to handle downloading and deleting models...
try:
    omanager = OllamaManager(client=oclient, aclient=aclient)
except Exception as e:
    log.error("Could not instantiate Ollama Manager.")
    log.error(f"{e}")

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


@app.put("/draft/download/{model_name}")
async def put_async_download(request: Request, model_name: str, tag: str):
    finish_code = f"{model_name}:{tag}"
    if model_name in omanager.catalog.models.keys():
        if tag in omanager.catalog.models[f"{model_name}"].tag_collection.tags.keys():
            return templates.TemplateResponse(
                request=request,
                name="button-downloaded.html",
                context={
                    "tag_name": f"{tag}",
                    "url": f"/delete/{model_name}?tag={tag}",
                    "model_name": f"{model_name}",
                },
            )
    if MOCK_REMOTE_TRAFFIC:
        identifier = await mock_initiate_work(
            job_stack=mock_job_stack, finish_code=finish_code
        )
    else:
        identifier = await omanager.download_wrap(model=model_name, tag=tag)
    # return {"identifier": identifier}
    return templates.TemplateResponse(
        request=request,
        name="start-download.html",
        context={
            "tag_name": f"{tag}",
            "url": f"/delete/{model_name}?tag={tag}",
            "model_name": f"{model_name}",
            "identifier": f"{identifier}",
            "message": f"Initiating download of {model_name}:{tag}",
            "job_type": "download-model",
        },
    )


# TODO: Parametize the finish code
@app.post("/refresh-library")
async def post_refresh(request: Request):
    finish_code = "refresh-library"
    if MOCK_REMOTE_TRAFFIC:
        identifier = await mock_initiate_work(
            job_stack=mock_job_stack, finish_code=finish_code
        )
    else:
        identifier = await oregistry.arefresh()
    return templates.TemplateResponse(
        request=request,
        name="start-library-refresh.html",
        context={
            "button_value": "Refreshing...",
            "tag_name": "Refreshing the library...",
            "url": f"/finished/{finish_code}",
            "model_name": "N/A",
            "identifier": f"{identifier}",
            "job_type": f"{finish_code}",
            "message": "Initiating refresh of remote catalog",
        },
    )


@app.get("/finished/{job_type}")
async def read_finished(request: Request, job_type: str):
    # identifier = await oregistry.arefresh()
    #
    if job_type == "refresh-library":
        return HTMLResponse(headers={"HX-Redirect": "/"})


@app.post("/delete/{model_name}")
def post_delete(request: Request, model_name: str, tag: str):
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
            "url": f"/draft/download/{model_name}?tag={tag}",
            "model_name": f"{model_name}",
        },
    )


@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    try:
        remote = oregistry.catalog
        local = omanager.catalog
    except Exception as e:
        return HTMLResponse(
            content=f"""
            FATAL ERROR: Most likely the server cannot talk to Ollama at:'{OLLAMA_ADDRESS}'             |            Error exception: {e}"
            """
        )
    return templates.TemplateResponse(
        request=request,
        name="library.html",
        context={"remote": remote, "local": local, "ollama_address": OLLAMA_ADDRESS},
    )


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return FileResponse("static/favicon-32x32.png")


@app.get("/status/{job_type}/{identifier}")
async def status(request: Request, job_type: str, identifier: str):
    if job_type == "download-model":
        if MOCK_REMOTE_TRAFFIC:
            status = mock_job_stack["jobs"].get(identifier, "job undefined...")
        else:
            status = omanager.context["jobs"].get(
                identifier, "job with that identifier is undefined"
            )
        finish_code = status["finish_code"]
        status_message = status["status"]
        if not status["status"] == "done":
            return templates.TemplateResponse(
                request=request,
                name="message-poll.html",
                context={
                    "identifier": f"{identifier}",
                    "message": f"{finish_code}: {status_message}",
                    "job_type": f"{job_type}",
                },
            )
        else:
            return templates.TemplateResponse(
                request=request,
                headers={"HX-Trigger": f"{finish_code}"},
                name="message.html",
                context={
                    "identifier": f"{identifier}",
                    "message": f"{finish_code}: Finished downloading!",
                    "job_type": f"{job_type}",
                },
            )
    elif job_type == "refresh-library":
        try:
            if MOCK_REMOTE_TRAFFIC:
                status = mock_job_stack["jobs"].get(identifier, "job undefined...")
            else:
                status = oregistry.context["jobs"].get(
                    identifier, "job with that identifier is undefined"
                )
            finish_code = status["finish_code"]
            status_message = status["status"]
        except Exception as e:
            log.error(f"{e}")
            finish_code = job_type
            status_message = "Something went wrong!"
        if not status_message == "done":
            return templates.TemplateResponse(
                request=request,
                name="message-poll.html",
                context={
                    "identifier": f"{identifier}",
                    "message": f"Refreshing the model catalog: {status_message}",
                    "job_type": f"{job_type}",
                },
            )
        else:
            return templates.TemplateResponse(
                request=request,
                headers={"HX-Trigger": f"refresh-library"},
                name="message.html",
                context={
                    "identifier": f"{identifier}",
                    "message": "Finished downloading!",
                },
            )


# TODO: Add a /local endpoint to see all downloaded models in one view.
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
