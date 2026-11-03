"""Browser (E2E) tests: the real React app against the test backend.

Firebase, OpenAI, email and Facebook are all faked (see backend/tests/e2e_server.py
and e2e/firebase-stub.js), so nothing is published and no real account is used.

Run from the project root:
    python frontend/e2e/test_e2e.py
It starts the test backend (port 8010) and the Vite test server (port 5198) if they
are not running yet, and stops the ones it started.
"""

import json
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[2]
BACKEND = "http://127.0.0.1:8010"
APP = "http://localhost:5198"
VENV_PYTHON = ROOT / "backend" / "venv" / "Scripts" / "python.exe"

results = []
page_errors = []  # uncaught exceptions in the browser, from every test


def check(name, ok, detail=""):
    results.append((name, bool(ok)))
    print(("PASS  " if ok else "FAIL  ") + name + (f"  [{detail}]" if detail and not ok else ""), flush=True)


def api(path, method="GET"):
    request = urllib.request.Request(BACKEND + path, method=method, data=b"" if method == "POST" else None)
    return json.loads(urllib.request.urlopen(request, timeout=10).read())


def up(url):
    try:
        urllib.request.urlopen(url, timeout=2)
        return True
    except Exception:
        return False


def start_servers():
    started = []

    if not up(BACKEND + "/__e2e/state"):
        started.append(subprocess.Popen([str(VENV_PYTHON), str(ROOT / "backend" / "tests" / "e2e_server.py")], cwd=ROOT / "backend"))

    if not up(APP + "/login"):
        started.append(
            subprocess.Popen("npx vite --config e2e/vite.e2e.config.js", cwd=ROOT / "frontend", shell=True)
        )

    for _ in range(90):
        if up(BACKEND + "/__e2e/state") and up(APP + "/login"):
            return started
        time.sleep(1)

    raise SystemExit("E2E servers did not start")


# ---------------- page helpers ----------------

def fresh_page(browser, clock=False):
    api("/__e2e/reset", "POST")
    context = browser.new_context(viewport={"width": 1400, "height": 1000})
    page = context.new_page()
    page.on("pageerror", lambda error: page_errors.append(str(error)))

    if clock:
        page.clock.install()

    return page


def send_code_and_enter(page):
    """On the code screen: ask for a code, read it from the sandbox inbox, type it."""

    page.get_by_role("button", name="Send code").click()
    expect(page.locator(".au-sub", has_text="Code sent to")).to_be_visible(timeout=15000)
    page.get_by_placeholder("6-digit code").fill(api("/__e2e/last_code")["code"])  # auto-submits
    page.wait_for_url("**/home", timeout=15000)
    expect(page.get_by_text("E2E Test Page").first).to_be_visible(timeout=15000)


def password_login(page):
    page.goto(APP + "/login")
    page.get_by_placeholder("Email Address").fill("tester@example.com")
    page.get_by_placeholder("Password").fill("e2e-password")
    page.get_by_role("button", name="Login").click()
    expect(page.get_by_text("Check your email")).to_be_visible(timeout=15000)
    send_code_and_enter(page)


def tabs(page):
    return page.get_by_role("navigation", name="Sections")


def open_section(page, label, path):
    """Opens a dashboard page with its tab, unless it is open already."""

    if not page.url.endswith(path):
        tabs(page).get_by_role("link", name=re.compile(label)).click()
        page.wait_for_url("**" + path, timeout=15000)


def autopilot(page):
    open_section(page, "Autopilot", "/autopilot")
    return {
        "topic": page.get_by_placeholder(re.compile("limited time offer")),
        "go": page.get_by_role("button", name=re.compile("Create and post")),
        "consent": page.get_by_text(re.compile("I allow Marketing AI")),
        "picture": page.get_by_text("Create an AI picture"),
        "best": page.get_by_role("button", name="Post at the best time"),
        "error": page.locator("#ap-topic-error"),
    }


def ready_autopilot(page, topic="Summer sale on running shoes", consent=True):
    ap = autopilot(page)
    ap["topic"].fill(topic)

    if consent:
        ap["consent"].click()

    return ap


def wait_result(page, text, timeout=15000):
    expect(page.locator(".ap-card").get_by_text(text).first).to_be_visible(timeout=timeout)


def state():
    return api("/__e2e/state")


# ---------------- Autopilot ----------------

GARBAGE = ["123456", "1234563qrguoherjgnvsui", "!!!???", "aaaaaaaaaa", "asdfghjkl",
           "<script>alert(1)</script>", "😀😀😀😀😀😀😀😀😀😀😀", "x" * 600]


def test_garbage_never_reaches_ai(browser):
    page = fresh_page(browser)
    password_login(page)
    ap = autopilot(page)
    ap["consent"].click()

    for text in GARBAGE:
        ap["topic"].fill(text)
        shown = ap["error"].is_visible()
        disabled = ap["go"].is_disabled()
        ap["go"].click(force=True)
        check(f"garbage {text[:22]!r} shows an error and keeps the button disabled", shown and disabled)

    ap["topic"].fill("   ")
    check("blank topic is rejected", ap["error"].is_visible() and ap["go"].is_disabled())

    page.wait_for_timeout(500)
    check("no AI or Facebook call for any garbage input", state()["ai_calls"] == [] and state()["fb_calls"] == [])
    check("the example is shown in the error", "Summer sale on running shoes" in ap["error"].inner_text() if ap["error"].count() else False)
    page.context.close()


def test_server_rejects_what_the_ai_check_rejects(browser):
    page = fresh_page(browser)
    password_login(page)
    ap = ready_autopilot(page, "Lorem ipsum dolor sit amet")
    ap["go"].click()
    wait_result(page, "placeholder text")
    check("AI intent check stops a meaningless topic", state()["fb_calls"] == [])
    check("only the intent check ran", [c[0] for c in state()["ai_calls"]] == ["intent"])
    page.context.close()


