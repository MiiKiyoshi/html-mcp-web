"""The page-wide parts the review pages share, as the HTML review page uses them, in Chrome: the
grips that size the comments panel, and the holds that keep the page at its size."""

from __future__ import annotations

import time
from pathlib import Path

from tests.test_comment_panel_browser import needs_browser, review_page, wait_until

# A browser that says it is an iPhone, the one that zooms into a field as it takes the cursor.
IPHONE = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
          "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1")
# A finger landing on, or lifting from, the element the selector names, as a touch screen sends
# it; the viewport's content after it.
FINGER = '''
  const [kind, selector] = arguments;
  const target = document.querySelector(selector);
  const box = target.getBoundingClientRect();
  const touch = new Touch({identifier: 1, target, clientX: box.left + 2, clientY: box.top + 2});
  const lifted = kind === "touchend";
  target.dispatchEvent(new TouchEvent(kind, {bubbles: true, cancelable: true, composed: true,
    touches: lifted ? [] : [touch], targetTouches: lifted ? [] : [touch], changedTouches: [touch]}));
  return document.querySelector('meta[name="viewport"]').content;'''
VIEWPORT = 'return document.querySelector(\'meta[name="viewport"]\').content'


@needs_browser
def test_the_panels_left_edge_sets_its_width_and_keeps_it(tmp_path: Path) -> None:
    """Beside the artifact, the comments' left edge is dragged to set their width, or moved by
    the keys on it, between 240px and 70% of the window, and the artifact takes the room left.
    The width is kept for the next visit, a tap that ends a drag reaches no tab, and stacked the
    edge gives way to the bar on top."""
    with review_page(tmp_path) as (browser, base):
        width = 'return document.querySelector("#sidebar").getBoundingClientRect().width'
        stored = 'return Number(localStorage.getItem("htmlMcpSidebarWidth"))'
        frame = 'return document.querySelector("#artifact-frame").getBoundingClientRect().width'
        active = 'return document.querySelector(".tab-btn.active").dataset.tab'
        assert browser.execute_script(width) == 360
        before = browser.execute_script(frame)
        grip = browser.execute_script('''
          const box = document.querySelector("#sidebar-width-grip").getBoundingClientRect();
          return {x: Math.round(box.left + box.width / 2), y: Math.round(box.top + box.height / 2)};''')
        # The edge is a strip over the panel's border, which a pointer finds there.
        assert browser.execute_script(
            'return document.elementFromPoint(arguments[0], arguments[1]).id', script_args=[grip["x"], grip["y"]]
        ) == "sidebar-width-grip"
        # The tap that ends the drag lands on no tab. It comes just after the release, as a
        # finger's does, from the page itself: a command sent after the drag may come later.
        browser.execute_script('''document.addEventListener("pointerup", () => setTimeout(() => {
            document.querySelector(".tab-btn[data-tab=pages]").click();
            window.tappedAfterDrag = true;
          }, 50), {capture: true, once: true});''', sandbox=None)
        drag = browser.actions("pointer", "mouse", {"pointerType": "mouse"})
        drag.pointer_move(grip["x"], grip["y"]).pointer_down()
        for step in range(1, 5):
            drag.pointer_move(grip["x"] - 30 * step, grip["y"], duration=30)
        drag.pointer_up().perform()
        wait_until(lambda: browser.execute_script("return window.tappedAfterDrag === true", sandbox=None))
        assert browser.execute_script(active) == "comments"
        dragged = browser.execute_script(width)
        assert abs(dragged - 480) <= 2 and abs(browser.execute_script(stored) - dragged) <= 1
        assert browser.execute_script('''return [document.body.classList.contains("sidebar-resizing"),
          document.querySelector("#sidebar-width-grip").classList.contains("dragging")]''') == [False, False]
        assert abs(browser.execute_script(frame) - (before - (dragged - 360))) <= 2
        time.sleep(0.5)
        browser.execute_script('document.querySelector(".tab-btn[data-tab=pages]").click()')
        assert browser.execute_script(active) == "pages"
        browser.execute_script('document.querySelector(".tab-btn[data-tab=comments]").click()')

        # The keys: a step wider or narrower, the widest and the narrowest, each kept.
        keyed = browser.execute_script('''
          const grip = document.querySelector("#sidebar-width-grip");
          const width = () => document.querySelector("#sidebar").getBoundingClientRect().width;
          grip.focus();
          return ["ArrowLeft", "ArrowRight", "ArrowRight", "Home", "End"].map((key) => {
            grip.dispatchEvent(new KeyboardEvent("keydown", {key, bubbles: true}));
            return [width(), Number(localStorage.getItem("htmlMcpSidebarWidth"))];
          });''')
        widest = round(browser.execute_script("return innerWidth") * 0.7)
        assert [round(shown) for shown, _ in keyed] == [round(dragged) + 40, round(dragged), round(dragged) - 40, widest, 240]
        assert all(abs(shown - kept) <= 1 for shown, kept in keyed)
        browser.execute_script(
            'document.querySelector("#sidebar-width-grip").dispatchEvent(new KeyboardEvent("keydown", {key: "ArrowLeft", bubbles: true}))')
        browser.refresh()
        wait_until(lambda: browser.execute_script(width) == 280)

        # Stacked, the comments sit under the artifact and the bar on their top sets their height.
        browser.set_window_rect(width=500, height=900)
        wait_until(lambda: browser.execute_script('''return [getComputedStyle(document.querySelector("#sidebar-width-grip")).display,
          getComputedStyle(document.querySelector("#sidebar-grip")).display]''') == ["none", "flex"])


