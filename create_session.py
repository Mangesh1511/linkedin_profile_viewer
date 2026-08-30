#!/usr/bin/env python3
"""
LinkedIn Session File Creator

This script authenticates into LinkedIn using credentials from .env
(or interactive browser login if 2FA/CAPTCHA is triggered)
and automatically saves your authenticated cookies to `linkedin_session.json`.

Usage:
    python3 create_session.py
"""

import sys
import asyncio
from linkedin_profile_viewer.core import (
    BrowserManager,
    login_with_credentials,
    wait_for_manual_login,
    load_credentials_from_env,
)


async def create_session():
    print("=" * 60)
    print("LinkedIn Session Creator & Cookie Generator")
    print("=" * 60)

    email, password = load_credentials_from_env()
    session_path = "linkedin_session.json"

    # Start browser in headful mode if 2FA is needed, or headless if automated
    headless_mode = False
    print(f"\nLaunching Playwright Chromium browser (headless={headless_mode})...")

    browser = BrowserManager(headless=headless_mode)
    await browser.start()

    try:
        page = await browser.context.new_page()

        if email and password:
            print(f"🔑 Logging in automatically with credentials from .env ({email})...")
            try:
                await login_with_credentials(page, email=email, password=password, warm_up=True)
            except Exception as login_err:
                print(f"⚠️ Automated login notice: {login_err}")
                print("Falling back to manual login detection...")
                await page.goto("https://www.linkedin.com/login")
                await wait_for_manual_login(page, timeout=300000)
        else:
            print("⚠️ No credentials found in .env. Opening login page for manual authentication...")
            await page.goto("https://www.linkedin.com/login")
            await wait_for_manual_login(page, timeout=300000)

        # Save session to root directory
        print(f"\n💾 Saving authenticated session cookies to: {session_path}...")
        await browser.save_session(session_path)

        print("\n" + "=" * 60)
        print("✅ SUCCESS! Session file 'linkedin_session.json' created!")
        print("=" * 60 + "\n")

    finally:
        await browser.close()


if __name__ == "__main__":
    asyncio.run(create_session())
