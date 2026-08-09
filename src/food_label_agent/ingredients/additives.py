"""Conservative additive identity and plain-language function knowledge."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AdditiveKnowledge:
    canonical_name: str
    function_category: str
    plain_language_function: str
    aliases: tuple[str, ...] = ()

    @property
    def evidence_id(self) -> str:
        return f"knowledge.additives.cn.v1.{self.canonical_name}"


_ENTRIES = (
    AdditiveKnowledge(
        "亚硝酸钠", "护色剂、防腐剂", "常用于肉制品护色，并帮助抑制特定微生物。"
    ),
    AdditiveKnowledge(
        "山梨酸钾", "防腐剂", "用于帮助抑制霉菌、酵母等微生物造成的腐败。"
    ),
    AdditiveKnowledge("苯甲酸钠", "防腐剂", "用于帮助抑制特定微生物造成的腐败。"),
    AdditiveKnowledge("谷氨酸钠", "增味剂", "用于增强食品的鲜味。", ("味精",)),
    AdditiveKnowledge("柠檬酸", "酸度调节剂", "用于调节食品的酸味和酸碱度。"),
    AdditiveKnowledge(
        "碳酸氢钠",
        "膨松剂、酸度调节剂",
        "可帮助焙烤食品形成疏松结构，也可调节酸碱度。",
        ("小苏打",),
    ),
    AdditiveKnowledge(
        "三聚磷酸钠", "水分保持剂、稳定剂", "常用于帮助保持食品水分和加工状态。"
    ),
    AdditiveKnowledge(
        "焦磷酸钠", "水分保持剂、稳定剂", "常用于帮助保持食品水分和加工状态。"
    ),
    AdditiveKnowledge(
        "六偏磷酸钠", "水分保持剂、稳定剂", "常用于帮助保持食品水分和加工状态。"
    ),
    AdditiveKnowledge(
        "D-异抗坏血酸钠",
        "抗氧化剂",
        "用于延缓氧化引起的颜色或风味变化。",
        ("异抗坏血酸钠",),
    ),
    AdditiveKnowledge(
        "卡拉胶", "增稠剂、稳定剂", "用于改善稠度、凝胶结构或体系稳定性。"
    ),
    AdditiveKnowledge("乙基麦芽酚", "食品用香料", "用于调整或增强食品香气。"),
    AdditiveKnowledge("红曲红", "着色剂", "用于赋予或改善食品颜色。"),
    AdditiveKnowledge(
        "食用香精", "食品用香精", "由香味物质配制，用于赋予或调整食品香气。"
    ),
)

ADDITIVES: dict[str, AdditiveKnowledge] = {
    alias: entry
    for entry in _ENTRIES
    for alias in (entry.canonical_name, *entry.aliases)
}


def additive_knowledge(name: str) -> AdditiveKnowledge | None:
    return ADDITIVES.get(name.strip())


def normalized_term(name: str) -> tuple[str, str, tuple[str, ...], str] | None:
    entry = additive_knowledge(name)
    if entry is None:
        return None
    return (
        entry.canonical_name,
        f"食品添加剂·{entry.function_category}",
        (),
        "additive",
    )