def test_consent_is_required(browser):
    page = fresh_page(browser)
    password_login(page)
    ap = ready_autopilot(page, consent=False)
    check("valid topic without consent keeps the button disabled", ap["go"].is_disabled())
    ap["go"].click(force=True)
    page.wait_for_timeout(800)
    check("without consent nothing is published", state()["fb_calls"] == [] and state()["ai_calls"] == [])
    page.context.close()


def test_publish_with_picture_once_on_double_click(browser):
    page = fresh_page(browser)
    password_login(page)
    ap = ready_autopilot(page, "  SUMMER sale on Running Shoes  ")
    ap["go"].dblclick()
    wait_result(page, "Published just now")
    page.wait_for_timeout(800)
    calls = state()["fb_calls"]
    check("double click publishes exactly once", len(calls) == 1, calls)
    check("published as a photo post", calls and calls[0]["type"] == "photo")
    check("topic was trimmed before reaching the AI", ("post", "SUMMER sale on Running Shoes") in [tuple(c) for c in state()["ai_calls"]])
    check("hashtags rendered from the typed post", "#E2E #Test #Sale" in calls[0]["message"] if calls else False)
    page.context.close()


def test_publish_without_picture(browser):
    page = fresh_page(browser)
    password_login(page)
    ap = ready_autopilot(page, "Grand opening of our new cafe in Lahore this Friday")
    ap["picture"].click()
    ap["go"].click()
    wait_result(page, "Published just now")
    calls = state()["fb_calls"]
    check("picture unticked publishes a text post", len(calls) == 1 and calls[0]["type"] == "text", calls)
    check("no picture was generated", "image" not in [c[0] for c in state()["ai_calls"]])
    page.context.close()


def test_post_at_best_time(browser):
    page = fresh_page(browser)
    password_login(page)
    ap = ready_autopilot(page)
    ap["best"].click()
    ap["go"].click()
    wait_result(page, re.compile("Scheduled for"))
    calls = state()["fb_calls"]
    check("best time schedules instead of publishing", len(calls) == 1 and calls[0]["scheduled"], calls)
    page.context.close()


def test_urdu_topic(browser):
    page = fresh_page(browser)
    password_login(page)
    ap = ready_autopilot(page, "ہماری نئی بیکری کا افتتاح جمعہ کو ہے")
    check("Urdu topic is accepted", not ap["error"].is_visible() and ap["go"].is_enabled())
    page.context.close()


def test_image_failure_then_retry(browser):
    page = fresh_page(browser)
    password_login(page)
    api("/__e2e/fail/image/1", "POST")
    ap = ready_autopilot(page)
    ap["go"].click()
    wait_result(page, "Could not create the picture")
    check("failed picture says nothing was published", page.get_by_text(re.compile("Nothing was published")).is_visible())
    check("nothing published after the picture failed", state()["fb_calls"] == [])
    retry = page.get_by_role("button", name="Retry this step")
    check("failed step offers Retry", retry.count() == 1)
    retry.click()
    wait_result(page, "Published just now")
    check("retry continues and publishes once", len(state()["fb_calls"]) == 1)
    check("retry did not write the post again", [c[0] for c in state()["ai_calls"]].count("post") == 1)
    page.context.close()


def test_ai_timeout_then_retry(browser):
    page = fresh_page(browser)
    password_login(page)
    api("/__e2e/fail/post/1", "POST")
    ap = ready_autopilot(page)
    ap["go"].click()
    wait_result(page, "Could not write the post")
    check("AI timeout message shown", page.get_by_text(re.compile("took too long")).is_visible())
    page.get_by_role("button", name="Retry this step").click()
    wait_result(page, "Published just now")
    check("retry after AI timeout publishes once", len(state()["fb_calls"]) == 1)
    page.context.close()


def test_facebook_401_then_retry(browser):
    page = fresh_page(browser)
    password_login(page)
    api("/__e2e/fail/fb401/1", "POST")
    ap = ready_autopilot(page)
    ap["go"].click()
    wait_result(page, "Could not publish the post")
    check("expired Facebook token message shown", page.get_by_text(re.compile("Facebook connection has expired")).is_visible())
    check("nothing published on 401", state()["fb_calls"] == [])
    page.get_by_role("button", name="Retry this step").click()
    wait_result(page, "Published just now")
    check("retry after 401 publishes once", len(state()["fb_calls"]) == 1)
    page.context.close()


def test_network_offline(browser):
    page = fresh_page(browser)
    password_login(page)
    ap = ready_autopilot(page)
    page.context.set_offline(True)
    ap["go"].click()
    wait_result(page, "Could not reach the server")
    page.context.set_offline(False)
    check("offline shows a friendly error and publishes nothing", state()["fb_calls"] == [])
    page.context.close()


# ---------------- the code screen ----------------

def code_box(page):
    return page.get_by_placeholder("6-digit code")


def auth_error(page):
    return page.locator(".au-error")


def calls(page, name):
    return page.evaluate(f"window.__e2eCalls.{name}")


def google_click(page, mode="ok", start="/login"):
    page.goto(APP + start)
    page.evaluate(f"window.__e2eGoogle = {mode!r}")
    page.get_by_role("button", name="Google").click()

    if mode in ("ok", "unverified"):
        expect(page.get_by_text("Check your email")).to_be_visible(timeout=15000)


def send_code(page):
    page.get_by_role("button", name="Send code").click()
    expect(page.locator(".au-sub", has_text="Code sent to")).to_be_visible(timeout=15000)
    return api("/__e2e/last_code")


def paste(page, text):
    """A real paste event, as when the user pastes from the email."""

    code_box(page).focus()
    page.evaluate(
        """text => {
            const data = new DataTransfer();
            data.setData("text", text);
            document.activeElement.dispatchEvent(new ClipboardEvent("paste", { clipboardData: data, bubbles: true, cancelable: true }));
        }""",
        text,
    )


