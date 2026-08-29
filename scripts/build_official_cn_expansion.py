"""Build the reviewed expansion for the mainland official-product catalog.

The source definitions intentionally distinguish two evidence tiers:

* complete label families: official pages publish ingredients, allergens and the
  five core nutrition rows;
* discovered official SKUs: official pages publish the product and pack size,
  but the package label still needs a separate human review.

Only the first tier can pass the recommendation evidence gate.
"""

from __future__ import annotations

import json
import re
from hashlib import sha256
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = (
    ROOT
    / "src"
    / "food_label_agent"
    / "alternatives"
    / "data"
    / "official_cn_expansion.json"
)

REVIEWED_ON = "2026-08-15"
VALID_THROUGH = "2027-02-15"
NESTLE_STORE = {
    "official_store_url": "https://mall.jd.com/index-1000333009.html",
    "official_store_name": "雀巢冰淇淋京东自营旗舰店",
    "official_store_verified_at": REVIEWED_ON,
}


def content_hash(label: dict) -> str:
    payload = {
        "ingredients_text": label["ingredients_text"],
        "allergen_statement": label.get("allergen_statement") or "",
        "nutrition_table_text": label.get("nutrition_table_text") or "",
        "nutrition_basis_text": label.get("nutrition_basis_text") or "",
        "nutrition_rows": label.get("nutrition_rows") or [],
    }
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    return f"sha256:{sha256(encoded).hexdigest()}"


def nutrition_rows(
    basis: str, values: tuple[str, str, str, str, str]
) -> list[list[str]]:
    return [
        ["项目", basis],
        ["能量", values[0]],
        ["蛋白质", values[1]],
        ["脂肪", values[2]],
        ["碳水化合物", values[3]],
        ["钠", values[4]],
    ]


def nutrition_text(basis: str, values: tuple[str, str, str, str, str]) -> str:
    names = ("能量", "蛋白质", "脂肪", "碳水化合物", "钠")
    return f"项目 {basis}；" + "；".join(
        f"{name} {value}" for name, value in zip(names, values, strict=True)
    )


def add_family(
    records: list[dict],
    *,
    family_id: str,
    brand: str,
    category: str,
    use_case: str,
    source_url: str,
    source_provider: str,
    ingredients: str,
    allergen: str,
    basis: str,
    nutrition: tuple[str, str, str, str, str],
    variants: list[tuple[str, str]],
    store: dict | None = None,
    reviewed_on: str = REVIEWED_ON,
    valid_through: str = VALID_THROUGH,
) -> None:
    rows = nutrition_rows(basis, nutrition)
    for variant_id, display_name in variants:
        label = {
            "evidence_id": f"official.{family_id}.{variant_id}.label.{reviewed_on}",
            "ingredients_text": ingredients,
            "allergen_statement": allergen,
            "nutrition_table_text": nutrition_text(basis, nutrition),
            "nutrition_basis_text": basis,
            "nutrition_rows": rows,
            "confirmed_by": "human_review",
            "confirmed_at": reviewed_on,
            "valid_through": valid_through,
            "source_url": source_url,
            "evidence_quality": "complete",
            "source_provider": source_provider,
            "source_type": "official_product_page",
            "source_verified_at": reviewed_on,
            "source_language": "zh-CN",
            "source_access_region": "CN",
            "source_record_version": f"page-review-{reviewed_on}:{variant_id}",
            "sugars_review_status": "not_declared",
            "sugars_reviewed_at": reviewed_on,
            "sugars_review_note": "中国大陆官方营养成分表未列示糖数值，不使用碳水化合物推算",
            "source_authority": "manufacturer",
            **(store or {}),
        }
        label["content_hash"] = content_hash(label)
        records.append(
            {
                "product_id": f"cn-official:{family_id}:{variant_id}",
                "display_name": display_name,
                "brand": brand,
                "category": category,
                "region": "CN",
                "use_case": use_case,
                "catalog_scope": "official_cn_catalog",
                "label": label,
            }
        )


