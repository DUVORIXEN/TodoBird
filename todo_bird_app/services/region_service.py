"""
TODO BIRD — Region Service (countries & regional defaults)

Country coverage comes from the offline system tz database (the same source
the World Clock uses), so every ISO-3166 country is available without any
network access. On top of that catalog this service carries a regional
profile map — typical working week, 12/24-hour clock, and date style — used
by the "Apply Region Defaults" action in Settings → Language & Region.

Applying defaults is ALWAYS an explicit user action: the service never
silently rewrites a working week the user has already customized.
"""

from dataclasses import dataclass
from typing import Dict, Optional

# Weekday indices follow WEEKDAY_NAMES in services/working_week.py
# (0 = Monday … 6 = Sunday).
DAY_MON, DAY_TUE, DAY_WED, DAY_THU, DAY_FRI, DAY_SAT, DAY_SUN = range(7)

# date styles: DMY = 25/12/2026, MDY = 12/25/2026, YMD = 2026-12-25


@dataclass(frozen=True)
class RegionProfile:
    first_working_day: int = DAY_MON
    working_days: tuple = (DAY_MON, DAY_TUE, DAY_WED, DAY_THU, DAY_FRI)
    use_24h: bool = True
    date_style: str = "dmy"  # dmy | mdy | ymd