def test_google_success(browser):
    page = fresh_page(browser)
    google_click(page)
    check("code screen asks before sending", page.get_by_text(re.compile("We.ll send a 6-digit code to")).is_visible())
    check("nothing is sent until the user asks", state()["emails"] == 0)
    mail = send_code(page)
    expect(page.locator(".toast-success", has_text="Code sent")).to_be_visible()
    check("a 'Code sent' pop-up appears", True)
    check("code goes to the Google address", mail["to"] == ["owner@gmail.com"], mail["to"])
    check("email subject has no code in it", mail["code"] not in mail["subject"])
    code_box(page).fill(mail["code"])
    page.wait_for_url("**/home", timeout=15000)
    expect(page.get_by_text("E2E Test Page").first).to_be_visible(timeout=15000)
    check("right code opens the dashboard (auto-submit, no click)", True)
    page.reload()
    expect(page.get_by_text("E2E Test Page").first).to_be_visible(timeout=15000)
    check("session survives a reload after the code", page.url.endswith("/home"))
    page.context.close()


def test_password_login_needs_code(browser):
    page = fresh_page(browser)
    password_login(page)
    check("email login goes through the same code screen to the dashboard", page.url.endswith("/home"))
    page.context.close()


def test_dashboard_locked_before_code(browser):
    page = fresh_page(browser)
    google_click(page)
    page.goto(APP + "/home")
    expect(page.get_by_text("Check your email")).to_be_visible(timeout=15000)
    check("dashboard is not reachable before the code", page.get_by_text("Create and post").count() == 0)
    page.context.close()


def test_refresh_in_the_middle(browser):
    page = fresh_page(browser)
    google_click(page)
    mail = send_code(page)
    page.reload()
    expect(page.locator(".au-sub", has_text="Code sent to")).to_be_visible(timeout=15000)
    check("after a reload the screen still knows the code was sent", page.get_by_text(re.compile("expires in [0-9]:")).is_visible())
    expect(page.get_by_role("button", name=re.compile(r"Send a new code in \d+s"))).to_be_visible()
    check("the resend wait survives the reload", True)
    check("the reload sent no new email", state()["emails"] == 1)
    code_box(page).fill(mail["code"])
    page.wait_for_url("**/home", timeout=15000)
    check("the code still works after the reload", True)
    page.context.close()


def test_paste_code(browser):
    page = fresh_page(browser)
    google_click(page)
    mail = send_code(page)
    paste(page, f"Your code is {mail['code']}.")
    page.wait_for_url("**/home", timeout=15000)
    check("pasting the code (with extra text) signs in", True)
    page.context.close()


def test_digits_only(browser):
    page = fresh_page(browser)
    google_click(page)
    send_code(page)
    code_box(page).fill("12ab3")
    check("letters are dropped from the code box", code_box(page).input_value() == "123")
    page.context.close()


def test_google_cancel(browser):
    page = fresh_page(browser)
    google_click(page, "cancel")
    expect(auth_error(page)).to_contain_text("Google sign-in was cancelled.")
    check("cancelled popup shows a message and sends no email", state()["emails"] == 0)
    page.context.close()


def test_google_unverified_email(browser):
    page = fresh_page(browser)
    google_click(page, "unverified")
    page.get_by_role("button", name="Send code").click()
    expect(auth_error(page)).to_contain_text("email is not verified")
    check("unverified Google email gets no code", state()["emails"] == 0)
    check("unverified user is signed out again", page.get_by_role("button", name="Login").is_visible())
    page.context.close()


def test_wrong_code_then_lock(browser):
    page = fresh_page(browser)
    google_click(page)
    real = send_code(page)["code"]
    wrong = "000000" if real != "000000" else "111111"

    code_box(page).fill(wrong)
    expect(auth_error(page)).to_contain_text("4 tries left")
    check("wrong code shows tries left", True)

    for left in (3, 2, 1):
        code_box(page).fill(wrong)
        expect(auth_error(page)).to_contain_text(f"{left} tr")

    code_box(page).fill(wrong)
    expect(auth_error(page)).to_contain_text("Try again in 15 minutes")
    expect(page.get_by_text(re.compile("You can try again in 1[45]:"))).to_be_visible()
    check("5 wrong codes lock the sign-in for 15 minutes", "/home" not in page.url)
    check("during the lock the code box and sending are disabled", page.get_by_role("button", name="Send code").is_disabled())
    page.context.close()


def test_expired_code_then_resend(browser):
    page = fresh_page(browser, clock=True)
    google_click(page)
    first = send_code(page)["code"]
    resend = page.get_by_role("button", name=re.compile("Send a new code"))
    check("resend is disabled during the 60 second wait", resend.is_disabled())

    api("/__e2e/expire_otp", "POST")
    code_box(page).fill(first)
    expect(auth_error(page)).to_contain_text("code has expired")
    expect(page.get_by_text(re.compile("has expired. Send a new code"))).to_be_visible()
    check("expired code is refused and the screen offers a new one", True)

    page.get_by_role("button", name="Send code").click()
    expect(page.locator(".au-sub", has_text="Code sent to")).to_be_visible(timeout=15000)
    check("a new email was sent", state()["emails"] == 2)
    code_box(page).fill(api("/__e2e/last_code")["code"])
    page.wait_for_url("**/home", timeout=15000)
    check("the new code signs in", True)
    page.context.close()


def test_email_not_set_up_then_resend(browser):
    page = fresh_page(browser)
    api("/__e2e/fail/email/1", "POST")
    google_click(page, start="/signup")
    page.get_by_role("button", name="Send code").click()
    expect(auth_error(page)).to_contain_text("Email sending is not set up yet")
    text = auth_error(page).inner_text()
    check("email not set up: friendly message, no server details", "SMTP" not in text and ".env" not in text, text)
    send_code(page)
    code_box(page).fill(api("/__e2e/last_code")["code"])
    page.wait_for_url("**/home", timeout=15000)
    check("after email works, Send code + code signs in", True)
    page.context.close()


