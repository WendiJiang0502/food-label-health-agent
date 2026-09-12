from pathlib import Path


def test_category_suggestion_never_starts_alternative_search_automatically() -> None:
    script = (
        Path(__file__).parents[1]
        / "src"
        / "food_label_agent"
        / "web"
        / "static"
        / "app.js"
    ).read_text(encoding="utf-8")

    assert "findAndRevalidateAlternatives({ automatic: true })" not in script
    assert 'elements.findAlternatives.addEventListener("click"' in script
