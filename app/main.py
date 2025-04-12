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
from typing import List
# local imports
# import app. as lib

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
# - [-] Get progress from ollama operations.
# - [-] Setup logging.
# - [-] Setup error handling.
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
omanager = OllamaManager(client=oclient, aclient=aclient)

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
    # return templates.TemplateResponse(
    #     request=request,
    #     name="error-bar.html",
    #     context={"error_message": f"{e}"},
    #     status_code=500,
    # )


@app.put("/create")
async def create():
    identifier = await omanager.do_work_wrap()
    return {"identifier": identifier}


@app.put("/download/{model_name}")
def put_download(request: Request, model_name: str, tag: str):
    if model_name in omanager.catalog.models.keys():
        if tag in omanager.catalog.models["model_name"].tag_collection.tags.keys():
            return templates.TemplateResponse(
                request=request,
                name="button-downloaded.html",
                context={
                    "tag_name": f"{tag}",
                    "url": f"/delete/{model_name}?tag={tag}",
                    "model_name": f"{model_name}",
                },
            )

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


# TODO: Parametize the finish code
# TODO: Rename finish code to finish message
@app.post("/refresh-library")
async def post_refresh(request: Request):
    # identifier = await oregistry.arefresh()
    finish_code = "refresh-library"
    identifier = await mock_initiate_work(
        job_stack=mock_job_stack, finish_code=finish_code
    )
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
        # return templates.TemplateResponse(
        #     request=request,
        #     name="refresh-library.html",
        #     context={
        #         "button_value": "Refreshing...",
        #         "tag_name": "Refreshing the library...",
        #         "url": "/static/refresh-library.html",
        #         "model_name": "N/A",
        #         "identifier": f"{identifier}",
        #         "job_type": f"{finish_code}",
        #         "message": "Initiating refresh of remote catalog",
        #     },
        # )
        #


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
    return templates.TemplateResponse(
        request=request,
        name="library.html",
        context={"remote": oregistry.catalog, "local": omanager.catalog},
    )


@app.get("/test", response_class=HTMLResponse)
async def read_test(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="message.html",
        context={"message": f"{str(uuid.uuid4())}test!"},
    )


@app.get("/time", response_class=HTMLResponse)
async def read_time(request: Request):
    import datetime
    import time

    now_time = time.time()
    return templates.TemplateResponse(
        request=request,
        name="message-poll.html",
        context={"message": f"Current Time{str(now_time)}"},
    )


# @app.post("/work/test")
# async def testing(files: List[UploadFile]):
#     identifier = str(uuid.uuid4())
#     context[jobs][identifier] = {}
#     asyncio.run_coroutine_threadsafe(
#         do_work(identifier, files), loop=asyncio.get_running_loop()
#     )
#
#     return {"identifier": identifier}
#


@app.get("/status")
def status():
    return {
        "all": list(omanager.context["jobs"].values()),
    }


@app.get("/status/{job_type}/{identifier}")
async def status(request: Request, job_type: str, identifier: str):
    if job_type == "download-model":
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
                },
            )
        else:
            return templates.TemplateResponse(
                request=request,
                headers={"HX-Trigger": f"{finish_code}"},
                name="message.html",
                context={
                    "identifier": f"{identifier}",
                    "message": "Finished downloading!!",
                    "job_type": "download-model",
                },
            )
    elif job_type == "refresh-library":
        try:
            status = oregistry.context["jobs"].get(
                identifier, "job with that identifier is undefined"
            )
            status = mock_job_stack["jobs"].get(identifier, "job undefined...")
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
                headers={"HX-Trigger": f"{finish_code}"},
                name="message.html",
                context={
                    "identifier": f"{identifier}",
                    "message": "Finished downloading!",
                },
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