def test_logout_and_back_button(browser):
    page = fresh_page(browser)
    password_login(page)
    page.get_by_role("button", name=re.compile("Log ?out", re.I)).first.click()
    page.wait_for_url("**/login", timeout=15000)
    check("logout returns to the login page", True)
    page.go_back()
    page.wait_for_timeout(1500)
    check("back button after logout does not reopen the dashboard", page.get_by_text("Create and post").count() == 0)
    page.context.close()


# ---------------- Sign-up with email ----------------

def signup_form(page, name="Umer Irfan", email="new.owner@example.com", password="Secret-123", confirm=None):
    page.goto(APP + "/signup")
    page.get_by_placeholder("Full Name").fill(name)
    page.get_by_placeholder("Email Address").fill(email)
    page.get_by_placeholder("Password", exact=True).fill(password)
    page.get_by_placeholder("Confirm Password").fill(password if confirm is None else confirm)
    return page.get_by_role("button", name="Create account")


def test_signup_new_email(browser):
    page = fresh_page(browser)
    signup_form(page).click()
    expect(page.get_by_text("Check your email")).to_be_visible(timeout=15000)
    mail = send_code(page)
    check("sign-up code goes to the new address", mail["to"] == ["new.owner@example.com"], mail["to"])
    check("sign-up email says sign-up", "sign-up" in mail["subject"], mail["subject"])
    code_box(page).fill(mail["code"])
    page.wait_for_url("**/home", timeout=15000)
    expect(page.get_by_text("E2E Test Page").first).to_be_visible(timeout=15000)
    check("new email: sign up -> code -> dashboard", True)
    users = api("/__e2e/users")
    check("the name is saved on the account", users == [{"email": "new.owner@example.com", "name": "Umer Irfan"}], users)
    page.context.close()


def test_signup_existing_email(browser):
    page = fresh_page(browser)
    signup_form(page, email="taken.owner@example.com").click()
    expect(auth_error(page)).to_contain_text("already registered")
    text = auth_error(page).inner_text()
    check("existing email shows a friendly message", "Firebase" not in text and "auth/" not in text, text)
    auth_error(page).get_by_role("link", name="Log in").click()
    page.wait_for_url("**/login")
    check("Log in link keeps the email filled in", page.get_by_placeholder("Email Address").input_value() == "taken.owner@example.com")
    page.context.close()


def test_signup_form_checks(browser):
    page = fresh_page(browser)
    cases = [
        (dict(name="  "), "enter your name"),
        (dict(email=""), "enter your email"),
        (dict(email="not-an-email"), "valid email"),
        (dict(password="short7!"), "at least 8 characters"),
        (dict(password="secret-123"), "a capital letter"),
        (dict(password="Secret1234"), "a special character"),
        (dict(confirm="Different-123"), "do not match"),
    ]

    for fields, expected in cases:
        signup_form(page, **fields).click()
        expect(auth_error(page)).to_contain_text(expected)
        check(f"sign-up form check: {expected}", True)

    check("invalid forms never reach Firebase", calls(page, "createUser") == 0)

    signup_form(page, password="secret123", confirm="secret12")
    expect(page.locator(".au-hint.bad", has_text="don't match yet")).to_be_visible()
    check("checklist shows the missing capital letter", page.locator(".au-hint:not(.ok)", has_text="capital letter").is_visible())
    page.get_by_placeholder("Confirm Password").fill("secret123")
    expect(page.locator(".au-hint.ok", has_text="Passwords match")).to_be_visible()
    check("live hint shows while typing: mismatch, then match", True)
    page.context.close()


def test_signup_double_click(browser):
    page = fresh_page(browser)
    signup_form(page, email="double.click@example.com").dblclick()
    expect(page.get_by_text("Check your email")).to_be_visible(timeout=15000)
    check("double click creates the account once", calls(page, "createUser") == 1)
    page.context.close()


def test_signup_offline(browser):
    page = fresh_page(browser)
    button = signup_form(page, email="offline.owner@example.com")
    page.context.set_offline(True)
    button.click()
    expect(auth_error(page)).to_contain_text("No connection")
    page.context.set_offline(False)
    check("offline sign-up shows a connection message", True)
    page.context.close()


# ---------------- more Google cases ----------------

def test_google_popup_blocked_uses_redirect(browser):
    page = fresh_page(browser)
    page.goto(APP + "/login")
    page.evaluate("window.__e2eGoogle = 'blocked'")
    page.get_by_role("button", name="Google").click()
    expect(page.get_by_text("Check your email")).to_be_visible(timeout=15000)
    check("blocked pop-up falls back to redirect and reaches the code screen", True)
    send_code(page)
    code_box(page).fill(api("/__e2e/last_code")["code"])
    page.wait_for_url("**/home", timeout=15000)
    check("redirect sign-in finishes with the code", True)
    page.context.close()


def test_google_unauthorized_domain(browser):
    page = fresh_page(browser)
    google_click(page, "unauthorized")
    expect(auth_error(page)).to_contain_text("Authorized domains")
    check("unauthorized domain explains the Firebase setting", state()["emails"] == 0)
    page.context.close()


def test_google_existing_password_account(browser):
    page = fresh_page(browser)
    google_click(page, "exists")
    expect(auth_error(page)).to_contain_text("Log in with your password")
    check("existing password account is explained", True)
    page.context.close()


# ---------------- whole journey ----------------