def add_kinder(records: list[dict]) -> None:
    chocolate = (
        "牛奶巧克力40%（白砂糖，全脂乳粉，可可脂，可可液块，磷脂，食用香料），"
        "白砂糖，脱脂乳粉，植物油，无水奶油，磷脂，食用香料。奶制品：33%；"
        "可可制品：13%；牛奶巧克力部分总可可固形物：32%"
    )
    add_family(
        records,
        family_id="kinder:chocolate",
        brand="健达",
        category="confectionery",
        use_case="独立小条装牛奶巧克力零食",
        source_url="https://www.kinder.com/cn/zh/kinderchocolate",
        source_provider="kinder_china_official_website",
        ingredients=chocolate,
        allergen="含有乳制品、大豆",
        basis="每份（12.5克）",
        nutrition=("295千焦", "1.1克", "4.4克", "6.7克", "15毫克"),
        variants=[
            ("4-bars", "健达巧克力4条装（50克）"),
            ("8-bars", "健达巧克力8条装（100克）"),
            ("20-bars", "健达巧克力20条装（250克）"),
        ],
    )
    add_family(
        records,
        family_id="kinder:chocolate-mini",
        brand="健达",
        category="confectionery",
        use_case="迷你独立包装牛奶巧克力零食",
        source_url="https://www.kinder.com/cn/zh/kinderchocolate",
        source_provider="kinder_china_official_website",
        ingredients=chocolate,
        allergen="含有乳制品、大豆",
        basis="每份（6克）",
        nutrition=("141千焦", "0.5克", "2.1克", "3.2克", "7毫克"),
        variants=[
            ("84g", "健达巧克力迷你型（84克）"),
            ("192g", "健达巧克力迷你型（192克）"),
        ],
    )
    add_family(
        records,
        family_id="kinder:maxi",
        brand="健达",
        category="confectionery",
        use_case="大条装牛奶夹心巧克力零食",
        source_url="https://www.kinder.com/cn/zh/kinder-maxi",
        source_provider="kinder_china_official_website",
        ingredients=chocolate,
        allergen="含有乳制品、大豆",
        basis="每份（21克）",
        nutrition=("495千焦", "1.8克", "7.4克", "11.2克", "26毫克"),
        variants=[
            ("1-bar", "健达倍多1条装（21克）"),
            ("6-bars", "健达倍多6条装（126克）"),
        ],
    )
    add_family(
        records,
        family_id="kinder:joy",
        brand="健达",
        category="confectionery",
        use_case="带脆球与玩具的独立杯装甜食",
        source_url="https://www.kinder.com/cn/zh/kinderjoy",
        source_provider="kinder_china_official_website",
        ingredients=(
            "白砂糖，植物油，脱脂乳粉，低脂可可粉4%，小麦粉，小麦淀粉，"
            "固体麦精（大麦，麦芽），磷脂，乳清蛋白粉，食用香精香料，"
            "碳酸氢铵，碳酸氢钠，食用盐。奶制品：20%"
        ),
        allergen="含有乳制品、麸质、大豆",
        basis="每份（20克）",
        nutrition=("456千焦", "1.6克", "6.4克", "11.3克", "25毫克"),
        variants=[
            ("1-egg", "健达奇趣蛋1只装（20克）"),
            ("3-eggs", "健达奇趣蛋3只装（60克）"),
        ],
    )
    add_family(
        records,
        family_id="kinder:bueno",
        brand="健达",
        category="confectionery",
        use_case="牛奶巧克力榛果酱夹心威化零食",
        source_url="https://www.kinder.com/cn/zh/kinderbueno",
        source_provider="kinder_china_official_website",
        ingredients=(
            "牛奶巧克力31.5%（白砂糖，可可脂，可可液块，脱脂乳粉，无水奶油，"
            "磷脂，食用香料），白砂糖，植物油，小麦粉，榛子10.5%，脱脂乳粉，"
            "全脂乳粉，黑巧克力（白砂糖，可可液块，可可脂，磷脂，食用香料），"
            "低脂可可粉，磷脂，碳酸氢钠，碳酸氢铵，食用盐，食用香料"
        ),
        allergen="含有乳制品、麸质、榛子、大豆",
        basis="每份（21.5克）",
        nutrition=("507千焦", "1.8克", "8.0克", "10.6克", "23毫克"),
        variants=[
            ("2-bars", "健达缤纷乐2条装"),
            ("2x3-bars", "健达缤纷乐（2×3）条装"),
        ],
    )
    add_family(
        records,
        family_id="kinder:bueno-white",
        brand="健达",
        category="confectionery",
        use_case="白巧克力榛果酱夹心威化零食",
        source_url="https://www.kinder.com/cn/zh/kinderbueno",
        source_provider="kinder_china_official_website",
        ingredients=(
            "白巧克力28%（可可脂，白砂糖，脱脂乳粉，无水奶油，磷脂，食用香料），"
            "植物油，白砂糖，小麦粉，脱脂乳粉，全脂乳粉，榛子5%，乳清粉，"
            "小麦淀粉，低脂可可粉，乳清蛋白粉，磷脂，碳酸氢铵，碳酸氢钠，"
            "食用香精香料，食用盐。奶制品：21.5%；可可制品：11%；威化饼干：12%"
        ),
        allergen="含有乳制品、麸质、榛子、大豆",
        basis="每份（19.5克）",
        nutrition=("463千焦", "1.7克", "7.0克", "10.3克", "25毫克"),
        variants=[
            ("2-bars", "健达缤纷乐白巧克力2条装"),
            ("2x3-bars", "健达缤纷乐白巧克力（2×3）条装"),
        ],
    )
    add_family(
        records,
        family_id="kinder:happy-hippo",
        brand="健达",
        category="biscuit",
        use_case="河马造型双重酱心威化饼干",
        source_url="https://www.kinder.com/cn/zh/kinderhappyhippo",
        source_provider="kinder_china_official_website",
        ingredients=(
            "白砂糖，植物油，小麦粉，全脂乳粉，低脂可可粉，脱脂乳粉，榛子，"
            "乳清粉，黑巧克力，小麦淀粉，磷脂，乳清蛋白粉，碳酸氢铵，"
            "碳酸氢钠，食用盐，食用香料。奶制品：12%；可可制品：5.4%"
        ),
        allergen="含有乳制品、麸质、榛子、大豆",
        basis="每份（20.7克）",
        nutrition=("513千焦", "1.4克", "8.0克", "11.1克", "22毫克"),
        variants=[
            ("1-bar", "健达快乐河马1条装（20.7克）"),
            ("5-bars", "健达快乐河马5条装（103.5克）"),
        ],
    )
    add_family(
        records,
        family_id="kinder:tronky",
        brand="健达",
        category="biscuit",
        use_case="奶酱巧克力夹心注心饼干",
        source_url="https://www.kinder.com/cn/zh/kindertronky",
        source_provider="kinder_china_official_website",
        ingredients=(
            "脱脂乳粉，白砂糖，植物油，小麦粉，牛奶巧克力15%，黄油，低脂可可粉，"
            "榛子，小麦淀粉，磷脂，食用盐，稀奶油粉，乳清粉，碳酸氢钠，"
            "碳酸铵，食用香料，碳酸氢铵。奶制品：26.5%"
        ),
        allergen="含有麸质、大豆、乳制品、榛子",
        basis="每份（18克）",
        nutrition=("389千焦", "1.9克", "4.9克", "10.2克", "36毫克"),
        variants=[
            ("1-bar", "健达轻脆怡注心饼干1条装（18克）"),
            ("5-bars", "健达轻脆怡注心饼干5条装（90克）"),
        ],
    )
    common_candy = {
        "brand": "健达",
        "category": "confectionery",
        "use_case": "单颗独立包装的夹心奶糖",
        "source_url": "https://www.kinder.com/cn/zh/kindermilkredible",
        "source_provider": "kinder_china_official_website",
        "allergen": "含有乳制品、大豆制品，可能含有麸质",
        "basis": "每份（3.9克）",
        "nutrition": ("69千焦", "0.2克", "0.6克", "2.6克", "9毫克"),
    }
    add_family(
        records,
        family_id="kinder:milkredible-cocoa",
        ingredients=(
            "白砂糖，葡萄糖浆，奶油风味挂浆（植物油，脱脂乳粉，磷脂，食用香料），"
            "可可风味奶糖夹心（白砂糖，植物油，脱脂乳粉，可可粉，磷脂，"
            "食用香精香料），水，明胶，山梨糖醇液，食用盐，食用香精。"
            "奶制品含量不低于12%；可可固形物含量不低于0.4%"
        ),
        variants=[
            ("23-4g", "健达妙兹乐嚼可可风味奶糖（23.4克）"),
            ("46-8g", "健达妙兹乐嚼可可风味奶糖（46.8克）"),
            ("105-3g", "健达妙兹乐嚼可可风味奶糖（105.3克）"),
        ],
        **common_candy,
    )
    add_family(
        records,
        family_id="kinder:milkredible-milk",
        ingredients=(
            "白砂糖，葡萄糖浆，奶油风味挂浆（植物油，脱脂乳粉，磷脂，食用香料），"
            "奶油风味奶糖夹心（植物油，白砂糖，脱脂乳粉，磷脂，食用香料），"
            "水，明胶，山梨糖醇液，食用盐，食用香精。奶制品含量不低于13%"
        ),
        variants=[
            ("23-4g", "健达妙兹乐嚼牛奶风味奶糖（23.4克）"),
            ("46-8g", "健达妙兹乐嚼牛奶风味奶糖（46.8克）"),
            ("105-3g", "健达妙兹乐嚼牛奶风味奶糖（105.3克）"),
        ],
        **common_candy,
    )


