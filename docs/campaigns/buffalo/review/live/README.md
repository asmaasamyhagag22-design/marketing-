# نتائج المصادر الحية

الطلبات العامة من التطبيق بتاريخ 13 نوفمبر 2026. لا استدعاءات لمزود مدفوع.

| الجولة | الأثر |
|---|---|
| Buffalo من Campaign عند نقطة البداية | تعثّر الجلب بمهلة عند الصفحة الرئيسية والمنيو، وظهرت فجوة `EDITORIAL_SOURCE_GAP`. [الـRun ومسار الجلب](buffalo-timeout.json) |
| Buffalo من checkout المراجعة | قرأ حقول الناشر في أربع زيارات وصدّر المقاسين. بصمات PNG طابقت اللقطة. [إيصال التصدير الحي](buffalo-export.json) |
| Five Guys بالمسار العام | قرأ الناشر في زيارة واحدة، اختار Bacon Burger وصدّر المقاسين. [إيصال التصدير الحي](five-guys.json) |
| Nando’s بالمسار العام | رفض الناقل متن HTML عند حد 2,000,000 بايت (`PAGE_TOO_LARGE`)، فوصل التطبيق إلى فجوة `FEATURE_EVIDENCE` قبل استخراج الوصف. نفس الحالة من اللقطة المنقحة صدّرت الحزمة. [الـRun ومسار الجلب](nandos-size-limit.json) |

[صفحة منيو Buffalo](https://buffaloburger.com/menu) · [صفحة Five Guys](https://www.fiveguys.com/menu/burgers/) · [صفحة Nando’s](https://www.nandos.co.uk/food/menu/)
