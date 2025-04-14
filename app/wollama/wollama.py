import time
import os
import requests
import pickle
from bs4 import BeautifulSoup
from typing import Dict, Optional
import urllib.parse
from pydantic import BaseModel
from typing import List, Any
from yarl import URL
from ollama import Client, AsyncClient, ListResponse, StatusResponse
from typing_extensions import TypedDict
from pathlib import Path
from dotenv import load_dotenv
import json
import importlib_resources  # https://github.com/wimglenn/resources-example/tree/main
from log2d import Log
import asyncio
import uuid
import aiohttp

wollama_resource_dir = importlib_resources.files("wollama")
wollama_cache_dir = wollama_resource_dir.joinpath("cache")

# TODO::
# - [ ] Setup test suite.
# - [ ] Setup error handling.
# - [ ] Add docstrings.
# - [ ] Clean up comments.
# - [ ] Clean up imports.

log = Log(Path(__file__).stem).logger
LOG_LEVEL = "INFO"
log.setLevel(level=f"{LOG_LEVEL}")

mock_job_stack = {"jobs": {}}


async def mock_initiate_work(job_stack: dict, finish_code: str):
    identifier = str(uuid.uuid4())
    job_stack["jobs"][identifier] = {}
    job_stack["jobs"][identifier]["finish_code"] = finish_code
    job_stack["jobs"][identifier]["status"] = "Starting"
    asyncio.run_coroutine_threadsafe(
        mock_do_work(job_stack, identifier),
        loop=asyncio.get_running_loop(),
    )
    return identifier


async def mock_do_work(job_stack: dict, job_key: str):
    iter_over = range(40)
    jobs = job_stack["jobs"]
    iter = 0
    for file, file_number in enumerate(iter_over):
        iter += 1
        job_info = jobs[job_key]
        job_info["iteration"] = file_number
        job_info["status"] = f"inprogress {iter}"
        await asyncio.sleep(1)
    jobs[job_key]["status"] = "done"


# NOTE: Ollama doesn't expose this class like ListResponse but I wish they would!
class OllamaInfo(BaseModel):
    """
    A container for model information returned by the ollama python client.
    """

    model: Any = None
    details: Any = None


class ModelTag(BaseModel):
    name: str = ""
    link: str = ""
    ollama_info: OllamaInfo = None


class ModelTagCollection(BaseModel):
    tags: Dict[str, ModelTag] = {}


class CatalogLLM(BaseModel):
    name: str = ""
    link: str = ""
    short_description: str = ""
    tag_collection: ModelTagCollection


class Catalog(BaseModel):
    """
    Represent ollama models and tags in a collection hierarchy.

    This object:
    - Makes answering questions like: "Which models and tags are installed?" easy.
    - Allows additional data to be associated with models and tags.
    - Exposes the same model information that the ollama client does.

    Catalog
    |
    |-Model
    |--Tag
    |--Tag
    |
    |-Model
    |--Tag

    Attributes:
    models: Dict[str, CatalogLLM]: A dictionary of CatalogLLMs, e.g. {"llama3.2" : CatalogLLM(name="llama3.2"....)}
    object_version: str: A versioning identifier for the catalog schema.
    """

    name: str = "ollama-catalog"
    models: Dict[str, CatalogLLM] = {}
    object_version: str = "0.0.0"

    def export_catalog(self, filepath: str):
        """
        Exports a JSON formatted file of the catalog.
        """
        try:
            with open(filepath, "w") as file:
                # A new file will be created
                json_string = self.model_dump_json(indent=4)
                file.write(json_string)
                # json.dump(obj=self, fp=file, indent=4)
        except Exception as e:
            log.error(e)

    def save_to_cache(self, file_dir: str):
        """
        Exports a pickled Catalog object.
        """
        cache_filename: str = f"{self.name}-cache-{self.object_version}"
        filepath = os.path.join(file_dir, cache_filename)
        try:
            # Open a file and use dump()
            with open(filepath, "wb") as file:
                # A new file will be created
                pickle.dump(self, file)
        except Exception as e:
            log.error(e)

    def load_from_cache(self, file_dir: str):
        """
        Attempts to load the Catalog pickle object.
        """
        cache_filename: str = f"{self.name}-cache-{self.object_version}"
        filepath = os.path.join(f"{file_dir}", f"{cache_filename}")
        try:
            # Open a file and use dump()
            with open(filepath, "rb") as file:
                # Call load method to deserialze
                cached_catalog = pickle.load(file)
                self.models = cached_catalog.models
        except Exception as e:
            log.error(e)
            raise e


