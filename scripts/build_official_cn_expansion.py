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


def nutrition_rows(basis: str, values: tuple[str, str, str, str, str]) -> list[list[str]]:
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
) -> None:
    rows = nutrition_rows(basis, nutrition)
    for variant_id, display_name in variants:
        label = {
            "evidence_id": f"official.{family_id}.{variant_id}.label.{REVIEWED_ON}",
            "ingredients_text": ingredients,
            "allergen_statement": allergen,
            "nutrition_table_text": nutrition_text(basis, nutrition),
            "nutrition_basis_text": basis,
            "nutrition_rows": rows,
            "confirmed_by": "human_review",
            "confirmed_at": REVIEWED_ON,
            "valid_through": VALID_THROUGH,
            "source_url": source_url,
            "evidence_quality": "complete",
            "source_provider": source_provider,
            "source_type": "official_product_page",
            "source_verified_at": REVIEWED_ON,
            "source_language": "zh-CN",
            "source_access_region": "CN",
            "source_record_version": f"page-review-{REVIEWED_ON}:{variant_id}",
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
    for family_id, variant, name, url, use_case, ingredients, allergen, basis, values in entries:
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
        ("牛奶巧克力", "65g"), ("特浓牛奶巧克力", "65g"),
        ("黑巧克力50%", "65g"), ("特纯黑巧克力60%", "65g"),
        ("超纯黑巧克力70%", "65g"), ("草莓巧克力", "65g"),
        ("牛奶巧克力", "75g"), ("特浓牛奶巧克力", "75g"),
        ("黑巧克力50%", "75g"), ("特纯黑巧克力60%", "75g"),
        ("超纯黑巧克力70%", "75g"), ("草莓巧克力", "75g"),
        ("雪吻巧克力可可口味", "55g"), ("雪吻巧克力抹茶口味", "55g"),
        ("雪吻巧克力草莓口味", "55g"), ("雪吻巧克力牛奶口味", "55g"),
        ("雪吻巧克力柚子口味", "55g"), ("雪吻巧克力意式榛果巴旦木口味", "55g"),
        ("雪吻巧克力可可口味", "29g"), ("雪吻巧克力抹茶口味", "29g"),
        ("雪吻巧克力草莓口味", "29g"), ("雪吻巧克力牛奶口味", "29g"),
        ("雪吻巧克力柚子口味", "29g"), ("雪吻巧克力意式榛果巴旦木口味", "29g"),
        ("澳洲坚果夹心巧克力", "58g"), ("澳洲坚果夹心黑巧克力", "58g"),
        ("澳洲坚果夹心巧克力龙井口味", "58g"),
        ("澳洲坚果夹心巧克力桂花乌龙口味", "58g"),
        ("巴旦木夹心巧克力", "80g"), ("巴旦木夹心黑巧克力", "80g"),
        ("巴旦木夹心巧克力脆脆燕麦味", "66g"),
        ("巴旦木夹心黑巧克力脆脆燕麦味", "66g"),
        ("橡皮糖巧克力青提味", "50g"), ("橡皮糖巧克力草莓味", "50g"),
        ("橡皮糖巧克力水蜜桃酸奶味", "50g"), ("橡皮糖巧克力芒果味", "50g"),
        ("巧克娃娃巧克力", "50g"), ("幻彩巧克力", "50g"),
        ("巧克娃娃巧克力", "8g"), ("幻彩巧克力", "8g"),
        ("香蕉巧克力", "8g"), ("橡皮糖巧克力青提味", "8g"),
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


def main() -> None:
    records: list[dict] = []
    add_kinder(records)
    add_nestle(records)
    add_meiji_review_queue(records)
    assert len(records) == 86, len(records)
    assert len({item["product_id"] for item in records}) == len(records)
    OUTPUT.write_text(
        json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"wrote {len(records)} records to {OUTPUT}")


if __name__ == "__main__":
    main()
