class ScraperException(Exception):
    pass

class NetworkError(ScraperException):
    pass

class ParsingError(ScraperException):
    pass
