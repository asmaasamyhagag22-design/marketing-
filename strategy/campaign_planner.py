"""Bounded public research and conservative compilation for campaign briefs."""
from collections import Counter
from hashlib import sha256
import re
import unicodedata
from urllib.error import HTTPError
from urllib.parse import urldefrag, urlsplit
from time import monotonic

from pydantic import Field

from scraper.extractors.links import extract_links_from_html
from strategy.campaign_package import Brief, Input, Source, digest, proposal, public_soup, valid_source_url
from strategy.campaign_research import ResearchGap, same_source
from strategy.campaign_v2 import CampaignConflict
from strategy.campaign_copy import CopyEdit, plan_copy, validate_copy, writing_for


PAGE_LIMIT = 4
SECONDS = 12.0
POLICY = "source-campaign-planner@1"
STOP = set("""increase grow drive boost get for from about the and into with people visit visits
explanation clicks click catalog page more a an to of in find want interested concerned
using use explain how what who discover build builds download downloads install
book bookings purchase purchases orders buy sale prices price boost awareness
زيادة زيارات زيارة رفع عن إلى في على من جذب صفحة مزيد المستخدمين عملاء جمهور شرح
تحميل تنزيل تثبيت شراء حجز أسعار سعر خصم عروض""".split())
PATTERNS = {
    "DOWNLOAD": r"\b(downloads?|install(?:s|ation)?)\b|تحميل|تنزيل|تثبيت",
    "OFFER": r"\b(discounts?|offers?|prices?|sales?|promo(?:tion)?)\b|سعر|أسعار|خصم|عرض",
    "TRANSACTION": r"\b(bookings?|reserve|reservations?|buy|purchases?|orders?|tickets?|sign.?ups?|donations?)\b|حجز|شراء|طلب|تذاكر|تبرع|اشتراك",
}
UNSAFE_URL = re.compile(r"login|logout|cart|checkout|register|signup|unsubscribe|account|(?:^|/)api(?:/|$)", re.I)
CONFLICT_SIGNAL = re.compile(
    r"\b(?:no longer|discontinued|not available|unavailable|does not support|temporarily suspended)\b"
    r"|لم يعد|غير متاح|توقف دعم", re.I,
)
CONDITIONAL = re.compile(
    r"[$€£]|\b(?:USD|EUR|EGP|GBP|AED|SAR|only|except|until|availability|offer|eligible|trial)\b"
    r"|فقط|حتى|سعر|خصم|عرض|فرع", re.I,
)


class PlanInput(Input):
    url: str = Field(min_length=10, max_length=500)
    objective: str = Field(min_length=8, max_length=200)
    language: str = Field(pattern=r"^(ar|en)(?:-[A-Za-z0-9]{2,8}){0,2}$")


class BriefReview(Input):
    audience: str = Field(min_length=4, max_length=200)
    tone: str = Field(min_length=2, max_length=75)
    selected: int = Field(ge=0, le=2)
    copy_edit: CopyEdit | None = None


def words(text):
    tokens = set(re.findall(r"[^\W_]+", unicodedata.normalize("NFKC", text).casefold())) - STOP
    return {re.sub(r"(?:ers?|ing|s)$", "", word) if re.fullmatch(r"[a-z]{4,}(?:ers?|ing|s)", word)
            else word for word in tokens}


def clean(text):
    return " ".join(text.split())


def goal_kind(objective):
    return next((kind for kind, pattern in PATTERNS.items() if re.search(pattern, objective, re.I)), "DISCOVERY")


def public_link(url, root):
    parts = urlsplit(url)
    return valid_source_url(url) and same_source(url, root) and not UNSAFE_URL.search(parts.path)


