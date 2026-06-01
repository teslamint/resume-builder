try:
    from patchright.sync_api import TimeoutError as PlaywrightTimeoutError
    from patchright.sync_api import sync_playwright
except ImportError:
    from playwright import sync_api as playwright_sync_api

    sync_playwright = playwright_sync_api.sync_playwright
    PlaywrightTimeoutError = getattr(playwright_sync_api, "TimeoutError", TimeoutError)

__all__ = ["sync_playwright", "PlaywrightTimeoutError"]
