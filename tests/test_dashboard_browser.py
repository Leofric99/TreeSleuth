import json
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
import pytest_asyncio
from playwright.async_api import Page, async_playwright, expect

STATIC_DIRECTORY = Path(__file__).resolve().parents[1] / "static"


@pytest_asyncio.fixture
async def page():
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        page = await browser.new_page()
        yield page
        await browser.close()


class QuietStaticHandler(SimpleHTTPRequestHandler):
    def log_message(self, _format: str, *args: object) -> None:
        return


@pytest.fixture
def dashboard_url():
    handler = partial(QuietStaticHandler, directory=str(STATIC_DIRECTORY))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    address, port = server.server_address
    yield f"http://{address}:{port}"
    server.shutdown()
    worker.join(timeout=5)
    server.server_close()


def _sse(events: list[dict[str, object]]) -> str:
    return "".join(
        f"id: {event['sequence']}\nevent: {event['event']}\ndata: {json.dumps(event)}\n\n"
        for event in events
    )


async def _mock_models(page: Page) -> None:
    await page.route(
        "**/api/system-check",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"ollama_available": True, "models": ["fixture-model"], "error": None}),
        ),
    )
    await page.route("https://cdn.tailwindcss.com/**", lambda route: route.abort())


@pytest.mark.asyncio
async def test_dashboard_updates_person_status_and_reviews_sources(page: Page, dashboard_url: str) -> None:
    await _mock_models(page)
    person = {
        "id": "I1",
        "name": "Ada Lovelace",
        "birth_year": 1815,
        "death_year": 1852,
        "document_count": 1,
        "status": "Finished",
        "error": None,
        "biography": "Ada Lovelace was born in London in 1815.",
        "biography_path": "output/ada_LifeStory.txt",
        "conflicts": [
            {
                "outcome": "conflict",
                "source_document_id": "letter.txt",
                "source_claim": "A census lists Ada in 1860.",
                "baseline_source_id": "gedcom:I1:death",
                "baseline_claim": "Ada died in 1852.",
                "explanation": "The dates conflict.",
                "confidence": 0.9,
            }
        ],
    }
    events = [
        {
            "run_id": "browser-success",
            "sequence": 0,
            "event": "file",
            "stage": "Parsing Records",
            "message": "Extracted letter.txt",
            "payload": {},
        },
        {
            "run_id": "browser-success",
            "sequence": 1,
            "event": "person",
            "stage": "Comparing with GEDCOM",
            "message": "Ada Lovelace: Comparing with GEDCOM",
            "person_id": "I1",
            "payload": {**person, "status": "Comparing with GEDCOM"},
        },
        {
            "run_id": "browser-success",
            "sequence": 2,
            "event": "person",
            "stage": "Writing Biography",
            "message": "Ada Lovelace: Writing Biography",
            "person_id": "I1",
            "payload": {**person, "status": "Writing Biography"},
        },
        {
            "run_id": "browser-success",
            "sequence": 3,
            "event": "person",
            "stage": "Finished",
            "message": "Ada Lovelace: Finished",
            "person_id": "I1",
            "payload": person,
        },
        {
            "run_id": "browser-success",
            "sequence": 4,
            "event": "complete",
            "stage": "Finished",
            "message": "Analysis pipeline completed",
            "payload": {},
        },
    ]
    await page.route(
        "**/api/analyze-directory",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "root": "C:/Research",
                    "gedcom_files": 1,
                    "document_files": 1,
                    "files_by_type": {"gedcom": 1, "text": 1},
                    "has_gedcom_baseline": True,
                }
            ),
        ),
    )
    await page.route(
        "**/api/run-pipeline",
        lambda route: route.fulfill(
            status=202,
            content_type="application/json",
            body=json.dumps(
                {"run_id": "browser-success", "events_url": "/api/runs/browser-success/events"}
            ),
        ),
    )
    await page.route(
        "**/api/runs/browser-success/events",
        lambda route: route.fulfill(
            status=200,
            headers={"content-type": "text/event-stream", "cache-control": "no-cache"},
            body=_sse(events),
        ),
    )
    await page.route(
        "**/api/runs/browser-success",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {"run_id": "browser-success", "status": "completed", "people": [person], "warnings": []}
            ),
        ),
    )

    await page.goto(dashboard_url)
    await page.get_by_label("Folder path").fill("C:/Research")
    await page.get_by_role("button", name="Preview folder").click()
    await page.get_by_label("Local Ollama model").select_option("fixture-model")
    await page.get_by_role("button", name="Start analysis").click()

    await expect(page.get_by_role("cell", name="Ada Lovelace")).to_be_visible()
    await expect(page.locator("#runStatus")).to_have_text("Finished")
    await expect(page.get_by_text("Extracted letter.txt")).to_be_visible()
    await page.get_by_role("button", name="View", exact=True).click()
    await expect(page.get_by_text("Ada Lovelace was born in London in 1815.")).to_be_visible()
    await expect(page.get_by_text("A census lists Ada in 1860.")).to_be_visible()
    await expect(page.get_by_text("Ada died in 1852.")).to_be_visible()


@pytest.mark.asyncio
async def test_dashboard_shows_failed_analysis_without_success_fallback(page: Page, dashboard_url: str) -> None:
    await _mock_models(page)
    failed_person = {
        "id": "I-failed",
        "name": "Uncertain Person",
        "birth_year": None,
        "death_year": None,
        "document_count": 1,
        "status": "Failed",
        "error": "Local model returned invalid JSON.",
        "biography": None,
        "biography_path": None,
        "conflicts": [],
    }
    error_event = {
        "run_id": "browser-failure",
        "sequence": 0,
        "event": "error",
        "stage": "Failed",
        "message": "Pipeline failed: invalid model response",
        "payload": {},
    }
    await page.route(
        "**/api/run-pipeline",
        lambda route: route.fulfill(
            status=202,
            content_type="application/json",
            body=json.dumps(
                {"run_id": "browser-failure", "events_url": "/api/runs/browser-failure/events"}
            ),
        ),
    )
    await page.route(
        "**/api/runs/browser-failure/events",
        lambda route: route.fulfill(
            status=200,
            headers={"content-type": "text/event-stream"},
            body=_sse([error_event]),
        ),
    )
    await page.route(
        "**/api/runs/browser-failure",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "run_id": "browser-failure",
                    "status": "failed",
                    "people": [failed_person],
                    "warnings": [],
                    "error": "invalid model response",
                }
            ),
        ),
    )

    await page.goto(dashboard_url)
    await page.get_by_label("Folder path").fill("C:/Research")
    await page.get_by_label("Local Ollama model").select_option("fixture-model")
    await page.get_by_role("button", name="Start analysis").click()
    await page.get_by_role("button", name="View", exact=True).click()

    await expect(page.locator("#errorMessage")).to_have_text("Pipeline failed: invalid model response")
    await expect(page.get_by_text("Local model returned invalid JSON.")).to_be_visible()
    await expect(page.get_by_text("Analysis did not complete. Review the status and error above.")).to_be_visible()