def inspect(page, clock, terms):
    soup = public_soup(page.body)
    body = soup.body
    if body is None:
        raise ResearchGap("SOURCE_TEXT_MISSING")
    text_hash = digest(clean(body.get_text(" ", strip=True)))
    heading = ""
    entries = []
    title = clean(soup.title.get_text(" ", strip=True))[:180] if soup.title else ""
    for node in (body.select_one("main") or body).select("h1,h2,h3,h4,p"):
        if node.find_parent(["header", "nav", "footer", "aside"]):
            continue
        text = clean(node.get_text(" ", strip=True))
        if node.name != "p":
            heading = text
            continue
        if not 3 <= len(heading) <= 75 or not 30 <= len(text) <= 1600:
            continue
        for sentence in re.split(r"(?<=[.!?؟])\s+", text):
            if not 30 <= len(sentence) <= 180 or re.match(r"^(?:just|simply)\b", sentence, re.I):
                continue
            score = len(words(sentence) & terms) + 2 * len(words(heading) & terms)
            if score:
                entries.append({"label": heading, "quote": sentence, "context": text, "score": score})
    # Retain short passages from every fetched source for the one-shot comparison.
    counts = Counter(word for entry in entries for word in words(entry["quote"]) & terms)
    for entry in entries:
        entry["specificity"] = round(sum(1 / counts[word] for word in words(entry["quote"]) & terms), 3)
    entries.sort(key=lambda entry: (-entry["specificity"], -entry["score"]))
    return {
        "page_url": page.url, "capture_kind": page.source_kind, "captured_at": clock().isoformat(),
        "body_sha256": sha256(page.body).hexdigest(), "text_sha256": text_hash, "title": title,
        "entries": entries[:8],
    }


def rank_links(page, root, terms, visited, *, action=False):
    candidates = {}
    for link in extract_links_from_html(page.body.decode("utf-8", errors="replace"), page.url, root):
        url = urldefrag(link.href)[0]
        if len(url) > 500 or url in visited or not public_link(url, root):
            continue
        parts = urlsplit(url)
        anchor = link.anchor_text
        is_download = bool(re.search(r"\bdownload\b|تحميل|تنزيل", anchor, re.I))
        score = 3 * len(words(parts.path) & terms) + 2 * len(words(anchor) & terms)
        score -= 5 if parts.query else 0
        if action and is_download and re.search(r"/(?:download|downloads)(?:/|$)", parts.path, re.I):
            score += 20
        if score > candidates.get(url, (0, ""))[0]:
            candidates[url] = (score, anchor)
    return sorted(candidates.items(), key=lambda entry: (-entry[1][0], len(entry[0]), entry[0]))


def best_fact(pages, terms):
    candidates = [(page, item) for page in pages for item in page["entries"] if item["score"] >= 2]
    candidates = [(page, item) for page, item in candidates
                  if words(item["quote"]) & terms and not CONDITIONAL.search(item["context"])
                  and not CONFLICT_SIGNAL.search(item["quote"])]
    if not candidates:
        return None
    page, entry = max(candidates, key=lambda pair: (
        len(words(urlsplit(pair[0]["page_url"]).path) & terms),
        len(words(pair[1]["label"]) & terms),
        pair[1]["specificity"],
        len(words(pair[1]["quote"]) & words(pair[1]["label"]) & terms), pair[1]["score"],
        not bool(urlsplit(pair[0]["page_url"]).query), -len(pair[1]["quote"]),
    ))
    return {**{k: v for k, v in page.items() if k != "entries"}, **entry,
            "scope": entry["label"], "outcome": "QUOTE_OBSERVED",
            "constraints": {"basis": "FULL_SOURCE_CONTEXT", "page_path": urlsplit(page["page_url"]).path,
                            "price": None, "branch": None, "valid_until": None,
                            "market": "UNCONFIRMED"}}


def conflicting_evidence(fact, pages):
    if not fact:
        return []
    subject = words(fact["label"])
    if not subject:
        return []
    return [
        {"page_url": page["page_url"], "captured_at": page["captured_at"],
         "quote": entry["quote"], "context": entry["context"]}
        for page in pages for entry in page["entries"]
        if CONFLICT_SIGNAL.search(entry["quote"])
        and subject <= words(entry["label"] + " " + entry["quote"])
    ]


def question(kind, arabic):
    questions = {
        "DISCOVERY": ("أين يشرح الموقع الميزة المرتبطة بالهدف؟", "Which brand page describes the feature in the goal?"),
        "DOWNLOAD": ("أين شرح الميزة ورابط التنزيل المباشر المعتمد؟", "Where are the feature explanation and official download destination?"),
        "OFFER": ("أين الشروط المنشورة للسعر والمنطقة والصلاحية؟", "Where are the published price, market and validity terms?"),
        "TRANSACTION": ("أين رابط الإجراء وشروط الإتاحة للعميل؟", "Where is the action page with its eligibility and terms?"),
    }
    return questions[kind][not arabic]


