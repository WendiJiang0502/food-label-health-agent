from __future__ import annotations

from food_label_agent.evaluation.openai_evals import OpenAIEvalsClient, eval_items


def test_openai_eval_export_contains_only_synthetic_live_cases() -> None:
    items = eval_items()

    assert 10 <= len(items) <= 30
    assert all(set(row) == {"item"} for row in items)
    assert all("case_id" in row["item"] for row in items)
    assert all("input" in row["item"] for row in items)


def test_openai_eval_payload_uses_supplemental_grader_and_fixed_model() -> None:
    class CaptureClient(OpenAIEvalsClient):
        def __init__(self):
            super().__init__("test")
            self.calls = []

        def _request(self, method, path, payload=None):
            self.calls.append((method, path, payload))
            return {"id": "eval-test" if path == "/evals" else "run-test", "status": "queued"}

    client = CaptureClient()
    evaluation = client.create_eval()
    run = client.create_run(evaluation["id"], model="gpt-5.6-terra")

    assert run["id"] == "run-test"
    eval_payload = client.calls[0][2]
    assert eval_payload["data_source_config"]["type"] == "custom"
    assert eval_payload["testing_criteria"][0]["type"] == "label_model"
    run_payload = client.calls[1][2]
    assert run_payload["data_source"]["model"] == "gpt-5.6-terra"
    assert run_payload["data_source"]["sampling_params"]["reasoning_effort"] == "low"
    assert run_payload["data_source"]["sampling_params"]["max_completions_tokens"] == 900
    assert len(run_payload["data_source"]["source"]["content"]) == len(eval_items())