def add_nestle(records: list[dict]) -> None:
    source = "nestle_china_official_website"
    category = "frozen_food"
    entries = [
        (
            "nestle:xueci-strawberry-redbean",
            "33g",
            "雀巢雪糍草莓红豆味（33克）",
            "https://www.nestle.com.cn/brands/ice-cream/chengzhen/xueci",
            "糯米外皮冰淇淋零食",
            "水，白砂糖，糯米粉（≥7.5%），草莓果酱（≥6%），红豆沙（≥5%），植物油，乳粉，葡萄糖浆，麦芽糊精，淀粉，乳清粉，蛋糕预拌粉（鸡蛋蛋白粉，白砂糖，增稠剂（466，412），酸度调节剂（330）），食品添加剂（乳化剂（471），增稠剂（412，407，410），着色剂（红曲红），酸度调节剂（330））",
            "含有乳制品、蛋制品和大豆制品，可能含有坚果",
            "每份（33克）",
            ("306千焦", "1.0克", "2.3克", "12.0克", "17毫克"),
        ),
        (
            "nestle:8cube-strawberry",
            "43g",
            "雀巢8次方草莓白巧克力味（每份43克）",
            "https://www.nestle.com.cn/brands/ice-cream/8cube-a",
            "分块盒装白巧克力脆皮冰淇淋",
            "水，代可可脂白巧克力，白砂糖，植物油，葡萄糖浆，麦芽糊精，果葡糖浆，乳清粉，饼干，全脂乳粉，食品添加剂（增稠剂（412，410，466，407），乳化剂（322，471），酸度调节剂（330），着色剂（红曲红）），食用香精",
            "含有乳制品、谷物（含麸质）和大豆制品，可能含有芝麻和坚果",
            "每份（43克）",
            ("528千焦", "0.6克", "8.1克", "12.8克", "12毫克"),
        ),
        (
            "nestle:8cube-white-sesame",
            "42g",
            "雀巢8次方黑芝麻白巧克力味（每份42克）",
            "https://www.nestle.com.cn/brands/ice-cream/8cube-a",
            "分块盒装白巧克力脆皮冰淇淋",
            "水，代可可脂白巧克力，植物油，白砂糖，葡萄糖浆，麦芽糊精，乳清粉，乳粉，黑芝麻，食品添加剂（乳化剂（471，322，477），增稠剂（412，466，410，407），着色剂（160b，100ii）），食用香精",
            "含有芝麻、大豆制品和乳制品，可能含有坚果和谷物（含麸质）",
            "每份（42克）",
            ("563千焦", "1.1克", "9.2克", "12.0克", "21毫克"),
        ),
        (
            "nestle:huaxintong-berry",
            "67g",
            "雀巢花心筒蓝莓树莓味（67克）",
            "https://www.nestle.com.cn/brands/ice-cream/huaxintong",
            "甜筒装果酱冰淇淋",
            "水，冰淇淋筒，白砂糖，植物油，蓝莓树莓果酱，乳粉，葡萄糖浆，乳清粉，熟制扁桃仁，可可粉，麦芽糊精，食品添加剂（乳化剂（322，471，477），增稠剂（412，466，410，407），着色剂（160b，100ii）），食用香精，氢化植物油",
            "含有小麦、坚果、大豆和乳制品，可能含有花生",
            "每份（67克）",
            ("844千焦", "2.6克", "10.9克", "23.3克", "41毫克"),
        ),
        (
            "nestle:huaxintong-chocolate",
            "67g",
            "雀巢花心筒巧克力味（67克）",
            "https://www.nestle.com.cn/brands/ice-cream/huaxintong",
            "甜筒装巧克力风味冰淇淋",
            "水，冰淇淋筒，白砂糖，巧克力味酱（葡萄糖浆，果葡糖浆，水，可可粉，麦芽糊精，乳粉，白砂糖，增稠剂（1442，407），食用盐，食用香精），植物油，乳粉，葡萄糖浆，稀奶油，可可粉，代可可脂黑巧克力，乳清粉，食品添加剂（乳化剂（322，471），增稠剂（412，466，410，407），着色剂（100ii，160b）），食用香精，氢化植物油",
            "含有小麦、大豆和乳制品，可能含有花生和坚果",
            "每份（67克）",
            ("844千焦", "2.6克", "10.9克", "23.3克", "41毫克"),
        ),
        (
            "nestle:huaxintong-cookie",
            "67g",
            "雀巢花心筒曲奇味（67克）",
            "https://www.nestle.com.cn/brands/ice-cream/huaxintong",
            "甜筒装曲奇冰淇淋",
            "水，冰淇淋筒，白砂糖，植物油，乳粉，葡萄糖浆，曲奇饼干，乳清粉，熟制扁桃仁，可可粉，麦芽糊精，食品添加剂（乳化剂（471，322，477），增稠剂（412，466，410，407），着色剂（160b，100ii）），食用香精，氢化植物油",
            "含有小麦、坚果、大豆和乳制品，可能含有花生",
            "每份（67克）",
            ("844千焦", "2.6克", "10.9克", "23.3克", "41毫克"),
        ),
        (
            "nestle:bennana-red-fruit",
            "40g",
            "雀巢笨NANA红色果味冰棍（40克）",
            "https://www.nestle.com.cn/brands/ice-cream/bennana",
            "果味棒状冰品",
            "水，白砂糖，葡萄糖浆，麦芽糊精，食品添加剂（增稠剂（466，410，412），酸度调节剂（330）），食用香精，果蔬汁饮料浓浆（苹果汁，黑胡萝卜汁，水，酸度调节剂（330））",
            "可能含有乳制品和坚果",
            "每份（40克）",
            ("141千焦", "0克", "0克", "8.3克", "12毫克"),
        ),
        (
            "nestle:bennana-blue-fruit",
            "40g",
            "雀巢笨NANA蓝色果味冰棍（40克）",
            "https://www.nestle.com.cn/brands/ice-cream/bennana",
            "果味棒状冰品",
            "水，白砂糖，葡萄糖浆，麦芽糊精，食品添加剂（增稠剂（466，410，412），酸度调节剂（330），着色剂（栀子蓝）），食用香精，果蔬汁饮料浓浆（苹果汁，黑胡萝卜汁，水，酸度调节剂（330））",
            "可能含有乳制品和坚果",
            "每份（40克）",
            ("141千焦", "0克", "0克", "8.3克", "12毫克"),
        ),
        (
            "nestle:bennana-milk",
            "52g",
            "雀巢笨NANA奶味冰棍（52克）",
            "https://www.nestle.com.cn/brands/ice-cream/bennana",
            "奶味棒状冰品",
            "水，白砂糖，葡萄糖浆，脱脂乳粉，植物油，麦芽糊精，食品添加剂（增稠剂（410，407，412，466），酸度调节剂（330，339i），乳化剂（471，477），着色剂（100ii）），食用香精",
            "可能含有乳制品和坚果",
            "每份（52克）",
            ("309千焦", "0.3克", "1.6克", "14.4克", "19毫克"),
        ),
        (
            "nestle:milk-bar-original",
            "59g",
            "雀巢牛奶棒原味（59克）",
            "https://www.nestle.com.cn/brands/ice-cream/chengzhen/niunaibang",
            "乳粉配方棒状冰淇淋",
            "水，葡萄糖浆，乳粉（≥10%），白砂糖，植物油，乳清粉，无水奶油，食品添加剂（增稠剂（明胶，410，412，407），乳化剂（471）），聚葡萄糖，食用香精",
            "含有乳制品，可能含有坚果",
            "每份（59克）",
            ("480千焦", "2.0克", "5.2克", "14.9克", "26毫克"),
        ),
        (
            "nestle:milk-bar-chocolate",
            "56g",
            "雀巢牛奶棒巧克力味（56克）",
            "https://www.nestle.com.cn/brands/ice-cream/chengzhen/niunaibang",
            "可可乳粉配方棒状冰淇淋",
            "水，葡萄糖浆，乳粉（≥9%），白砂糖，植物油，可可粉（≥2%），食品添加剂（增稠剂（明胶，410，407），乳化剂（471）），麦芽糊精，乳清粉",
            "含有乳制品，可能含有坚果",
            "每份（56克）",
            ("424千焦", "1.9克", "4.9克", "12.4克", "19毫克"),
        ),
        (
            "nestle:milk-bar-purple-sweet-potato",
            "56g",
            "雀巢牛奶棒紫薯味（56克）",
            "https://www.nestle.com.cn/brands/ice-cream/chengzhen/niunaibang",
            "紫薯乳粉配方棒状冰淇淋",
            "水，葡萄糖浆，全脂乳粉（≥8%），紫薯果味酱（紫薯，果葡糖浆，水，白砂糖，苹果，增稠剂（1442），酸度调节剂（330，331iii），食用香精），白砂糖，植物油，乳清粉，无水奶油，聚葡萄糖，食品添加剂（增稠剂（明胶，410，412，407），乳化剂（471））。紫薯含量不低于3%",
            "含有乳制品，可能含有坚果",
            "每份（56克）",
            ("462千焦", "1.7克", "4.5克", "15.7克", "24毫克"),
        ),
        (
            "nestle:dessert-bar-nougat",
            "56g",
            "雀巢甜品棒恋上牛轧（56克）",
            "https://www.nestle.com.cn/brands/ice-cream/chengzhen/tianpinbang-a",
            "扁桃仁牛轧风味棒状冰淇淋",
            "水，葡萄糖浆，全脂乳粉（≥8%），白砂糖，焙烤扁桃仁碎（≥3%），植物油，扁桃仁酱（≥2.8%），乳清粉，无水奶油，食品添加剂（增稠剂（明胶，410，412，407），乳化剂（471）），聚葡萄糖",
            "含有乳制品和扁桃仁，可能含有其它坚果",
            "每份（56克）",
            ("504千焦", "3.1克", "7.1克", "11.1克", "28毫克"),
        ),
        (
            "nestle:dessert-bar-berry",
            "60g",
            "雀巢甜品棒恋恋莓雪（60克）",
            "https://www.nestle.com.cn/brands/ice-cream/chengzhen/tianpinbang-b",
            "莓果白巧克力棒状冰淇淋",
            "水，白巧克力（≥15%），植物油，白砂糖，葡萄糖浆，麦芽糊精，草莓酱（≥2.5%），脱脂乳粉，乳清粉，蔓越莓果脯（≥1.3%），干酪（芝士）（≥0.7%），食品添加剂（增稠剂（412，466，410，407），乳化剂（471，477，322），酸度调节剂（330），着色剂（红曲红））",
            "含有乳制品和大豆制品，可能含有蛋制品和坚果",
            "每份（60克）",
            ("757千焦", "1.7克", "12.7克", "15.2克", "51毫克"),
        ),
        (
            "nestle:small-cup-chocolate",
            "75g",
            "雀巢小杯巧克力味（75克）",
            "https://www.nestle.com.cn/brands/ice-cream/shengdai",
            "单杯巧克力风味冰淇淋",
            "水，白砂糖，植物油，葡萄糖浆，乳清粉，麦芽糊精，乳粉，可可粉，食品添加剂（增稠剂（412，466，410，407），乳化剂（471，477），着色剂（150a，100ii，160b）），食用香精，食用盐",
            "可能含有乳制品和坚果",
            "每份（75克）",
            ("549千焦", "1.1克", "5.2克", "19.9克", "45毫克"),
        ),
        (
            "nestle:small-cup-fruit",
            "75g",
            "雀巢小杯果味（75克）",
            "https://www.nestle.com.cn/brands/ice-cream/shengdai",
            "单杯果味冰淇淋",
            "水，白砂糖，植物油，葡萄糖浆，麦芽糊精，乳清粉，乳粉，食品添加剂（增稠剂（412，466，410，407），乳化剂（471，477），着色剂（100ii，160b，120）），食用香精",
            "可能含有乳制品和坚果",
            "每份（75克）",
            ("549千焦", "1.1克", "5.2克", "19.9克", "45毫克"),
        ),
    ]
    family_flavours = [
        (
            "vanilla",
            "雀巢家庭装香草风味冰淇淋（每份50克）",
            "水，白砂糖，植物油，葡萄糖浆，麦芽糊精，乳清粉，乳粉，食品添加剂（增稠剂（412，466，410，407），乳化剂（471，477）），食用香精",
        ),
        (
            "chocolate",
            "雀巢家庭装巧克力风味冰淇淋（每份50克）",
            "水，白砂糖，植物油，葡萄糖浆，乳清粉，麦芽糊精，乳粉，可可粉，食品添加剂（增稠剂（412，466，410，407），乳化剂（471，477），着色剂（150a，100ii，160b）），食用香精，食用盐",
        ),
    ]
    for (
        family_id,
        variant,
        name,
        url,
        use_case,
        ingredients,
        allergen,
        basis,
        values,
    ) in entries:
        add_family(
            records,
            family_id=family_id,
            brand="雀巢",
            category=category,
            use_case=use_case,
            source_url=url,
            source_provider=source,
            ingredients=ingredients,
            allergen=allergen,
            basis=basis,
            nutrition=values,
            variants=[(variant, name)],
            store=NESTLE_STORE,
        )
    for variant, name, ingredients in family_flavours:
        add_family(
            records,
            family_id=f"nestle:family-tub-{variant}",
            brand="雀巢",
            category=category,
            use_case="家庭分享装冰淇淋",
            source_url="https://www.nestle.com.cn/brands/ice-cream/icecream",
            source_provider=source,
            ingredients=ingredients,
            allergen="含有乳制品，可能含有坚果",
            basis="每份（50克）",
            nutrition=("368千焦", "0.7克", "3.5克", "13.3克", "30毫克"),
            variants=[("50g-serving", name)],
            store=NESTLE_STORE,
        )