def research_plan(request, load, clock):
    started = monotonic()
    kind = goal_kind(request.objective)
    terms = words(request.objective)
    arabic = request.language.split("-")[0] == "ar"
    pages, trace, visited, links, action_links = [], [], set(), {}, {}
    url, reason, anchor = request.url, "BRAND_ENTRY", ""
    destination = None
    while url and len(visited) < PAGE_LIMIT and monotonic() - started < SECONDS:
        visited.add(url)
        step = {"page_url": url, "reason": reason, "anchor": anchor, "outcome": "SOURCE_UNAVAILABLE"}
        trace.append(step)
        try:
            page = load(url, min(5.0, max(.05, SECONDS - (monotonic() - started))))
            if page.url != url:
                raise ResearchGap("SOURCE_URL_CHANGED")
            captured = inspect(page, clock, terms)
            pages.append(captured)
            step["outcome"] = "SOURCE_READ"
            step["candidate_count"] = len(captured["entries"])
            for link, score in rank_links(page, request.url, terms, visited):
                if link not in links or links[link][0] < score[0]:
                    links[link] = score
            if kind == "DOWNLOAD":
                for link, score in rank_links(page, request.url, terms, visited, action=True):
                    if score[0] >= 20:
                        action_links[link] = score
                if reason == "ACTION_DESTINATION" and re.search(r"download|تحميل|تنزيل", captured["title"], re.I):
                    destination = {k: v for k, v in captured.items() if k != "entries"}
                    destination.update(quote=captured["title"], context=captured["title"],
                                       scope="OFFICIAL_DESTINATION_TITLE", outcome="QUOTE_OBSERVED",
                                       anchor=anchor)
        except HTTPError as exc:
            step["outcome"] = "SOURCE_REDIRECT" if 300 <= exc.code < 400 else "SOURCE_UNAVAILABLE"
            step["http_status"] = exc.code
        except (OSError, ResearchGap) as exc:
            step["outcome"] = str(exc) if isinstance(exc, ResearchGap) else "SOURCE_UNAVAILABLE"
        fact = best_fact(pages, terms)
        conflicts = conflicting_evidence(fact, pages)
        step["gap_after"] = "SOURCE_CONFLICT" if conflicts else "FEATURE_EVIDENCE" if fact is None else (
            "ACTION_DESTINATION" if kind == "DOWNLOAD" and not destination else
            "COMMERCIAL_TERMS" if kind in {"OFFER", "TRANSACTION"} else None)
        pending = {k: v for k, v in links.items() if k not in visited}
        actions = {k: v for k, v in action_links.items() if k not in visited}
        if conflicts:
            break
        if kind == "DOWNLOAD" and fact and not destination and actions:
            pending, reason = actions, "ACTION_DESTINATION"
        elif fact and kind in {"DISCOVERY", "DOWNLOAD"}:
            # A more specific discovered page may answer the same question directly.
            specificity = len(words(urlsplit(fact["page_url"]).path) & terms)
            pending = {k: v for k, v in pending.items() if len(words(urlsplit(k).path) & terms) > specificity and not urlsplit(k).query}
            reason = "MORE_SPECIFIC_FEATURE"
        else:
            reason = "FIND_COMMERCIAL_TERMS" if kind in {"OFFER", "TRANSACTION"} else "FILL_FEATURE_GAP"
        url = max(pending, key=lambda key: (pending[key][0], not bool(urlsplit(key).query), -len(key)), default=None)
        anchor = pending[url][1] if url else ""
    fact = best_fact(pages, terms)
    gap = trace[-1]["gap_after"] if trace else "FEATURE_EVIDENCE"
    if fact and kind == "DOWNLOAD" and not destination and gap != "SOURCE_CONFLICT":
        gap = "ACTION_DESTINATION"
    if kind in {"OFFER", "TRANSACTION"} and gap != "SOURCE_CONFLICT":
        gap = "COMMERCIAL_TERMS"
    missing = {
        "SOURCE_CONFLICT": ("أي مصدر رسمي يوضح حالة الميزة الحالية؟", "Which official source confirms whether the feature is currently available?"),
        "FEATURE_EVIDENCE": ("أدخل رابط الصفحة الرسمية التي تشرح الميزة المطلوبة.", "Provide the official page explaining the feature in the goal."),
        "ACTION_DESTINATION": ("ما رابط صفحة التنزيل الرسمية التي تريد توجيه الجمهور إليها؟", "Which official download information page should the campaign link to?"),
        "COMMERCIAL_TERMS": ("ما الصفحة الرسمية التي تثبت شروط الإجراء والسعر إن وجد والنطاق والصلاحية؟", "Which official page confirms eligibility, price if relevant, market and validity?"),
    }
    plan = {
        "policy": POLICY, "input": request.model_dump(mode="json"), "intent": kind,
        "question": question(kind, arabic), "trace": trace, "pages": pages,
        "conflicts": conflicting_evidence(fact, pages),
        "gap": gap, "missing_question": missing[gap][not arabic] if gap else None,
        "stop": "SOURCE_CONFLICT" if gap == "SOURCE_CONFLICT" else "DECISION_EVIDENCE_FOUND" if not gap else
                "BUDGET_EXHAUSTED" if len(visited) >= PAGE_LIMIT or monotonic() - started >= SECONDS
                else "NO_MORE_RELEVANT_SOURCES",
        "page_calls": len(trace), "elapsed_ms": round((monotonic() - started) * 1000, 2),
        "provider_calls": 0, "cost_usd": 0, "brief_reviewed": False,
        "opportunity_hypothesis": (
            "اختبر هل ربط الميزة بالخطوة المطلوبة يرفع معدل النقر من الشريحة المقترحة."
            if arabic else "Test whether connecting the feature to a specific action improves clicks from the proposed audience."
        ),
    }
    return plan, fact, destination