class OllamaManager:
    """
    A high level object for managing ollama models via an ollama python client.

    Attributes:
        catalog: Catalog: A catalog object representing ollama models and tags.
        ollama_client Client: The ollama python client.
    """

    def __init__(self, client: Client, aclient: AsyncClient):
        self.catalog = Catalog(name="local-ollama-catalog")
        self.ollama_client = client
        self.ollama_aclient = aclient
        self.context = {"jobs": {}}

        # Ask Ollama for currently installed models and tags.
        result: ListResponse = client.list()
        for item in result.models:
            name, tag = item.model.split(":")
            ollama_info = OllamaInfo(model=item.model, details=item.details)
            # if the model is listed already in the catalog...
            if name in self.catalog.models.keys():
                model: CatalogLLM = self.catalog.models[f"{name}"]
                tag_collection: ModelTagCollection = model.tag_collection
                # If the tag is already listed in the catalog..
                if tag in tag_collection.tags.keys():
                    # Do Nothing
                    pass
                else:
                    # Tag isn't already in the catalog, so add it.
                    new_model_tag = ModelTag(name=tag, ollama_info=ollama_info)
                    tag_collection.tags[f"{tag}"] = new_model_tag
                    # self.catalog.models[f"{name}"].tags[tag] = new_model_tag
            else:
                new_model_tag = ModelTag(name=tag, ollama_info=ollama_info)
                new_model_tag_collection = ModelTagCollection()
                new_model_tag_collection.tags = {f"{new_model_tag.name}": new_model_tag}
                new_model = CatalogLLM(
                    name=name, tag_collection=new_model_tag_collection
                )
                self.catalog.models[name] = new_model

    def calling_back(self, message: str):
        log.info(message)

    async def do_work(self, job_key, files=None):
        iter_over = files if files else range(40)
        jobs = self.context["jobs"]
        for file, file_number in enumerate(iter_over):
            job_info = jobs[job_key]
            job_info["iteration"] = file_number
            job_info["status"] = "inprogress"
            await asyncio.sleep(1)
        jobs[job_key]["status"] = "done"
        self.calling_back(f"Howdy doody from: {job_key}")

    async def do_work_wrap(self):
        identifier = str(uuid.uuid4())
        self.context["jobs"][identifier] = {}
        asyncio.run_coroutine_threadsafe(
            self.do_work(identifier),
            loop=asyncio.get_running_loop(),
        )
        return identifier

    async def download(self, job_key, model: str, tag: str, finish_code: str):
        jobs = self.context["jobs"]
        try:
            iter = 0
            async for part in await self.ollama_aclient.pull(
                f"{model}:{tag}", stream=True
            ):
                log.info(part)
                iter += 1
                job_info = jobs[job_key]
                job_info["iteration"] = iter
                job_info["status"] = f"{part}"
                job_info["finish_code"] = finish_code
        except Exception as e:
            log.error(e)

        self.add_to_catalog(model=model, tag=tag)
        jobs[job_key]["status"] = "done"

    async def download_wrap(self, model: str, tag: str):
        identifier = str(uuid.uuid4())
        self.context["jobs"][identifier] = {}
        asyncio.run_coroutine_threadsafe(
            self.download(
                identifier, model=model, tag=tag, finish_code=f"{model}:{tag}"
            ),
            loop=asyncio.get_running_loop(),
        )
        return identifier

    def add_to_catalog(self, model: str, tag: str):
        try:
            new_model_tag = ModelTag(name=tag)
            if model in self.catalog.models.keys():
                catalog_model = self.catalog.models[f"{model}"]
                tag_collection = catalog_model.tag_collection
                if tag in tag_collection.tags.keys():
                    # tag was already in the library so do nothing.
                    pass
                else:
                    tag_collection.tags[f"{tag}"] = new_model_tag
            else:
                # new model in the catalog
                new_tag_collection = ModelTagCollection()
                new_tag_collection.tags[f"{tag}"] = new_model_tag
                new_model = CatalogLLM(name=model, tag_collection=new_tag_collection)
                self.catalog.models[f"{model}"] = new_model
        except Exception as e:
            log.error(e)

    def pull(self, model: str, tag: str):
        try:
            response: StatusResponse = self.ollama_client.pull(
                f"{model}:{tag}", stream=True
            )
            for message in response:
                log.info(message)

        except Exception as e:
            log.error(e)
            log.error(message)
        if message.status == "success":
            try:
                new_model_tag = ModelTag(name=tag)
                if model in self.catalog.models.keys():
                    catalog_model = self.catalog.models[f"{model}"]
                    tag_collection = catalog_model.tag_collection
                    if tag in tag_collection.tags.keys():
                        # tag was already in the library so do nothing.
                        pass
                    else:
                        tag_collection.tags[f"{tag}"] = new_model_tag
                else:
                    # new model in the catalog
                    new_tag_collection = ModelTagCollection()
                    new_tag_collection.tags[f"{tag}"] = new_model_tag
                    new_model = CatalogLLM(
                        name=model, tag_collection=new_tag_collection
                    )
                    self.catalog.models[f"{model}"] = new_model
            except Exception as e:
                log.error(e)
                log.error(response)
        else:
            raise Exception(f"Could not download {model}:{tag}")

    def delete(self, model: str, tag: str):
        try:
            response: StatusResponse = self.ollama_client.delete(f"{model}:{tag}")
        except Exception as e:
            log.error(e)
            log.error(response)
        try:
            model = self.catalog.models[f"{model}"]
            tag_collection = model.tag_collection
            tag_collection.tags.pop(f"{tag}")
        except Exception as e:
            log.error(e)
            log.error(response)


