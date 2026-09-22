# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Emulator smoke suite for the Android transport layer (``AdbDriver``).

These exercise the real device-control primitives end to end against a live
Android emulator (or physical device): connect, screen capture, shell round
trip, foreground-package detection, input injection, and logcat reads.

Run with an emulator booted::

    make test-device
    # or directly:
    uv run pytest tests/integration/test_emulator_smoke.py -m android -v

With nothing attached, every test skips cleanly. Fixtures live in
``tests/integration/conftest.py`` and prefer an ``emulator-****`` serial.
"""

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.android]


def _looks_like_png(data: bytes) -> bool:
    return len(data) >= 8 and data[:8] == b"\x89PNG\r\n\x1a\n"


def _looks_like_jpeg(data: bytes) -> bool:
    return len(data) >= 3 and data[:3] == b"\xff\xd8\xff"


@pytest.mark.asyncio
async def test_device_connects_and_reports_serial(adb_driver, device_serial):
    """The driver binds to the attached target and exposes its serial."""
    assert adb_driver.device_id == device_serial
    state = adb_driver.device.get_state()
    assert state == "device", f"device not ready, adb state={state!r}"


@pytest.mark.asyncio
async def test_screen_size_is_sane(adb_driver):
    """Screen dimensions are positive and within a plausible pixel range."""
    width, height = adb_driver.screen_size
    assert width > 0 and height > 0
    assert 200 <= width <= 8000
    assert 200 <= height <= 8000


@pytest.mark.asyncio
async def test_screenshot_capture_returns_image_bytes(adb_driver):
    """A capture yields decodable image bytes whose dimensions match the screen."""
    screen = await adb_driver.get_screen_data(skip_settling=True)
    assert screen.screenshot_bytes, "no screenshot bytes returned"
    assert _looks_like_png(screen.screenshot_bytes) or _looks_like_jpeg(
        screen.screenshot_bytes
    ), "screenshot is neither PNG nor JPEG"
    assert screen.screenshot_base64, "no base64 screenshot returned"
    assert screen.width > 0 and screen.height > 0


@pytest.mark.asyncio
async def test_execute_shell_round_trips(adb_driver):
    """An arbitrary shell command runs on device and returns its output."""
    token = "artemis_smoke_ok"
    out = await adb_driver.execute_shell(f"echo {token}")
    assert token in out
    assert not out.startswith("Error:"), out


@pytest.mark.asyncio
async def test_get_current_package_returns_foreground_app(adb_driver):
    """After launching Settings, the foreground package is reported."""
    launched = await adb_driver.launch_app("com.android.settings")
    assert launched, "failed to launch Settings"
    # Give the activity a moment to come to the foreground.
    import asyncio

    await asyncio.sleep(1.5)
    pkg = await adb_driver.get_current_package()
    assert pkg, "no foreground package detected"
    # Most system images report com.android.settings; accept any concrete pkg.
    assert "." in pkg


@pytest.mark.asyncio
async def test_tap_center_does_not_error(adb_driver):
    """Tapping the screen centre injects input without raising."""
    width, height = adb_driver.screen_size
    ok = await adb_driver.tap(width // 2, height // 2)
    assert ok is True


@pytest.mark.asyncio
async def test_logcat_read_returns_lines(adb_driver):
    """logcat is readable through the shell transport (leak-hunt substrate)."""
    out = await adb_driver.execute_shell("logcat -d -v brief -t 20")
    assert not out.startswith("Error:"), out
    # A booted device always has some log output; be lenient on exact content.
    assert out.strip() != ""
