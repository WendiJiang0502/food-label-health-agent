"""Small dependency-free demonstration of the workflow contract."""

from __future__ import annotations

import json

from .graph.routing import route_after_ocr
from .graph.state import create_initial_state


def main() -> None:
    state = create_initial_state(
        request_id="demo-request",
        jurisdiction="CN",
        applicable_date="2026-08-02",
    )
    print(
        json.dumps(
            {
                "request_id": state["request_id"],
                "stage": state["stage"],
                "next_route": route_after_ocr(state),
                "explanation": "No OCR fields exist yet, so confirmation is required.",
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