def draft_brief(request, fact, destination):
    arabic = request.language.split("-")[0] == "ar"
    language_index = not arabic
    label = fact["label"]
    terms = words(request.objective)
    heading_is_specific = len(words(label) & terms) >= 2
    proof = fact["quote"]
    guide = fact["page_url"]
    options = [
        {
            "action": "READ_FEATURE", "destination": guide, "evidence_index": 0,
            "name": ("شرح الميزة", "Explain the feature")[language_index],
            "audience": ("مهتمون يريدون فهم الميزة قبل اتخاذ قرار.", "People who want to understand the feature before acting.")[language_index],
            "message": ("ابدأ باسم الميزة ووجّه القارئ إلى شرحها الرسمي.", "Lead with the feature name and link to the publisher’s explanation.")[language_index],
            "headline": ("افهم الميزة أولًا", "Start with the feature")[language_index],
            "cta": ("اقرأ الشرح", "Read the explanation")[language_index],
            "metric": ("النقرات إلى الشرح لكل ظهور.", "Explanation clicks per impression.")[language_index],
            "tradeoff": ("يقلّل خطوة البحث للقارئ ويترك التقييم له.", "Shortens the path to the explanation and leaves the decision to the reader.")[language_index],
            "theme": "cobalt",
        },
        {
            "action": "COMPARE_FIT", "destination": guide, "evidence_index": 0,
            "name": ("قيّم الملاءمة", "Evaluate the fit")[language_index],
            "audience": ("أشخاص يقارنون بدائل ويحتاجون مراجعة التفاصيل.", "People comparing alternatives who need to inspect the details.")[language_index],
            "message": ("اطرح سؤال ملاءمة. استخدم شرح الناشر كنقطة للمقارنة.", "Ask a fit question. Use the publisher’s explanation as one input to a comparison.")[language_index],
            "headline": ("هل تناسب احتياجك؟", "Would it fit your needs?")[language_index],
            "cta": ("راجع تفاصيل الميزة", "Review the details")[language_index],
            "metric": ("زيارات صفحة الشرح بعد النقر على سؤال المقارنة.", "Visits to the explanation from the comparison creative.")[language_index],
            "tradeoff": ("يخدم مرحلة الاختيار ويحتاج بيانات قبل ادعاء تفوّق.", "Supports evaluation and would need comparative evidence for any superiority claim.")[language_index],
            "theme": "forest",
        },
        {
            "action": "DOWNLOAD_OPTIONS" if destination else "EXPLORE_TOPIC",
            "destination": destination["page_url"] if destination else guide,
            "evidence_index": 1 if destination else 0,
            "name": (("اختيار التنزيل", "Choose a download") if destination else ("استكشاف الموضوع", "Explore the topic"))[language_index],
            "audience": (("مهتمون وصلوا لمرحلة اختيار نسخة للتنزيل.", "People ready to choose a download option.") if destination else
                         ("جمهور في مرحلة الاستكشاف الأولي.", "People at the start of discovery."))[language_index],
            "message": (("وجّه المهتم إلى خيارات التنزيل الرسمية.", "Direct interested readers to official download options.") if destination else
                         ("قدّم اسم الموضوع كمدخل للقراءة المفتوحة.", "Use the topic name as an entry point for open-ended reading."))[language_index],
            "headline": (("اختر نسخة التنزيل", "Choose a download option") if destination else
                         ("من أين تبدأ؟", "Where would you start?"))[language_index],
            "cta": (("اعرض خيارات التنزيل", "View download options") if destination else
                    ("افتح صفحة الموضوع", "Explore the topic page"))[language_index],
            "metric": (("نقرات خيارات التنزيل، والتثبيت عند توفر رصد.", "Download-options clicks and installs when observable.") if destination else
                       ("النقرات من مادة الاستكشاف إلى صفحة الموضوع.", "Topic-page clicks from the discovery creative."))[language_index],
            "tradeoff": (("أقرب للتنزيل، ويحتاج رصد التثبيت لقياس النتيجة.", "Closer to download, with separate instrumentation needed for installation.") if destination else
                         ("أوسع في الاستكشاف ويستخدم نفس صفحة الشرح.", "Broader discovery with the same explanation page as the destination."))[language_index],
            "theme": "ember",
        },
    ]
    selected = 2 if destination else 0
    directions = []
    for option, writing in zip(options, plan_copy(fact, options, request.language)):
        title = option["headline"]
        if option["action"] == "READ_FEATURE" and heading_is_specific and len(label) <= 55:
            title = label
        if not arabic and len(proof) <= 105:
            card_message = proof
        else:
            card_message = label
        if title == card_message:
            card_message = ("الدليل والشرح من موقع البراند.", "The publisher explains the feature.")[language_index]
        caption = f"{title.rstrip('.?!؟')} — {card_message.rstrip('.?!؟')}. {option['cta']}."
        if arabic:
            caption = f"{title.rstrip('.?!؟')} · {card_message.rstrip('.?!؟')}. {option['cta']}."
        if writing:
            title, card_message, caption = writing.headline, writing.message, writing.caption
            option["cta"] = writing.cta
            option["concept"] = writing.concept
            if option["action"] == "COMPARE_FIT":
                title = ("إيه اللي يهمّك في الاختيار؟" if arabic else "What matters in the comparison?")
                caption = f"{title} {writing.caption}"
            elif option["action"] == "EXPLORE_TOPIC":
                title = ("ابدأ بسؤال" if arabic else "Start with a question")
                caption = f"{title} · {writing.caption}"
        directions.append({
            "name": option["name"], "rationale": option["message"], "headline": title,
            "message": card_message, "cta": option["cta"], "theme": option["theme"], "caption": caption,
            "hook": title, "shot": ("يظهر سؤال الحملة فوق شكل هندسي بسيط.", "Reveal the campaign prompt over a simple geometric motif.")[language_index],
            "middle_shot": ("يظهر اسم الميزة وتظل الخلفية ثابتة.", "Reveal the topic label and hold the background still.")[language_index],
            "end_shot": ("تظهر بطاقة باسم البراند والدعوة.", "End on the brand name and exact call to action.")[language_index],
        })
    chosen = options[selected]
    assumption = ("الجمهور فرضية تحريرية. نختبر هل اهتمامه بالميزة يدفعه للنقر.",
                  "The audience is a working hypothesis. Test whether interest in the feature drives the intended click.")[language_index]
    reason = (("وجد البحث صفحة رسمية لخيارات التنزيل. لو تغيّرت الوجهة أو فقدنا شرح الميزة، أعد القرار.",
               "Research found an official download-options page. Reopen the choice if the destination or feature evidence changes.") if destination else
              ("الهدف زيارة شرح محدد. لو اختفى شرح الميزة أو تغيّر الهدف لإجراء، أعد البحث عن الوجهة.",
               "The goal is a visit to a specific explanation. Reopen the choice if it disappears or the goal changes to an action."))[language_index]
    brief = Brief.model_validate({
        "summary": fact["quote"], "audience": chosen["audience"],
        "market": ("نطاق السوق يحتاج تأكيدًا قبل النشر.", "Confirm market scope before publishing.")[language_index],
        "source": Source(url=guide, quote=fact["quote"], scope=fact["scope"]),
        "objective": request.objective, "metric": chosen["metric"], "assumption": assumption,
        "alternatives": [{"name": item["name"], "plan": item["message"], "tradeoff": item["tradeoff"]}
                         for item in options],
        "strategy_index": selected, "strategy_reason": reason,
        "tone": ("واضحة وهادئة", "Plain and concise")[language_index], "directions": directions,
        "selected": selected, "human_review": [
            ("راجع الاسم الأصلي للميزة واللغة ونطاق المصدر والحقوق.", "Review the original feature label, language, source scope and rights.")[language_index],
            ("راجع الوجهة على الموبايل ووسيلة قياس النتيجة.", "Check the destination on mobile and confirm the conversion measurement.")[language_index],
        ],
        "language": request.language, "direction": "rtl" if arabic else "ltr",
    })
    return brief, options


