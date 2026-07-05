"""Configuration constants for the scraper.

All tunable values live here. No magic numbers in the rest of the code.
"""

# --- Scrape budget --------------------------------------------------
# MEASURED (2026-06-15, 32 saved sites): the 60s wall was the BINDING constraint on
# 21/32 sites — they hit it after only 1-7 subpages (JS pages render ~15s each), so
# the page cap of 7 was almost never reached and content-rich sites (median 17 HIGH
# pages) were badly under-covered. The LLM evidence pack is char-capped, so more
# pages cost crawl TIME only, not tokens. Raised for solid coverage; a slow site now
# takes ~2.5 min instead of ~1 min. Tune down for speed-over-coverage.
TOTAL_BUDGET_SECONDS = 150
MAX_INTERNAL_PAGES = 12  # in addition to homepage

# Adaptive crawl budget for E-COMMERCE (Pillar 1). MEASURED (benchmark/measure_ecom_*.py): a
# store discovers 100-300+ internal pages but the default 12-page / 150s budget reaches only
# ~12 of them (azzafahmy fresh scrape: 12 pages / 4% coverage) — AND the page cap and the time
# budget now bind at roughly the SAME point (~13 pages at ~11s/page render), so raising the
# page cap ALONE is a no-op; a store needs BOTH a higher cap AND a proportionally larger time
# budget. Triggered UNIVERSALLY when the homepage links + sitemap reveal many product-type URLs
# (a SIGNAL via the page-type classifier — never a vertical or a hardcoded name). A store scrape
# then takes ~5-6 min; per-page render-speed work is the follow-up to bring that down.
ECOMMERCE_MAX_INTERNAL_PAGES = 30
ECOMMERCE_BUDGET_SECONDS = 330        # ~30 pages at ~11s/page (cap and time bind together)
ECOMMERCE_PRODUCT_URL_MIN = 15        # >= this many PRODUCTS-type URLs (homepage+sitemap) -> store

# A crawl must NEVER end homepage-only when internal links exist: pre-crawl stages
# (dead sitemaps, a heavy homepage) can eat the whole time budget, and a budget check
# firing at subpage #1 produced a 1-page scrape of a 300-link store (measured on
# nahdionline.com -> no product pages -> "no prices" downstream). The budget guard is
# for stopping a long tail, not preventing the start.
MIN_SUBPAGE_ATTEMPTS = 5

PAGE_TIMEOUT_MS = 20_000
NAV_TIMEOUT_MS = 25_000
INTER_PAGE_DELAY_SECONDS = 1.0

# --- Fetch retry (Tier 0 resilience) --------------------------------
# Transient failures (DNS blips, HTTP/2 resets, nav timeouts) get this many
# EXTRA attempts with linear backoff. Permanent outcomes (bot-block, 4xx,
# empty DOM, success) never retry. See fetcher.fetch_page.
RETRY_ATTEMPTS = 2                # total tries = 1 + RETRY_ATTEMPTS
RETRY_BACKOFF_SECONDS = 1.5       # sleep grows: 1.5s, 3.0s, ...

# --- Browser settings -----------------------------------------------
# A realistic current desktop-Chrome UA so normal sites don't reject an
# obviously-automated UA string. NOTE: this is the one Tier-0 honesty trade-off
# — we no longer self-identify as a bot in the UA. We STILL respect robots.txt
# and rate-limit politely (INTER_PAGE_DELAY_SECONDS); this is not stealth/evasion.
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
ACCEPT_LANGUAGE = "en-US,en;q=0.9,ar;q=0.8"   # EN-first, AR accepted (MENA sites)
VIEWPORT_WIDTH = 1366
VIEWPORT_HEIGHT = 800

# --- URL params to strip during normalization -----------------------
TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "fbclid", "gclid", "msclkid", "ref", "ref_src", "yclid", "_ga",
    "mc_cid", "mc_eid", "igshid", "ttclid",
}