def test_full_flow(browser):
    page = fresh_page(browser)
    signup_form(page, email="journey.owner@example.com").click()
    expect(page.get_by_text("Check your email")).to_be_visible(timeout=15000)
    send_code_and_enter(page)

    ap = autopilot(page)
    ap["consent"].click()
    ap["topic"].fill("1234563qrguoherjgnvsui")
    check("full flow: garbage topic blocked", ap["error"].is_visible() and ap["go"].is_disabled())
    ap["topic"].fill("Grand opening of our new cafe in Lahore this Friday")
    ap["go"].click()
    wait_result(page, "Published just now")
    check("full flow: sign up -> code -> dashboard -> valid post published once", len(state()["fb_calls"]) == 1)
    page.context.close()


# ---------------- forgot password ----------------

def test_forgot_password(browser):
    page = fresh_page(browser)
    page.goto(APP + "/login")
    page.get_by_placeholder("Email Address").fill("reset.owner@example.com")
    page.get_by_role("link", name="Forgot password?").click()
    page.wait_for_url("**/forgot-password")
    check("forgot password keeps the typed email", page.get_by_placeholder("Email Address").input_value() == "reset.owner@example.com")
    page.get_by_role("button", name="Send code").click()
    expect(page.get_by_text(re.compile("If an account exists for this email"))).to_be_visible(timeout=15000)
    mail = api("/__e2e/last_code")
    check("reset code goes to that email", mail["to"] == ["reset.owner@example.com"] and "password reset" in mail["subject"], mail)
    page.get_by_placeholder("6-digit code").fill(mail["code"])
    page.get_by_placeholder("New Password", exact=True).fill("Brand-new-pass1")
    page.get_by_placeholder("Confirm New Password").fill("Brand-new-pass1")
    page.get_by_role("button", name="Set new password").click()
    page.wait_for_url("**/login", timeout=15000)
    expect(page.locator(".toast-success", has_text="Password changed")).to_be_visible()
    expect(page.locator(".au-success", has_text="password has been changed")).to_be_visible()
    check("new password set, back on login with a notice", state()["password_changes"] == ["pw-reset-owner"])
    check("login has the email filled in", page.get_by_placeholder("Email Address").input_value() == "reset.owner@example.com")
    page.context.close()


def test_forgot_password_unknown_email_and_wrong_code(browser):
    page = fresh_page(browser)
    page.goto(APP + "/forgot-password")
    page.get_by_placeholder("Email Address").fill("nobody@example.com")
    page.get_by_role("button", name="Send code").click()
    expect(page.get_by_text(re.compile("If an account exists for this email"))).to_be_visible(timeout=15000)
    check("unknown email: same message, no email sent", state()["emails"] == 0)
    check("the reply is the same as for a real account", page.get_by_text(re.compile("If an account exists for this email")).is_visible())
    page.get_by_placeholder("6-digit code").fill("123456")
    page.get_by_placeholder("New Password", exact=True).fill("Brand-new-pass1")
    page.get_by_placeholder("Confirm New Password").fill("Brand-new-pass1")
    page.get_by_role("button", name="Set new password").click()
    expect(auth_error(page)).to_contain_text("not right or has expired")
    check("wrong code changes nothing", state()["password_changes"] == [])
    page.context.close()


def test_google_account_can_set_a_password(browser):
    page = fresh_page(browser)
    page.goto(APP + "/forgot-password")
    page.get_by_placeholder("Email Address").fill("owner@gmail.com")
    page.get_by_role("button", name="Send code").click()
    expect(page.locator(".au-success")).to_be_visible(timeout=15000)
    mail = api("/__e2e/last_code")
    check("a Google-only account also gets a reset code", mail["to"] == ["owner@gmail.com"], mail["to"])
    page.get_by_placeholder("6-digit code").fill(mail["code"])
    page.get_by_placeholder("New Password", exact=True).fill("weakpass")
    page.get_by_placeholder("Confirm New Password").fill("weakpass")
    page.get_by_role("button", name="Set new password").click()
    expect(auth_error(page)).to_contain_text("a capital letter")
    check("a weak new password is refused with what is missing", state()["password_changes"] == [])
    page.get_by_placeholder("6-digit code").fill(mail["code"])
    page.get_by_placeholder("New Password", exact=True).fill("Marketing@2026")
    page.get_by_placeholder("Confirm New Password").fill("Marketing@2026")
    page.get_by_role("button", name="Set new password").click()
    page.wait_for_url("**/login", timeout=15000)
    check("Google account now has a password", state()["password_changes"] == ["google-owner"])
    page.context.close()


def test_show_hide_password(browser):
    page = fresh_page(browser)

    for path, field in (("/login", "Password"), ("/signup", "Confirm Password")):
        page.goto(APP + path)
        box = page.get_by_placeholder(field, exact=True)
        box.fill("Secret-123")
        check(f"{path}: password hidden at first", box.get_attribute("type") == "password")
        page.get_by_role("button", name=f"Show {field.lower()}").click()
        check(f"{path}: Show reveals the password", box.get_attribute("type") == "text" and box.input_value() == "Secret-123")
        page.get_by_role("button", name=f"Hide {field.lower()}").click()
        check(f"{path}: Hide hides it again", box.get_attribute("type") == "password")

    page.context.close()


def test_toast_can_be_closed(browser):
    page = fresh_page(browser)
    google_click(page)
    send_code(page)
    toast = page.locator(".toast-success")
    expect(toast).to_be_visible()
    toast.get_by_role("button", name="Close notification").click()
    expect(toast).to_have_count(0)
    check("pop-up closes when clicked", True)
    page.context.close()


