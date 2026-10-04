import sqlite3

from food_label_agent.evaluation.domestic_pilot import assess, prepare, run_pilot


def item():
    return {
        "barcode": "4006381333931",
        "category": "breakfast_cereal",
        "group": "identity_gap",
        "identity_gaps": ["brand"],
        "baseline": {"name": "燕麦", "brand": "", "specification": "500g"},
    }


def response(**updates):
    return {
        "showapi_res_code": 0,
        "showapi_res_body": {
            "ret_code": "0",
            "code": "4006381333931",
            "goodsName": "燕麦",
            "trademark": "测试品牌",
            "spec": "0.5kg",
            **updates,
        },
    }


def test_fill_is_proposed_not_verified():
    result = assess(item(), response(img="https://example.com/front.jpg"))
    assert result["proposed_identity_fills"] == ["brand"]
    assert not result["identity_differences"]
    assert result["ingredients_available"] is None
    assert result["nutrition_available"] is None
    assert not result["recommendation_eligible"]


def test_mismatch_missing_code_and_conflicting_sku():
    assert assess(item(), response(code="12345670"))["status"] == "barcode_mismatch"
    assert assess(item(), response(code=""))["status"] == "barcode_mismatch"
    assert assess(item(), response(spec="250g"))["identity_differences"] == [
        "specification"
    ]


def test_missing_credentials_is_unmeasured_not_failure_rate():
    result = run_pilot(
        {"items": [item()]}, query=lambda *_: (_ for _ in ()).throw(AssertionError())
    )
    assert result["status"] == "awaiting_credentials"
    assert result["attempted"] == 0
    assert result["match_rate"] is None


def test_provider_error_stops_calls_and_does_not_log_exception_secrets():
    manifest = {"items": [item(), item()]}
    calls = []

    def query(*args):
        calls.append(args)
        return {"showapi_res_code": -1}

    result = run_pilot(manifest, key="secret", query=query, delay=0)
    assert len(calls) == 1
    assert result["status"] == "stopped_on_provider_error"

    def bad_query(*_):
        raise RuntimeError("https://example.com/?appKey=secret")

    result = run_pilot({"items": [item()]}, key="secret", query=bad_query, delay=0)
    assert "secret" not in str(result)


def test_sample_preparation_never_writes_source(tmp_path):
    import json

    path = tmp_path / "source.sqlite3"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE candidates (id,category,payload,content_hash)")
        db.execute(
            "INSERT INTO candidates VALUES (?,?,?,?)",
            (
                "4006381333931",
                "drink",
                json.dumps({"product_name": "燕麦饮"}),
                "version",
            ),
        )
    before = path.read_bytes()
    manifest = prepare(path)
    assert manifest["sample_count"] == 1
    assert path.read_bytes() == before


def test_supplier_withheld_fields_are_not_gap_fills():
    row = {**item(), "identity_gaps": ["name", "brand", "specification"]}
    result = assess(
        row,
        response(goodsName="****(企业未公开详细信息！)", trademark="****", spec="暂无"),
    )
    assert result["proposed_identity_fills"] == []
    assert not result["usable_identity_data"]


def test_fullwidth_unit_formatting_and_http_image_reference():
    result = assess(
        item(), response(spec="500（g）", img="http://example.com/front.jpg")
    )
    assert result["identity_differences"] == []
    assert result["image_reference_count"] == 1
    assert result["image_urls"] == []
