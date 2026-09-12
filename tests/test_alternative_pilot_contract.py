from scripts.run_alternative_pilot import (
    EXPECTED_TASK_OUTCOMES,
    SAFE_OUTCOMES,
)


def test_safe_abstention_is_not_counted_as_task_success() -> None:
    assert "abstained" in SAFE_OUTCOMES["case_016"]
    assert EXPECTED_TASK_OUTCOMES["case_016"] == "eligible"


def test_high_risk_cases_never_accept_an_eligible_outcome() -> None:
    assert "eligible" not in SAFE_OUTCOMES["case_018"]
    assert "eligible" not in SAFE_OUTCOMES["case_019"]