def test_choose_facebook_page(browser):
    page = fresh_page(browser)
    password_login(page)
    api("/__e2e/seed_pages", "POST")
    page.reload()
    switch = page.get_by_label("Facebook Page to post to")
    expect(switch).to_be_visible(timeout=15000)
    check("Page chooser lists both Pages", switch.locator("option").all_inner_texts() == ["Cake Corner", "Lahore Bakery"])
    check("the first Page is chosen at first", switch.input_value() == "111")

    switch.select_option("222")
    expect(page.locator(".toast-success", has_text="Page changed")).to_be_visible()
    autopilot(page)
    expect(page.get_by_text("I allow Marketing AI to publish this post on Cake Corner")).to_be_visible()
    check("Autopilot now names the chosen Page", True)

    ap = ready_autopilot(page, "Weekend sale on chocolate cakes")
    ap["go"].click()
    wait_result(page, "Published just now")
    calls = state()["fb_calls"]
    check("the post went to the chosen Page", len(calls) == 1 and calls[0]["page"] == "222", calls)

    page.reload()
    expect(page.get_by_label("Facebook Page to post to")).to_have_value("222", timeout=15000)
    check("the choice is remembered after a reload", True)
    page.context.close()


def test_single_page_has_no_chooser(browser):
    page = fresh_page(browser)
    password_login(page)
    check("with one Page there is no chooser", page.get_by_label("Facebook Page to post to").count() == 0)
    page.context.close()


# ---------------- dashboard pages ----------------

SECTIONS = [
    ("Overview", "/home", "What would you like to do?"),
    ("Autopilot", "/autopilot", "One-click Autopilot"),
    ("Create post", "/create", "Create Your Facebook Post"),
    ("7-day plan", "/plan", "Post every day for 7 days"),
    ("Scheduled", "/scheduled", "Nothing is scheduled"),
    ("History", "/history", "Your activity"),
]


def test_every_section_opens(browser):
    page = fresh_page(browser)
    password_login(page)

    for label, path, text in SECTIONS:
        tabs(page).get_by_role("link", name=re.compile(label)).click()
        page.wait_for_url("**" + path, timeout=15000)
        expect(page.get_by_text(text).first).to_be_visible(timeout=15000)
        active = tabs(page).locator("a.on").inner_text()
        check(f"{label} tab opens its own page and is highlighted", label in active, active)
        check(f"{label} page shows the Facebook bar", page.locator(".dx-fbbar").get_by_text("E2E Test Page").count() == 1)

    for label, path, text in SECTIONS:
        page.goto(APP + path)
        expect(page.get_by_text(text).first).to_be_visible(timeout=15000)
    check("every page opens directly by its address and after a reload", True)

    page.goto(APP + "/home")
    page.locator(".dx-shortcut", has_text="7-day plan").click()
    page.wait_for_url("**/plan", timeout=15000)
    check("Overview shortcut cards open their page", True)

    page.get_by_role("link", name="Marketing AI overview").click()
    page.wait_for_url("**/home", timeout=15000)
    check("the logo goes back to the Overview", True)

    page.goto(APP + "/no-such-page")
    page.wait_for_url("**/home", timeout=15000)
    check("an unknown address goes to the Overview", True)

    page.go_back()
    page.go_back()
    page.wait_for_url("**/plan", timeout=15000)
    check("the browser back button moves between pages", True)
    page.context.close()


def test_sections_need_sign_in(browser):
    page = fresh_page(browser)

    for _, path, _ in SECTIONS:
        page.goto(APP + path)
        page.wait_for_url("**/login", timeout=15000)

    check("every dashboard page sends a signed-out visitor to login", True)
    page.goto(APP + "/somewhere")
    page.wait_for_url(re.compile(r"5198/$"), timeout=15000)
    check("an unknown address while signed out goes to the intro page", True)
    page.context.close()


def test_create_post_page_publishes(browser):
    page = fresh_page(browser)
    password_login(page)
    open_section(page, "Create post", "/create")

    page.get_by_role("button", name="Post to Facebook").click()
    expect(page.get_by_text("Please write some content or select an image.")).to_be_visible()
    check("empty post is not published", state()["fb_calls"] == [])

    page.get_by_placeholder("Write your Facebook post here...").fill("Fresh bread every morning at 7")
    page.get_by_role("button", name="Post to Facebook").click()
    expect(page.get_by_text("Facebook post published successfully")).to_be_visible(timeout=15000)
    calls = state()["fb_calls"]
    check("Create post publishes the caption once", len(calls) == 1 and calls[0]["message"] == "Fresh bread every morning at 7", calls)

    open_section(page, "History", "/history")
    expect(page.get_by_text("Published posts (1)")).to_be_visible(timeout=15000)
    expect(page.get_by_text("Fresh bread every morning at 7")).to_be_visible()
    check("History shows the new post without a reload", True)

    open_section(page, "Overview", "/home")
    stat = page.locator(".dx-card", has_text="Posts published").first
    check("Overview counts the published post", "1" in stat.inner_text(), stat.inner_text())
    page.context.close()


def test_autopilot_schedule_updates_scheduled_tab(browser):
    page = fresh_page(browser)
    password_login(page)
    ap = ready_autopilot(page, "Weekend sale on running shoes")
    ap["best"].click()
    ap["go"].click()
    wait_result(page, re.compile("Scheduled for"), timeout=20000)

    count = tabs(page).locator(".dx-tab-count")
    expect(count).to_have_text("1", timeout=15000)
    check("the Scheduled tab shows how many posts wait", True)

    open_section(page, "Scheduled", "/scheduled")
    expect(page.locator(".sp-item")).to_have_count(1, timeout=15000)
    page.once("dialog", lambda dialog: dialog.accept())
    page.locator(".sp-item").get_by_role("button", name="Remove").click()
    expect(page.get_by_text("Nothing is scheduled")).to_be_visible(timeout=15000)
    expect(count).to_have_count(0, timeout=15000)
    check("removing the post empties the list and the tab count", True)
    page.context.close()


