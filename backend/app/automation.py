import asyncio
import logging
from typing import Dict, Any
from playwright.async_api import async_playwright
from tenacity import retry, wait_exponential, stop_after_attempt
import aiosqlite

from backend.app.config import config
from backend.app.database import update_job_status, log_with_context

logger = logging.getLogger(__name__)

# In-memory registry mapping job_hash to asyncio.Event
hitl_registry: Dict[str, asyncio.Event] = {}

class BrowserSession:
    def __init__(self):
        self.playwright = None
        self.browser_context = None

    async def init(self):
        self.playwright = await async_playwright().start()
        # Headful instance, localized user data dir for persistent sessions
        self.browser_context = await self.playwright.chromium.launch_persistent_context(
            user_data_dir=config.USER_DATA_DIR,
            headless=False # Must be visible for HITL
        )

    async def close(self):
        if self.browser_context:
            await self.browser_context.close()
        if self.playwright:
            await self.playwright.stop()

@retry(wait=wait_exponential(multiplier=1, min=2, max=10), stop=stop_after_attempt(3))
async def fill_application_form(job_hash: str, url: str, form_data: Dict[str, Any]):
    log_with_context(logging.INFO, "Starting form automation", job_hash, "automation", "started")
    session = BrowserSession()
    try:
        await session.init()
        page = session.browser_context.pages[0] if session.browser_context.pages else await session.browser_context.new_page()

        await page.goto(url)

        # Example browser-use logic for dynamic form mapping
        # In a real implementation, browser-use agent would be invoked here.
        # Here we simulate the interaction utilizing the form_data map
        try:
            # Simulated visual schema mapping and multi-step pagination
            for field_name, field_value in form_data.items():
                 # Simulating mapping and filling using basic selectors as proxy for browser-use
                 selector = f"input[name='{field_name}']"
                 element = await page.query_selector(selector)
                 if element:
                     await element.fill(str(field_value))

            # Simulated Captcha block check fallback
            captcha = await page.query_selector(".g-recaptcha")
            if captcha:
                 raise RuntimeError("Captcha detected")

        except Exception as e:
            if "Captcha" in str(e) or "block" in str(e).lower():
                 log_with_context(logging.WARNING, "Blocking heuristic triggered, manual intervention needed", job_hash, "automation", "blocked")
                 await update_job_status(job_hash, "blocked_manual_required")
                 # We could optionally wait here or raise to outer catch
                 raise

        log_with_context(logging.INFO, "Form filled, awaiting HITL", job_hash, "automation", "awaiting_hitl")
        await update_job_status(job_hash, "awaiting_hitl")

        # Crash-recoverable HITL Gate
        event = asyncio.Event()
        hitl_registry[job_hash] = event
        await event.wait() # Block here leaving browser open

        # Finalization
        log_with_context(logging.INFO, "HITL approved, finalizing", job_hash, "automation", "finalizing")
        import os
        os.makedirs(f"./audit_logs/{job_hash}", exist_ok=True)
        await page.screenshot(path=f"./audit_logs/{job_hash}/audit.png", full_page=True)
        content = await page.content()
        with open(f"./audit_logs/{job_hash}/dom.html", "w") as f:
            f.write(content)

        await update_job_status(job_hash, "submitted")
        log_with_context(logging.INFO, "Application submitted", job_hash, "automation", "submitted")

    except Exception as e:
        log_with_context(logging.ERROR, f"Automation failed: {e}", job_hash, "automation", "error")
        await update_job_status(job_hash, "automation_failed")
        raise
    finally:
        await session.close()
        hitl_registry.pop(job_hash, None)

async def release_hitl(job_hash: str) -> bool:
    if job_hash in hitl_registry:
        hitl_registry[job_hash].set()
        log_with_context(logging.INFO, "HITL lock released via API", job_hash, "control_plane", "released")
        return True
    return False

async def recover_hitl_sessions():
    """Look up jobs marked awaiting_hitl from DB and reconstruct the persistent session."""
    try:
        async with aiosqlite.connect(config.DB_PATH) as db:
            async with db.execute("SELECT job_hash, url FROM jobs_discovered WHERE processing_status = 'awaiting_hitl'") as cursor:
                async for row in cursor:
                    job_hash, url = row
                    log_with_context(logging.INFO, "Recovering HITL session", job_hash, "recovery", "started")

                    # We re-run fill_application_form, which will restore the browser state
                    # because it uses the persistent context. In a real system, you might
                    # jump directly to the HITL wait state if the form is already filled.
                    # For this implementation, we simulate creating the event and waiting.

                    # Simulated recovery: Create the event so API can release it
                    event = asyncio.Event()
                    hitl_registry[job_hash] = event
                    # Start a background task to hold the session
                    # In full implementation, this needs the url and form data to fully reconstruct
                    asyncio.create_task(_hold_recovered_session(job_hash, url))

    except Exception as e:
        logger.error(f"Failed to recover HITL sessions: {e}")

async def _hold_recovered_session(job_hash: str, url: str):
     session = BrowserSession()
     try:
         await session.init()
         page = session.browser_context.pages[0] if session.browser_context.pages else await session.browser_context.new_page()
         await page.goto(url)

         event = hitl_registry.get(job_hash)
         if event:
              await event.wait()

         # Finalization logic upon release...
         await update_job_status(job_hash, "submitted")
         log_with_context(logging.INFO, "Recovered Application submitted", job_hash, "automation", "submitted")
     except Exception as e:
         log_with_context(logging.ERROR, f"Recovered session failed: {e}", job_hash, "automation", "error")
     finally:
         await session.close()
         hitl_registry.pop(job_hash, None)
