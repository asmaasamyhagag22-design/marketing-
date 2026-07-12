"""U8c labeling kit — makes the OWNER's labeling task start-able the moment real reviews
exist (zero network here). `build_labeling_file(reviews, category, out_path)` writes a
100-row JSONL where each row = one review + the category's aspect sheet + empty label slots;
`write_guide(out_dir)` drops the one-page guide."""
from __future__ import annotations

import json
from pathlib import Path

from .schemas import Review
from .taxonomy import aspects_for

GUIDE = """# دليل التوسيم — سطر لكل ريفيو (5-10 ثواني للسطر)
1) اقرئي `text`. 2) لكل جانب (aspect) ذُكر فعلًا في الكلام: أضيفي عنصرًا في `labels`
   بالشكل {"aspect": "<key من الورقة>", "sentiment": "pos|neg|neu",
   "evidence_quote": "<قصّي الجملة الحرفية من النص>"} —
   الاقتباس لازم يكون substring حرفي من `text` (الفاليديتور بيرفض غير كده).
3) جانب لم يُذكر = لا تضيفيه (ممنوع الاستنتاج). 4) سخرية/مدح مبطّن: احكمي بالمقصود.
5) لو الريفيو كله عام ("ممتاز") بلا جانب محدد: labels=[{"aspect":"service_quality",...}].
6) شكّ؟ اتركي `labels` فاضية وحطي "؟" في `note` — بنراجعها سويًا.
"""


def build_labeling_file(reviews: list[Review], category: str | None, out_path: str | Path,
                        sample_size: int = 100) -> Path:
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet = aspects_for(category)
    with open(out, "w", encoding="utf-8") as f:
        f.write(json.dumps({"_aspect_sheet": sheet, "_category": category or "default",
                            "_instructions": "see LABELING_GUIDE.md"}, ensure_ascii=False) + "\n")
        for i, r in enumerate(reviews[:sample_size]):
            f.write(json.dumps({
                "review_id": f"{r.source}:{r.author_hash}:{i}",
                "lang": r.lang, "rating": r.rating, "text": r.text,
                "labels": [], "note": "",
            }, ensure_ascii=False) + "\n")
    return out


def write_guide(out_dir: str | Path) -> Path:
    p = Path(out_dir) / "LABELING_GUIDE.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(GUIDE, encoding="utf-8")
    return p