def test_clear_earlier_posts(browser):
    page = fresh_page(browser)
    password_login(page)
    api("/__e2e/seed_earlier", "POST")
    open_section(page, "Scheduled", "/scheduled")

    rows = page.locator(".sp-past")
    expect(rows).to_have_count(3, timeout=15000)
    check("Earlier lists the 3 finished posts with their status",
          [r.locator(".dx-chip").inner_text() for r in rows.all()] == ["Cancelled", "Removed", "Published"])
    check("a waiting post has no Clear button", page.locator(".sp-item:not(.sp-past)").get_by_role("button", name="Clear").count() == 0)

    page.get_by_role("button", name="Clear this cancelled post from the list").click()
    expect(page.locator(".toast-success", has_text="Cleared")).to_be_visible()
    expect(rows).to_have_count(2)
    check("Clear removes only that post", page.get_by_text("Cancelled tax offer").count() == 0)

    page.once("dialog", lambda dialog: dialog.dismiss())
    page.get_by_role("button", name="Clear all").click()
    page.wait_for_timeout(500)
    check("saying No to Clear all keeps the list", rows.count() == 2)

    page.once("dialog", lambda dialog: dialog.accept())
    page.get_by_role("button", name="Clear all").click()
    expect(page.locator(".toast-success", has_text="List cleared")).to_be_visible()
    expect(page.get_by_role("heading", name="Earlier")).to_have_count(0)
    check("Clear all empties Earlier", True)

    page.reload()
    expect(page.get_by_text("Waiting post for Friday")).to_be_visible(timeout=15000)
    check("cleared posts stay gone after a reload", rows.count() == 0)
    check("the waiting post is untouched", page.locator(".sp-item").count() == 1)
    check("Facebook was not contacted", state()["fb_calls"] == [])

    open_section(page, "History", "/history")
    expect(page.get_by_text("Published bread post")).to_be_visible(timeout=15000)
    check("the published post is still in History", True)
    page.context.close()


# ---------------- intro page ----------------

def in_view(page, text):
    expect(page.get_by_role("heading", name=re.compile(text))).to_be_in_viewport(timeout=5000)


def test_intro_scrolls(browser):
    page = fresh_page(browser)
    page.goto(APP + "/")
    expect(page.get_by_role("heading", name=re.compile("Your marketing, on"))).to_be_visible(timeout=15000)
    check("intro has no Next button", page.get_by_role("button", name=re.compile("Next")).count() == 0)
    check("intro has no section dots", page.locator(".in-dots, .in-dot").count() == 0)
    check("intro has no progress line", page.locator(".in-progress").count() == 0)

    page.mouse.move(700, 500)
    page.mouse.wheel(0, 1000)
    in_view(page, "Three jobs")
    check("the mouse wheel scrolls to the next section", True)

    page.keyboard.press("PageDown")
    in_view(page, "From idea to published post")
    check("Page Down scrolls one section", True)

    page.keyboard.press("Home")
    in_view(page, "Your marketing, on")
    page.get_by_role("button", name="See how it works").click()
    in_view(page, "Three jobs")
    check("See how it works scrolls to the features", True)

    page.keyboard.press("Home")
    in_view(page, "Your marketing, on")
    page.get_by_role("button", name="Scroll down").click()
    in_view(page, "Three jobs")
    check("the Scroll cue scrolls down", True)

    page.keyboard.press("End")
    create = page.get_by_role("link", name="Create account")
    expect(create).to_be_in_viewport(timeout=5000)
    check("End reaches the last section", True)
    create.click()
    page.wait_for_url("**/signup", timeout=15000)
    check("Create account at the end opens sign-up", True)
    page.context.close()

    phone = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True).new_page()
    phone.on("pageerror", lambda error: page_errors.append(str(error)))
    phone.goto(APP + "/")
    expect(phone.get_by_role("heading", name=re.compile("Your marketing, on"))).to_be_visible(timeout=15000)
    phone.evaluate("document.querySelector('.in-page').scrollTo(0, document.querySelector('.in-page').scrollHeight)")
    expect(phone.get_by_role("link", name="Create account")).to_be_in_viewport(timeout=5000)
    check("on a phone the intro scrolls to the end without sideways scroll",
          not phone.evaluate("document.querySelector('.in-page').scrollWidth > innerWidth + 1"))
    phone.context.close()


# ---------------- voice ----------------

# Chrome's built-in fake microphone (a steady tone) with permission granted automatically.
FAKE_MIC = ["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream"]

# Records what the app reads aloud instead of playing it.
SPEECH_SPY = """
window.__spoken = [];
Object.defineProperty(window, 'speechSynthesis', { configurable: true, value: {
  speak(u) { window.__spoken.push(u.text); setTimeout(() => u.onend && u.onend(), 300); },
  cancel() {}, getVoices() { return []; }, speaking: false,
}});
"""

VOICE_TEXT = "I run a bakery in Lahore and want more customers"


def record_voice(page, button_name, seconds=1.5):
    page.get_by_role("button", name=button_name).click()
    expect(page.get_by_text(re.compile("Listening"))).to_be_visible(timeout=10000)
    page.wait_for_timeout(int(seconds * 1000))
    page.get_by_role("button", name="Stop recording").click()


