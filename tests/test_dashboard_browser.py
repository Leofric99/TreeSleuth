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

    await expect(page.get_by_role("cell", name="Ada Lovelace", exact=True)).to_be_hidden()
    await expect(page.locator("#runStatus")).to_have_text("Finished")
    await expect(page.get_by_text("Extracted letter.txt")).to_be_visible()
    await page.locator("#peopleGroups summary").get_by_text("Lovelace (1)", exact=True).click()
    await expect(page.get_by_role("cell", name="Ada Lovelace", exact=True)).to_be_visible()
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
    await page.get_by_text("Person (1)", exact=True).click()
    await page.get_by_role("button", name="View", exact=True).click()

    await expect(page.locator("#errorMessage")).to_have_text("Pipeline failed: invalid model response")
    await expect(page.get_by_text("Local model returned invalid JSON.")).to_be_visible()
    await expect(page.get_by_text("Analysis did not complete. Review the status and error above.")).to_be_visible()


@pytest.mark.asyncio
async def test_dashboard_groups_surnames_and_persists_display_mapping(
    page: Page,
    dashboard_url: str,
) -> None:
    await _mock_models(page)
    people = [
        {
            "id": "I1",
            "name": "Ada Lovelace",
            "given_name": "Ada",
            "surname": "Lovelace",
            "display_surname": "Lovelace",
            "document_count": 0,
            "status": "Ready",
        },
        {
            "id": "I2",
            "name": "Eve Edmonds",
            "given_name": "Eve",
            "surname": "Edmonds",
            "display_surname": "Edmonds",
            "document_count": 0,
            "status": "Ready",
        },
        {
            "id": "I3",
            "name": "Adam Edmunds",
            "given_name": "Adam",
            "surname": "Edmunds",
            "display_surname": "Edmunds",
            "document_count": 0,
            "status": "Ready",
        },
        {
            "id": "I4",
            "name": "Bob Allen",
            "given_name": "Bob",
            "surname": "Allen",
            "display_surname": "Allen",
            "document_count": 0,
            "status": "Ready",
        },
    ]
    events = [
        {
            "run_id": "surname-run",
            "sequence": index,
            "event": "person",
            "stage": person["status"],
            "message": f"{person['name']}: Ready",
            "person_id": person["id"],
            "payload": person,
        }
        for index, person in enumerate(people)
    ]
    events.append(
        {
            "run_id": "surname-run",
            "sequence": len(events),
            "event": "complete",
            "stage": "Ready",
            "message": "Document preparation completed",
            "payload": {},
        }
    )
    await page.route(
        "**/api/run-pipeline",
        lambda route: route.fulfill(
            status=202,
            content_type="application/json",
            body=json.dumps({"run_id": "surname-run", "events_url": "/api/runs/surname-run/events"}),
        ),
    )
    await page.route(
        "**/api/runs/surname-run/events",
        lambda route: route.fulfill(
            status=200,
            headers={"content-type": "text/event-stream"},
            body=_sse(events),
        ),
    )
    await page.route(
        "**/api/runs/surname-run",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "run_id": "surname-run",
                    "status": "completed",
                    "people": people,
                    "surname_mappings": {},
                    "warnings": [],
                }
            ),
        ),
    )
    saved_mappings: dict[str, str] = {}

    async def save_mapping(route):
        nonlocal saved_mappings
        saved_mappings = route.request.post_data_json["mappings"]
        await route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"mappings": {"edmonds": "Edmunds"}}),
        )

    await page.route("**/api/runs/surname-run/surname-mappings", save_mapping)

    await page.goto(dashboard_url)
    await expect(page.get_by_role("button", name="Generate all stories")).to_be_disabled()
    await page.get_by_label("Folder path").fill("C:/Research")
    await page.get_by_label("Local Ollama model").select_option("fixture-model")
    await page.get_by_role("button", name="Start analysis").click()
    await expect(page.locator("#runStatus")).to_have_text("Finished")
    await expect(page.get_by_role("button", name="Generate all stories")).to_be_enabled()
    assert await page.locator("#peopleGroups summary").all_text_contents() == [
        "Allen (1)",
        "Edmonds (1)",
        "Edmunds (1)",
        "Lovelace (1)",
    ]
    await expect(page.get_by_role("cell", name="Eve Edmonds", exact=True)).to_be_hidden()
    await page.locator("#peopleGroups summary").get_by_text("Edmonds (1)", exact=True).click()
    await expect(page.get_by_role("cell", name="Eve Edmonds", exact=True)).to_be_visible()
    await page.locator("#peopleGroups summary").get_by_text("Edmonds (1)", exact=True).click()
    await expect(page.get_by_role("cell", name="Eve Edmonds", exact=True)).to_be_hidden()
    await expect(page.get_by_role("cell", name="Adam Edmunds", exact=True)).to_be_hidden()
    await page.locator("#peopleGroups summary").get_by_text("Edmunds (1)", exact=True).click()
    await expect(page.get_by_role("cell", name="Adam Edmunds", exact=True)).to_be_visible()

    await page.get_by_label("Merge this spelling").select_option("Edmonds")
    await page.get_by_label("Into this surname").select_option("Edmunds")
    await page.get_by_role("button", name="Merge surnames").click()
    await expect(page.get_by_role("status").filter(has_text="Edmonds will be displayed as Edmunds.")).to_be_visible()
    assert saved_mappings == {"Edmonds": "Edmunds"}
    assert await page.locator("#peopleGroups summary").all_text_contents() == [
        "Allen (1)",
        "Edmunds (2)",
        "Lovelace (1)",
    ]
    await expect(page.get_by_role("cell", name="Eve Edmonds", exact=True)).to_be_visible()