@needs_browser
def test_a_pinch_outside_the_artifact_leaves_the_page_at_its_size(tmp_path: Path) -> None:
    """A trackpad's pinch reaches the page as a wheel turned with Ctrl held. Over the top bar or
    the comments the browser would magnify the whole page, so there it is kept from the browser;
    a wheel without Ctrl still scrolls."""
    with review_page(tmp_path) as (browser, base):
        assert browser.execute_script('''
          const turn = (selector, ctrlKey) => document.querySelector(selector).dispatchEvent(
            new WheelEvent("wheel", {deltaY: -3, ctrlKey, bubbles: true, cancelable: true}));
          return [turn(".topbar", true), turn(".topbar", false), turn(".sidebar-tabs", true), turn(".sidebar-tabs", false)];''',
            sandbox=None) == [False, True, False, True]


@needs_browser
def test_a_finger_on_a_field_keeps_an_iphone_from_zooming_into_it(tmp_path: Path) -> None:
    """An iPhone zooms the page into a field whose text is under 16px as it takes the cursor.
    The fields keep the size of the text around them, and from a finger landing on one until
    just after it has the cursor the page may not grow past its size. A finger anywhere else
    frees it at once. The source editor's hidden input, which no finger lands on, is 16px."""
    with review_page(tmp_path, user_agent=IPHONE, touch=True) as (browser, base):
        assert browser.execute_script('return [navigator.userAgent.includes("iPhone"), matchMedia("(pointer: coarse)").matches]',
                                      sandbox=None) == [True, True]
        assert browser.execute_script('''
          const field = getComputedStyle(document.querySelector("#comment-search")).fontSize;
          const probe = document.createElement("textarea");
          probe.className = "ace_text-input";
          document.body.append(probe);
          const hidden = getComputedStyle(probe).fontSize;
          probe.remove();
          return [parseFloat(field) < 16, hidden];''') == [True, "16px"]
        free = "width=device-width, initial-scale=1"
        held = f"{free}, maximum-scale=1"
        assert browser.execute_script(VIEWPORT) == free
        assert browser.execute_script(FINGER, script_args=["touchstart", "#comment-search"], sandbox=None) == held
        # The field takes the cursor and the finger lifts within the moment the hold lasts after
        # it, in one script: as two commands, a slow runner let the moment pass between them.
        assert browser.execute_script('document.querySelector("#comment-search").focus();' + FINGER,
                                      script_args=["touchend", "#comment-search"], sandbox=None) == held
        wait_until(lambda: browser.execute_script(VIEWPORT) == free)
        # A finger on anything but a field frees the page at once.
        browser.execute_script(FINGER, script_args=["touchstart", "#comment-search"], sandbox=None)
        browser.execute_script(FINGER, script_args=["touchstart", "#settings-btn"], sandbox=None)
        wait_until(lambda: browser.execute_script(VIEWPORT) == free)
