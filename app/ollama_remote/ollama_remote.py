# Initial generation with grok3 beta
# website_fetcher.py
import time
import os
import requests
import pickle
from bs4 import BeautifulSoup
from typing import Optional
import urllib.parse
from pydantic import BaseModel
from typing import List
from yarl import URL
from ollama import Client


class LanguageModel(BaseModel):
    name: str = ""
    link: str = ""
    short_description: str = ""
    tags: List[str] = []
    installed_tags: List[str] = []


class OllamaRemote:
    url: str = "https://ollama.com/library"
    models: List[LanguageModel] = []
    delay: int = 3
    cache_dir: str = os.path.abspath("./remote-library.json")

    def __init__(
        self,
        ollama_url: str = "https://ollama.com/library",
        cache_dir: str = os.path.abspath("./remote-library.json"),
    ):
        self.url = ollama_url
        self.cache_dir = cache_dir
        if os.path.exists(cache_dir):
            try:
                print("Attempting to load library from cache")
                self.load_from_cache()
                print("Loaded library from cache!...")
            except:
                print("Loading from cache failed...")
                print(f"Querying {self.ollama_url}")
                self.refresh()
        else:
            print(f"Querying {self.ollama_url}")
            self.refresh()

    def save_to_cache(self):
        # Open a file and use dump()
        with open(self.cache_dir, "wb") as file:
            # A new file will be created
            pickle.dump(self, file)

    #
    def load_from_cache(self):
        # Open the file in binary mode
        with open(self.cache_dir, "rb") as file:
            # Call load method to deserialze
            cached_ollama_remote = pickle.load(file)
            self.models = cached_ollama_remote.models

    def refresh(self):
        self.models = self.fetch_model_list(url=self.url)
        self.save_to_cache()

    def fetch_tags(self, model_name: str = None, timeout: int = 10) -> List[str]:
        """
        Fetches the model tags from the remote model library.

        Args:
            url (str): The URL of the website to fetch, defaults to https://ollama.com/library
            timeout (int): Request timeout in seconds (default: 10)

        Returns:
            List[str]

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
            tags = []
            for result in results:
                # Save the tags.
                if f"/library/{model_name}:" in result["href"]:
                    tag_url = URL(result["href"]).path
                    result = tag_url.split(":")[-1]
                    print(result)
                    tags.append(result)

            return tags

        except requests.exceptions.RequestException as e:
            print(f"Error fetching website: {str(e)}")
            return None
        except Exception as e:
            print(f"Unexpected error: {str(e)}")
            return None

    def fetch_model_list(self, url: str, timeout: int = 10) -> [LanguageModel]:
        """
        Fetches the model cards from the remote model library.

        Args:
            url (str): The URL of the website to fetch, defaults to https://ollama.com/library
            timeout (int): Request timeout in seconds (default: 10)

        Returns:
            [LanguageModel]

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
            models = []
            for result in results:
                # Save the tags.
                description_stub = result.find("p").text
                link_stub = result["href"]
                name_stub = link_stub.split("/")[-1]
                tags = self.fetch_tags(model_name=name_stub)
                new_model = LanguageModel(
                    name=name_stub,
                    link=f"{url_parse.scheme}://{url_parse.netloc}{link_stub}",
                    short_description=f"{description_stub}",
                    tags=tags,
                )
                models.append(new_model)

            return models

        except requests.exceptions.RequestException as e:
            print(f"Error fetching website: {str(e)}")
            return None
        except Exception as e:
            print(f"Unexpected error: {str(e)}")
            return None


# TODO: Write this class to accept an OllamaRemote and OllamaClient so that OllamaLibraryManager becomes an aggregator.
class OllamaLibrary:
    catalog: List[LanguageModel] = []
    ollama_remote: OllamaRemote = None
    ollama_client: Client = None

    def __init__(self) -> None:
        pass


# Example usage
if __name__ == "__main__":
    # Test the function
    ollama_remote = OllamaRemote()
    model_list = ollama_remote.models
    if model_list:
        print(f"URL: {ollama_remote.url}")
        for model in model_list:
            print(f"""
--------------------------------------------------------------
{model.name}     
{model.short_description}
{model.link}
--------------------------------------------------------------
""")