# --- Page type patterns (bilingual EN + AR) -------------------------
# Match against URL path AND anchor text. First match wins.
# Each tuple: (page_type, tier, [patterns])
PAGE_TYPE_PATTERNS = [
    ("contact", "HIGH", [
        "contact", "contact-us", "contactus", "get-in-touch", "reach-us",
        "find-us",
        "تواصل", "اتصل", "اتصال", "تواصل-معنا", "اتصل-بنا",
    ]),
    # CATERING before SERVICES: "/catering-services" should map to CATERING,
    # not SERVICES, because "services" is a substring match that would
    # otherwise win the first-match-wins lookup.
    ("catering", "HIGH", [
        "catering", "catering-services", "catering-menu",
        "ضيافة", "خدمات-الضيافة",
    ]),
    # BRANCHES_LOCATIONS before PRODUCTS: "/store-locator" contains "store"
    # (a PRODUCTS pattern) and would otherwise be misclassified.
    ("branches_locations", "HIGH", [
        "branches", "our-branches", "branch", "locations", "our-locations",
        "store-locator", "find-a-store",
        "فروع", "فروعنا", "الفروع", "مواقعنا",
    ]),
    # Cart / checkout SKIP must come BEFORE products so "/shopping-cart"
    # doesn't get classified as PRODUCTS via the "shop" pattern. These
    # are transactional UIs with no content worth extracting; we still
    # capture them as CTA *links* via the CTA verb list elsewhere.
    ("other", "SKIP", [
        "cart", "cart-details", "checkout", "basket", "my-cart",
        "shopping-cart", "view-cart",
        "عربة", "السلة", "سلة", "الدفع",
    ]),
    ("services", "HIGH", [
        "services", "service", "our-services", "what-we-do",
        "solutions", "offerings",
        "خدمات", "خدماتنا", "الخدمات",
    ]),
    ("products", "HIGH", [
        "products", "product", "our-products", "shop", "store",
        "catalog", "catalogue", "product-catalog",
        "collections", "collection",
        "best-sellers", "bestsellers", "new-arrivals",
        # PLP/PDP — the product-list/product-detail URL convention of enterprise
        # storefronts (measured on nahdionline.com: /ar-sa/plp/... URLs weren't
        # recognized as products, so the e-commerce crawl budget never triggered).
        "plp", "pdp",
        "منتجات", "منتجاتنا", "المنتجات", "المتجر", "متجر",
        "مجموعات",
    ]),
    ("menu", "HIGH", [
        # food / restaurant menus — keep the existing tag, expand patterns
        "menu", "menus", "the-menu", "our-menu", "food-menu",
        "restaurant-menu", "dishes", "meals", "food",
        "قائمة", "قائمة-الطعام", "قائمتنا",
        "المنيو", "منيو", "أطباق", "وجبات", "طعام", "أكلات",
    ]),
    ("delivery_order", "HIGH", [
        "order", "order-online", "order-now", "online-order",
        "delivery", "takeaway", "take-away", "takeout", "pickup",
        "اطلب", "اطلب-الآن", "توصيل", "ديليفري",
    ]),
    ("courses", "HIGH", [
        "courses", "our-courses", "course-list", "course", "all-courses",
        "كورسات", "دورات", "الدورات",
    ]),
    ("programs", "HIGH", [
        "programs", "programmes", "our-programs", "academic-programs",
        "training-programs", "tracks", "training",
        "برامج", "برامجنا", "تدريب",
    ]),
    ("admissions", "HIGH", [
        "admissions", "admission", "apply", "application",
        "how-to-apply", "enroll", "enrolment", "enrollment", "register-now",
        "التقديم", "التسجيل", "قدم", "سجل",
    ]),
    ("pricing", "HIGH", [
        "pricing", "prices", "plans", "rates", "packages", "fees",
        "أسعار", "الأسعار", "الباقات", "الاسعار", "تسعير",
    ]),
    ("booking", "HIGH", [
        "book", "booking", "reserve", "reservation", "appointment",
        "احجز", "حجز", "موعد", "احجز-الآن",
    ]),
    ("about", "MEDIUM", [
        "about", "about-us", "aboutus", "who-we-are", "company",
        "story", "our-story", "mission", "vision",
        "من-نحن", "عن-الشركة", "من_نحن", "نبذة", "رؤيتنا",
    ]),
    ("portfolio", "MEDIUM", [
        "portfolio", "our-work", "work", "projects", "our-projects",
        "case-studies", "case-study", "showcase",
        "أعمالنا", "مشاريعنا", "دراسات-الحالة",
    ]),
    ("testimonials", "MEDIUM", [
        "testimonials", "reviews", "client-reviews",
        "what-clients-say", "success-stories",
        "آراء", "آراء-العملاء", "شهادات", "قصص-نجاح",
    ]),
    ("events", "MEDIUM", [
        "events", "upcoming-events", "our-events", "event",
        "فعاليات", "أحداث", "الفعاليات",
    ]),
    ("offers", "MEDIUM", [
        "offers", "promotions", "deals", "special-offers", "discounts",
        "offer-detail", "offer-details",
        "عروض", "عروضنا", "خصومات",
    ]),
    ("faq", "MEDIUM", [
        "faq", "faqs", "questions", "help",
        "الأسئلة", "اسئلة-شائعة", "الاسئله",
    ]),
    ("gallery", "LOW", [
        "gallery", "photo-gallery", "photos", "our-gallery", "images",
        "معرض", "صور", "المعرض",
    ]),
    ("blog", "LOW", [
        "blog", "news", "articles", "posts",
        "مدونة", "أخبار", "مقالات",
    ]),
    ("careers", "LOW", [
        "career", "careers", "jobs", "join-us",
        "وظائف", "التوظيف",
    ]),
    ("legal", "SKIP", [
        "privacy", "terms", "tos", "legal", "cookie", "cookies",
        "خصوصية", "شروط", "الشروط",
    ]),
]

