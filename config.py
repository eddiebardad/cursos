import os
import logging

class Config:
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    HTTP_TIMEOUT = int(os.getenv("HTTP_TIMEOUT", 30))
    USER_AGENT = os.getenv("USER_AGENT", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) CourseScraper/1.0")

config = Config()