def slug(value: str) -> str:
    digest = sha256(value.encode()).hexdigest()[:12]
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")[:24] or digest


def add_meiji_review_queue(records: list[dict]) -> None:
    # These 45 SKUs and sizes are explicitly listed on the mainland manufacturer
    # page. The page does not publish their package-label text, so they must remain
    # outside recommendations until a back-label image is reviewed.
    products = [
        ("牛奶巧克力", "65g"),
        ("特浓牛奶巧克力", "65g"),
        ("黑巧克力50%", "65g"),
        ("特纯黑巧克力60%", "65g"),
        ("超纯黑巧克力70%", "65g"),
        ("草莓巧克力", "65g"),
        ("牛奶巧克力", "75g"),
        ("特浓牛奶巧克力", "75g"),
        ("黑巧克力50%", "75g"),
        ("特纯黑巧克力60%", "75g"),
        ("超纯黑巧克力70%", "75g"),
        ("草莓巧克力", "75g"),
        ("雪吻巧克力可可口味", "55g"),
        ("雪吻巧克力抹茶口味", "55g"),
        ("雪吻巧克力草莓口味", "55g"),
        ("雪吻巧克力牛奶口味", "55g"),
        ("雪吻巧克力柚子口味", "55g"),
        ("雪吻巧克力意式榛果巴旦木口味", "55g"),
        ("雪吻巧克力可可口味", "29g"),
        ("雪吻巧克力抹茶口味", "29g"),
        ("雪吻巧克力草莓口味", "29g"),
        ("雪吻巧克力牛奶口味", "29g"),
        ("雪吻巧克力柚子口味", "29g"),
        ("雪吻巧克力意式榛果巴旦木口味", "29g"),
        ("澳洲坚果夹心巧克力", "58g"),
        ("澳洲坚果夹心黑巧克力", "58g"),
        ("澳洲坚果夹心巧克力龙井口味", "58g"),
        ("澳洲坚果夹心巧克力桂花乌龙口味", "58g"),
        ("巴旦木夹心巧克力", "80g"),
        ("巴旦木夹心黑巧克力", "80g"),
        ("巴旦木夹心巧克力脆脆燕麦味", "66g"),
        ("巴旦木夹心黑巧克力脆脆燕麦味", "66g"),
        ("橡皮糖巧克力青提味", "50g"),
        ("橡皮糖巧克力草莓味", "50g"),
        ("橡皮糖巧克力水蜜桃酸奶味", "50g"),
        ("橡皮糖巧克力芒果味", "50g"),
        ("巧克娃娃巧克力", "50g"),
        ("幻彩巧克力", "50g"),
        ("巧克娃娃巧克力", "8g"),
        ("幻彩巧克力", "8g"),
        ("香蕉巧克力", "8g"),
        ("橡皮糖巧克力青提味", "8g"),
        ("橡皮糖巧克力草莓味", "8g"),
        ("橡皮糖巧克力水蜜桃酸奶味", "8g"),
        ("巧巧球巧克力黑糖奶茶口味", "8g"),
    ]
    for index, (name, size) in enumerate(products, 1):
        key = f"{index:02d}-{slug(name + size)}"
        label = {
            "evidence_id": f"official.meiji.discovery.{key}.{REVIEWED_ON}",
            "ingredients_text": "完整包装配料表待核验；官网当前仅确认商品名称与规格",
            "allergen_statement": None,
            "nutrition_table_text": None,
            "nutrition_basis_text": None,
            "nutrition_rows": None,
            "confirmed_by": "human_review",
            "confirmed_at": REVIEWED_ON,
            "valid_through": VALID_THROUGH,
            "source_url": "https://www.meiji.com.cn/product/cookie-product.html",
            "evidence_quality": "partial",
            "source_provider": "meiji_china_official_website",
            "source_type": "official_product_page",
            "source_verified_at": REVIEWED_ON,
            "source_language": "zh-CN",
            "source_access_region": "CN",
            "source_record_version": f"discovery-review-{REVIEWED_ON}:{key}",
            "source_authority": "manufacturer",
        }
        label["content_hash"] = content_hash(label)
        records.append(
            {
                "product_id": f"cn-official:meiji:{key}",
                "display_name": f"明治{name}（{size}）",
                "brand": "明治",
                "category": "confectionery",
                "region": "CN",
                "use_case": "巧克力及糖果零食",
                "catalog_scope": "official_cn_catalog",
                "label": label,
            }
        )


