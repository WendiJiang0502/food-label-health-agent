"""Version registry for the first official Chinese food-label standards."""

from __future__ import annotations

from datetime import date

from .models import StandardDocument

NHC = "国家卫生健康委员会"
NHC_SAMR = "国家卫生健康委员会、国家市场监督管理总局"

STANDARD_DOCUMENTS: tuple[StandardDocument, ...] = (
    StandardDocument(
        document_id="GB7718-2011",
        standard_number="GB 7718-2011",
        title="食品安全国家标准 预包装食品标签通则",
        jurisdiction="CN",
        publisher=NHC,
        published_on="2011-04-20",
        effective_from="2012-04-20",
        effective_to="2027-03-15",
        official_page_url="https://www.nhc.gov.cn/zwgk/cybz/201106/53c53d99b71940c7a74830f86b46f8db.shtml",
        pdf_url="https://www.nhc.gov.cn/zwgkzt/cybz/201106/a054a6affd0e489da150cf2b51a971a7/files/e84256474d1445919246b4a41a87f172.pdf",
        authority_level="A",
        source_type="official_standard",
        topics=("ingredient_labeling", "allergen", "labeling"),
        replaced_by="GB7718-2025",
    ),
    StandardDocument(
        document_id="GB7718-2025",
        standard_number="GB 7718-2025",
        title="食品安全国家标准 预包装食品标签通则",
        jurisdiction="CN",
        publisher=NHC_SAMR,
        published_on="2025-03-16",
        effective_from="2027-03-16",
        effective_to=None,
        official_page_url="https://www.nhc.gov.cn/wjw/zcwjgg/202503/97802a2683b840dd8be0e1449982c6a5.shtml",
        pdf_url=None,
        authority_level="A",
        source_type="official_standard",
        topics=("ingredient_labeling", "allergen", "labeling"),
        replaces="GB7718-2011",
    ),
    StandardDocument(
        document_id="GB28050-2011",
        standard_number="GB 28050-2011",
        title="食品安全国家标准 预包装食品营养标签通则",
        jurisdiction="CN",
        publisher=NHC,
        published_on="2011-10-12",
        effective_from="2013-01-01",
        effective_to="2027-03-15",
        official_page_url="https://www.nhc.gov.cn/sps/c100088/201111/714fdca49f15450580fc03a2ee3163f9.shtml",
        pdf_url="https://www.nhc.gov.cn/ewebeditor/uploadfile/2013/06/20130605104041625.pdf",
        authority_level="A",
        source_type="official_standard",
        topics=("nutrition_labeling", "nutrition_claim"),
        replaced_by="GB28050-2025",
    ),
    StandardDocument(
        document_id="GB28050-2025",
        standard_number="GB 28050-2025",
        title="食品安全国家标准 预包装食品营养标签通则",
        jurisdiction="CN",
        publisher=NHC_SAMR,
        published_on="2025-03-16",
        effective_from="2027-03-16",
        effective_to=None,
        official_page_url="https://www.nhc.gov.cn/wjw/zcwjgg/202503/97802a2683b840dd8be0e1449982c6a5.shtml",
        pdf_url=None,
        authority_level="A",
        source_type="official_standard",
        topics=("nutrition_labeling", "nutrition_claim"),
        replaces="GB28050-2011",
    ),
    StandardDocument(
        document_id="GB2760-2014",
        standard_number="GB 2760-2014",
        title="食品安全国家标准 食品添加剂使用标准",
        jurisdiction="CN",
        publisher=NHC,
        published_on="2014-12-24",
        effective_from="2015-05-24",
        effective_to="2025-02-07",
        official_page_url="https://www.nhc.gov.cn/sps/c100088/201412/b2b4a716a5494277b4219154c89b23a9.shtml",
        pdf_url=None,
        authority_level="A",
        source_type="official_standard",
        topics=("food_additive", "ingredient_labeling"),
        replaced_by="GB2760-2024",
    ),
    StandardDocument(
        document_id="GB2760-2024",
        standard_number="GB 2760-2024",
        title="食品安全国家标准 食品添加剂使用标准",
        jurisdiction="CN",
        publisher=NHC_SAMR,
        published_on="2024-02-08",
        effective_from="2025-02-08",
        effective_to=None,
        official_page_url="https://www.nhc.gov.cn/sps/c100088/202403/bda120e678df4a49a8beb90852559d7c.shtml",
        pdf_url=None,
        authority_level="A",
        source_type="official_standard",
        topics=("food_additive", "ingredient_labeling"),
        replaces="GB2760-2014",
    ),
)


def get_document(document_id: str) -> StandardDocument:
    for document in STANDARD_DOCUMENTS:
        if document.document_id == document_id:
            return document
    raise KeyError(f"Unknown standard document: {document_id}")


def documents_applicable_on(
    applicable_date: date, *, jurisdiction: str = "CN"
) -> tuple[StandardDocument, ...]:
    return tuple(
        document
        for document in STANDARD_DOCUMENTS
        if document.jurisdiction == jurisdiction
        and document.is_applicable(applicable_date)
    )


def validate_registry() -> None:
    ids = [document.document_id for document in STANDARD_DOCUMENTS]
    if len(ids) != len(set(ids)):
        raise ValueError("Standard document IDs must be unique")
    by_id = {document.document_id: document for document in STANDARD_DOCUMENTS}
    for document in STANDARD_DOCUMENTS:
        if not document.official_page_url.startswith("https://www.nhc.gov.cn/"):
            raise ValueError(f"Non-official source URL: {document.document_id}")
        if document.replaces:
            previous = by_id.get(document.replaces)
            if previous is None or previous.replaced_by != document.document_id:
                raise ValueError(f"Broken replacement link: {document.document_id}")
            if previous.effective_to is None:
                raise ValueError(
                    f"Replaced standard has no end date: {previous.document_id}"
                )
            previous_end = date.fromisoformat(previous.effective_to)
            current_start = date.fromisoformat(document.effective_from)
            if (current_start - previous_end).days != 1:
                raise ValueError(
                    f"Version window has a gap or overlap: {document.document_id}"
                )
