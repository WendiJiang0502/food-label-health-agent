"""Small, auditable seed corpus sourced from official Chinese authorities.

This is intentionally clause-sized and narrow. It supplements the packaged
official indexes used by the versioned hybrid-retrieval pipeline.
"""

from __future__ import annotations

from .models import RegulationClause

NHC_GB7718_2011_PDF = (
    "https://www.nhc.gov.cn/zwgkzt/cybz/201106/"
    "a054a6affd0e489da150cf2b51a971a7/files/"
    "e84256474d1445919246b4a41a87f172.pdf"
)
NHC_GB7718_2011_FAQ = (
    "https://www.nhc.gov.cn/zwgk/zcjd/201402/544c0539b95d4d35b99ffbc105579071.shtml"
)
NHC_GB7718_2025_FAQ = (
    "https://www.nhc.gov.cn/sps/c100087/202509/bc824a504ec34c27883da73f14c20d44.shtml"
)

OFFICIAL_CLAUSES: tuple[RegulationClause, ...] = (
    RegulationClause(
        evidence_id="reg.cn.gb7718-2011.4.4.3.1.allergens",
        source_id="GB7718-2011",
        standard_number="GB 7718-2011",
        title="食品安全国家标准 预包装食品标签通则",
        section="4.4.3.1 致敏物质用作配料时的推荐标示",
        evidence_text=(
            "列出含麸质谷物、甲壳纲类动物、鱼、蛋、花生、大豆、乳和坚果等"
            "八类食品及其制品作为可能含有致敏物质的食品。"
        ),
        jurisdiction="CN",
        published_on="2011-04-20",
        effective_from="2012-04-20",
        effective_to="2027-03-15",
        source_url=NHC_GB7718_2011_PDF,
        authority_level="A",
        source_type="official_standard",
        topics=("allergen", "ingredient_labeling"),
        keywords=(
            "过敏原",
            "致敏物质",
            "麸质",
            "小麦",
            "甲壳类",
            "虾",
            "鱼",
            "蛋",
            "花生",
            "大豆",
            "乳",
            "乳清",
            "坚果",
        ),
    ),
    RegulationClause(
        evidence_id="reg.cn.gb7718-2011.faq-62.allergen-labeling",
        source_id="NHC-GB7718-2011-FAQ",
        standard_number="GB 7718-2011",
        title="《预包装食品标签通则》问答（修订版）",
        section="第六十二条 关于致敏物质的标示",
        evidence_text=(
            "八类致敏物质可在配料表中用易识别名称直接标示，"
            "也可在配料表附近提示；同线生产可能带入时可使用“可能含有”等提示。"
        ),
        jurisdiction="CN",
        published_on="2014-02-26",
        effective_from="2014-02-26",
        effective_to="2027-03-15",
        source_url=NHC_GB7718_2011_FAQ,
        authority_level="A",
        source_type="official_interpretation",
        topics=("allergen", "precautionary_labeling"),
        keywords=(
            "过敏原",
            "致敏物质",
            "配料表",
            "可能含有",
            "同一生产线",
            "交叉污染",
        ),
    ),
    RegulationClause(
        evidence_id="reg.cn.gb7718-2025.faq-38.allergen-ingredients",
        source_id="NHC-GB7718-2025-FAQ",
        standard_number="GB 7718-2025",
        title="《食品安全国家标准 预包装食品标签通则》（GB 7718-2025）问答",
        section="第三十八条 关于致敏物质标示",
        evidence_text=(
            "八类致敏食品配料如用作配料，应在配料表中加以提示，"
            "或在配料表临近位置标示提示信息。"
        ),
        jurisdiction="CN",
        published_on="2025-03-16",
        effective_from="2027-03-16",
        effective_to=None,
        source_url=NHC_GB7718_2025_FAQ,
        authority_level="A",
        source_type="official_interpretation",
        topics=("allergen", "ingredient_labeling"),
        keywords=(
            "过敏原",
            "致敏物质",
            "麸质",
            "小麦",
            "甲壳类",
            "虾",
            "鱼",
            "蛋",
            "花生",
            "大豆",
            "乳",
            "乳清",
            "坚果",
            "配料表",
        ),
    ),
    RegulationClause(
        evidence_id="reg.cn.gb7718-2025.faq-39.precautionary-labeling",
        source_id="NHC-GB7718-2025-FAQ",
        standard_number="GB 7718-2025",
        title="《食品安全国家标准 预包装食品标签通则》（GB 7718-2025）问答",
        section="第三十九条 关于致敏物质预防性提示信息",
        evidence_text=(
            "生产加工过程可能带入致敏物质时，例如共用生产车间或生产线，"
            "鼓励标示致敏物质提示信息。"
        ),
        jurisdiction="CN",
        published_on="2025-03-16",
        effective_from="2027-03-16",
        effective_to=None,
        source_url=NHC_GB7718_2025_FAQ,
        authority_level="A",
        source_type="official_interpretation",
        topics=("allergen", "precautionary_labeling"),
        keywords=(
            "过敏原",
            "致敏物质",
            "可能含有",
            "共用生产线",
            "交叉污染",
        ),
    ),
    RegulationClause(
        evidence_id="reg.cn.gb2760-2024.announcement",
        source_id="NHC-2024-ANNOUNCEMENT-1",
        standard_number="GB 2760-2024",
        title="关于发布《食品安全国家标准 食品添加剂使用标准》等标准的公告",
        section="2024年第1号公告",
        evidence_text=(
            "国家卫生健康委员会发布GB 2760-2024《食品安全国家标准 "
            "食品添加剂使用标准》。"
        ),
        jurisdiction="CN",
        published_on="2024-02-08",
        effective_from="2025-02-08",
        effective_to=None,
        source_url=(
            "https://www.nhc.gov.cn/sps/c100088/202403/"
            "bda120e678df4a49a8beb90852559d7c.shtml"
        ),
        authority_level="A",
        source_type="official_announcement",
        topics=("food_additive", "ingredient_labeling"),
        keywords=("食品添加剂", "使用标准", "GB 2760"),
    ),
)