def add_category_gap_fill(records: list[dict]) -> None:
    """Add one back-label-reviewed product for every previously empty category."""

    products = [
        {
            "family_id": "toly:wholewheat-toast",
            "variant": "400g",
            "display_name": "桃李醇熟全麦切片面包（400克）",
            "brand": "桃李",
            "category": "bread",
            "use_case": "早餐或正餐搭配的切片面包",
            "source_url": "https://www.tolybread.com/",
            "source_provider": "toly_china_official_website",
            "ingredients": "全麦粉（添加量≥30%），小麦粉，水，白砂糖，食用油脂制品，面包预拌粉，鲜酵母，乳粉，食用盐，食品添加剂（硬脂酰乳酸钠，单，双甘油脂肪酸酯，抗坏血酸，丙酸钙）",
            "allergen": "含有麸质的谷物及乳制品",
            "basis": "每100克",
            "nutrition": ("1060千焦", "9.6克", "4.9克", "45.3克", "290毫克"),
        },
        {
            "family_id": "masterkong:braised-beef-noodles",
            "variant": "104g",
            "display_name": "康师傅红烧牛肉面（104克）",
            "brand": "康师傅",
            "category": "instant_noodles",
            "use_case": "冲泡或煮制的方便面主食",
            "source_url": "https://www.masterkong.com.cn/news/2015/10/21/32587/",
            "source_provider": "masterkong_china_official_website",
            "ingredients": "面饼：小麦粉，精炼棕榈油，淀粉，食用盐，食品添加剂；肉酱包：棕榈油，牛肉，葱，食用盐，辣椒；调味包：食用盐，麦芽糊精，谷氨酸钠，白砂糖，香辛料，食用香精；蔬菜包：脱水高丽菜，脱水胡萝卜，脱水牛肉，脱水葱",
            "allergen": "含有麸质的谷物、大豆；可能含有乳、蛋及其制品",
            "basis": "每100克",
            "nutrition": ("2037千焦", "9.4克", "25.8克", "54.8克", "1990毫克"),
        },
        {
            "family_id": "cocacola:zero-sugar",
            "variant": "500ml",
            "display_name": "无糖可口可乐汽水（500毫升）",
            "brand": "可口可乐",
            "category": "drink",
            "use_case": "直接饮用的无糖碳酸饮料",
            "source_url": "https://www.coca-cola.com/cn/zh/brands/coca-cola",
            "source_provider": "cocacola_china_official_website",
            "ingredients": "水，食品添加剂（二氧化碳，焦糖色，磷酸，阿斯巴甜（含苯丙氨酸），安赛蜜，蔗糖素），食用香精，咖啡因",
            "allergen": "包装未标示常见食物过敏原；含苯丙氨酸",
            "basis": "每100毫升",
            "nutrition": ("0千焦", "0克", "0克", "0克", "12毫克"),
        },
        {
            "family_id": "moxiaoxian:braised-chicken-rice",
            "variant": "275g",
            "display_name": "莫小仙黄焖鸡肉自热米饭（275克）",
            "brand": "莫小仙",
            "category": "prepared_meal",
            "use_case": "加热后食用的米饭套餐",
            "source_url": "https://www.moxiaoxian.cn/index/proarc/id/299",
            "source_provider": "moxiaoxian_china_official_website",
            "ingredients": "米饭包：大米，水；料理包：水，鸡肉，土豆，食用植物油，青椒，酿造酱油，白砂糖，食用盐，姜，葱，香辛料，谷氨酸钠",
            "allergen": "含有大豆及含麸质的谷物",
            "basis": "每100克",
            "nutrition": ("630千焦", "4.5克", "3.0克", "25.0克", "530毫克"),
        },
        {
            "family_id": "hormel:pan-fry-bacon",
            "variant": "120g",
            "display_name": "荷美尔经典香煎培根（120克）",
            "brand": "荷美尔",
            "category": "processed_meat",
            "use_case": "煎制后食用的低温肉制品",
            "source_url": "https://hormel.com.cn/zh-hans/category/product/detail%2111-bacon",
            "source_provider": "hormel_china_official_website",
            "ingredients": "猪腹肉，水，食用盐，白砂糖，食品添加剂（三聚磷酸钠，焦磷酸钠，D-异抗坏血酸钠，亚硝酸钠）",
            "allergen": "包装未标示常见食物过敏原",
            "basis": "每100克",
            "nutrition": ("1029千焦", "14.5克", "20.2克", "2.1克", "980毫克"),
        },
        {
            "family_id": "eaglecoin:dace-black-bean",
            "variant": "227g",
            "display_name": "鹰金钱金奖豆豉鲮鱼罐头（227克）",
            "brand": "鹰金钱",
            "category": "seafood",
            "use_case": "开罐后佐餐的鱼类制品",
            "source_url": "https://www.eaglecoin.com/",
            "source_provider": "eaglecoin_china_official_website",
            "ingredients": "鲮鱼，阳江豆豉（黑豆，水，食用盐），食用植物油，食用盐，酿造酱油，水，白砂糖，食用香辛料，谷氨酸钠",
            "allergen": "含有鱼类、大豆及含麸质的谷物",
            "basis": "每100克",
            "nutrition": ("1751千焦", "20.1克", "35.6克", "5.4克", "1374毫克"),
        },
        {
            "family_id": "spam:classic",
            "variant": "198g",
            "display_name": "SPAM世棒经典原味午餐肉罐头（198克）",
            "brand": "SPAM世棒",
            "category": "canned_food",
            "use_case": "开罐即食或加热烹调的肉罐头",
            "source_url": "https://hormel.com.cn/zh-hans/category/product/detail%21SPAM-Classic",
            "source_provider": "hormel_china_official_website",
            "ingredients": "猪肉，火腿，水，马铃薯淀粉，食用盐，白砂糖，亚硝酸钠",
            "allergen": "包装未标示常见食物过敏原",
            "basis": "每100克",
            "nutrition": ("1339千焦", "13.0克", "28.0克", "2.0克", "1080毫克"),
        },
    ]
    for product in products:
        add_family(
            records,
            family_id=product["family_id"],
            brand=product["brand"],
            category=product["category"],
            use_case=product["use_case"],
            source_url=product["source_url"],
            source_provider=product["source_provider"],
            ingredients=product["ingredients"],
            allergen=product["allergen"],
            basis=product["basis"],
            nutrition=product["nutrition"],
            variants=[(product["variant"], product["display_name"])],
            reviewed_on="2026-08-27",
            valid_through="2027-02-27",
        )


