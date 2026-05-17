"""
Fetch program data from Almedalsveckan organizer portal.

Strategy:
1. Open the portal in headless Chromium with Playwright
2. Log in with username/password from environment variables
3. Capture the JWT token from network traffic or localStorage
4. Use the JWT to call the JSON export endpoint directly
5. Save the result to data/program.json

Why Playwright instead of plain HTTP requests:
The login uses a challenge-response mechanism where the "username" and
"credentials" fields in the login POST are derived from the real password
plus a per-session nonce returned by the server. Replaying these values
fails because the nonce rotates. A real browser handles this transparently.
"""

import os
import sys
import json
import re
import time
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
import requests

PORTAL_URL = "https://evenemangsportal.almedalsveckan.info/"
EXPORT_URL = "https://alme.inadra.se/export/json"
OUTPUT_PATH = Path("data/program.json")
LAST_RUN_PATH = Path("data/last_run.json")

USERNAME = os.environ.get("ALME_USERNAME", "").strip()
PASSWORD = os.environ.get("ALME_PASSWORD", "").strip()

if not USERNAME or not PASSWORD:
    print("ERROR: ALME_USERNAME and ALME_PASSWORD must be set as env vars", file=sys.stderr)
    sys.exit(1)


def find_login_inputs(page):
    """Try to locate email and password inputs robustly."""
    # Try several common selectors
    email_selectors = [
        'input[type="email"]',
        'input[name="email"]',
        'input[name="username"]',
        'input[autocomplete="username"]',
        'input[autocomplete="email"]',
        'input[placeholder*="post" i]',
        'input[placeholder*="mail" i]',
        'input[placeholder*="namn" i]',
    ]
    password_selectors = [
        'input[type="password"]',
        'input[name="password"]',
        'input[autocomplete="current-password"]',
    ]

    email_input = None
    for sel in email_selectors:
        loc = page.locator(sel).first
        if loc.count() > 0 and loc.is_visible():
            email_input = loc
            break

    password_input = None
    for sel in password_selectors:
        loc = page.locator(sel).first
        if loc.count() > 0 and loc.is_visible():
            password_input = loc
            break

    return email_input, password_input


def find_submit_button(page):
    """Locate the login submit button."""
    selectors = [
        'button[type="submit"]',
        'input[type="submit"]',
        'button:has-text("Logga in")',
        'button:has-text("Login")',
        'button:has-text("Sign in")',
        'button:has-text("Logga")',
    ]
    for sel in selectors:
        loc = page.locator(sel).first
        if loc.count() > 0 and loc.is_visible():
            return loc
    return None


def extract_jwt_from_storage(page):
    """Look for JWT in localStorage or sessionStorage."""
    for storage_type in ['localStorage', 'sessionStorage']:
        keys = page.evaluate(f"Object.keys(window.{storage_type})")
        for key in keys:
            value = page.evaluate(f"window.{storage_type}.getItem({json.dumps(key)})")
            if not value:
                continue
            # JWT pattern: eyJxxx.yyy.zzz
            if isinstance(value, str) and value.startswith('eyJ') and value.count('.') == 2:
                print(f"Found JWT in {storage_type}[{key}]")
                return value
            # Sometimes JWT is wrapped in a JSON object
            try:
                obj = json.loads(value)
                if isinstance(obj, dict):
                    for v in obj.values():
                        if isinstance(v, str) and v.startswith('eyJ') and v.count('.') == 2:
                            print(f"Found JWT in {storage_type}[{key}] (wrapped)")
                            return v
            except (json.JSONDecodeError, TypeError):
                pass
    return None


