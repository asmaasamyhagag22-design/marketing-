"""ABSA aspect taxonomy — CONFIG keyed by the universal category signal with a universal
default (D-8). Arabic-first labels with English keys; extend per category, never in logic."""
from __future__ import annotations

_UNIVERSAL: list[dict] = [
    {"aspect": "service_quality", "ar": "جودة الخدمة", "en": "service quality"},
    {"aspect": "staff", "ar": "المعاملة/الموظفون", "en": "staff & treatment"},
    {"aspect": "price_value", "ar": "السعر مقابل القيمة", "en": "price/value"},
    {"aspect": "waiting_time", "ar": "الانتظار/الالتزام بالمواعيد", "en": "waiting time"},
    {"aspect": "cleanliness_place", "ar": "النظافة/المكان", "en": "cleanliness & place"},
    {"aspect": "communication", "ar": "التواصل/الرد", "en": "communication"},
]

_BY_CATEGORY: dict[str, list[dict]] = {
    "clinic": _UNIVERSAL + [
        {"aspect": "doctor_competence", "ar": "كفاءة الطبيب", "en": "doctor competence"},
        {"aspect": "results_outcome", "ar": "النتيجة العلاجية", "en": "treatment outcome"},
        {"aspect": "booking", "ar": "سهولة الحجز", "en": "booking ease"},
    ],
    "hospital": _UNIVERSAL + [
        {"aspect": "doctor_competence", "ar": "كفاءة الأطباء", "en": "doctor competence"},
        {"aspect": "emergency", "ar": "الطوارئ", "en": "emergency"},
        {"aspect": "nursing", "ar": "التمريض", "en": "nursing"},
    ],
    "restaurant": _UNIVERSAL + [
        {"aspect": "food_quality", "ar": "جودة الأكل/الطعم", "en": "food quality & taste"},
        {"aspect": "portion", "ar": "الكمية", "en": "portion size"},
        {"aspect": "delivery", "ar": "التوصيل", "en": "delivery"},
    ],
    "ecommerce": _UNIVERSAL + [
        {"aspect": "product_quality", "ar": "جودة المنتج", "en": "product quality"},
        {"aspect": "shipping", "ar": "الشحن والتغليف", "en": "shipping & packaging"},
        {"aspect": "returns", "ar": "الاسترجاع", "en": "returns"},
    ],
    "education": _UNIVERSAL + [
        {"aspect": "instructor", "ar": "المدرب/المحاضر", "en": "instructor"},
        {"aspect": "content_quality", "ar": "جودة المحتوى", "en": "content quality"},
        {"aspect": "certification", "ar": "الشهادة/الاعتماد", "en": "certification"},
    ],
}


def aspects_for(category: str | None) -> list[dict]:
    """The labeling taxonomy for a category — universal default when unknown."""
    return list(_BY_CATEGORY.get((category or "").strip().lower(), _UNIVERSAL))
