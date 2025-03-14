# Initial generation with grok3 beta
# website_fetcher.py
import requests
from bs4 import BeautifulSoup
from typing import Optional
import urllib.parse
from pydantic import BaseModel

# TODO: Make this an environment variable
ollama_library_url = "https://ollama.com/library"


class LanguageModel(BaseModel):
    name: str
    link: str
    short_description: str


def fetch_model_list(
    url: str, timeout: int = 10, user_agent: str = None
) -> [LanguageModel]:
    """
    Fetches the contents of a website and returns it as a WebsiteContent object.

    Args:
        url (str): The URL of the website to fetch
        timeout (int): Request timeout in seconds (default: 10)
        user_agent (str): Custom User-Agent string (optional)

    Returns:

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
        result = urllib.parse.urlparse(url)
        if not all([result.scheme, result.netloc]):
            raise ValueError("Invalid URL format")
    except Exception:
        raise ValueError("Invalid URL format")

    # Set default User-Agent if none provided
    # if user_agent is None:
    #     user_agent = (
    #         "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    #         "AppleWebKit/537.36 (KHTML, like Gecko) "
    #         "Chrome/91.0.4472.124 Safari/537.36"
    #     )

    # headers = {"User-Agent": user_agent}

    try:
        # Fetch the website
        # response = requests.get(url, headers=headers, timeout=timeout)
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
            description_stub = result.find("p").text
            link_stub = result["href"]
            name_stub = link_stub.replace("/library/", "")
            new_model = LanguageModel(
                name=name_stub,
                link=f"https://ollama.com{link_stub}",
                short_description=f"{description_stub}",
            )
            models.append(new_model)

        return models

    except requests.exceptions.RequestException as e:
        print(f"Error fetching website: {str(e)}")
        return None
    except Exception as e:
        print(f"Unexpected error: {str(e)}")
        return None


# Example usage
if __name__ == "__main__":
    # Test the function
    model_list = fetch_model_list(f"{ollama_library_url}")
    if model_list:
        print(f"URL: {ollama_library_url}")
        for model in model_list:
            print(f"""
--------------------------------------------------------------
{model.name}     
{model.short_description}
{model.link}
--------------------------------------------------------------
""")
