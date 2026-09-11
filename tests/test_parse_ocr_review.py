from scripts.parse_ocr_review import confirm_remaining, parse_review


def test_parse_review_accepts_spaced_checkbox_and_correction_without_checkbox() -> None:
    review = parse_review(
        """## Photo 1 · `abc123`
### 产品名称
```text
机器文字
```
审核：- [ x] 正确　- [ ] 有误　- [ ] 无法确认
修正文本：
### 配料表
```text
错误文字
```
审核：- [ ] 正确　- [ ] 有误　- [ ] 无法确认
修正文本：正确文字
"""
    )

    assert review["summary"] == {
        "photo_count": 1,
        "field_count": 2,
        "completed_field_count": 2,
        "unresolved_field_count": 0,
        "complete_photo_count": 1,
    }
    assert [field["status"] for field in review["photos"][0]["fields"]] == [
        "confirmed",
        "corrected",
    ]


def test_parse_review_does_not_treat_blank_or_note_as_approval() -> None:
    review = parse_review(
        """## Photo 2 · `def456`
### 配料表
```text
机器文字
```
审核：- [ ] 正确　- [ ] 有误　- [ ] 无法确认 已修改
修正文本：
### 营养成分表
```text
机器文字
```
审核：- [ ] 正确　- [ ] 有误　- [ ] 无法确认
修正文本：
"""
    )

    fields = review["photos"][0]["fields"]
    assert [field["status"] for field in fields] == ["note_only", "unreviewed"]
    assert review["review_status"] == "partial"


def test_explicit_blanket_confirmation_is_auditable() -> None:
    review = parse_review(
        """## Photo 1 · `abc123`
### 配料表
```text
机器文字
```
审核：- [ ] 正确　- [ ] 有误　- [ ] 无法确认
修正文本：
"""
    )

    confirmed = confirm_remaining(review, source="user_message:2026-09-11")

    assert confirmed["review_status"] == "complete"
    assert confirmed["summary"]["unresolved_field_count"] == 0
    field = confirmed["photos"][0]["fields"][0]
    assert field["status"] == "confirmed_by_blanket_review"
    assert field["confirmation_source"] == "user_message:2026-09-11"