class OllamaRegistry:
    """
    A high level object for representing ollama models available for download.

    Scrapes ollama.com for available models and tags...

    Attributes:
        url: str: The url of the ollama library.
        catalog: Catalog: A catalog object representing ollama models and tags.
        delay: int = 3: The delay in seconds which the object waits before issuing a request to the url.
        cache_dir: str = path/to/wollama/cache/:  The file directory at which the catalog is saved as a pickle.
    """

    def __init__(
        self,
        url: str = "https://ollama.com/library",
        delay: int = 3,
        cache_dir: str = wollama_cache_dir,
    ):
        self.url = url
        self.cache_dir = cache_dir
        self.catalog: Catalog = Catalog(name="remote-ollama-catalog")
        self.delay = delay
        self.context = {"jobs": {}}
        # if os.path.exists(cache_dir):
        #     try:
        #         print("Attempting to load catalog from cache")
        #         self.load_from_cache()
        #         print("Loaded library from cache!...")
        #     except:
        #         print("Loading from cache failed...")
        #         print(f"Querying {self.url}")
        #         self.refresh()
        # else:
        #     print(f"Querying {self.url}")
        #     self.refresh()

    def save_to_cache(self):
        catalog: Catalog = self.catalog
        try:
            catalog.save_to_cache(file_dir=wollama_cache_dir)
        except Exception as e:
            log.error(e)

    def load_from_cache(self):
        # Open the file in binary mode
        catalog: Catalog = self.catalog
        try:
            catalog.load_from_cache(file_dir=wollama_cache_dir)
        except Exception as e:
            log.error(e)
            raise e

    async def do_work(self, job_key, files=None):
        iter_over = files if files else range(40)
        jobs = self.context["jobs"]
        for file, file_number in enumerate(iter_over):
            job_info = jobs[job_key]
            job_info["iteration"] = file_number
            job_info["status"] = "inprogress"
            await asyncio.sleep(1)
        jobs[job_key]["status"] = "done"
        self.calling_back(f"Howdy doody from: {job_key}")

    async def arefresh(self):
        identifier = str(uuid.uuid4())
        job_type = "refresh-library"
        self.context["jobs"][identifier] = {}
        self.context["jobs"][identifier]["finish_code"] = (
            "Finished refreshing the library!"
        )

        asyncio.run_coroutine_threadsafe(
            self.afetch_model_list(url=self.url, job_id=identifier),
            loop=asyncio.get_running_loop(),
        )
        # self.catalog = self.afetch_model_list(url=self.url)
        return identifier
        # self.save_to_cache()

    def refresh(self):
        self.catalog = self.fetch_model_list(url=self.url)
        self.save_to_cache()

    async def afetch_tags(
        self, model_name: str = None, timeout: int = 10
    ) -> ModelTagCollection:
        """
        Fetches the model tags from the remote model library.

        Args:
            url (str): The URL of the website to fetch, defaults to https://ollama.com/library
            timeout (int): Request timeout in seconds (default: 10)

        Returns:
            ModelTagCollection

        Raises:
            ValueError: If URL is invalid or empty
        """

        # Creating a URL
        yarl_url = URL(f"{self.url}")
        log.debug(yarl_url.host)  # 'example.com'
        log.debug(yarl_url.path)  # '/path/to/resource'# Adding query parameters
        yarl_url = yarl_url.with_path(f"/library/{model_name}")
        url = str(yarl_url)
        log.debug(url)  # 'https://example.com/new/path?key=value&param=other'

        # Input validation
        if not url or not isinstance(url, str):
            raise ValueError("URL must be a non-empty string")

        # Ensure URL has a scheme
        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        # Validate URL format
        try:
            url_parse = urllib.parse.urlparse(url)
            if not all([url_parse.scheme, url_parse.netloc]):
                raise ValueError("Invalid URL format")
        except Exception:
            raise ValueError("Invalid URL format")

        try:
            # Fetch the website
            await asyncio.sleep(self.delay)
            # response = requests.get(url, timeout=timeout)
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{url}") as response:
                    response.raise_for_status()
                    text = await response.text(encoding="utf-8")
                    # Parse HTML with BeautifulSoup
                    soup = BeautifulSoup(text, "html.parser")
                    # https://realpython.com/beautiful-soup-web-scraper-python/#step-3-parse-html-code-with-beautiful-soup
                    # Note: You’ll want to pass .content instead of .text to avoid problems with character encoding. The .content attribute holds raw bytes, which Python’s built-in HTML parser can decode better than the text representation you printed earlier using the .text attribute.

            # now get all the anchor tags
            results = soup.find_all("a")

            # now iterate and extract the model urls..
            tag_collection = ModelTagCollection()
            for result in results:
                # Save the tags.
                if f"/library/{model_name}:" in result["href"]:
                    new_tag = ModelTag()
                    tag_url = URL(result["href"]).path
                    result = tag_url.split(":")[-1]
                    new_tag.name = result
                    new_tag.link = tag_url
                    tag_collection.tags[f"{new_tag.name}"] = new_tag

            return tag_collection

        except requests.exceptions.RequestException as e:
            log.error(f"Error fetching website: {str(e)}")
            return ModelTagCollection()
        except Exception as e:
            log.error(f"Unexpected error: {str(e)}")
            return ModelTagCollection()

    def fetch_tags(
        self, model_name: str = None, timeout: int = 10
    ) -> ModelTagCollection:
        """
        Fetches the model tags from the remote model library.

        Args:
            url (str): The URL of the website to fetch, defaults to https://ollama.com/library
            timeout (int): Request timeout in seconds (default: 10)

        Returns:
            ModelTagCollection

        Raises:
            ValueError: If URL is invalid or empty
        """

        # Creating a URL
        yarl_url = URL(f"{self.url}")
        log.debug(yarl_url.host)  # 'example.com'
        log.debug(yarl_url.path)  # '/path/to/resource'# Adding query parameters
        yarl_url = yarl_url.with_path(f"/library/{model_name}")
        url = str(yarl_url)
        log.debug(url)  # 'https://example.com/new/path?key=value&param=other'

        # Input validation
        if not url or not isinstance(url, str):
            raise ValueError("URL must be a non-empty string")

        # Ensure URL has a scheme
        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        # Validate URL format
        try:
            url_parse = urllib.parse.urlparse(url)
            if not all([url_parse.scheme, url_parse.netloc]):
                raise ValueError("Invalid URL format")
        except Exception:
            raise ValueError("Invalid URL format")

        try:
            # Fetch the website
            # response = requests.get(url, headers=headers, timeout=timeout)
            time.sleep(self.delay)
            response = requests.get(url, timeout=timeout)
            response.raise_for_status()  # Raise exception for bad status codes

            # Parse HTML with BeautifulSoup
            soup = BeautifulSoup(response.content, "html.parser")
            # https://realpython.com/beautiful-soup-web-scraper-python/#step-3-parse-html-code-with-beautiful-soup
            # Note: You’ll want to pass .content instead of .text to avoid problems with character encoding. The .content attribute holds raw bytes, which Python’s built-in HTML parser can decode better than the text representation you printed earlier using the .text attribute.

            # now get all the anchor tags
            results = soup.find_all("a")

            # now iterate and extract the model urls..
            tag_collection = ModelTagCollection()
            for result in results:
                # Save the tags.
                if f"/library/{model_name}:" in result["href"]:
                    new_tag = ModelTag()
                    tag_url = URL(result["href"]).path
                    result = tag_url.split(":")[-1]
                    new_tag.name = result
                    new_tag.link = tag_url
                    tag_collection.tags[f"{new_tag.name}"] = new_tag

            return tag_collection

        except requests.exceptions.RequestException as e:
            log.error(f"Error fetching website: {str(e)}")
            return None
        except Exception as e:
            log.error(f"Unexpected error: {str(e)}")
            return None

    async def afetch_model_list(
        self, url: str, job_id: str, timeout: int = 10
    ) -> Catalog:
        """
        Fetches the model cards from the remote model library.

        Args:
            url (str): The URL of the website to fetch, defaults to https://ollama.com/library
            timeout (int): Request timeout in seconds (default: 10)

        Returns:
            Catalog

        Raises:
            ValueError: If URL is invalid or empty
        """
        jobs = self.context["jobs"]
        job_info = jobs[job_id]
        job_info["status"] = "Preparing to fetch model and tag metadata..."
        # Input validation
        if not url or not isinstance(url, str):
            raise ValueError("URL must be a non-empty string")

        # Ensure URL has a scheme
        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        # Validate URL format
        try:
            url_parse = urllib.parse.urlparse(url)
            if not all([url_parse.scheme, url_parse.netloc]):
                raise ValueError("Invalid URL format")
        except Exception:
            raise ValueError("Invalid URL format")

        try:
            # Fetch the website
            # response = requests.get(url, headers=headers, timeout=timeout)
            await asyncio.sleep(self.delay)
            # response = requests.get(url, timeout=timeout)
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{url}") as response:
                    response.raise_for_status()
                    text = await response.text(encoding="utf-8")
                    # Raise exception for bad status codes
                    # Parse HTML with BeautifulSoup
                    soup = BeautifulSoup(text, "html.parser")
                    # https://realpython.com/beautiful-soup-web-scraper-python/#step-3-parse-html-code-with-beautiful-soup
                    # Note: You’ll want to pass .content instead of .text to avoid problems with character encoding. The .content attribute holds raw bytes, which Python’s built-in HTML parser can decode better than the text representation you printed earlier using the .text attribute.

            # Try to get the repo div...
            results = soup.find(id="repo")
            # Now try to get the list
            results = results.find(role="list")

            # now get all the anchor tags
            results = results.find_all("a")

            # now iterate and extract the model urls..
            catalog = Catalog()
            models = catalog.models
            for result in results:
                # Save the tags.
                description_stub = result.find("p").text
                link_stub = result["href"]
                name_stub = link_stub.split("/")[-1]
                try:
                    tag_collection = await self.afetch_tags(model_name=name_stub)
                except Exception as e:
                    log.error(f"Trouble pulling tags for {name_stub}")
                    log.error(f"{e}")
                    tag_collection = ModelTagCollection()
                new_model = CatalogLLM(
                    name=name_stub,
                    link=f"{url_parse.scheme}://{url_parse.netloc}{link_stub}",
                    short_description=f"{description_stub}",
                    tag_collection=tag_collection,
                )
                models[f"{new_model.name}"] = new_model
                job_info["iteration"] = "Null"
                status = f"Retrieved {name_stub} metadata..."
                job_info["status"] = status
                log.info(f"{status}")
            job_info["status"] = "done"
            self.catalog = catalog
            self.save_to_cache()
            return catalog

        except requests.exceptions.RequestException as e:
            log.error(f"Error fetching website: {str(e)}")
            return self.catalog
        except Exception as e:
            log.error(f"Unexpected error: {str(e)}")
            return self.catalog

    def fetch_model_list(self, url: str, timeout: int = 10) -> Catalog:
        """
        Fetches the model cards from the remote model library.

        Args:
            url (str): The URL of the website to fetch, defaults to https://ollama.com/library
            timeout (int): Request timeout in seconds (default: 10)

        Returns:
            Catalog

        Raises:
            ValueError: If URL is invalid or empty
        """
        # Input validation
        if not url or not isinstance(url, str):
            raise ValueError("URL must be a non-empty string")

        # Ensure URL has a scheme
        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        # Validate URL format
        try:
            url_parse = urllib.parse.urlparse(url)
            if not all([url_parse.scheme, url_parse.netloc]):
                raise ValueError("Invalid URL format")
        except Exception:
            raise ValueError("Invalid URL format")

        try:
            # Fetch the website
            # response = requests.get(url, headers=headers, timeout=timeout)
            time.sleep(self.delay)
            response = requests.get(url, timeout=timeout)
            response.raise_for_status()  # Raise exception for bad status codes

            # Parse HTML with BeautifulSoup
            soup = BeautifulSoup(response.content, "html.parser")
            # https://realpython.com/beautiful-soup-web-scraper-python/#step-3-parse-html-code-with-beautiful-soup
            # Note: You’ll want to pass .content instead of .text to avoid problems with character encoding. The .content attribute holds raw bytes, which Python’s built-in HTML parser can decode better than the text representation you printed earlier using the .text attribute.

            # Try to get the repo div...
            results = soup.find(id="repo")
            # Now try to get the list
            results = results.find(role="list")

            # now get all the anchor tags
            results = results.find_all("a")

            # now iterate and extract the model urls..
            catalog = Catalog()
            models = catalog.models
            for result in results:
                # Save the tags.
                description_stub = result.find("p").text
                link_stub = result["href"]
                name_stub = link_stub.split("/")[-1]
                tag_collection = self.fetch_tags(model_name=name_stub)
                new_model = CatalogLLM(
                    name=name_stub,
                    link=f"{url_parse.scheme}://{url_parse.netloc}{link_stub}",
                    short_description=f"{description_stub}",
                    tag_collection=tag_collection,
                )
                models[f"{new_model.name}"] = new_model
            return catalog

        except requests.exceptions.RequestException as e:
            log.error(f"Error fetching website: {str(e)}")
            return None
        except Exception as e:
            log.error(f"Unexpected error: {str(e)}")
            return None