@pytest.mark.asyncio
async def test_dashboard_generates_story_for_selected_person(page: Page, dashboard_url: str) -> None:
    await _mock_models(page)
    prepared = {
        "id": "I1",
        "name": "Ada Lovelace",
        "given_name": "Ada",
        "surname": "Lovelace",
        "display_surname": "Lovelace",
        "document_count": 1,
        "status": "Ready",
    }
    finished = {
        **prepared,
        "status": "Finished",
        "biography": "Ada's reviewed life story.",
        "conflicts": [],
    }
    prep_events = [
        {
            "run_id": "prepared",
            "sequence": 0,
            "event": "person",
            "stage": "Ready",
            "message": "Ada Lovelace: Ready",
            "person_id": "I1",
            "payload": prepared,
        },
        {
            "run_id": "prepared",
            "sequence": 1,
            "event": "complete",
            "stage": "Ready",
            "message": "Document preparation completed",
            "payload": {},
        },
    ]
    generation_events = [
        {
            "run_id": "generation",
            "sequence": 0,
            "event": "person",
            "stage": "Finished",
            "message": "Ada Lovelace: Finished",
            "person_id": "I1",
            "payload": finished,
        },
        {
            "run_id": "generation",
            "sequence": 1,
            "event": "complete",
            "stage": "Finished",
            "message": "Story generation completed",
            "payload": {},
        },
    ]
    await page.route(
        "**/api/run-pipeline",
        lambda route: route.fulfill(
            status=202,
            content_type="application/json",
            body=json.dumps({"run_id": "prepared", "events_url": "/api/runs/prepared/events"}),
        ),
    )
    await page.route(
        "**/api/runs/prepared/events",
        lambda route: route.fulfill(
            status=200,
            headers={"content-type": "text/event-stream"},
            body=_sse(prep_events),
        ),
    )
    await page.route(
        "**/api/runs/prepared",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {"run_id": "prepared", "status": "completed", "people": [prepared], "warnings": []}
            ),
        ),
    )
    generation_request: dict[str, object] = {}

    async def generate_one(route):
        nonlocal generation_request
        generation_request = route.request.post_data_json
        await route.fulfill(
            status=202,
            content_type="application/json",
            body=json.dumps(
                {"run_id": "generation", "events_url": "/api/runs/generation/events"}
            ),
        )

    await page.route("**/api/runs/prepared/generate", generate_one)
    await page.route(
        "**/api/runs/generation/events",
        lambda route: route.fulfill(
            status=200,
            headers={"content-type": "text/event-stream"},
            body=_sse(generation_events),
        ),
    )
    await page.route(
        "**/api/runs/generation",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "run_id": "generation",
                    "parent_run_id": "prepared",
                    "status": "completed",
                    "people": [finished],
                    "warnings": [],
                }
            ),
        ),
    )

    await page.goto(dashboard_url)
    await page.get_by_label("Folder path").fill("C:/Research")
    await page.get_by_label("Local Ollama model").select_option("fixture-model")
    await page.get_by_role("button", name="Start analysis").click()
    await page.get_by_text("Lovelace (1)", exact=True).click()
    await expect(page.get_by_role("button", name="Generate story")).to_be_enabled()
    await page.get_by_role("checkbox", name="Select Ada Lovelace for story generation").check()
    await page.get_by_role("button", name="Generate selected stories (1)").click()
    await expect(page.get_by_role("button", name="View", exact=True)).to_be_enabled()
    assert generation_request == {"person_ids": ["I1"]}
    await page.get_by_role("button", name="View", exact=True).click()
    await expect(page.get_by_text("Ada's reviewed life story.")).to_be_visible()