# --- CTA detection --------------------------------------------------
# Anchor texts (lowercased) that mark a link as a CTA candidate.
CTA_VERBS = {
    # English — general conversion verbs
    "book", "book now", "buy", "buy now", "shop", "shop now", "order",
    "order now", "order online",
    "get started", "get a quote", "request a quote",
    "sign up", "subscribe", "join", "register", "contact us", "call now",
    "call us",
    "schedule", "start", "try free", "try now", "download", "apply",
    "reserve", "reserve now", "claim", "learn more",
    # English — ECOMMERCE shop entry-points (added 2026-06-14 from Azza Fahmy:
    # the real shop CTAs were scraped as <a> ("Catalog", "VIEW ALL") but missed,
    # so the CTA degraded to a generic "Visit website" on a store. "shop *"/"order *"
    # already match via the startswith rule; these are the non-"shop" phrasings.)
    "catalog", "shop all", "view all", "browse", "explore the collection",
    "view collection", "shop the collection", "shop collection",
    # "explore *" (added 2026-07-03 from daturial "Explore Solutions"; MEASURED
    # corpus-wide: fires only on real action anchors — "Explore Now",
    # "EXPLORE OUR MENU", "Explore More Posts" — zero flooding on 87 scrapes).
    "explore", "استكشف",
    # English — restaurant/food-ordering CTAs (added 2026-05 from Buffalo Burger benchmark).
    # NOTE: "menu" alone is special-cased in _is_cta_anchor so it only matches
    # as an exact anchor, not as a substring of "menu of the day".
    "view menu", "menu", "see menu", "our menu",
    "cart", "go to cart", "view cart",
    "delivery", "takeaway", "pickup",
    "download app", "download our app", "get the app", "mobile app",
    # Arabic
    "احجز", "احجز الآن", "اطلب", "اطلب الآن", "اشتري", "اشترك", "سجل",
    "تواصل", "تواصل معنا", "اتصل", "اتصل بنا", "ابدأ", "جرب", "حمل",
    "احصل", "اطلب عرض", "اطلب عرض سعر",
    # Arabic — restaurant/food-ordering CTAs (added 2026-05)
    "اطلب دلوقتي", "حمل التطبيق", "حمّل التطبيق",
    "القائمة", "المنيو", "السلة", "عربة التسوق",
    "توصيل", "ديليفري",
    # Arabic — ecommerce shop entry-points (added 2026-06-14)
    "تسوق", "تسوّق", "تسوق الآن", "تصفح", "الكتالوج", "عرض الكل", "تسوق الكل",
    # H5 (2026-07-05) — major expansion-market languages (product is "any language, any
    # country"; a French store previously scored cta_candidates=0 on 310 internal links).
    # Grounded in elietop.com's real CTAs + common conversion verbs; MEASURED corpus-wide:
    # +CTAs only on the French site, ZERO inflation on the 100+ EN/AR scrapes. Italian
    # "registrati" was DROPPED — it is a prefix of English "Registration" (false match).
    # French
    "nous contacter", "contactez-nous", "contacter", "en savoir plus", "voir plus",
    "panier", "connectez-vous", "connexion", "continuer les achats", "acheter",
    "commander", "réserver", "découvrir", "s'inscrire", "ajouter au panier",
    # Spanish
    "contáctanos", "contactar", "comprar", "comprar ahora", "añadir al carrito",
    "carrito", "reservar", "saber más", "más información", "iniciar sesión",
    "regístrate", "descubrir", "ver más",
    # German
    "kontakt", "kontaktieren", "jetzt kaufen", "kaufen", "mehr erfahren", "anmelden",
    "warenkorb", "buchen", "bestellen", "entdecken", "registrieren",
    # Italian
    "contattaci", "acquista", "acquista ora", "scopri", "scopri di più", "scopri di piu",
    "prenota", "carrello", "iscriviti",
    # Portuguese
    "saiba mais", "fale conosco", "contato", "carrinho", "cadastre-se",
    "adicionar ao carrinho", "descubra",
    # Turkish
    "satın al", "iletişim", "bize ulaşın", "keşfet", "sepet", "sepete ekle",
    "rezervasyon", "kayıt ol", "üye ol",
}

# --- Social platforms -----------------------------------------------
# Map of (domain substring) -> platform name
SOCIAL_DOMAINS = {
    "facebook.com": "facebook",
    "fb.com": "facebook",
    "instagram.com": "instagram",
    "twitter.com": "twitter",
    "x.com": "twitter",
    "linkedin.com": "linkedin",
    "youtube.com": "youtube",
    "youtu.be": "youtube",
    "tiktok.com": "tiktok",
    "pinterest.com": "pinterest",
    "snapchat.com": "snapchat",
    "telegram.org": "telegram",
    "t.me": "telegram",
    "wa.me": "whatsapp",
    "whatsapp.com": "whatsapp",
    "threads.net": "threads",
    "github.com": "github",
}

# --- Bot protection indicators --------------------------------------
BOT_PROTECTION_TEXT_SIGNALS = [
    "verify you are human",
    "checking your browser",
    "cf-challenge",
    "captcha",
    "are you a robot",
    "access denied",
    "blocked by",
    "ddos protection",
    "just a moment",
    "please enable javascript and cookies",
]

# --- Regex patterns -------------------------------------------------
EMAIL_REGEX = r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"

# --- Output dirs ----------------------------------------------------
DEFAULT_OUTPUT_ROOT = "scrapes"

# --- Image / asset ----
MAX_PALETTE_COLORS = 6