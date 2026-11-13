# Buffalo Burger · شيدر كلاسيك ولا هالبينو؟

حملة مراجعة داخل ADZY. الفكرة تقارن بين أولد سكول وراستافاري وتفتح المنيو مباشرة. الاتجاه البديل يبدأ من بايتس الهالبينو في راستافاري ويأخذ الزائر لصفحة الساندوتش. حالة ترافل بيف برجر تختبر هدف قراءة مكونات صنف محدد.

| الحملة | التنزيل | المعاينة |
|---|---|---|
| المنيو · المقارنة | [ZIP](menu/campaign.zip) | [طولي](menu/poster-portrait.png) · [مربع](menu/poster-square.png) · [النص والدليل](menu/campaign.json) |
| راستافاري · اتجاه بديل | [ZIP](rastafari/campaign.zip) | [طولي](rastafari/poster-portrait.png) · [مربع](rastafari/poster-square.png) |
| ترافل بيف برجر · المكونات | [ZIP](truffle/campaign.zip) | [طولي](truffle/poster-portrait.png) · [مربع](truffle/poster-square.png) |

[قبل وبعد](design/comparison.png) · [رفض تعميم الهالبينو](menu/rejected.png) · [سجل التنفيذ](EXECUTION.md) · [مذاكرة الكود](../INTERVIEW.md)

## إعادة الرحلة

الديمو المحلي المفتوح عند التسليم على [Campaign](http://127.0.0.1:8043/app#stage=campaign&brand=buffaloburger_com) بحساب `review-01322e3468d0@adzy.invalid` وكلمة مرور `LocalCampaignReview42`. الحزمة الرئيسية هي آخر نسخة معتمدة في هذا الديمو. مسار تشغيله `/tmp/adzy-buffalo-release-20261113` على هذا الجهاز.

من جذر worktree استخدمي Python باعتماديات `requirements-app.txt` وChromium المثبّت عبر Playwright وDocker بصورة `postgres:16-alpine` محلية.

```bash
export ADZY_CAMPAIGN_EDITIONS_FILE="$PWD/docs/campaigns/buffalo/editions.json"
run_dir=$(mktemp -d)
python -m workflows.public_campaign_demo init --directory "$run_dir/demo"
python -m workflows.public_campaign_demo serve --directory "$run_dir/demo" --port 8020
```

1. افتحي [التطبيق](http://127.0.0.1:8020/app) وسجّلي بالحساب المطبوع. اختاري **Campaign**.
2. أدخلي `https://buffaloburger.com`، والهدف «تشجيع المستخدم على تصفّح المنيو واختيار برجر يناسبه»، واللغة العربية. افتحي خطوات البحث و«دليل كل حقل».
3. جرّبي «كل برجر في المنيو فيه هالبينو» في العنوان ثم احفظي. الواجهة تشير إلى العنوان وتحتفظ بالنص لمحاولة التصحيح. أعيدي العنوان واقبلي الصياغة البديلة من زر الاختيار داخل محرر النص.
4. احفظي الـbrief. اعرضي المقاسين واضغطي «اعتمد هذه النسخة» ثم «نزّل حزمة المراجعة». زر «اختَر هذا الاتجاه» ينشئ نسخة أخرى تتطلب مراجعة واعتمادًا.
5. أوقفي الخادم فقط وأعيدي أمر `serve` بنفس المجلد لاستعادة آخر نسخة واعتمادها. زر «أعد فحص الدليل» يعيد قراءة الحقول التي تعتمد عليها الحملة.
6. كرري باستخدام حالة `truffle` من [cases.json](cases.json). هدفها قراءة مكونات المنتج ووجهتها صفحة ترافل.

`editions.json` فيه قرارات التحرير والأوصاف التي تتوقعها الحملة. أثناء التشغيل يقرأ التطبيق الحقول من الناشر ويحفظ الاقتباس والمصدر ووقت الالتقاط. لتحديث صياغة جديدة خارج الاقتراحات الظاهرة، يراجع محرر الحملة النص مع المصدر ويحدّث ملف الحملة المحلي، ثم يعيد البحث والمراجعة. تغيير حقل أساسي أو تعذّر الوصول إليه يوقف الاعتماد بعد إعادة الفحص. النبرة في محرر الـbrief ملاحظة مرتبطة بالنسخة، وصياغة النص تتغير من محرر النص أو بتبديل الاتجاه.

```bash
run_dir=$(mktemp -d)
python tools/verify_public_campaign_browser.py --directory "$run_dir/demo" \
  --evidence-dir "$run_dir/output" --planner-cases docs/campaigns/buffalo/cases.json
python -m workflows.verify -q tests/test_campaign_editions.py tests/test_campaign_planner.py \
  tests/test_public_campaign_package.py tests/test_adzy_v2_campaign.py tests/test_adzy_v2_research.py \
  tests/test_ssrf_coverage.py tests/test_route_persistence_classification_2gb.py tests/test_security_headers.py
python -m tools.measure_catalog_campaign "$run_dir/output/menu/initial"
```

بعد المراجعة يمكن إيقاف الديمو وإزالة حاويته بأمر `python -m workflows.public_campaign_demo cleanup --directory "$run_dir/demo"`. الـZIP والـPNG المحفوظة في هذا الدليل تبقى متاحة للمذاكرة.