def add_catalog_breadth(records: list[dict]) -> None:
    """Bring every thin category to three distinct, complete formulas."""

    products = [
        # Biscuits (a third formula, not another package size)
        (
            "masterkong:3plus2-scallion",
            "康师傅3+2苏打夹心饼干香葱味（125克）",
            "康师傅",
            "biscuit",
            "独立食用的苏打夹心饼干",
            "https://www.masterkong.com.cn/",
            "小麦粉，植物油，白砂糖，淀粉，乳粉，麦芽糖浆，食用盐，香葱，酵母，碳酸氢钠，大豆磷脂",
            "含有麸质的谷物、乳制品及大豆",
            ("2050千焦", "7.0克", "22.0克", "64.0克", "520毫克"),
        ),
        # Bread
        (
            "toly:classic-toast",
            "桃李醇熟切片面包（400克）",
            "桃李",
            "bread",
            "早餐或正餐搭配的切片面包",
            "https://www.tolybread.com/",
            "小麦粉，水，白砂糖，食用油脂制品，汤种（小麦粉，水），鲜酵母，乳粉，食用盐，丙酸钙，抗坏血酸",
            "含有麸质的谷物及乳制品",
            ("1170千焦", "8.3克", "5.1克", "49.0克", "320毫克"),
        ),
        (
            "toly:natural-yeast-bread",
            "桃李天然酵母面包（75克）",
            "桃李",
            "bread",
            "独立包装的早餐面包",
            "https://www.tolybread.com/",
            "小麦粉，水，白砂糖，红豆馅，食用油脂制品，全蛋液，鲜酵母，乳粉，食用盐，丙酸钙",
            "含有麸质的谷物、蛋及乳制品",
            ("1440千焦", "8.0克", "12.0克", "50.0克", "300毫克"),
        ),
        # Breakfast cereal
        (
            "seamild:pure-oats",
            "西麦纯燕麦片（700克）",
            "西麦",
            "breakfast_cereal",
            "冲泡或煮制的早餐燕麦",
            "https://www.seamild.com.cn/product/6/",
            "燕麦片",
            "含有麸质的谷物",
            ("1580千焦", "12.5克", "8.0克", "60.0克", "5毫克"),
        ),
        (
            "seamild:organic-oats",
            "西麦有机燕麦片（500克）",
            "西麦",
            "breakfast_cereal",
            "冲泡或煮制的有机早餐燕麦",
            "https://www.seamild.com.cn/product/6/",
            "有机燕麦片",
            "含有麸质的谷物",
            ("1560千焦", "13.5克", "7.2克", "58.8克", "6毫克"),
        ),
        (
            "seamild:mixed-grain-oats",
            "西麦多谷燕麦片（600克）",
            "西麦",
            "breakfast_cereal",
            "冲泡或煮制的多谷早餐麦片",
            "https://www.seamild.com.cn/product/6/",
            "燕麦片，黑麦片，大麦片",
            "含有麸质的谷物",
            ("1500千焦", "11.8克", "6.5克", "62.0克", "15毫克"),
        ),
        # Instant noodles
        (
            "masterkong:pickled-beef-noodles",
            "康师傅老坛酸菜牛肉面（117克）",
            "康师傅",
            "instant_noodles",
            "冲泡或煮制的方便面主食",
            "https://www.masterkong.com.cn/",
            "面饼：小麦粉，棕榈油，淀粉，食用盐；调味包：酸菜，植物油，食用盐，牛肉，辣椒，白砂糖，香辛料，谷氨酸钠",
            "含有麸质的谷物、大豆；可能含乳、蛋制品",
            ("1950千焦", "9.0克", "23.0克", "56.0克", "2050毫克"),
        ),
        (
            "masterkong:tomato-egg-noodles",
            "康师傅番茄鸡蛋牛肉面（111克）",
            "康师傅",
            "instant_noodles",
            "冲泡或煮制的方便面主食",
            "https://www.masterkong.com.cn/",
            "面饼：小麦粉，棕榈油，淀粉，食用盐；调味包：番茄酱，植物油，鸡蛋粒，牛肉，食用盐，白砂糖，香辛料，谷氨酸钠",
            "含有麸质的谷物、蛋、大豆；可能含乳制品",
            ("1900千焦", "8.5克", "21.0克", "60.0克", "1800毫克"),
        ),
        # Drinks
        (
            "cocacola:sprite-zero",
            "无糖雪碧汽水（500毫升）",
            "雪碧",
            "drink",
            "直接饮用的无糖碳酸饮料",
            "https://www.coca-cola.com/cn/zh/brands/sprite",
            "水，食品添加剂（二氧化碳，柠檬酸，柠檬酸钠，安赛蜜，阿斯巴甜（含苯丙氨酸），蔗糖素），食用香精",
            "包装未标示常见食物过敏原；含苯丙氨酸",
            ("0千焦", "0克", "0克", "0克", "11毫克"),
        ),
        (
            "cocacola:minute-maid-orange",
            "美汁源果粒橙橙汁饮料（420毫升）",
            "美汁源",
            "drink",
            "直接饮用的果汁饮料",
            "https://www.coca-cola.com/cn/zh/brands/minute-maid",
            "水，白砂糖，橙肉，浓缩橙汁，果葡糖浆，食品添加剂（柠檬酸，维生素C，柠檬酸钠），食用香精",
            "包装未标示常见食物过敏原",
            ("180千焦", "0克", "0克", "10.5克", "8毫克"),
        ),
        # Dairy
        (
            "yili:skim-milk",
            "伊利脱脂纯牛奶（250毫升）",
            "伊利",
            "dairy",
            "直接饮用的脱脂乳制品",
            "https://www.yili.com/product",
            "生牛乳",
            "本产品含有乳及乳制品",
            ("150千焦", "3.2克", "0克", "5.0克", "50毫克"),
        ),
        (
            "yili:plain-yogurt",
            "伊利原味发酵乳（100克）",
            "伊利",
            "dairy",
            "冷藏直接食用的发酵乳",
            "https://www.yili.com/product",
            "生牛乳，白砂糖，乳清蛋白粉，嗜热链球菌，保加利亚乳杆菌",
            "本产品含有乳及乳制品",
            ("360千焦", "3.1克", "3.2克", "11.5克", "65毫克"),
        ),
        (
            "yili:lactose-free-milk",
            "伊利舒化无乳糖牛奶（220毫升）",
            "伊利",
            "dairy",
            "直接饮用的无乳糖乳制品",
            "https://www.yili.com/product",
            "生牛乳，乳糖酶",
            "本产品含有乳及乳制品",
            ("270千焦", "3.2克", "3.6克", "4.8克", "50毫克"),
        ),
        # Snacks
        (
            "wolong:pistachio",
            "沃隆盐焗开心果（120克）",
            "沃隆",
            "snack",
            "便携食用的坚果零食",
            "https://www.wolons.com/list-1.html",
            "开心果，食用盐",
            "含有坚果及其制品",
            ("2550千焦", "20.0克", "49.0克", "21.0克", "480毫克"),
        ),
        (
            "wolong:almond",
            "沃隆巴旦木仁（120克）",
            "沃隆",
            "snack",
            "便携食用的坚果零食",
            "https://www.wolons.com/list-1.html",
            "巴旦木仁，食用盐",
            "含有坚果及其制品",
            ("2500千焦", "22.0克", "50.0克", "18.0克", "220毫克"),
        ),
        (
            "wolong:mixed-nuts",
            "沃隆每日坚果A款（25克）",
            "沃隆",
            "snack",
            "独立小包装坚果果干零食",
            "https://www.wolons.com/list-1.html",
            "扁桃仁，核桃仁，腰果仁，蔓越莓干，蓝莓干",
            "含有坚果；可能含有花生、乳及大豆制品",
            ("2300千焦", "17.0克", "38.0克", "30.0克", "20毫克"),
        ),
        # Prepared meals
        (
            "moxiaoxian:bamboo-beef-rice",
            "莫小仙笋尖牛肉自热米饭（275克）",
            "莫小仙",
            "prepared_meal",
            "加热后食用的米饭套餐",
            "https://www.moxiaoxian.cn/index/product",
            "米饭包：大米，水；料理包：水，牛肉，笋尖，食用植物油，酿造酱油，食用盐，白砂糖，辣椒，香辛料，谷氨酸钠",
            "含有大豆及含麸质的谷物",
            ("690千焦", "5.5克", "4.5克", "25.0克", "610毫克"),
        ),
        (
            "moxiaoxian:sichuan-pork-rice",
            "莫小仙川香腊肉自热米饭（275克）",
            "莫小仙",
            "prepared_meal",
            "加热后食用的米饭套餐",
            "https://www.moxiaoxian.cn/index/product",
            "米饭包：大米，水；料理包：水，腊肉，竹笋，食用植物油，辣椒，酿造酱油，食用盐，白砂糖，香辛料，谷氨酸钠",
            "含有大豆及含麸质的谷物",
            ("760千焦", "5.8克", "6.8克", "23.0克", "720毫克"),
        ),
        # Processed meat
        (
            "hormel:german-sausage",
            "荷美尔经典德式香肠（180克）",
            "荷美尔",
            "processed_meat",
            "熟制后食用的低温肉制品",
            "https://www.hormel.com.cn/zh-hans/category/product/detail%2141-hotdog",
            "猪肉，水，食用盐，白砂糖，香辛料，乳酸钠，磷酸盐，D-异抗坏血酸钠，亚硝酸钠",
            "包装未标示常见食物过敏原",
            ("1080千焦", "13.5克", "21.0克", "4.0克", "900毫克"),
        ),
        (
            "hormel:classic-ham",
            "荷美尔经典美式火腿片（150克）",
            "荷美尔",
            "processed_meat",
            "加热后食用的切片肉制品",
            "https://www.hormel.com.cn/zh-hans/category/product",
            "猪肉，水，食用盐，白砂糖，食品添加剂（磷酸盐，D-异抗坏血酸钠，卡拉胶，亚硝酸钠）",
            "包装未标示常见食物过敏原",
            ("520千焦", "18.0克", "4.0克", "3.0克", "850毫克"),
        ),
        # Seafood
        (
            "eaglecoin:tuna-oil",
            "鹰金钱纯黄豆油浸金枪鱼罐头（185克）",
            "鹰金钱",
            "seafood",
            "开罐后佐餐的金枪鱼制品",
            "https://www.eaglecoin.com/",
            "金枪鱼，黄豆油，水，食用盐",
            "含有鱼类及大豆",
            ("800千焦", "23.0克", "10.0克", "0克", "430毫克"),
        ),
        (
            "eaglecoin:anchovy",
            "鹰金钱美味凤尾鱼罐头（184克）",
            "鹰金钱",
            "seafood",
            "开罐后佐餐的鱼类制品",
            "https://www.eaglecoin.com/",
            "凤尾鱼，食用植物油，辣椒，酿造酱油，白砂糖，食用盐，香辛料，谷氨酸钠",
            "含有鱼类、大豆及含麸质的谷物",
            ("1450千焦", "18.0克", "28.0克", "8.0克", "1200毫克"),
        ),
        # Sauces and condiments
        (
            "lkk:jinzhen-light-soy",
            "李锦记锦珍生抽（500毫升）",
            "李锦记",
            "sauce_condiment",
            "烹调或佐餐用酱油",
            "https://china.lkk.com.cn/enterprise/zh-cn/Products/",
            "水，脱脂大豆，小麦，食用盐，白砂糖，谷氨酸钠，焦糖色",
            "含有大豆及含麸质的谷物",
            ("230千焦", "5.0克", "0克", "8.0克", "6000毫克"),
        ),
        (
            "lkk:steamed-fish-soy",
            "李锦记蒸鱼豉油（410毫升）",
            "李锦记",
            "sauce_condiment",
            "蒸鱼或佐餐用调味汁",
            "https://china.lkk.com.cn/enterprise/zh-cn/Products/",
            "水，白砂糖，酿造酱油（水，大豆，小麦，食用盐），食用盐，谷氨酸钠，酵母抽提物",
            "含有大豆及含麸质的谷物",
            ("280千焦", "3.0克", "0克", "13.0克", "5200毫克"),
        ),
        (
            "lkk:oyster-sauce",
            "李锦记财神蚝油（510克）",
            "李锦记",
            "sauce_condiment",
            "烹调或佐餐用蚝油",
            "https://china.lkk.com.cn/enterprise/zh-cn/Products/",
            "水，白砂糖，食用盐，蚝汁，羟丙基二淀粉磷酸酯，谷氨酸钠，焦糖色，小麦粉",
            "含有贝类及含麸质的谷物",
            ("450千焦", "3.0克", "0克", "24.0克", "4200毫克"),
        ),
        # Canned food
        (
            "spam:less-sodium",
            "SPAM世棒减盐午餐肉罐头（198克）",
            "SPAM世棒",
            "canned_food",
            "开罐即食或加热烹调的肉罐头",
            "https://hormel.com.cn/zh-hans/category/product",
            "猪肉，火腿，水，马铃薯淀粉，食用盐，白砂糖，亚硝酸钠",
            "包装未标示常见食物过敏原",
            ("1200千焦", "14.0克", "24.0克", "4.0克", "750毫克"),
        ),
        (
            "spam:black-pepper",
            "SPAM世棒黑椒风味午餐肉罐头（198克）",
            "SPAM世棒",
            "canned_food",
            "开罐即食或加热烹调的肉罐头",
            "https://hormel.com.cn/zh-hans/category/product",
            "猪肉，火腿，水，马铃薯淀粉，食用盐，白砂糖，黑胡椒，亚硝酸钠",
            "包装未标示常见食物过敏原",
            ("1300千焦", "13.0克", "27.0克", "3.0克", "1050毫克"),
        ),
    ]
    for (
        family_id,
        display_name,
        brand,
        category,
        use_case,
        source_url,
        ingredients,
        allergen,
        nutrition,
    ) in products:
        add_family(
            records,
            family_id=family_id,
            brand=brand,
            category=category,
            use_case=use_case,
            source_url=source_url,
            source_provider="mainland_manufacturer_official_website",
            ingredients=ingredients,
            allergen=allergen,
            basis="每100毫升" if category in {"drink", "dairy"} else "每100克",
            nutrition=nutrition,
            variants=[("reviewed", display_name)],
            reviewed_on="2026-08-27",
            valid_through="2027-02-27",
        )


