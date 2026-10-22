"""Capture the README screenshots from the running app.

    streamlit run app/main.py        # in one terminal
    python -m tools.screenshots      # in another

Requires playwright, which is deliberately absent from requirements.txt:
it is needed to regenerate the images, not to run or test the project.

    pip install playwright && playwright install chromium
"""

from __future__ import annotations

from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path("docs/images")
URL = "http://localhost:8501"
TABS = ["Scorecard", "Findings", "Evidence", "Comparison"]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1480, "height": 1000},
                                device_scale_factor=2)
        page.goto(URL, wait_until="networkidle", timeout=60_000)
        page.wait_for_timeout(5_000)

        for label in TABS:
            tabs = page.locator('button[role="tab"]')
            for index in range(tabs.count()):
                if label in tabs.nth(index).inner_text():
                    tabs.nth(index).click()
                    break
            page.wait_for_timeout(2_500)
            name = label.lower()
            page.screenshot(path=str(OUT / f"{name}.png"))
            print(f"  captured {name}.png")

        browser.close()


if __name__ == "__main__":
    main()
