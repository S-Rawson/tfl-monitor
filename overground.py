"""Lightweight overground departures fetcher.

This module exposes an async compatibility function
``get_live_overground_trains`` and an ``Overground`` class which
breaks the work into smaller, testable steps.

The public behavior is preserved: a DataFrame is returned with the same
columns and sorting logic. Network and parsing errors are logged and
problematic items are skipped.
"""

from __future__ import annotations

import asyncio
import httpx
import pandas as pd
import json
import re
import logging
from typing import Any

logger = logging.getLogger(__name__)


class Overground:
    """Fetch and parse overground departures from a route-search API.

    The class isolates HTTP I/O, payload extraction and item parsing so each
    step is small and testable.
    """

    def __init__(self, client: httpx.AsyncClient, api_url: str, auth: tuple | None = None) -> None:
        self.client = client
        self.api_url = api_url.rstrip("/")
        self.auth = auth

    async def fetch_services(self, frm: str, to: str) -> list[dict]:
        """Call the provider endpoint and return the list-like 'services'.

        Network errors and invalid JSON cause an empty list to be returned; the
        caller will treat an empty list as "no services".
        """
        url = f"{self.api_url}/json/search/{frm}/to/{to}"
        try:
            if self.auth and isinstance(self.auth, (list, tuple)) and len(self.auth) == 2:
                auth_obj = httpx.BasicAuth(self.auth[0], self.auth[1])
                resp = await self.client.get(url, auth=auth_obj)
            else:
                resp = await self.client.get(url, auth=self.auth)
        except httpx.RequestError as exc:
            logger.warning("Network error fetching %s: %s", url, exc)
            return []

        if resp.status_code != 200:
            return []

        try:
            payload = json.loads(resp.text)
        except json.JSONDecodeError:
            logger.warning("Invalid JSON from %s", url)
            return []

        return self._extract_services(payload)

    def _extract_services(self, payload: Any) -> list[dict]:
        """Normalize common payload shapes to a list of service items.

        Accept either a mapping with keys like 'services' or 'departures', or a
        top-level list.
        """
        if isinstance(payload, dict):
            return payload.get("services") or payload.get("departures") or []
        if isinstance(payload, list):
            return payload
        return []

    def _parse_item(self, item: dict, name: str, frm: str, to: str) -> dict | None:
        """Parse a single service item into a row dict or return None if missing data."""
        if not isinstance(item, dict):
            return None

        loc = item.get("locationDetail") or {}
        runDate = item.get("runDate") or item.get("serviceDate")

        # Destination extraction: support list/dict/scalar shapes
        dest = ""
        loc_dest = loc.get("destination") if isinstance(loc, dict) else None
        match loc_dest:
            case list() if loc_dest:
                last = loc_dest[-1]
                dest = last.get("description") if isinstance(last, dict) else str(last)
            case dict():
                dest = loc_dest.get("description", "")
            case _:
                dest = item.get("destination") or item.get("destinationName") or ""

        # platform
        platform = (
            (loc.get("platform") if isinstance(loc, dict) else None)
            or (loc.get("platformName") if isinstance(loc, dict) else None)
            or ""
        )

        expected_raw = (
            (loc.get("realtimeDeparture") if isinstance(loc, dict) else None)
            or (loc.get("gbttBookedDeparture") if isinstance(loc, dict) else None)
            or (loc.get("workingTime") if isinstance(loc, dict) else None)
            or item.get("expected")
            or item.get("expectedArrival")
        )

        if not expected_raw or not runDate:
            return None

        s = str(expected_raw).zfill(4)
        hh = s[-4:-2]
        mm = s[-2:]

        run_date_norm = runDate
        if isinstance(runDate, str) and re.fullmatch(r"\d{8}", runDate):
            run_date_norm = f"{runDate[:4]}-{runDate[4:6]}-{runDate[6:]}"

        expected_iso = f"{run_date_norm}T{hh}:{mm}:00Z"
        expected_time = f"{hh}:{mm}"
        expected_date = f"{run_date_norm}"

        _line = item.get("atocName") or item.get("service") or item.get("operator") or ""
        line_abbr = "".join([word[0] for word in _line.split()])

        return {
            "route": name,
            "stationFrom": frm,
            "stationTo": to,
            "destination": dest,
            "platform": platform,
            "expectedTime": expected_time,
            "expectedDate": expected_date,
            "TimeToArrival": "",
            "Line": line_abbr,
            "_expected_iso": expected_iso,
        }

    async def get_live_trains(self, routes: list[dict]) -> pd.DataFrame:
        """Main orchestration: iterate routes, collect rows and return a DataFrame."""
        cols: list[str] = [
            "route",
            "stationFrom",
            "stationTo",
            "destination",
            "platform",
            "expectedTime",
            "expectedDate",
            "TimeToArrival",
            "Line",
        ]

        rows: list[dict] = []

        if not routes or not self.api_url:
            return pd.DataFrame(columns=pd.Index(cols))

        for route in routes:
            if not isinstance(route, dict):
                continue

            name = route.get("name") or f"{route.get('from')}→{route.get('to')}"
            pairs = [(route.get("from"), route.get("to"))]
            if route.get("bidirectional"):
                pairs.append((route.get("to"), route.get("from")))

            for frm, to in pairs:
                if not frm or not to:
                    continue

                services = await self.fetch_services(frm, to)
                for item in services:
                    parsed = self._parse_item(item, name, frm, to)
                    if parsed:
                        rows.append(parsed)

                # polite pause
                await asyncio.sleep(0.05)

        if not rows:
            return pd.DataFrame(columns=pd.Index(cols))

        df = pd.DataFrame(rows, columns=pd.Index(cols + ["_expected_iso"]))

        # Ensure internal ISO timestamp column exists by combining expectedDate and expectedTime
        def _make_iso(r):
            date = r.get("expectedDate") or ""
            time = r.get("expectedTime") or ""
            if date and time:
                return f"{date}T{time}:00Z"
            return pd.NA

        df["_expected_iso"] = df.apply(_make_iso, axis=1)

        # Parse internal ISO timestamps to datetimes (UTC) and drop rows without a parsable time
        df["expected_dt"] = pd.to_datetime(df["_expected_iso"], utc=True, errors="coerce")
        df = df.dropna(subset=["expected_dt"])
        if df.empty:
            return df

        # Sort by expected time, then take up to 3 per direction (from->to)
        df = df.sort_values("expected_dt")
        df_limited = df.groupby(["stationFrom", "stationTo"], sort=False).head(3).copy()

        # Recompute TimeToArrival relative to now
        now = pd.Timestamp.utcnow()

        def fmt_td(td):
            try:
                secs = int(td.total_seconds())
                if secs < 0:
                    secs = 0
                mins = secs // 60
                s = secs % 60
                return f"{mins} m {s} s"
            except Exception:
                return ""

        df_limited["TimeToArrival"] = (df_limited["expected_dt"] - now).apply(fmt_td)

        # Final ordering by time
        df_limited = df_limited.sort_values("expected_dt")
        # drop internal helper columns before returning
        df_limited = df_limited.drop(columns=["expected_dt", "_expected_iso"])
        df_limited.reset_index(drop=True, inplace=True)
        return df_limited


async def get_live_overground_trains(
    client: httpx.AsyncClient, routes: list, api_url: str, auth: tuple | None = None
) -> pd.DataFrame:
    """Compatibility wrapper matching the previous module function signature.

    Creates an Overground and delegates the work to it.
    """
    fetcher = Overground(client, api_url, auth)
    return await fetcher.get_live_trains(routes)
