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

"""Shared fixtures for integration tests that drive a live Android target.

Everything here skips cleanly when no emulator or device is attached, so the
suite is safe to run on a machine with nothing plugged in. Emulator serials
(``emulator-****``) are preferred over physical devices when both are present.
"""

import os

import pytest
import pytest_asyncio

try:
    from adbutils import AdbClient
except Exception:  # pragma: no cover - adbutils is a hard dep in practice
    AdbClient = None  # type: ignore[assignment]

from artemis.drivers.android.adb_driver import AdbDriver


def _adb_client() -> "AdbClient":
    host = os.environ.get("ADB_HOST", "127.0.0.1")
    port = int(os.environ.get("ADB_PORT", "5037"))
    return AdbClient(host=host, port=port)


@pytest.fixture(scope="session")
def adb_client():
    """A live adb client, or a skip when adb is unavailable."""
    if AdbClient is None:
        pytest.skip("adbutils is not installed")
    try:
        client = _adb_client()
        client.device_list()  # forces a connection to the adb server
    except Exception as exc:
        pytest.skip(f"No reachable adb server: {exc}")
    return client


@pytest.fixture(scope="session")
def device_serial(adb_client) -> str:
    """The target serial. Prefers an emulator; skips when nothing is attached.

    Override with ADB_DEVICE_SERIAL to pin a specific target.
    """
    pinned = os.environ.get("ADB_DEVICE_SERIAL")
    devices = adb_client.device_list()
    serials = [d.serial for d in devices]
    if not serials:
        pytest.skip("No active Android emulator or device detected")
    if pinned:
        if pinned not in serials:
            pytest.skip(f"Pinned ADB_DEVICE_SERIAL={pinned} not in {serials}")
        return pinned
    emulators = [s for s in serials if s.startswith("emulator-")]
    return emulators[0] if emulators else serials[0]


@pytest_asyncio.fixture
async def adb_driver(adb_client, device_serial) -> AdbDriver:
    """A connected AdbDriver bound to the live target.

    Screen size is synced from the device so downstream coordinate math is real.
    """
    driver = AdbDriver(device_id=device_serial, adb_client=adb_client)
    await driver.connect()
    try:
        screen = await driver.get_screen_data(skip_settling=True)
        driver._width = screen.width or driver._width
        driver._height = screen.height or driver._height
    except Exception:
        # Non-fatal: individual tests assert on their own captures.
        pass
    yield driver
    await driver.disconnect()
