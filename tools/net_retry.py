"""Bounded retries for transport failures, never authentication/code failures."""
import time
import urllib.error
import urllib.request


def urlopen(request, timeout=30, attempts=4):
    for attempt in range(attempts):
        try:
            return urllib.request.urlopen(request, timeout=timeout)
        except urllib.error.HTTPError as error:
            if error.code not in (408, 429, 500, 502, 503, 504) or attempt+1 == attempts:
                raise
            delay = min(60, max(2**attempt, int(error.headers.get('Retry-After', '0') or 0)))
        except (urllib.error.URLError, TimeoutError, ConnectionResetError, ConnectionError):
            if attempt+1 == attempts:
                raise
            delay = 2**attempt
        time.sleep(delay)