# Region profiles for major countries; everything else falls back to DEFAULT_PROFILE.
_REGION_PROFILES: Dict[str, RegionProfile] = {
    # Americas
    "US": RegionProfile(DAY_MON, (DAY_MON, DAY_TUE, DAY_WED, DAY_THU, DAY_FRI), False, "mdy"),
    "CA": RegionProfile(DAY_MON, (DAY_MON, DAY_TUE, DAY_WED, DAY_THU, DAY_FRI), False, "ymd"),
    "BR": RegionProfile(DAY_MON, (DAY_MON, DAY_TUE, DAY_WED, DAY_THU, DAY_FRI), True, "dmy"),
    "MX": RegionProfile(DAY_MON, (DAY_MON, DAY_TUE, DAY_WED, DAY_THU, DAY_FRI), True, "dmy"),
    "AR": RegionProfile(DAY_MON, (DAY_MON, DAY_TUE, DAY_WED, DAY_THU, DAY_FRI), True, "dmy"),
    "CO": RegionProfile(DAY_MON, (DAY_MON, DAY_TUE, DAY_WED, DAY_THU, DAY_FRI), True, "dmy"),
    "CL": RegionProfile(DAY_MON, (DAY_MON, DAY_TUE, DAY_WED, DAY_THU, DAY_FRI), True, "dmy"),
    # Europe
    "GB": RegionProfile(DAY_MON, (DAY_MON, DAY_TUE, DAY_WED, DAY_THU, DAY_FRI), True, "dmy"),
    "IE": RegionProfile(DAY_MON, (DAY_MON, DAY_TUE, DAY_WED, DAY_THU, DAY_FRI), True, "dmy"),
    "DE": RegionProfile(DAY_MON, (DAY_MON, DAY_TUE, DAY_WED, DAY_THU, DAY_FRI), True, "dmy"),
    "FR": RegionProfile(DAY_MON, (DAY_MON, DAY_TUE, DAY_WED, DAY_THU, DAY_FRI), True, "dmy"),
    "ES": RegionProfile(DAY_MON, (DAY_MON, DAY_TUE, DAY_WED, DAY_THU, DAY_FRI), True, "dmy"),
    "IT": RegionProfile(DAY_MON, (DAY_MON, DAY_TUE, DAY_WED, DAY_THU, DAY_FRI), True, "dmy"),
    "PT": RegionProfile(DAY_MON, (DAY_MON, DAY_TUE, DAY_WED, DAY_THU, DAY_FRI), True, "dmy"),
    "NL": RegionProfile(DAY_MON, (DAY_MON, DAY_TUE, DAY_WED, DAY_THU, DAY_FRI), True, "dmy"),
    "BE": RegionProfile(DAY_MON, (DAY_MON, DAY_TUE, DAY_WED, DAY_THU, DAY_FRI), True, "dmy"),
    "CH": RegionProfile(DAY_MON, (DAY_MON, DAY_TUE, DAY_WED, DAY_THU, DAY_FRI), True, "dmy"),
    "AT": RegionProfile(DAY_MON, (DAY_MON, DAY_TUE, DAY_WED, DAY_THU, DAY_FRI), True, "dmy"),
    "SE": RegionProfile(DAY_MON, (DAY_MON, DAY_TUE, DAY_WED, DAY_THU, DAY_FRI), True, "ymd"),
    "NO": RegionProfile(DAY_MON, (DAY_MON, DAY_TUE, DAY_WED, DAY_THU, DAY_FRI), True, "dmy"),
    "DK": RegionProfile(DAY_MON, (DAY_MON, DAY_TUE, DAY_WED, DAY_THU, DAY_FRI), True, "dmy"),
    "FI": RegionProfile(DAY_MON, (DAY_MON, DAY_TUE, DAY_WED, DAY_THU, DAY_FRI), True, "dmy"),
    "PL": RegionProfile(DAY_MON, (DAY_MON, DAY_TUE, DAY_WED, DAY_THU, DAY_FRI), True, "dmy"),
    "CZ": RegionProfile(DAY_MON, (DAY_MON, DAY_TUE, DAY_WED, DAY_THU, DAY_FRI), True, "dmy"),
    "GR": RegionProfile(DAY_MON, (DAY_MON, DAY_TUE, DAY_WED, DAY_THU, DAY_FRI), True, "dmy"),
    "RU": RegionProfile(DAY_MON, (DAY_MON, DAY_TUE, DAY_WED, DAY_THU, DAY_FRI), True, "dmy"),
    "UA": RegionProfile(DAY_MON, (DAY_MON, DAY_TUE, DAY_WED, DAY_THU, DAY_FRI), True, "dmy"),
    "TR": RegionProfile(DAY_MON, (DAY_MON, DAY_TUE, DAY_WED, DAY_THU, DAY_FRI), True, "dmy"),
    # Middle East (Sat–Thu or Sun–Thu work weeks)
    "AE": RegionProfile(DAY_MON, (DAY_MON, DAY_TUE, DAY_WED, DAY_THU, DAY_FRI), True, "dmy"),
    "SA": RegionProfile(DAY_SUN, (DAY_SUN, DAY_MON, DAY_TUE, DAY_WED, DAY_THU), True, "dmy"),
    "IL": RegionProfile(DAY_SUN, (DAY_SUN, DAY_MON, DAY_TUE, DAY_WED, DAY_THU), True, "dmy"),
    "EG": RegionProfile(DAY_SUN, (DAY_SUN, DAY_MON, DAY_TUE, DAY_WED, DAY_THU), True, "dmy"),
    "QA": RegionProfile(DAY_SUN, (DAY_SUN, DAY_MON, DAY_TUE, DAY_WED, DAY_THU), True, "dmy"),
    # Asia-Pacific
    "IN": RegionProfile(DAY_MON, (DAY_MON, DAY_TUE, DAY_WED, DAY_THU, DAY_FRI), True, "dmy"),
    "PK": RegionProfile(DAY_MON, (DAY_MON, DAY_TUE, DAY_WED, DAY_THU, DAY_FRI), True, "dmy"),
    "BD": RegionProfile(DAY_SUN, (DAY_SUN, DAY_MON, DAY_TUE, DAY_WED, DAY_THU), True, "dmy"),
    "CN": RegionProfile(DAY_MON, (DAY_MON, DAY_TUE, DAY_WED, DAY_THU, DAY_FRI), True, "ymd"),
    "JP": RegionProfile(DAY_MON, (DAY_MON, DAY_TUE, DAY_WED, DAY_THU, DAY_FRI), True, "ymd"),
    "KR": RegionProfile(DAY_MON, (DAY_MON, DAY_TUE, DAY_WED, DAY_THU, DAY_FRI), True, "ymd"),
    "SG": RegionProfile(DAY_MON, (DAY_MON, DAY_TUE, DAY_WED, DAY_THU, DAY_FRI), True, "dmy"),
    "MY": RegionProfile(DAY_MON, (DAY_MON, DAY_TUE, DAY_WED, DAY_THU, DAY_FRI), True, "dmy"),
    "ID": RegionProfile(DAY_MON, (DAY_MON, DAY_TUE, DAY_WED, DAY_THU, DAY_FRI), True, "dmy"),
    "TH": RegionProfile(DAY_MON, (DAY_MON, DAY_TUE, DAY_WED, DAY_THU, DAY_FRI), True, "dmy"),
    "VN": RegionProfile(DAY_MON, (DAY_MON, DAY_TUE, DAY_WED, DAY_THU, DAY_FRI), True, "dmy"),
    "PH": RegionProfile(DAY_MON, (DAY_MON, DAY_TUE, DAY_WED, DAY_THU, DAY_FRI), True, "mdy"),
    "AU": RegionProfile(DAY_MON, (DAY_MON, DAY_TUE, DAY_WED, DAY_THU, DAY_FRI), True, "dmy"),
    "NZ": RegionProfile(DAY_MON, (DAY_MON, DAY_TUE, DAY_WED, DAY_THU, DAY_FRI), True, "dmy"),
    # Africa
    "ZA": RegionProfile(DAY_MON, (DAY_MON, DAY_TUE, DAY_WED, DAY_THU, DAY_FRI), True, "ymd"),
    "NG": RegionProfile(DAY_MON, (DAY_MON, DAY_TUE, DAY_WED, DAY_THU, DAY_FRI), True, "dmy"),
    "KE": RegionProfile(DAY_MON, (DAY_MON, DAY_TUE, DAY_WED, DAY_THU, DAY_FRI), True, "dmy"),
}

