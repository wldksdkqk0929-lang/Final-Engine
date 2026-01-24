import os
import sys
import logging
from contextlib import contextmanager

class SniperLogger:
    """
    [Phase-4B] Sniper System Logger
    - Supports GitHub Actions Grouping & Annotations
    - Uses Context Manager for safe UI grouping
    """

    def __init__(self, name="SNIPER"):
        self.name = name
        self.is_actions = os.getenv("GITHUB_ACTIONS") == "true"

        # Standard Logging Setup
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.INFO)

        if not self.logger.handlers:
            handler = logging.StreamHandler(sys.stdout)
            formatter = logging.Formatter('[%(levelname)s] %(message)s')
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)

    @contextmanager
    def group(self, title: str):
        """
        Context Manager for GitHub Actions Log Grouping.
        Ensures '::endgroup::' is always called even if errors occur.
        Usage:
            with logger.group("My Section"):
                ...
        """
        if self.is_actions:
            print(f"::group::{title}")
            sys.stdout.flush()
        else:
            print(f"\n{'='*5} [START: {title}] {'='*5}")

        try:
            yield
        finally:
            if self.is_actions:
                print("::endgroup::")
                sys.stdout.flush()
            else:
                print(f"{'='*5} [END: {title}] {'='*5}\n")

    def info(self, message: str):
        self.logger.info(message)

    def success(self, message: str):
        if self.is_actions:
            print(f"✅ {message}")
        else:
            self.logger.info(f"✅ {message}")

    def warning(self, message: str):
        if self.is_actions:
            print(f"::warning::{message}")
        else:
            self.logger.warning(message)

    def error(self, message: str, exception: Exception = None):
        if self.is_actions:
            print(f"::error::{message}")
        else:
            self.logger.error(message)

        if exception:
            self.logger.error(f"Traceback: {str(exception)}")

# Create Singleton Instance
logger = SniperLogger()