# TODO: Setup an actual test suite.
if __name__ == "__main__":
    # Get environment variables
    dotenv_path = Path("../../.env")
    load_dotenv(dotenv_path=dotenv_path)
    OLLAMA_ADDRESS = os.getenv("OLLAMA_ADDRESS")

    # Initialize the ollama client
    oclient = Client(host=OLLAMA_ADDRESS)
    aclient = AsyncClient(host=OLLAMA_ADDRESS)

    # Test local library.
    local_library = OllamaManager(client=oclient)
    local_models = local_library.catalog.models
    # Test the function
    # ollama_remote = OllamaRemote()
    # model_list = ollama_remote.models
    models = local_models
    if models:
        print("URL: Locally installed models")
        for model_key in models.keys():
            model = models[f"{model_key}"]
            tags = list(model.tag_collection.tags.keys())
            print(f"""
--------------------------------------------------------------
{model.name}     
{model.short_description}
{model.link}
Tags: {tags}
--------------------------------------------------------------
""")

    # Test the remote
    # ollama_remote = OllamaRemote()
    # model_list = ollama_remote.models
    ollama_remote = OllamaRegistry()
    # ollama_remote.load_from_cache()
    # remote_catalog = ollama_remote.catalog
    # remote_catalog.export_catalog("./catalog.json")
    # ollama_remote.export_catalog("./catalog.json")
    ollama_remote.refresh()
    models = ollama_remote.catalog.models
    if models:
        print("URL: Locally installed models")
        for model_key in models.keys():
            model = models[f"{model_key}"]
            tags = list(model.tag_collection.tags.keys())
            print(f"""
--------------------------------------------------------------
{model.name}     
{model.short_description}
{model.link}
Tags: {tags}
--------------------------------------------------------------
""")

    # try deleting a model.
    local_library.pull(model="llama3.2", tag="1b")
    local_library.delete(model="llama3.2", tag="1b")