DEFAULT_PROFILE = RegionProfile()


class RegionService:
    """Country catalog + regional defaults."""

    _country_cache: Optional[Dict[str, Dict]] = None

    @classmethod
    def _catalog(cls) -> Dict[str, Dict]:
        if cls._country_cache is not None:
            return cls._country_cache
        catalog: Dict[str, Dict] = {}
        try:
            from todo_bird_app.services.world_clock_service import WorldClockService

            for meta in WorldClockService.get_all_countries() or []:
                code = str(meta.get("code", "")).upper()
                if code:
                    catalog[code] = meta
        except Exception:
            catalog = {}
        cls._country_cache = catalog
        return cls._country_cache

    @classmethod
    def available_countries(cls):
        """Sorted (code, name, flag) tuples for selectors."""
        catalog = cls._catalog()
        entries = [
            (str(meta.get("code", code)), str(meta.get("name", code)), str(meta.get("flag", "")))
            for code, meta in catalog.items()
        ]
        return sorted(entries, key=lambda item: item[1].lower())

    @classmethod
    def country_name(cls, code: str) -> str:
        for c_code, name, _flag in cls.available_countries():
            if c_code == code:
                return name
        return code

    @classmethod
    def country_flag(cls, code: str) -> str:
        for c_code, _name, flag in cls.available_countries():
            if c_code == code:
                return flag
        return ""

    @classmethod
    def profile_for(cls, country_code: str) -> RegionProfile:
        return _REGION_PROFILES.get(str(country_code or "").upper(), DEFAULT_PROFILE)

    @classmethod
    def known_profile_countries(cls):
        return sorted(_REGION_PROFILES.keys())

    @classmethod
    def apply_region_defaults(cls, settings_manager, country_code: str) -> Dict[str, object]:
        """Explicitly apply the region's working week and 12/24-hour clock.

        Returns a summary dict the caller can surface in a toast.
        """
        profile = cls.profile_for(country_code)
        applied = {"working_days": list(profile.working_days), "use_24h": profile.use_24h}

        try:
            from todo_bird_app.services.working_week import WorkingWeekService

            WorkingWeekService(settings_manager).set_working_weekdays(
                set(profile.working_days)
            )
            applied["working_week"] = True
        except Exception:
            applied["working_week"] = False

        try:
            settings_manager.set("region_use_24h", bool(profile.use_24h))
        except Exception:
            pass

        try:
            settings_manager.set("region_date_style", profile.date_style)
        except Exception:
            pass

        return applied
