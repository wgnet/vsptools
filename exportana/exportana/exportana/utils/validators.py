from urllib.parse import urlparse


def str_is_url(url_str: str) -> bool:
    EMPTY_VALUE = ""
    parse_result = urlparse(url_str)
    return parse_result.scheme != EMPTY_VALUE and parse_result.netloc != EMPTY_VALUE
