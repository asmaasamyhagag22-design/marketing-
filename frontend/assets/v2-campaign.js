(function () {
  'use strict';

  const byId = id => document.getElementById(id);
  const esc = value => String(value ?? '').replace(/[&<>"']/g, ch =>
    ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'})[ch]);
  const messages = {
    READY: 'أُغلقت فجوة الدليل',
    BUDGET_EXHAUSTED: 'انتهت ميزانية البحث قبل اكتمال الدليل',
    NO_SUPPORTED_OFFER: 'انتهى البحث من دون عرض صالح',
    BRAND_ENTRY: 'بدء البحث من موقع البراند',
    GAP_MATCH: 'الرابط يرجّح وجود السعر أو الشروط الناقصة',
    OWNER_SOURCE: 'صفحة اقترحها صاحب البراند',
    RECHECK_BOUND_EVIDENCE: 'إعادة قراءة الصفحة التي يعتمد عليها الإعلان',
    SUPPORTED_OFFER: 'وُجد السعر والفرع والشروط والصلاحية في المصدر',
    OFFER_NOT_FOUND: 'الصفحة لا تحتوي عرضًا منظمًا',
    SOURCE_UNAVAILABLE: 'تعذر الوصول إلى المصدر',
    UNSUPPORTED_OFFER_PAGE_CONTENT: 'الصفحة تحتاج مراجعة بسبب محتوى خارج الصيغة المدعومة',
    UNPARSED_OFFER_CONTEXT: 'ظهر سياق إضافي يحتاج مراجعة قبل صياغة الإعلان',
    OFFER_EXPIRED: 'انتهت صلاحية العرض',
    EVIDENCE_GAP: 'الأدلة غير كافية لاعتماد الإعلان.',
    PROFILE_CHANGED: 'تغيّر بروفايل البراند. ابدأ بحثًا على النسخة الجديدة.',
    CAMPAIGN_CHANGED: 'تغيّرت نسخة الحملة. راجع النسخة المعروضة.',
  };
  const label = value => messages[value] || value;
  let brand, state, timer, requestNumber = 0, busy = false;

  function path(suffix = '') {
    return '/api/v2/campaigns/' + encodeURIComponent(brand.domain_key) + suffix;
  }

  function link(value, text) {
    try {
      const url = new URL(value);
      if (['http:', 'https:'].includes(url.protocol)) {
        return `<a href="${esc(url.href)}" target="_blank" rel="noopener noreferrer">${esc(text)}</a>`;
      }
    } catch (_) {}
    return esc(text);
  }

  function showStatus(text) {
    byId('v2-status').textContent = text;
  }

  function card(proposal) {
    const {copy, page_url, sha256, brand_name} = proposal.creative;
    return `<article class="v2-creative" id="v2-creative" aria-label="الإبداع العربي">
      ${brand_name ? `<div class="v2-creative-header" dir="auto">${esc(brand_name)}</div>` : ''}
      <h2>${esc(copy.headline)}</h2>
      <p class="v2-price" dir="ltr">${esc(copy.price)}</p>
      <p>${esc(copy.branch)}</p>
      <p>${esc(copy.terms)}</p>
      <p class="v2-validity">ساري حتى <bdi>${esc(copy.validity)}</bdi></p>
      <p class="v2-creative-cta">${link(page_url, copy.cta)}</p>
      <details><summary>بصمة محتوى النسخة</summary><code dir="ltr">${esc(sha256)}</code></details>
    </article>`;
  }

  function render() {
    clearTimeout(timer);
    const form = byId('v2-form');
    form.querySelector('button').disabled = busy || !state;
    const root = byId('v2-result');
    if (!state?.proposal) {
      root.innerHTML = '';
      return;
    }
    const {proposal, approved, reason, decision} = state;
    const offer = proposal.offer;
    const trace = proposal.research.trace.map(row =>
      `<li>${link(row.page_url, row.page_url)} <span>${esc(label(row.reason))} · ${esc(label(row.outcome))}</span></li>`
    ).join('');
    const changes = proposal.changes.map(row => `<li><strong>${esc(row.affects)}</strong>
      <p><bdi>${esc(label(row.before))}</bdi> ← <bdi>${esc(label(row.after))}</bdi></p>
      ${row.observed_excerpt ? `<blockquote>${esc(row.observed_excerpt)}</blockquote>` : ''}</li>`).join('');
    const plan = proposal.strategy;
    const copy = proposal.creative?.copy;
    const eligible = !!plan && !reason;
    const pending = eligible && !approved;
    root.innerHTML = `
      <section class="v2-panel">
        <h2>قرار البحث</h2>
        <p id="v2-question">${esc(proposal.research.questions.at(-1))}</p>
        <p id="v2-stop">${esc(label(proposal.research.status))}</p>
        <ol id="v2-trace">${trace}</ol>
        ${reason ? `<p id="v2-blocker">${esc(label(reason))}</p>` : ''}
        ${proposal.research.next_action ? '<p>أضف رابط صفحة مخصصة لشروط العرض وأعد البحث.</p>' : ''}
        ${changes ? `<h3>ما الذي تغيّر؟</h3><ul id="v2-changes">${changes}</ul>` : ''}
        ${proposal.watch_url ? '<button type="button" class="adzy-btn flat" id="v2-refresh">أعد فحص الدليل</button>' : ''}
      </section>
      ${plan ? `<section class="v2-panel" id="v2-strategy">
        <h2>الاستراتيجية المقترحة</h2>
        <dl>
          <dt>الهدف</dt><dd>${esc(proposal.goal)}</dd>
          <dt>التوصية</dt><dd>${esc(plan.recommendation)}</dd>
          <dt>الافتراض</dt><dd>${esc(plan.assumption)}</dd>
          <dt>البديل</dt><dd>${esc(plan.alternative)} ${esc(plan.tradeoff)}</dd>
          <dt>مقياس الحملة</dt><dd>${esc(plan.metric)}${proposal.booking_target ? ` · الهدف ${esc(proposal.booking_target)} حجزًا` : ''}</dd>
        </dl>
        <details open><summary>دليل العرض${offer.source_kind === 'synthetic_fixture' ? ' · مصدر مصطنع للديمو' : ''}</summary>
          <p>${link(offer.page_url, offer.page_url)}</p>
          <p><bdi>${esc(copy.price)}</bdi> · ${esc(copy.branch)}</p>
          <blockquote>${esc(copy.terms)}</blockquote>
          <p>ساري حتى <bdi>${esc(copy.validity)}</bdi></p>
          <details><summary>نسخة المصدر ووقت التقاطه</summary><code dir="ltr">${esc(offer.sha256)}</code><p dir="ltr">${esc(offer.captured_at)}</p></details>
        </details>
      </section>` : ''}
      ${pending ? `<section class="v2-panel">
        <h2>النص المقترح للمراجعة</h2>
        <p>${esc(copy.headline)} · ${esc(copy.cta)}</p>
        ${decision === 'rejected' ? '<p>رُفضت هذه النسخة.</p>' : ''}
        <div class="v2-actions"><button type="button" class="adzy-btn coral" id="v2-approve">اعتمد هذه النسخة</button>
        <button type="button" class="adzy-btn flat" id="v2-reject">ارفض هذه النسخة</button></div>
      </section>` : ''}
      ${approved && !busy ? card(proposal) : ''}`;
    for (const button of root.querySelectorAll('button')) button.disabled = busy;
    byId('v2-refresh')?.addEventListener('click', () => submit('/refresh', {run_id: state.run_id}));
    byId('v2-approve')?.addEventListener('click', () => submit('/review', {run_id: state.run_id, decision: 'approved'}));
    byId('v2-reject')?.addEventListener('click', () => submit('/review', {run_id: state.run_id, decision: 'rejected'}));
    if (approved && !busy) {
      const remaining = Date.parse(offer.expires_at) - Date.parse(state.checked_at);
      if (Number.isFinite(remaining)) {
        timer = setTimeout(() => {
          if (window.Adzy?.stage === 'campaign') load();
        }, Math.min(2147483647, Math.max(0, remaining)));
      }
    }
  }

  async function load() {
    const seq = ++requestNumber;
    busy = true;
    render();
    showStatus('بنحمّل نسخة الحملة…');
    try {
      const next = await window.api('GET', path());
      if (seq !== requestNumber) return;
      state = next;
      showStatus(state.approved ? 'تم اعتماد نسخة الحملة الحالية.' : '');
    } catch (_) {
      if (seq !== requestNumber) return;
      state = null;
      showStatus('تعذّر تحميل الحملة.');
    } finally {
      if (seq === requestNumber) {
        busy = false;
        render();
      }
    }
  }

  async function submit(suffix, body) {
    if (busy || !state) return;
    const seq = ++requestNumber;
    busy = true;
    render();
    showStatus(suffix === '/review' ? 'بنسجّل قرارك…' : 'بنبحث في صفحات المصدر…');
    try {
      const next = await window.api('POST', path(suffix), body);
      if (seq !== requestNumber) return;
      const unchanged = suffix === '/refresh' && next.run_id === state.run_id;
      state = next;
      showStatus(unchanged ? 'بصمة الدليل تطابق النسخة المحفوظة.'
        : state.approved ? 'تم اعتماد نسخة الحملة الحالية.' : 'حُفظت نتيجة النسخة الحالية.');
    } catch (error) {
      if (seq !== requestNumber) return;
      await load();
      showStatus(error.status === 409 ? 'راجع النسخة الحالية بعد تغيّر الحملة أو الدليل.' : 'تعذّر إكمال الطلب.');
    } finally {
      if (seq === requestNumber) {
        busy = false;
        render();
      }
    }
  }

  window.adzyCampaign = {
    reset() {
      requestNumber += 1;
      state = null;
      render();
      byId('v2-brand').textContent = '';
      showStatus('بنحمّل البراند…');
    },
    async open(nextBrand) {
      const form = byId('v2-form');
      if (brand?.domain_key !== nextBrand.domain_key) form.reset();
      brand = nextBrand;
      state = null;
      byId('v2-brand').textContent = nextBrand.organization_name || nextBrand.name || nextBrand.domain_key;
      form.onsubmit = event => {
        event.preventDefault();
        const fields = new FormData(form);
        submit('', {expected_run_id: state?.run_id ?? null, goal: fields.get('goal'),
                    booking_target: fields.get('booking_target') ? Number(fields.get('booking_target')) : null,
                    offer_name: fields.get('offer_name'), terms_url: fields.get('terms_url') || null});
      };
      await load();
      if (brand === nextBrand && state?.proposal) {
        form.elements.goal.value ||= 'TRIAL_BOOKINGS';
        form.elements.booking_target.value ||= state.proposal.booking_target ?? '';
        form.elements.offer_name.value ||= state.proposal.offer_name;
      }
    },
  };
})();