@pytest.mark.asyncio
async def test_dashboard_keeps_generation_disabled_before_preparation_completes(
    page: Page,
    dashboard_url: str,
) -> None:
    await _mock_models(page)
    person = {
        "id": "I1",
        "name": "Ada Lovelace",
        "surname": "Lovelace",
        "display_surname": "Lovelace",
        "document_count": 0,
        "status": "Parsing Records",
    }
    await page.route(
        "**/api/run-pipeline",
        lambda route: route.fulfill(
            status=202,
            content_type="application/json",
            body=json.dumps(
                {"run_id": "preparing", "events_url": "/api/runs/preparing/events"}
            ),
        ),
    )
    await page.route(
        "**/api/runs/preparing/events",
        lambda route: route.fulfill(
            status=200,
            headers={"content-type": "text/event-stream"},
            body=_sse(
                [
                    {
                        "run_id": "preparing",
                        "sequence": 0,
                        "event": "person",
                        "stage": "Parsing Records",
                        "message": "Ada Lovelace: Parsing Records",
                        "person_id": "I1",
                        "payload": person,
                    }
                ]
            ),
        ),
    )

    await page.goto(dashboard_url)
    await page.get_by_label("Folder path").fill("C:/Research")
    await page.get_by_label("Local Ollama model").select_option("fixture-model")
    await page.get_by_role("button", name="Start analysis").click()
    await page.get_by_text("Lovelace (1)", exact=True).click()
    await expect(page.get_by_role("cell", name="Ada Lovelace", exact=True)).to_be_visible()
    await expect(page.get_by_role("button", name="Generate story")).to_be_disabled()
    await expect(page.get_by_role("button", name="Generate all stories")).to_be_disabled()
    await expect(page.get_by_role("checkbox", name="Select Ada Lovelace for story generation")).to_be_disabled()


@pytest.mark.asyncio
async def test_dashboard_generates_all_stories_and_shows_person_failure(
    page: Page,
    dashboard_url: str,
) -> None:
    await _mock_models(page)
    people = [
        {
            "id": "I1",
            "name": "Ada Lovelace",
            "surname": "Lovelace",
            "display_surname": "Lovelace",
            "document_count": 0,
            "status": "Ready",
        },
        {
            "id": "I2",
            "name": "Eve Edmonds",
            "surname": "Edmonds",
            "display_surname": "Edmonds",
            "document_count": 0,
            "status": "Ready",
        },
    ]
    outcomes = [
        {**people[0], "status": "Finished", "biography": "Generated story.", "conflicts": []},
        {**people[1], "status": "Failed", "error": "Evidence is not readable.", "conflicts": []},
    ]
    await page.route(
        "**/api/run-pipeline",
        lambda route: route.fulfill(
            status=202,
            content_type="application/json",
            body=json.dumps({"run_id": "prepared-all", "events_url": "/api/runs/prepared-all/events"}),
        ),
    )
    await page.route(
        "**/api/runs/prepared-all/events",
        lambda route: route.fulfill(
            status=200,
            headers={"content-type": "text/event-stream"},
            body=_sse(
                [
                    {
                        "run_id": "prepared-all",
                        "sequence": 0,
                        "event": "complete",
                        "stage": "Ready",
                        "message": "Document preparation completed",
                        "payload": {},
                    }
                ]
            ),
        ),
    )
    await page.route(
        "**/api/runs/prepared-all",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "run_id": "prepared-all",
                    "status": "completed",
                    "people": people,
                    "warnings": [],
                }
            ),
        ),
    )
    generate_all_request: dict[str, object] = {"not-called": True}

    async def generate_all(route):
        nonlocal generate_all_request
        generate_all_request = route.request.post_data_json
        await route.fulfill(
            status=202,
            content_type="application/json",
            body=json.dumps(
                {"run_id": "generation-all", "events_url": "/api/runs/generation-all/events"}
            ),
        )

    await page.route("**/api/runs/prepared-all/generate", generate_all)
    await page.route(
        "**/api/runs/generation-all/events",
        lambda route: route.fulfill(
            status=200,
            headers={"content-type": "text/event-stream"},
            body=_sse(
                [
                    {
                        "run_id": "generation-all",
                        "sequence": index,
                        "event": "person",
                        "stage": outcome["status"],
                        "message": f"{outcome['name']}: {outcome['status']}",
                        "person_id": outcome["id"],
                        "payload": outcome,
                    }
                    for index, outcome in enumerate(outcomes)
                ]
                + [
                    {
                        "run_id": "generation-all",
                        "sequence": len(outcomes),
                        "event": "complete",
                        "stage": "Finished",
                        "message": "Story generation completed with person failures",
                        "payload": {},
                    }
                ]
            ),
        ),
    )
    await page.route(
        "**/api/runs/generation-all",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "run_id": "generation-all",
                    "parent_run_id": "prepared-all",
                    "status": "completed",
                    "people": outcomes,
                    "warnings": [],
                }
            ),
        ),
    )

    await page.goto(dashboard_url)
    await page.get_by_label("Folder path").fill("C:/Research")
    await page.get_by_label("Local Ollama model").select_option("fixture-model")
    await page.get_by_role("button", name="Start analysis").click()
    await page.get_by_role("button", name="Generate all stories").click()
    await page.get_by_text("Edmonds (1)", exact=True).click()
    await page.get_by_text("Lovelace (1)", exact=True).click()
    await expect(page.locator("#peopleGroups").get_by_text("Finished", exact=True)).to_be_visible()
    failed_row = page.get_by_role("row").filter(has=page.get_by_role("cell", name="Eve Edmonds"))
    await expect(failed_row.get_by_role("button", name="View", exact=True)).to_be_enabled()
    assert generate_all_request == {}
    await failed_row.get_by_role("button", name="View", exact=True).click()
    await expect(page.get_by_text("Evidence is not readable.")).to_be_visible()
