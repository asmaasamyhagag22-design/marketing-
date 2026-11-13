# دورة إصدار Campaign

المسار يبدأ من رابط وهدف ولغة ويستخدم `/api/v2/campaigns/plan` ثم مراجعة النص والاعتماد والتصدير القائمين. المقارنة تضبط سياسة مراجعة النص فقط. الإصدار `stable` يعيد سلوك المراجعة المرجعي من `4648fbc` على نفس بناء التطبيق. `candidate` يضيف إعادة استعمال عنوان القسم نفسه في اتجاه آخر لنفس الوجهة، بشروط القاعدة المسجلة. إعادة إنتاج خلل Five Guys التاريخي لها checkout منفصل من `9cb6f42`.

## العرض من checkout نظيف

نفّذي أوامر تثبيت Python 3.12 وChromium وصورة PostgreSQL 16 من [README](../../../README.md) ثم:

```bash
output=$(mktemp -d)
python -m workflows.campaign_eval --output "$output/replay.json"
python tools/demo_campaign_lifecycle.py --output-dir "$output/demo"
python -m workflows.campaign_monitor "$output/demo/server.log"
python -m workflows.campaign_eval --live --output "$output/live.json"
```

الـreplay يتحقق من بصمات اللقطات ويمنع الشبكة الخارجية. النتيجة الآلية تحفظ `eval_set_id` وبصمة manifest لكل لقطة، وcommit ونسخ إعدادات التنفيذ، والاقتباس والوجهة ونتيجة كل تعديل. الـlive يخرج تشخيصًا مستقلًا بلا قرار إصدار. لقطة Python تحفظ فقرة Applications من صفحة Python الرسمية. لقطة OpenStreetMap تحفظ فقرة Local Knowledge من صفحة About. اختيرتا لحالتين جديدتين في المسار العام بلا ملفات تحرير خاصة، وثُبّتتا قبل التقييم. البيانات تحت `snapshots/` تحفظ تاريخ الالتقاط وبصمة المتن الأصلي والمقتطف المستخدم. [Python](https://www.python.org/about/) · [OpenStreetMap](https://www.openstreetmap.org/about)

## نسخة أوقفتها CI

شغّلنا نفس workflow من clone نظيف باستخدام `act` 0.2.97 على Linux، مع Python من بيئة المشروع. يخرج نجاح عند `f46f176` وفشل عند `8ea787a`. إعداد Actions المستضاف يحتاج قرار النشر. لتكرار التجربة، افحصي النسخة السليمة ثم طبقي [التعديل المتعمد](regression.patch) في clone محلي منفصل.

```bash
repo=$(pwd)
clean_ci=$(mktemp -d)/clean
git clone --no-local "$repo" "$clean_ci"
cd "$clean_ci"
git checkout -b clean-replay f46f176
act -W .github/workflows/campaign-replay.yml -P ubuntu-latest=-self-hosted \
  --env-file /dev/null --secret-file /dev/null --env ACT=true --env "PYTHONPATH=$PWD"

git switch -c regressed-replay
git apply "$repo/docs/campaigns/lifecycle/regression.patch"
git add strategy/campaign_planner.py strategy/campaign_editions.py
git commit -m 'Demo only: reintroduce Campaign regressions'
act -W .github/workflows/campaign-replay.yml -P ubuntu-latest=-self-hosted \
  --env-file /dev/null --secret-file /dev/null --env ACT=true --env "PYTHONPATH=$PWD"
```

النداء الأخير يرجع 1 عند خطوة `Evaluate the frozen replay`. القياس السليم يُبقي `stable` افتراضيًا حتى بعد أهلية التفعيل المحلي. في تجربة الحجب كانت السياسة المستقرة سليمة، والمرشح اختار Little Bacon Burger وسمح بعنوان «كل برجر في المنيو فيه هالبينو». [نجاح المهمة](results/ci-pass.log) · [حجب المرشح](results/ci-blocked.log) · [التفاصيل](results/rejected-candidate.json)

## قراءة الـtrace والتنبيه

- في إخفاق Nando’s الحي يظهر `campaign.fetch → PAGE_TOO_LARGE` ثم `campaign.select_evidence → FEATURE_EVIDENCE`. في الـreplay المحاكى أُعيد متن يتجاوز سقف الناقل الحقيقي البالغ 2,000,000 بايت، واختبرنا مهلة socket على حدة.
- في Five Guys مع الارتداد يظهر `campaign.fetch → SOURCE_READ` ونجاح `campaign.select_evidence` مع بصمة دليل مختلفة. `campaign.eval` يوسم `WRONG_EVIDENCE_SELECTION` بناءً على التسمية المرجعية. تشخيص الإنتاج من البصمة يحتاج ربطها بالدليل ومراجعة موضوعه.
- في رحلة Buffalo تظل مراحل الجلب والاختيار والكتابة والتحقق والاعتماد والتصدير مرتبطة عبر `trace_id` في `Run.output.planner` حتى بعد مراجعة تصنع Run جديدة. نقلنا النتيجة والسبب المحصور والزمن عبر SDK الموجود، واختبرنا المصدر والنص السري في مصدّر داخل الذاكرة. يمكن تفعيل Langfuse في الخدمة العادية بمتغيرات البيئة الموجودة `ADZY_LANGFUSE_ENABLED=1` و`LANGFUSE_PUBLIC_KEY` و`LANGFUSE_SECRET_KEY` و`LANGFUSE_BASE_URL`. إيصالات هذه الجولة محلية، ومُصدّر التجارب في الذاكرة.
- تقرير التشغيل يقرأ سطور `ADZY_CAMPAIGN_EVENT` ويحسب النسب لكل نمط مصدر وp95 لكل مرحلة. للرجوع لنفس نافذة الديمو استخدمي `--end` بقيمة `monitor.end` من `result.json`. التنبيه هنا نتيجة في التقرير يمكن جمعها في نظام التشغيل. لا توجد قناة إرسال خارجية في التجربة.

## الرجوع

يعمل الرجوع عبر إعادة تشغيل نفس بناء التطبيق بـ`ADZY_CAMPAIGN_RELEASE=stable` مع نفس PostgreSQL ومجلد `BASEERA_WEBAPP_DIR` الذي يحفظ ملفات Campaign. يمكن ضبط `ADZY_CAMPAIGN_BUILD_COMMIT` إلى SHA البناء الكامل عند تشغيل مصدر بلا Git metadata. التفعيل المحلي للمرشح يبدأ بعد نجاح نفس gate الموجود في CI. الديمو يصدّر الحملة المرشحة، يعيد التشغيل على المستقر، ويعيد تنزيل نفس ZIP بايت ببايت قبل إنشاء طلب أحدث. يثبت الطلب الجديد سلوك المستقر برفض إعادة استعمال العنوان في الاتجاه البديل. اختبار قرار قديم بعد طلب أحدث يرجع 409 حسب عقد التصدير الحالي.

سجل التشغيل يبقي معرفات Run وApproval والبروفايل، وبصمة الأدلة، وبايتات الحزمة المنزّلة. الرجوع داخل نفس البناء لا يحتاج migration. الرجوع إلى بناء تاريخي أقدم مسار مختلف عن تبديل هذه السياسة ولم يُختبر هنا.

## إيصالات العرض

- [المقارنة والـtrace المحلي](results/replay.json)
- [تشخيص المصادر الحية](results/live.json)
- [الديمو والرجوع وإيصال التنبيه](results/demo.json)
- [رحلة Buffalo في Chromium](results/buffalo-browser.json)
- [آخر حالة متحققة والخطوة التالية](EXECUTION.md)

تحتفظ نسخ JSON المرفقة من تجارب Langfuse بحقول المرحلة والزمن والارتباط والنتيجة من SDK المحلي. ملف JSON الخارج من أمر الـeval يتضمن السمات المحصورة الأصلية أيضًا.
