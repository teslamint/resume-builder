try:
    from patchright.sync_api import Error as PlaywrightError
    from patchright.sync_api import TimeoutError as PlaywrightTimeoutError
    from patchright.sync_api import sync_playwright
except ImportError:
    from playwright import sync_api as playwright_sync_api

    sync_playwright = playwright_sync_api.sync_playwright
    PlaywrightError = getattr(playwright_sync_api, "Error", Exception)
    PlaywrightTimeoutError = getattr(playwright_sync_api, "TimeoutError", TimeoutError)

__all__ = ["sync_playwright", "PlaywrightError", "PlaywrightTimeoutError"]
