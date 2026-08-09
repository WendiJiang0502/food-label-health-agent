"""Conservative additive identity and plain-language function knowledge."""

from __future__ import annotations

from dataclasses import dataclass

NHC_STANDARDS_CATALOG_URL = (
    "https://www.nhc.gov.cn/sps/c100087/202601/"
    "b8bc7bf0fd6243c1914d8c0708d9929a/files/"
    "%E9%A3%9F%E5%93%81%E5%AE%89%E5%85%A8%E5%9B%BD%E5%AE%B6%E6%A0%87%E5%87%86"
    "%E7%9B%AE%E5%BD%95%EF%BC%88%E6%88%AA%E8%87%B32025%E5%B9%B49%E6%9C%88"
    "%E5%85%B11725%E9%A1%B9%EF%BC%89.pdf"
)
ADDITIVE_DICTIONARY_VERSION = "cn.v2"


@dataclass(frozen=True, slots=True)
class AdditiveKnowledge:
    canonical_name: str
    function_category: str
    plain_language_function: str
    aliases: tuple[str, ...] = ()
    identity_standard: str = "GB 2760-2024"
    official_source_url: str = NHC_STANDARDS_CATALOG_URL

    @property
    def evidence_id(self) -> str:
        return (
            f"knowledge.additives.{ADDITIVE_DICTIONARY_VERSION}.{self.canonical_name}"
        )


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
    AdditiveKnowledge(
        "磷酸酯双淀粉",
        "增稠剂",
        "属于改性淀粉，可用于改善食品的稠度和加工稳定性。",
        identity_standard="GB 29926-2013",
    ),
    AdditiveKnowledge(
        "酸处理淀粉",
        "增稠剂",
        "属于改性淀粉，可用于改善食品的稠度和加工稳定性。",
        identity_standard="GB 29928-2013",
    ),
    AdditiveKnowledge(
        "羟丙基二淀粉磷酸酯",
        "增稠剂",
        "属于改性淀粉，可用于改善食品的稠度和加工稳定性。",
        identity_standard="GB 29931-2013",
    ),
    AdditiveKnowledge(
        "单，双甘油脂肪酸酯",
        "乳化剂",
        "用于帮助油和水等成分形成较稳定的混合体系。",
        ("单硬脂酸甘油酯", "单双硬脂酸甘油酯", "单、双甘油脂肪酸酯"),
        "GB 1886.65-2015",
    ),
    AdditiveKnowledge(
        "碳酸钙",
        "膨松剂",
        "可帮助食品形成加工所需的疏松结构。",
        identity_standard="GB 1886.214-2016",
    ),
    AdditiveKnowledge(
        "特丁基对苯二酚",
        "抗氧化剂",
        "用于延缓油脂等成分氧化引起的品质变化。",
        ("TBHQ",),
        "GB 26403-2011",
    ),
    AdditiveKnowledge(
        "二氧化硅",
        "抗结剂",
        "用于帮助粉末或颗粒状配料保持松散、减少结块。",
        identity_standard="GB 25576-2020",
    ),
    AdditiveKnowledge(
        "5′-呈味核苷酸二钠",
        "增味剂",
        "用于增强食品的鲜味。",
        ("5'-呈味核苷酸二钠", "5’-呈味核苷酸二钠", "呈味核苷酸二钠"),
        "GB 1886.171-2016",
    ),
    AdditiveKnowledge(
        "焦糖色",
        "着色剂",
        "用于赋予或改善食品颜色。",
        identity_standard="GB 1886.64-2015",
    ),
    AdditiveKnowledge(
        "柠檬黄",
        "着色剂",
        "用于赋予或改善食品颜色。",
        identity_standard="GB 4481.1-2010",
    ),
    AdditiveKnowledge(
        "辣椒红",
        "着色剂",
        "用于赋予或改善食品颜色。",
        identity_standard="GB 1886.34-2015",
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
