from functools import lru_cache
import logging
import json
import requests

WEBFINGER_TIMEOUT = 10

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


class WebfingerException(Exception):
    def __init__(self, error):
        super().__init__()
        self.error = error


def finger(username, domain):
    try:
        logger.debug("Initiating WebFinger lookup for: username=%s, domain=%s", username, domain)
        res = requests.get(
            f'https://{domain}/.well-known/webfinger',
            params={'resource': f'acct:{username}@{domain}'},
            headers={'Accept': 'application/jrd+json'},
            timeout=WEBFINGER_TIMEOUT,
            verify=True
        )
        res.raise_for_status()
        webfinger_data = res.json()
        logger.debug("Received WebFinger data: %s", json.dumps(webfinger_data, indent=2))
    except requests.RequestException as e:
        logger.error("Error during WebFinger request: %s", e)
        raise WebfingerException(e)

    profile_link = next((rel for rel in webfinger_data.get('links', []) if
                         rel.get('rel') == 'self' and rel.get('type') == 'application/activity+json'), None)
    
    if profile_link is not None:
        logger.debug("Found profile link: %s", profile_link.get('href'))
        profile_data = fetch_remote_profile(profile_link.get('href'))
    else:
        logger.warning("No profile link found in WebFinger data")
        profile_data = None

    data = {
        'webfinger': webfinger_data,
        'profile': profile_data,
    }
    logger.debug("Final combined WebFinger and profile data: %s", json.dumps(data, indent=2))

    return data



@lru_cache(maxsize=256)
def fetch_remote_profile(url):
    try:
        res = requests.get(url, headers={'Accept': 'application/activity+json'})
        res.raise_for_status()
    except requests.RequestException as e:
        raise WebfingerException(e)

    return res.json()