def test_voice_chat(browser):
    page = fresh_page(browser)
    page.add_init_script(SPEECH_SPY)
    password_login(page)
    open_section(page, "Create post", "/create")

    record_voice(page, "Speak to the assistant")
    expect(page.locator(".dx-bubble-user", has_text=VOICE_TEXT)).to_be_visible(timeout=15000)
    expect(page.get_by_text(f"Sure, here is a plan for {VOICE_TEXT}")).to_be_visible(timeout=15000)
    calls = [c[0] for c in state()["ai_calls"]]
    check("speech is turned into text and sent to the assistant", calls == ["voice", "chat"], calls)
    voice_call = next(c for c in state()["ai_calls"] if c[0] == "voice")
    check("a real recording is uploaded", voice_call[1] > 1000 and voice_call[2].startswith("audio/"), voice_call)
    check("the spoken message is marked with a mic", page.locator(".dx-bubble-user .dx-said").count() == 1)

    page.wait_for_function("window.__spoken.length === 1", timeout=5000)
    spoken = page.evaluate("window.__spoken[0]")
    check("the reply to a spoken message is read aloud", spoken.startswith("Sure, here is a plan for"), spoken)

    page.get_by_role("button", name="Read this reply aloud").last.click()
    expect(page.get_by_role("button", name="Stop reading aloud")).to_be_visible()
    check("Listen reads a reply again and shows Stop", page.evaluate("window.__spoken.length") == 2)

    page.get_by_role("button", name=re.compile("Voice replies on")).click()
    expect(page.get_by_role("button", name=re.compile("Voice replies off"))).to_be_visible()
    record_voice(page, "Speak to the assistant")
    expect(page.locator(".dx-bubble-user", has_text=VOICE_TEXT)).to_have_count(2, timeout=15000)
    expect(page.locator(".dx-bubble-ai", has_text="Sure, here is a plan for")).to_have_count(2, timeout=15000)
    page.wait_for_timeout(800)
    check("with voice replies off the reply is only shown", page.evaluate("window.__spoken.length") == 2)

    page.reload()
    expect(page.get_by_role("button", name=re.compile("Voice replies off"))).to_be_visible(timeout=15000)
    check("the voice replies choice is remembered", True)

    page.get_by_placeholder(re.compile("I run a bakery")).fill("Typed question")
    page.get_by_role("button", name="Send").click()
    expect(page.get_by_text("Sure, here is a plan for Typed question")).to_be_visible(timeout=15000)
    check("typing still works next to the mic", True)
    page.context.close()


def test_voice_autopilot_topic(browser):
    page = fresh_page(browser)
    password_login(page)
    ap = autopilot(page)

    record_voice(page, "Say what the post is about")
    expect(ap["topic"]).to_have_value(VOICE_TEXT, timeout=15000)
    check("speaking fills the Autopilot topic", True)
    check("nothing is published until the user confirms", state()["fb_calls"] == [])

    record_voice(page, "Say what the post is about", seconds=1)
    expect(ap["topic"]).to_have_value(f"{VOICE_TEXT} {VOICE_TEXT}", timeout=15000)
    check("speaking again adds to the topic instead of replacing it", True)
    page.context.close()


def test_voice_problems(browser):
    page = fresh_page(browser)
    password_login(page)
    open_section(page, "Create post", "/create")

    api("/__e2e/fail/voice/1", "POST")
    record_voice(page, "Speak to the assistant", seconds=1)
    expect(page.get_by_role("alert").filter(has_text="Could not reach the AI service")).to_be_visible(timeout=15000)
    check("a failed transcription shows a clear message", True)
    check("nothing is sent to the chat after a failure", [c[0] for c in state()["ai_calls"]] == ["voice"])

    record_voice(page, "Speak to the assistant", seconds=1)
    expect(page.locator(".dx-bubble-user", has_text=VOICE_TEXT)).to_be_visible(timeout=15000)
    check("trying again after a failure works", True)
    page.context.close()

    page = fresh_page(browser)
    page.add_init_script(
        "navigator.mediaDevices.getUserMedia = () => Promise.reject(new DOMException('blocked', 'NotAllowedError'));"
    )
    password_login(page)
    open_section(page, "Create post", "/create")
    page.get_by_role("button", name="Speak to the assistant").click()
    expect(page.get_by_text(re.compile("Microphone access is blocked"))).to_be_visible(timeout=10000)
    check("a blocked microphone explains how to allow it", state()["ai_calls"] == [])
    page.context.close()


TESTS = [
    test_garbage_never_reaches_ai,
    test_server_rejects_what_the_ai_check_rejects,
    test_consent_is_required,
    test_publish_with_picture_once_on_double_click,
    test_publish_without_picture,
    test_post_at_best_time,
    test_urdu_topic,
    test_image_failure_then_retry,
    test_ai_timeout_then_retry,
    test_facebook_401_then_retry,
    test_network_offline,
    test_google_success,
    test_password_login_needs_code,
    test_dashboard_locked_before_code,
    test_refresh_in_the_middle,
    test_paste_code,
    test_digits_only,
    test_google_cancel,
    test_google_unverified_email,
    test_wrong_code_then_lock,
    test_expired_code_then_resend,
    test_email_not_set_up_then_resend,
    test_logout_and_back_button,
    test_signup_new_email,
    test_signup_existing_email,
    test_signup_form_checks,
    test_signup_double_click,
    test_signup_offline,
    test_google_popup_blocked_uses_redirect,
    test_google_unauthorized_domain,
    test_google_existing_password_account,
    test_forgot_password,
    test_forgot_password_unknown_email_and_wrong_code,
    test_google_account_can_set_a_password,
    test_show_hide_password,
    test_toast_can_be_closed,
    test_choose_facebook_page,
    test_single_page_has_no_chooser,
    test_every_section_opens,
    test_sections_need_sign_in,
    test_create_post_page_publishes,
    test_autopilot_schedule_updates_scheduled_tab,
    test_clear_earlier_posts,
    test_intro_scrolls,
    test_voice_chat,
    test_voice_autopilot_topic,
    test_voice_problems,
    test_full_flow,
]


def main():
    started = start_servers()

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(args=FAKE_MIC)

            for test in TESTS:
                if not browser.is_connected():
                    # One crashed browser must not fail every test after it.
                    check("browser restarted after a crash", False)
                    browser = p.chromium.launch(args=FAKE_MIC)

                try:
                    test(browser)
                except Exception as error:  # a crash counts as a failure, the run goes on
                    check(test.__name__ + " (crashed)", False, f"{type(error).__name__}: {str(error)[:300]}")

            browser.close()

        check("no uncaught errors in the browser", not page_errors, page_errors[:3])
    finally:
        for process in started:
            process.terminate()

    failed = [name for name, ok in results if not ok]
    print(f"\n{len(results) - len(failed)} passed, {len(failed)} failed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
