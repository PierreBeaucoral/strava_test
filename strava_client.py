import time
from dataclasses import dataclass
from typing import Optional, List, Dict, Any

import requests
import pandas as pd
from dateutil import parser as dateparser


STRAVA_AUTH_URL = "https://www.strava.com/oauth/token"
STRAVA_ACTIVITIES_URL = "https://www.strava.com/api/v3/athlete/activities"


@dataclass
class StravaTokens:
    access_token: str
    refresh_token: str
    expires_at: int  # unix timestamp


class StravaClient:
    def __init__(self, client_id: str, client_secret: str, refresh_token: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.refresh_token = refresh_token
        self.tokens: Optional[StravaTokens] = None

    def _refresh_access_token(self) -> None:
        """Refresh the access token using the refresh token."""
        payload = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": "refresh_token",
            "refresh_token": self.refresh_token,
        }
        resp = requests.post(STRAVA_AUTH_URL, data=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        self.tokens = StravaTokens(
            access_token=data["access_token"],
            refresh_token=data["refresh_token"],
            expires_at=data["expires_at"],
        )
        # In case Strava rotates the refresh token
        self.refresh_token = data["refresh_token"]

    def _ensure_token(self) -> None:
        """Ensure we have a valid, non-expired token."""
        if self.tokens is None or self.tokens.expires_at <= int(time.time()) + 60:
            self._refresh_access_token()

    def _get_headers(self) -> Dict[str, str]:
        self._ensure_token()
        return {"Authorization": f"Bearer {self.tokens.access_token}"}

    def get_recent_activities(
        self,
        max_activities: int = 1000,
        per_page: int = 200,
    ) -> List[Dict[str, Any]]:
        """
        Fetch recent activities (up to max_activities).
        Strava paginates; per_page max is 200.
        """
        self._ensure_token()
        headers = self._get_headers()

        activities: List[Dict[str, Any]] = []
        page = 1

        while len(activities) < max_activities:
            params = {"page": page, "per_page": per_page}
            resp = requests.get(
                STRAVA_ACTIVITIES_URL, headers=headers, params=params, timeout=30
            )
            resp.raise_for_status()
            chunk = resp.json()
            if not chunk:
                break
            activities.extend(chunk)
            page += 1

        return activities[:max_activities]

    @staticmethod
    def activities_to_df(raw_acts: List[Dict[str, Any]]) -> pd.DataFrame:
        """Convert raw Strava JSON to a clean DataFrame."""
        if not raw_acts:
            return pd.DataFrame()

        df = pd.json_normalize(raw_acts)

        # Standardize and keep useful columns
        cols = {
            "id": "activity_id",
            "name": "name",
            "type": "sport",
            "sport_type": "sport_type",
            "distance": "distance_m",
            "moving_time": "moving_time_s",
            "elapsed_time": "elapsed_time_s",
            "total_elevation_gain": "elev_gain_m",
            "start_date_local": "start_date_local",
            "average_speed": "avg_speed_mps",
            "max_speed": "max_speed_mps",
            "average_heartrate": "avg_hr",
            "max_heartrate": "max_hr",
            "average_cadence": "avg_cadence",
            "kilojoules": "kilo_joules",
            "has_heartrate": "has_hr",
            "suffer_score": "suffer_score",
        }

        keep = [c for c in cols.keys() if c in df.columns]
        df = df[keep].rename(columns=cols)

        # Fix sport column: prefer sport_type if present
        if "sport_type" in df.columns:
            df["sport"] = df["sport_type"].fillna(df.get("sport", None))

        # Parse dates
        df["start_date_local"] = pd.to_datetime(df["start_date_local"].apply(
            lambda x: dateparser.parse(x) if isinstance(x, str) else pd.NaT
        ))

        # Convenience columns
        df["date"] = df["start_date_local"].dt.date
        df["year"] = df["start_date_local"].dt.year
        df["month"] = df["start_date_local"].dt.to_period("M").dt.to_timestamp()
        df["week"] = df["start_date_local"].dt.to_period("W").dt.start_time

        # Convert units
        df["distance_km"] = df["distance_m"] / 1000.0
        df["moving_time_h"] = df["moving_time_s"] / 3600.0
        df["elev_gain_m"] = df["elev_gain_m"].fillna(0.0)

        # Pace (min/km) for runs
        df["pace_min_per_km"] = None
        run_mask = df["distance_km"] > 0
        df.loc[run_mask, "pace_min_per_km"] = (
            df.loc[run_mask, "moving_time_s"] / 60.0 / df.loc[run_mask, "distance_km"]
        )

        return df
