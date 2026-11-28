from urllib.parse import urlsplit


class ScraperException(Exception):
    pass


class NetworkError(ScraperException):
    pass


class HTTPStatusError(NetworkError):
    def __init__(
        self,
        status_code: int,
        url: str,
        *,
        waf_blocked: bool = False,
    ) -> None:
        self.status_code = status_code
        self.url = url
        self.host = (urlsplit(url).hostname or "").casefold()
        self.waf_blocked = waf_blocked
        super().__init__(f"HTTP error {status_code} for {url}")


class WAFChallengeError(NetworkError):
    def __init__(self, url: str) -> None:
        self.url = url
        self.host = (urlsplit(url).hostname or "").casefold()
        self.waf_blocked = True
        super().__init__(
            f"Upstream anti-bot challenge detected for {url}; automated bypass is disabled"
        )


class ParsingError(ScraperException):
    pass


class UpstreamFormatError(ParsingError):
    pass


class QualityGateError(ScraperException):
    pass