def build_plan(request, brand_name, load, clock, *, request_id=None):
    planner, fact, destination = research_plan(request, load, clock)
    planner["request_id"] = request_id
    if planner["gap"]:
        return proposal(None, brand_name, [fact] if fact else [], planner=planner)
    brief, options = draft_brief(request, fact, destination)
    sources = [fact] + ([destination] if destination else [])
    planner.update(options=options, claims=[
        {"fields": ["brief.summary", "package.copy.message"], "evidence_index": 0,
         "basis": "PUBLISHER_QUOTE_AND_SECTION_LABEL", "semantic_review": "HUMAN_REVIEW_REQUIRED"},
    ])
    return proposal(brief, brand_name, sources, planner=planner)


def anchored_claim(previous, field, text):
    if field == "brief.summary":
        return text == previous["evidence"][0]["quote"]
    if field == "package.copy.message":
        evidence = previous["evidence"][0]
        return text in {evidence["quote"], evidence["label"],
                        "الدليل والشرح من موقع البراند.", "The publisher explains the feature."}
    return False


def review_draft(previous, edit):
    planner = {**previous["planner"], "brief_reviewed": True, "request_id": None}
    brief = Brief.model_validate(previous["brief"])
    option = planner["options"][edit.selected]
    directions = list(brief.directions)
    if edit.copy_edit:
        writing = writing_for(previous["evidence"][0], option["action"], brief.language)
        directions[edit.selected] = validate_copy(directions[edit.selected], edit.copy_edit, writing)
    revised = brief.model_copy(update={
        "audience": edit.audience, "tone": edit.tone, "selected": edit.selected,
        "directions": tuple(directions),
        "strategy_index": edit.selected, "metric": option["metric"],
        "strategy_reason": brief.strategy_reason if brief.strategy_index == edit.selected else (
            "اختار المراجع هذا البديل ضمن نفس البحث." if brief.direction == "rtl"
            else "The reviewer selected this alternative using the same research."
        ),
    })
    changes = [{"field": key, "before": getattr(brief, key), "after": getattr(revised, key)}
               for key in ("audience", "tone", "selected") if getattr(brief, key) != getattr(revised, key)]
    if directions[edit.selected] != brief.directions[edit.selected]:
        changes.append({"field": "copy", "before": brief.directions[edit.selected].message,
                        "after": directions[edit.selected].message})
    result = proposal(revised, previous["brand_name"], previous["evidence"], changes=changes, planner=planner)
    message = result["package"]["copy"]["message"]
    writing = writing_for(previous["evidence"][0], option["action"], brief.language)
    licensed = writing and writing.license("message", message)
    if not anchored_claim(result, "brief.summary", revised.summary) or (
        not anchored_claim(result, "package.copy.message", message) and not licensed
    ):
        raise CampaignConflict("CLAIM_EXCEEDS_SOURCE")
    return result


def refresh_plan(previous, load, clock):
    request = PlanInput.model_validate(previous["planner"]["input"])
    updated = build_plan(request, previous["brand_name"], load, clock)
    old = {(item["page_url"], item["text_sha256"]) for item in previous["planner"]["pages"]}
    new = {(item["page_url"], item["text_sha256"]) for item in updated["planner"]["pages"]}
    from strategy.campaign_package import check

    if old == new and previous["planner"]["gap"] == updated["planner"]["gap"] and check(previous, clock()) in (
        None, "BRIEF_REVIEW_REQUIRED",
    ):
        return None
    updated["changes"] = [{"field": "research", "before": previous["planner"]["stop"],
                           "after": updated["planner"]["stop"], "changed_pages": sorted({url for url, _ in old ^ new})}]
    updated["sha256"] = digest({key: value for key, value in updated.items() if key != "sha256"})
    return updated
