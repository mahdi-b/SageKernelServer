import os
import requests
from dotenv import load_dotenv
from urllib.parse import urlparse, urlunparse

load_dotenv()


def get_sage3_token():
    # Load params exported by Docker
    SAGE3_JWT_TOKEN = os.getenv("TOKEN")
    # Production or Development
    production = os.getenv("ENVIRONMENT") == "production"
    SAGE3_SERVER = os.getenv("SAGE3_SERVER", "localhost:3333")
    node_url = ("https://" if production else "http://") + SAGE3_SERVER

    # Get the jupyter token from the route /api/configuration
    head = {"Authorization": "Bearer {}".format(SAGE3_JWT_TOKEN)}
    r = requests.get(node_url + "/api/configuration", headers=head)
    token = r.json()["token"]
    return token


def get_jupyter_token(jupyter_hub_type="LOCAL"):
    if jupyter_hub_type == "LOCAL":
        return os.getenv("JUPYTER_TOKEN")
    elif jupyter_hub_type == "SAGE3":
        token = get_sage3_token()
        if token is not None:
            return token
        else:
            raise ValueError("Could not get the Jupter server token ")
    else:
        raise ValueError("JUPYTER_HUB_TYPE must be either LOCAL or SAGE3")


def build_jupyter_url(url):
    # Build a valid Jupyter URL
    # Get the Jupyter token
    token = get_jupyter_token(os.getenv('JUPYTER_HUB_TYPE'))
    # Concat the URL and the token
    parsed_url = urlparse(url + "?token=" + token)
    if not all([parsed_url.scheme, parsed_url.netloc, parsed_url.query]):
        raise ValueError("Invalid URL")

    base_url = urlunparse(
        (parsed_url.scheme, parsed_url.netloc, parsed_url.path, "", "", "")
    )
    return parsed_url, base_url
