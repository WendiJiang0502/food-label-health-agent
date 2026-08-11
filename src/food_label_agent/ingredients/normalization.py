"""Deterministic parsing and normalization for Chinese ingredient lists.

The parser deliberately uses separators and a bracket stack.  It never asks an
LLM to invent missing text or silently repair an unbalanced compound ingredient.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

from .additives import ADDITIVES

INGREDIENT_NORMALIZATION_VERSION = "cn.v2"

_PREFIX = re.compile(r"^\s*配料(?:表)?\s*[:：]\s*")
_SEPARATORS = {"、", ",", "，", ";", "；", "\n"}
_OPEN_TO_CLOSE = {"(": ")", "（": "）", "[": "]", "【": "】"}
_CLOSE_TO_OPEN = {value: key for key, value in _OPEN_TO_CLOSE.items()}


@dataclass(frozen=True, slots=True)
class SourceRange:
    field: str
    start: int
    end: int
    bounding_box: tuple[int, int, int, int] | None = None


@dataclass(frozen=True, slots=True)
class NormalizationIssue:
    code: str
    message: str
    source_span: str
    start: int
    end: int
    requires_confirmation: bool = True


@dataclass(frozen=True, slots=True)
class CorrectionRecord:
    field: str
    before: str
    after: str
    actor: str = "user"


@dataclass(frozen=True, slots=True)
class IngredientNode:
    raw_name: str
    canonical_name: str
    category: str
    source_span: str
    confidence: float
    normalization_method: str
    order: int
    path: tuple[int, ...]
    evidence_id: str
    source_range: SourceRange
    relation: str = "ingredient"
    allergen_keys: tuple[str, ...] = ()
    children: tuple[IngredientNode, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["path"] = list(self.path)
        value["allergen_keys"] = list(self.allergen_keys)
        value["children"] = [child.to_dict() for child in self.children]
        return value


@dataclass(frozen=True, slots=True)
class NormalizedLabel:
    raw_text: str
    ingredients: tuple[IngredientNode, ...]
    parse_status: str
    issues: tuple[NormalizationIssue, ...] = ()
    unknown_terms: tuple[str, ...] = ()
    corrections: tuple[CorrectionRecord, ...] = ()
    source_field: str = "ingredients"

    @property
    def requires_confirmation(self) -> bool:
        return any(issue.requires_confirmation for issue in self.issues)

    def iter_ingredients(self):
        stack = list(reversed(self.ingredients))
        while stack:
            item = stack.pop()
            yield item
            stack.extend(reversed(item.children))

    def to_dict(self) -> dict[str, Any]:
        return {
            "raw_text": self.raw_text,
            "source_field": self.source_field,
            "parse_status": self.parse_status,
            "requires_confirmation": self.requires_confirmation,
            "ingredients": [item.to_dict() for item in self.ingredients],
            "issues": [asdict(issue) for issue in self.issues],
            "unknown_terms": list(self.unknown_terms),
            "corrections": [asdict(record) for record in self.corrections],
        }


# canonical name, consumer-facing category, allergen keys, relation
_TERMS: dict[str, tuple[str, str, tuple[str, ...], str]] = {
    "小麦粉": ("小麦粉", "谷物及其制品", ("gluten",), "direct"),
    "小麦": ("小麦", "谷物及其制品", ("gluten",), "direct"),
    "斯佩耳特小麦": ("斯佩耳特小麦", "谷物及其制品", ("gluten",), "direct"),
    "全麦粉": ("全麦粉", "谷物及其制品", ("gluten",), "direct"),
    "黑麦": ("黑麦", "谷物及其制品", ("gluten",), "direct"),
    "大麦": ("大麦", "谷物及其制品", ("gluten",), "direct"),
    "燕麦": ("燕麦", "谷物及其制品", ("gluten",), "direct"),
    "麸质": ("麸质", "谷物及其制品", ("gluten",), "derivative"),
    "谷朵粉": ("麸质", "谷物及其制品", ("gluten",), "derivative"),
    "麦芽": ("麦芽", "谷物及其制品", ("gluten",), "derivative"),
    "牛奶": ("牛奶", "乳及乳制品", ("milk",), "direct"),
    "乳": ("乳", "乳及乳制品", ("milk",), "direct"),
    "奶粉": ("乳粉", "乳及乳制品", ("milk",), "derivative"),
    "乳粉": ("乳粉", "乳及乳制品", ("milk",), "derivative"),
    "全脂乳粉": ("全脂乳粉", "乳及乳制品", ("milk",), "derivative"),
    "脱脂乳粉": ("脱脂乳粉", "乳及乳制品", ("milk",), "derivative"),
    "乳清": ("乳清", "乳及乳制品", ("milk",), "derivative"),
    "乳清粉": ("乳清粉", "乳及乳制品", ("milk",), "derivative"),
    "乳清蛋白": ("乳清蛋白", "乳及乳制品", ("milk",), "derivative"),
    "酸奶": ("发酵乳", "乳及乳制品", ("milk",), "derivative"),
    "发酵乳": ("发酵乳", "乳及乳制品", ("milk",), "derivative"),
    "乳制品": ("乳制品", "乳及乳制品", ("milk",), "derivative"),
    "奶油": ("奶油", "乳及乳制品", ("milk",), "derivative"),
    "黄油": ("黄油", "乳及乳制品", ("milk",), "derivative"),
    "干酪": ("干酪", "乳及乳制品", ("milk",), "derivative"),
    "酸酪": ("干酪", "乳及乳制品", ("milk",), "derivative"),
    "酪蛋白": ("酪蛋白", "乳及乳制品", ("milk",), "derivative"),
    "酪蛋白酸钠": ("酪蛋白酸钠", "乳及乳制品", ("milk",), "derivative"),
    "乳糖": ("乳糖", "乳及乳制品", ("milk",), "regulated_derivative"),
    "鸡蛋": ("鸡蛋", "蛋类及其制品", ("egg",), "direct"),
    "蛋清": ("蛋清", "蛋类及其制品", ("egg",), "derivative"),
    "蛋黄": ("蛋黄", "蛋类及其制品", ("egg",), "derivative"),
    "蛋白粉": ("蛋白粉", "蛋类及其制品", ("egg",), "derivative"),
    "蛋黄酱": ("蛋黄酱", "蛋类及其制品", ("egg",), "derivative"),
    "蛋类": ("蛋类", "蛋类及其制品", ("egg",), "direct"),
    "花生": ("花生", "花生及其制品", ("peanut",), "direct"),
    "花生酱": ("花生酱", "花生及其制品", ("peanut",), "derivative"),
    "花生粉": ("花生粉", "花生及其制品", ("peanut",), "derivative"),
    "大豆": ("大豆", "大豆及其制品", ("soy",), "direct"),
    "黄豆": ("大豆", "大豆及其制品", ("soy",), "direct"),
    "大豆蛋白": ("大豆蛋白", "大豆及其制品", ("soy",), "derivative"),
    "大豆分离蛋白": ("大豆分离蛋白", "大豆及其制品", ("soy",), "derivative"),
    "大豆卵磷脂": ("大豆卵磷脂", "大豆及其制品", ("soy",), "derivative"),
    "豆粉": ("豆粉", "大豆及其制品", ("soy",), "derivative"),
    "虾": ("虾", "甲壳纲类动物及其制品", ("crustacean",), "direct"),
    "虾粉": ("虾粉", "甲壳纲类动物及其制品", ("crustacean",), "derivative"),
    "南极磷虾": ("南极磷虾", "甲壳纲类动物及其制品", ("crustacean",), "direct"),
    "蟹": ("蟹", "甲壳纲类动物及其制品", ("crustacean",), "direct"),
    "龙虾": ("龙虾", "甲壳纲类动物及其制品", ("crustacean",), "direct"),
    "鱼": ("鱼", "鱼类及其制品", ("fish",), "direct"),
    "鱼粉": ("鱼粉", "鱼类及其制品", ("fish",), "derivative"),
    "鱼露": ("鱼露", "鱼类及其制品", ("fish",), "derivative"),
    "鱼油": ("鱼油", "鱼类及其制品", ("fish",), "derivative"),
    "坚果": ("坚果", "坚果及其果仁类制品", ("tree_nut",), "direct"),
    "核桃": ("核桃", "坚果及其果仁类制品", ("tree_nut",), "direct"),
    "核桃仁": ("核桃仁", "坚果及其果仁类制品", ("tree_nut",), "direct"),
    "杏仁": ("杏仁", "坚果及其果仁类制品", ("tree_nut",), "direct"),
    "扁桃仁": ("扁桃仁", "坚果及其果仁类制品", ("tree_nut",), "direct"),
    "腰果": ("腰果", "坚果及其果仁类制品", ("tree_nut",), "direct"),
    "榛子": ("榛子", "坚果及其果仁类制品", ("tree_nut",), "direct"),
    "开心果": ("开心果", "坚果及其果仁类制品", ("tree_nut",), "direct"),
    "夏威夷果": ("夏威夷果", "坚果及其果仁类制品", ("tree_nut",), "direct"),
    "碧根果": ("碧根果", "坚果及其果仁类制品", ("tree_nut",), "direct"),
    "白砂糖": ("白砂糖", "糖类", (), "direct"),
    "食用盐": ("食用盐", "调味料", (), "direct"),
    "植物油": ("植物油", "油脂", (), "direct"),
    "酵母抽提物": ("酵母抽提物", "调味料", (), "direct"),
    "食品添加剂": ("食品添加剂", "食品添加剂分组", (), "group"),
    "复合调味料": ("复合调味料", "复合配料", (), "compound"),
}

_TERMS.update(
    {
        alias: (
            entry.canonical_name,
            f"食品添加剂·{entry.function_category}",
            (),
            "additive",
        )
        for alias, entry in ADDITIVES.items()
    }
)


def normalize_ingredients(
    raw_text: str,
    *,
    original_text: str | None = None,
    source_bounding_box: tuple[int, int, int, int] | None = None,
) -> NormalizedLabel:
    """Parse a confirmed ingredient list into a traceable tree."""

    prefix = _PREFIX.match(raw_text)
    content_start = prefix.end() if prefix else 0
    content = raw_text[content_start:]
    issues: list[NormalizationIssue] = []
    ingredients = _parse_sequence(
        content,
        absolute_start=content_start,
        path_prefix=(),
        issues=issues,
        bounding_box=source_bounding_box,
    )
    unknown_terms = tuple(
        dict.fromkeys(
            item.raw_name
            for item in _walk(ingredients)
            if item.normalization_method == "unresolved"
        )
    )
    corrections: tuple[CorrectionRecord, ...] = ()
    if original_text is not None and original_text.strip() != raw_text.strip():
        corrections = (
            CorrectionRecord(
                field="ingredients",
                before=original_text,
                after=raw_text,
            ),
        )
    return NormalizedLabel(
        raw_text=raw_text,
        ingredients=ingredients,
        parse_status="needs_confirmation" if issues else "parsed",
        issues=tuple(issues),
        unknown_terms=unknown_terms,
        corrections=corrections,
    )


def _parse_sequence(
    text: str,
    *,
    absolute_start: int,
    path_prefix: tuple[int, ...],
    issues: list[NormalizationIssue],
    bounding_box: tuple[int, int, int, int] | None,
) -> tuple[IngredientNode, ...]:
    segments = _split_top_level(text, absolute_start=absolute_start, issues=issues)
    result: list[IngredientNode] = []
    for order, (segment, start, end) in enumerate(segments, start=1):
        node = _parse_entry(
            segment,
            start=start,
            end=end,
            order=order,
            path=path_prefix + (order,),
            issues=issues,
            bounding_box=bounding_box,
        )
        if node is not None:
            result.append(node)
    return tuple(result)


def _split_top_level(
    text: str, *, absolute_start: int, issues: list[NormalizationIssue]
) -> list[tuple[str, int, int]]:
    stack: list[tuple[str, int]] = []
    parts: list[tuple[str, int, int]] = []
    part_start = 0
    for index, char in enumerate(text):
        if char in _OPEN_TO_CLOSE:
            stack.append((char, index))
        elif char in _CLOSE_TO_OPEN:
            if not stack or stack[-1][0] != _CLOSE_TO_OPEN[char]:
                issues.append(
                    NormalizationIssue(
                        code="UNMATCHED_CLOSING_BRACKET",
                        message="发现无法对应的右括号，请对照包装确认。",
                        source_span=char,
                        start=absolute_start + index,
                        end=absolute_start + index + 1,
                    )
                )
            else:
                stack.pop()
        elif char in _SEPARATORS and not stack:
            if char == "\n" and _is_known_line_wrap(text, index):
                continue
            _append_part(parts, text, part_start, index, absolute_start, issues)
            part_start = index + 1
    _append_part(parts, text, part_start, len(text), absolute_start, issues)
    for opener, index in stack:
        issues.append(
            NormalizationIssue(
                code="UNCLOSED_BRACKET",
                message="复合配料括号未闭合，请对照包装补全。",
                source_span=opener,
                start=absolute_start + index,
                end=absolute_start + index + 1,
            )
        )
    return parts


def _is_known_line_wrap(text: str, newline_index: int) -> bool:
    """Keep an OCR line break inside a known ingredient or additive name."""

    boundaries = _SEPARATORS | set(_OPEN_TO_CLOSE) | set(_CLOSE_TO_OPEN)
    left = newline_index - 1
    while left >= 0 and text[left] not in boundaries:
        left -= 1
    right = newline_index + 1
    while right < len(text) and text[right] not in boundaries:
        right += 1
    left_fragment = text[left + 1 : newline_index].strip()
    right_fragment = text[newline_index + 1 : right].strip()
    if not left_fragment or not right_fragment:
        return False
    return _clean_lookup_name(left_fragment + right_fragment) in _TERMS


def _append_part(
    parts: list[tuple[str, int, int]],
    text: str,
    start: int,
    end: int,
    absolute_start: int,
    issues: list[NormalizationIssue],
) -> None:
    raw = text[start:end]
    left_trimmed = len(raw) - len(raw.lstrip())
    stripped = raw.strip()
    if not stripped:
        if raw or start != end:
            issues.append(
                NormalizationIssue(
                    code="EMPTY_INGREDIENT",
                    message="分隔符之间没有配料名称，请对照包装确认。",
                    source_span=raw,
                    start=absolute_start + start,
                    end=absolute_start + end,
                )
            )
        return
    item_start = absolute_start + start + left_trimmed
    parts.append((stripped, item_start, item_start + len(stripped)))


def _parse_entry(
    segment: str,
    *,
    start: int,
    end: int,
    order: int,
    path: tuple[int, ...],
    issues: list[NormalizationIssue],
    bounding_box: tuple[int, int, int, int] | None,
) -> IngredientNode | None:
    bracket = _find_outer_bracket(segment)
    raw_name = segment
    children: tuple[IngredientNode, ...] = ()
    if bracket is not None:
        open_index, close_index = bracket
        parent_name = segment[:open_index].strip()
        if not parent_name:
            issues.append(
                NormalizationIssue(
                    code="MISSING_COMPOUND_NAME",
                    message="括号前缺少复合配料名称，请人工确认。",
                    source_span=segment,
                    start=start,
                    end=end,
                )
            )
            return _make_node(segment, start, end, order, path, (), bounding_box)
        raw_name = parent_name
        child_start_in_segment = open_index + 1
        children = _parse_sequence(
            segment[child_start_in_segment:close_index],
            absolute_start=start + child_start_in_segment,
            path_prefix=path,
            issues=issues,
            bounding_box=bounding_box,
        )
        trailing = segment[close_index + 1 :].strip()
        if trailing:
            issues.append(
                NormalizationIssue(
                    code="TRAILING_TEXT_AFTER_COMPOUND",
                    message="复合配料括号后存在未解析文字，请人工确认。",
                    source_span=trailing,
                    start=start + close_index + 1,
                    end=end,
                )
            )
    return _make_node(
        raw_name, start, end, order, path, children, bounding_box, segment
    )


def _find_outer_bracket(segment: str) -> tuple[int, int] | None:
    stack: list[tuple[str, int]] = []
    for index, char in enumerate(segment):
        if char in _OPEN_TO_CLOSE:
            stack.append((char, index))
        elif char in _CLOSE_TO_OPEN and stack and stack[-1][0] == _CLOSE_TO_OPEN[char]:
            _, open_index = stack.pop()
            if not stack:
                return open_index, index
    return None


def _make_node(
    raw_name: str,
    start: int,
    end: int,
    order: int,
    path: tuple[int, ...],
    children: tuple[IngredientNode, ...],
    bounding_box: tuple[int, int, int, int] | None,
    source_span: str | None = None,
) -> IngredientNode:
    lookup_name = _clean_lookup_name(raw_name)
    known = _TERMS.get(lookup_name)
    if known:
        canonical, category, allergen_keys, relation = known
        repaired_line_wrap = "\n" in raw_name
        method = (
            "dictionary_line_wrap_repair" if repaired_line_wrap else "dictionary_exact"
        )
        confidence = 0.98 if repaired_line_wrap else 1.0
        normalized_raw_name = re.sub(r"\s+", "", raw_name)
    else:
        canonical, category, allergen_keys, relation = (
            raw_name,
            "未分类",
            (),
            "ingredient",
        )
        method = "unresolved"
        confidence = 0.0
        normalized_raw_name = raw_name
    if children and category == "未分类":
        category = "复合配料"
        relation = "compound"
    evidence_id = "label.ingredients.item." + ".".join(map(str, path))
    return IngredientNode(
        raw_name=normalized_raw_name,
        canonical_name=canonical,
        category=category,
        source_span=source_span or raw_name,
        confidence=confidence,
        normalization_method=method,
        order=order,
        path=path,
        evidence_id=evidence_id,
        source_range=SourceRange(
            field="ingredients", start=start, end=end, bounding_box=bounding_box
        ),
        relation=relation,
        allergen_keys=allergen_keys,
        children=children,
    )


def _clean_lookup_name(value: str) -> str:
    value = re.sub(r"\s+", "", value)
    value = re.sub(r"\d+(?:\.\d+)?%$", "", value)
    return value.strip()


def _walk(items: tuple[IngredientNode, ...]):
    for item in items:
        yield item
        yield from _walk(item.children)