def main():
    jwt_token = None
    captured_requests = []

    print(f"Starting Playwright at {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        # Intercept network responses to capture JWT from login response
        def on_response(response):
            url = response.url
            if 'login' in url.lower() and response.request.method == 'POST':
                try:
                    body = response.json()
                    if isinstance(body, dict):
                        for k, v in body.items():
                            if isinstance(v, str) and v.startswith('eyJ') and v.count('.') == 2:
                                captured_requests.append({'source': 'login_response', 'key': k, 'token': v})
                                print(f"Captured JWT from login response key={k}")
                except Exception:
                    pass
            # Also catch Authorization headers on outgoing requests via request handler
        page.on('response', on_response)

        def on_request(request):
            auth = request.headers.get('authorization') or request.headers.get('Authorization')
            if auth and auth.lower().startswith('bearer '):
                token = auth.split(' ', 1)[1].strip()
                if token.startswith('eyJ') and token.count('.') == 2:
                    captured_requests.append({'source': 'request_header', 'url': request.url, 'token': token})
        page.on('request', on_request)

        print(f"Navigating to {PORTAL_URL}")
        page.goto(PORTAL_URL, wait_until='networkidle', timeout=60000)

        # Some portals show a landing page before login form. Try to navigate to login.
        # Wait for inputs to appear
        print("Looking for login inputs...")
        page.wait_for_timeout(2000)

        email_input, password_input = find_login_inputs(page)

        # If no inputs visible, try clicking a "Logga in" link
        if not email_input or not password_input:
            print("No login inputs found on landing page, trying to click a login link")
            for link_text in ["Logga in", "Login", "Sign in", "Logga"]:
                try:
                    link = page.get_by_text(link_text, exact=False).first
                    if link.count() > 0 and link.is_visible():
                        link.click()
                        page.wait_for_timeout(2000)
                        email_input, password_input = find_login_inputs(page)
                        if email_input and password_input:
                            break
                except Exception:
                    pass

        if not email_input or not password_input:
            # Dump page state for debugging
            html = page.content()
            print("FAILED to find login inputs. Page HTML snippet:")
            print(html[:3000])
            raise RuntimeError("Could not find login form")

        print("Filling credentials")
        email_input.fill(USERNAME)
        password_input.fill(PASSWORD)

        submit = find_submit_button(page)
        if submit:
            print("Clicking submit button")
            submit.click()
        else:
            print("No submit button found, pressing Enter on password field")
            password_input.press('Enter')

        # Wait for navigation/network to settle after login
        try:
            page.wait_for_load_state('networkidle', timeout=30000)
        except PWTimeout:
            print("Network did not go idle in 30s, continuing anyway")

        page.wait_for_timeout(3000)

        # Now JWT should be available either in captured_requests or in storage
        if captured_requests:
            jwt_token = captured_requests[0]['token']
            print(f"Using captured JWT (source={captured_requests[0]['source']})")
        else:
            print("No JWT captured from network, checking storage")
            jwt_token = extract_jwt_from_storage(page)

        if not jwt_token:
            # Last resort: navigate to download page and capture token from that request
            print("Trying download-program page to trigger token usage")
            try:
                page.goto("https://evenemangsportal.almedalsveckan.info/download-program",
                          wait_until='networkidle', timeout=30000)
                page.wait_for_timeout(2000)
                if captured_requests:
                    jwt_token = captured_requests[-1]['token']
            except Exception as e:
                print(f"Failed: {e}")

        browser.close()

    if not jwt_token:
        print("ERROR: Failed to obtain JWT after login attempt", file=sys.stderr)
        sys.exit(2)

    print(f"Got JWT (length={len(jwt_token)}), fetching JSON from {EXPORT_URL}")

    # Now fetch the JSON via plain requests with the JWT
    resp = requests.get(
        EXPORT_URL,
        headers={
            'Accept': 'application/json',
            'Authorization': f'Bearer {jwt_token}',
            'Origin': 'https://evenemangsportal.almedalsveckan.info',
            'Referer': 'https://evenemangsportal.almedalsveckan.info/',
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
                          '(KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36',
        },
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()

    print(f"Got JSON: {len(resp.content)} bytes")

    # Save raw JSON
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(data, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')

    # Save last-run metadata
    LAST_RUN_PATH.write_text(json.dumps({
        'timestamp': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'bytes': len(resp.content),
        'top_level_keys': list(data.keys()) if isinstance(data, dict) else None,
        'event_count': (
            len(data) if isinstance(data, list)
            else len(data.get('events', data.get('data', [])))
            if isinstance(data, dict) else None
        ),
    }, ensure_ascii=False, indent=2), encoding='utf-8')

    print(f"Saved to {OUTPUT_PATH}")


if __name__ == '__main__':
    main()
