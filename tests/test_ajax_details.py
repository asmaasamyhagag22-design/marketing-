"""JS-built 'reveal-on-click' detail URL discovery (scraper.ajax_details) — hermetic.

Reproduces the NTI pattern the owner hit: a course modal whose real detail page URL is assembled
in JS from a data-attribute and never appears in the HTML.
"""
from __future__ import annotations

from scraper.ajax_details import discover_ajax_details, extract_ajax_detail_urls

# The exact NTI shape: div.courseLinks a[data-target], and a .load() that wraps data-target in a
# pages/modules/<id>.html path with a random cache-buster query.
_NTI_JS = """
var courseLink = document.querySelectorAll('div.courseLinks a');
courseLink.forEach(function(link){
  link.addEventListener('click',function(){
    if(link.getAttribute('data-target')!="0"){
      $('#popover-cont').load("pages/modules/"+link.getAttribute('data-target')+".html?id="+Math.ceil(Math.random()*1000));
    }
  });
});
"""
_NTI_HTML = """
<html><body>
<div class="courseLinks">
  <a data-target="2631">Fiber Networks Essentials</a>
  <a data-target="2641">Microwave and Optical Transmission Essentials</a>
  <a data-target="0">Coming soon (no module yet)</a>
</div>
</body></html>
"""
_BASE = "https://www.nti.sci.eg/dey/coursesev.php?catID=205"


def test_resolves_nti_style_module_urls():
    urls = extract_ajax_detail_urls(_NTI_HTML, _BASE, [_NTI_JS])
    assert "https://www.nti.sci.eg/dey/pages/modules/2631.html" in urls
    assert "https://www.nti.sci.eg/dey/pages/modules/2641.html" in urls
    # the JS-side ?id= cache-buster is dropped; data-target="0" (no module) is skipped
    assert all("?id=" not in u for u in urls)
    assert not any(u.endswith("/0.html") for u in urls)
    assert len(urls) == 2


def test_supports_jquery_attr_and_dataset_variants():
    js_attr = """$('#c').load('mod/' + $(this).attr('data-id') + '.html');"""
    html_attr = '<a data-id="A7">x</a><a data-id="B8">y</a>'
    got = extract_ajax_detail_urls(html_attr, "https://s.example/base/list", [js_attr])
    assert got == ["https://s.example/base/mod/A7.html", "https://s.example/base/mod/B8.html"]

    js_ds = """box.load("details/" + el.dataset.courseId + ".php");"""
    html_ds = '<div data-course-id="99">z</div>'
    got2 = extract_ajax_detail_urls(html_ds, "https://s.example/x/", [js_ds])
    assert got2 == ["https://s.example/x/details/99.php"]      # dataset.courseId -> data-course-id


def test_no_template_returns_empty():
    # a page with data-target but NO .load() template -> nothing to resolve
    assert extract_ajax_detail_urls('<a data-target="1">x</a>', _BASE, ["console.log('hi')"]) == []
    assert extract_ajax_detail_urls('<a data-target="1">x</a>', _BASE, []) == []


def test_dedupes_repeated_targets():
    html = '<a data-target="5">a</a><a data-target="5">b</a>'
    urls = extract_ajax_detail_urls(html, "https://s.example/", ['x.load("m/"+e.getAttribute("data-target")+".html")'])
    assert urls == ["https://s.example/m/5.html"]


def test_discover_gathers_external_same_origin_js(monkeypatch):
    # The NTI shape: the .load() template lives in an EXTERNAL same-origin script.
    html = ('<html><body><div class="courseLinks"><a data-target="2631">X</a></div>'
            '<script src="/dey/js/popupCourse.js"></script>'
            '<script src="https://cdn.other.com/jquery.js"></script></body></html>')
    fetched = []

    def fake_fetch(u):
        fetched.append(u)
        return 'x.load("pages/modules/"+link.getAttribute("data-target")+".html?id="+r)'
    urls = discover_ajax_details(html, "https://www.nti.sci.eg/dey/coursesev.php?catID=205",
                                 fetch=fake_fetch)
    assert urls == ["https://www.nti.sci.eg/dey/pages/modules/2631.html"]
    # only the SAME-ORIGIN script is fetched (the CDN jQuery is skipped)
    assert fetched == ["https://www.nti.sci.eg/dey/js/popupCourse.js"]


def test_discover_uses_inline_script_without_any_fetch():
    html = ('<a data-target="5">x</a>'
            '<script>b.load("m/"+e.getAttribute("data-target")+".html")</script>')
    urls = discover_ajax_details(html, "https://s.example/", fetch=lambda u: None)
    assert urls == ["https://s.example/m/5.html"]