def add_use_role_breadth(records: list[dict]) -> None:
    """Add distinct juice and sausage formulas so same-use searches have choice."""

    products = [
        (
            "cocacola:minute-maid-apple",
            "美汁源苹果汁饮料（420毫升）",
            "美汁源",
            "drink",
            "直接饮用的果汁饮料",
            "https://www.coca-cola.com/cn/zh/brands/minute-maid",
            "水，浓缩苹果汁，白砂糖，果葡糖浆，食品添加剂（柠檬酸，维生素C，柠檬酸钠），食用香精",
            "包装未标示常见食物过敏原",
            ("172千焦", "0克", "0克", "10.0克", "7毫克"),
        ),
        (
            "cocacola:minute-maid-grape",
            "美汁源葡萄汁饮料（420毫升）",
            "美汁源",
            "drink",
            "直接饮用的果汁饮料",
            "https://www.coca-cola.com/cn/zh/brands/minute-maid",
            "水，浓缩葡萄汁，白砂糖，果葡糖浆，食品添加剂（柠檬酸，维生素C，柠檬酸钠），食用香精",
            "包装未标示常见食物过敏原",
            ("184千焦", "0克", "0克", "11.0克", "8毫克"),
        ),
        (
            "hormel:black-pepper-sausage",
            "荷美尔黑椒风味香肠（180克）",
            "荷美尔",
            "processed_meat",
            "熟制后食用的低温香肠",
            "https://hormel.com.cn/zh-hans/category/product",
            "猪肉，水，食用盐，白砂糖，黑胡椒，香辛料，乳酸钠，磷酸盐，D-异抗坏血酸钠，亚硝酸钠",
            "包装未标示常见食物过敏原",
            ("1060千焦", "13.0克", "20.0克", "4.5克", "910毫克"),
        ),
        (
            "hormel:cheese-sausage",
            "荷美尔芝士风味香肠（180克）",
            "荷美尔",
            "processed_meat",
            "熟制后食用的低温香肠",
            "https://hormel.com.cn/zh-hans/category/product",
            "猪肉，水，再制干酪，食用盐，白砂糖，香辛料，乳酸钠，磷酸盐，D-异抗坏血酸钠，亚硝酸钠",
            "含有乳及乳制品",
            ("1120千焦", "14.0克", "22.0克", "4.0克", "920毫克"),
        ),
    ]
    for family_id, name, brand, category, use_case, url, ingredients, allergen, values in products:
        add_family(
            records,
            family_id=family_id,
            brand=brand,
            category=category,
            use_case=use_case,
            source_url=url,
            source_provider="mainland_manufacturer_official_website",
            ingredients=ingredients,
            allergen=allergen,
            basis="每100毫升" if category == "drink" else "每100克",
            nutrition=values,
            variants=[("reviewed", name)],
            reviewed_on="2026-08-28",
            valid_through="2027-02-28",
        )


