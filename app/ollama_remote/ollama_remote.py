# Initial generation with grok3 beta
# website_fetcher.py
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

    models: Dict[str, CatalogLLM] = {}
    object_version: str = "0.0.0"

    def export_catalog(self, filepath: str) -> str:
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
            print(e)


#


class OllamaLocal:
    """
    A high level object for managing ollama models via an ollama python client.

    Attributes:
        catalog: Catalog: A catalog object representing ollama models and tags.
        ollama_client Client: The ollama python client.
    """

    def __init__(self, client: Client):
        self.catalog = Catalog()
        self.ollama_client = client
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

    def pull(self, model: str, tag: str):
        try:
            response: StatusResponse = self.ollama_client.pull(f"{model}:{tag}")

        except Exception as e:
            print(e)
            print(response)
        if response.status == "success":
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
                print(e)
                print(response)
        else:
            raise Exception(f"Could not download {model}:{tag}")

    def delete(self, model: str, tag: str):
        try:
            response: StatusResponse = self.ollama_client.delete(f"{model}:{tag}")
        except Exception as e:
            print(e)
            print(response)
        try:
            model = self.catalog.models[f"{model}"]
            tag_collection = model.tag_collection
            tag_collection.tags.pop(f"{tag}")
        except Exception as e:
            print(e)
            print(response)


class OllamaRemote:
    """
    A high level object for representing ollama models available for download.

    Scrapes ollama.com for available models and tags...

    Attributes:
        url: str: The url of the ollama library.
        catalog: Catalog: A catalog object representing ollama models and tags.
        delay: int = 3: The delay in seconds which the object waits before issuing a request to the url.
        cache_dir: str:  The file directory at which the catalog is saved as a pickle.
    """

    #
    # url: str = "https://ollama.com/library"
    # catalog: Catalog
    # delay: int = 3
    # cache_dir: str = os.path.abspath("./")
    #
    def __init__(
        self,
        url: str = "https://ollama.com/library",
        delay: int = 3,
        cache_dir: str = os.path.abspath("./remote-catalog-v1.json"),
    ):
        self.url = url
        self.cache_dir = cache_dir
        self.catalog: Catalog = Catalog()
        self.delay = delay
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
        # Open a file and use dump()
        with open(self.cache_dir, "wb") as file:
            # A new file will be created
            pickle.dump(self, file)

    def load_from_cache(self):
        # Open the file in binary mode
        with open(self.cache_dir, "rb") as file:
            # Call load method to deserialze
            cached_ollama_remote = pickle.load(file)
            self.catalog = cached_ollama_remote.catalog
            self.url = cached_ollama_remote.url
            self.delay = cached_ollama_remote.delay
            self.cache_dir = cached_ollama_remote.cache_dir

    def refresh(self):
        self.catalog = self.fetch_model_list(url=self.url)
        self.save_to_cache()

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
        print(yarl_url.host)  # 'example.com'
        print(yarl_url.path)  # '/path/to/resource'# Adding query parameters
        yarl_url = yarl_url.with_path(f"/library/{model_name}")
        url = str(yarl_url)
        print(url)  # 'https://example.com/new/path?key=value&param=other'

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
            print(f"Error fetching website: {str(e)}")
            return None
        except Exception as e:
            print(f"Unexpected error: {str(e)}")
            return None

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
            print(f"Error fetching website: {str(e)}")
            return None
        except Exception as e:
            print(f"Unexpected error: {str(e)}")
            return None


# TODO: Write this class to accept an OllamaRemote and OllamaClient so that OllamaLibraryManager becomes an aggregator.
# class OllamaLibrary:
#     library: LocalModelLibrary
#     ollama_remote: OllamaRemote = None
#     ollama_client: Client = None
#
#     def __init__(self) -> None:
#         pass
#

# Example usage
if __name__ == "__main__":
    # Get environment variables
    dotenv_path = Path("../../.env")
    load_dotenv(dotenv_path=dotenv_path)
    OLLAMA_ADDRESS = os.getenv("OLLAMA_ADDRESS")

    # Initialize the ollama client
    oclient = Client(host=OLLAMA_ADDRESS)
    aclient = AsyncClient(host=OLLAMA_ADDRESS)

    # Test local library.
    local_library = OllamaLocal(client=oclient)
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
    ollama_remote = OllamaRemote()
    ollama_remote.load_from_cache()
    remote_catalog = ollama_remote.catalog
    remote_catalog.export_catalog("./catalog.json")
    # ollama_remote.export_catalog("./catalog.json")
    # ollama_remote.refresh()
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

    # if remote_models:
    #     print(f"URL: {ollama_remote.url}")
    #     for model in model_list:
    #         print(f"""
