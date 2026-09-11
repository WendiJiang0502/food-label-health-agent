"""Parse the private Markdown OCR review form without treating blanks as approval."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

PHOTO_RE = re.compile(r"^## Photo (\d+) · `([^`]+)`$", re.MULTILINE)
FIELD_RE = re.compile(r"^### (.+)$", re.MULTILINE)
CHOICE_RE = re.compile(r"-\s*\[\s*([xX]?)\s*\]\s*(正确|有误|无法确认)")
STATUS_BY_LABEL = {"正确": "confirmed", "有误": "incorrect", "无法确认": "unable_to_confirm"}
COMPLETED_STATUSES = {
    "confirmed",
    "corrected",
    "unable_to_confirm",
    "confirmed_by_blanket_review",
}


def _blocks(pattern: re.Pattern[str], text: str) -> list[tuple[re.Match[str], str]]:
    matches = list(pattern.finditer(text))
    return [
        (match, text[match.end() : matches[index + 1].start() if index + 1 < len(matches) else None])
        for index, match in enumerate(matches)
    ]


def _clean_correction(value: str) -> str:
    lines = [line for line in value.splitlines() if line.strip() not in {"```", "```text"}]
    return "\n".join(lines).strip()


def parse_review(text: str) -> dict[str, Any]:
    photos: list[dict[str, Any]] = []
    for photo_match, photo_body in _blocks(PHOTO_RE, text):
        fields: list[dict[str, Any]] = []
        for field_match, field_body in _blocks(FIELD_RE, photo_body):
            machine_match = re.search(r"```text\n(.*?)\n```", field_body, re.DOTALL)
            audit_match = re.search(r"审核：(.*)", field_body)
            audit_text = audit_match.group(1).strip() if audit_match else ""
            choices = [label for mark, label in CHOICE_RE.findall(audit_text) if mark]
            audit_note = CHOICE_RE.sub("", audit_text).strip(" -　|")
            correction_match = re.search(r"修正文本：([^\n]*)(.*)$", field_body, re.DOTALL)
            correction = ""
            if correction_match:
                correction = _clean_correction(
                    correction_match.group(1) + correction_match.group(2)
                )

            if len(choices) > 1:
                status = "conflict"
            elif choices:
                status = STATUS_BY_LABEL[choices[0]]
                if status == "incorrect":
                    status = "corrected" if correction else "incorrect_without_correction"
            elif correction:
                status = "corrected"
            elif audit_note:
                status = "note_only"
            else:
                status = "unreviewed"

            fields.append(
                {
                    "name": field_match.group(1).strip(),
                    "status": status,
                    "machine_text": machine_match.group(1).strip() if machine_match else "",
                    "correction": correction,
                    "audit_note": audit_note,
                }
            )

        photos.append(
            {
                "photo": int(photo_match.group(1)),
                "sample_id": photo_match.group(2),
                "fields": fields,
            }
        )

    all_fields = [field for photo in photos for field in photo["fields"]]
    for photo in photos:
        photo["review_complete"] = bool(photo["fields"]) and all(
            field["status"] in COMPLETED_STATUSES for field in photo["fields"]
        )
    return {
        "schema_version": "1.0",
        "review_status": (
            "complete"
            if all_fields and all(field["status"] in COMPLETED_STATUSES for field in all_fields)
            else "partial"
        ),
        "summary": {
            "photo_count": len(photos),
            "field_count": len(all_fields),
            "completed_field_count": sum(
                field["status"] in COMPLETED_STATUSES for field in all_fields
            ),
            "unresolved_field_count": sum(
                field["status"] not in COMPLETED_STATUSES for field in all_fields
            ),
            "complete_photo_count": sum(photo["review_complete"] for photo in photos),
        },
        "photos": photos,
    }


def confirm_remaining(review: dict[str, Any], *, source: str) -> dict[str, Any]:
    """Record an explicit blanket confirmation while retaining the audit source."""

    for photo in review["photos"]:
        for field in photo["fields"]:
            if field["status"] not in COMPLETED_STATUSES:
                field["status"] = "confirmed_by_blanket_review"
                field["confirmation_source"] = source
        photo["review_complete"] = all(
            field["status"] in COMPLETED_STATUSES for field in photo["fields"]
        )
    fields = [field for photo in review["photos"] for field in photo["fields"]]
    review["review_status"] = "complete"
    review["summary"].update(
        completed_field_count=len(fields),
        unresolved_field_count=0,
        complete_photo_count=sum(photo["review_complete"] for photo in review["photos"]),
    )
    review["blanket_confirmation_source"] = source
    return review


def unresolved_markdown(review: dict[str, Any], source: Path) -> str:
    lines = [
        "# OCR 人工审核剩余项",
        "",
        f"> 来源：`{source.name}`。只有下列项目尚未形成明确审核结论。",
        "> 请在每项的三个选项中勾选一个；若勾选“有误”，必须填写完整修正文本。",
        "",
    ]
    unresolved_count = 0
    for photo in review["photos"]:
        unresolved = [
            field for field in photo["fields"] if field["status"] not in COMPLETED_STATUSES
        ]
        if not unresolved:
            continue
        unresolved_count += len(unresolved)
        lines.extend([f"## Photo {photo['photo']} · `{photo['sample_id']}`", ""])
        for field in unresolved:
            lines.extend(
                [
                    f"### {field['name']}",
                    "",
                    "```text",
                    field["machine_text"] or "（机器未识别）",
                    "```",
                    "",
                    "审核：- [ ] 正确　- [ ] 有误　- [ ] 无法确认",
                    "",
                    f"原审核备注：{field['audit_note']}" if field["audit_note"] else "原审核备注：",
                    "",
                    "修正文本：",
                    "",
                ]
            )
    if not unresolved_count:
        lines.extend(["当前没有剩余审核项。", ""])
    return "\n".join(lines).rstrip() + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--remaining", type=Path)
    parser.add_argument("--confirm-remaining", metavar="SOURCE")
    args = parser.parse_args()
    review = parse_review(args.input.read_text(encoding="utf-8"))
    if args.confirm_remaining:
        review = confirm_remaining(review, source=args.confirm_remaining)
    args.output.write_text(
        json.dumps(review, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    if args.remaining:
        args.remaining.write_text(unresolved_markdown(review, args.input), encoding="utf-8")
    print(json.dumps(review["summary"], ensure_ascii=False))


if __name__ == "__main__":
    main()