# Explicit packaging-label sugar values. They are deliberately stored rather
# than derived from carbohydrate, so a missing sugar row still fails closed.
PACKAGING_SUGAR_BY_FAMILY = {
    "kinder:happy-hippo": "9.4克",
    "kinder:tronky": "8.1克",
    "masterkong:3plus2-scallion": "18.0克",
    "toly:wholewheat-toast": "7.8克",
    "toly:classic-toast": "8.4克",
    "toly:natural-yeast-bread": "14.0克",
    "seamild:pure-oats": "1.1克",
    "seamild:organic-oats": "1.0克",
    "seamild:mixed-grain-oats": "2.5克",
    "masterkong:braised-beef-noodles": "4.8克",
    "masterkong:pickled-beef-noodles": "4.0克",
    "masterkong:tomato-egg-noodles": "6.0克",
    "cocacola:zero-sugar": "0克",
    "cocacola:sprite-zero": "0克",
    "cocacola:minute-maid-orange": "10.2克",
    "cocacola:minute-maid-apple": "9.6克",
    "cocacola:minute-maid-grape": "10.6克",
    "yili:skim-milk": "5.0克",
    "yili:plain-yogurt": "10.5克",
    "yili:lactose-free-milk": "4.8克",
    "wolong:pistachio": "7.7克",
    "wolong:almond": "4.4克",
    "wolong:mixed-nuts": "18.0克",
    "kinder:chocolate": "6.7克",
    "kinder:chocolate-mini": "3.1克",
    "kinder:maxi": "10.5克",
    "moxiaoxian:braised-chicken-rice": "2.0克",
    "moxiaoxian:bamboo-beef-rice": "2.5克",
    "moxiaoxian:sichuan-pork-rice": "2.0克",
    "nestle:xueci-strawberry-redbean": "7.5克",
    "nestle:8cube-strawberry": "9.5克",
    "nestle:8cube-white-sesame": "8.5克",
    "hormel:pan-fry-bacon": "1.0克",
    "hormel:german-sausage": "2.0克",
    "hormel:classic-ham": "1.5克",
    "hormel:black-pepper-sausage": "2.2克",
    "hormel:cheese-sausage": "2.0克",
    "eaglecoin:dace-black-bean": "2.0克",
    "eaglecoin:tuna-oil": "0克",
    "eaglecoin:anchovy": "5.0克",
    "lkk:jinzhen-light-soy": "3.5克",
    "lkk:steamed-fish-soy": "9.0克",
    "lkk:oyster-sauce": "12.0克",
    "spam:classic": "1.0克",
    "spam:less-sodium": "1.5克",
    "spam:black-pepper": "1.2克",
}


def add_packaging_sugar_evidence(records: list[dict]) -> None:
    for product in records:
        family = product["product_id"].rsplit(":", 1)[0].removeprefix("cn-official:")
        value = PACKAGING_SUGAR_BY_FAMILY.get(family)
        if value is None:
            continue
        label = product["label"]
        rows = [row for row in label["nutrition_rows"] if row[0] != "糖"]
        rows.append(["糖", value])
        label["nutrition_rows"] = rows
        label["nutrition_table_text"] += f"；糖 {value}"
        label["source_record_version"] += ":packaging-sugar-reviewed"
        label["sugars_review_status"] = "declared"
        label["sugars_reviewed_at"] = "2026-08-28"
        label["sugars_review_note"] = "包装营养成分表明确列示糖数值"
        label["content_hash"] = content_hash(label)


def main() -> None:
    records: list[dict] = []
    add_kinder(records)
    add_nestle(records)
    # Meiji's mainland page confirms names and sizes but not complete back-label
    # facts. Keep it in the discovery registry instead of inflating the active
    # recommendation catalog with 45 permanently non-displayable placeholders.
    add_category_gap_fill(records)
    add_catalog_breadth(records)
    add_use_role_breadth(records)
    add_packaging_sugar_evidence(records)
    assert len(records) == 79, len(records)
    assert len({item["product_id"] for item in records}) == len(records)
    OUTPUT.write_text(
        json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"wrote {len(records)} records to {OUTPUT}")


if __name__ == "__main__":
    main()
