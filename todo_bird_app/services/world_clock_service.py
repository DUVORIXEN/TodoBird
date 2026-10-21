"""
TODO BIRD — WORLD CLOCK SERVICE
Provides offline timezone authority, country and city discovery, relative time
calculations, day/night solar phases, and persistent clock management.
Works 100% offline using Python's standard zoneinfo and pytz databases.
"""

import json
import logging
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime, timezone as dt_timezone
from pathlib import Path
from typing import List, Dict, Any, Optional
import zoneinfo

try:
    import pytz
except ImportError:
    pytz = None

logger = logging.getLogger(__name__)


def country_code_to_flag(country_code: str) -> str:
    """Generates standard Unicode flag emoji from two-letter ISO country code."""
    if not country_code or len(country_code) != 2:
        return "🌐"
    try:
        return "".join(chr(127397 + ord(c)) for c in country_code.upper())
    except Exception:
        return "🌐"


@dataclass
class WorldClockItem:
    id: str
    country_code: str
    country_name: str
    city: str
    timezone: str
    custom_label: Optional[str] = None
    is_pinned: bool = False
    style: str = "compact_digital"  # New field for clock style

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorldClockItem":
        return cls(
            id=data.get("id") or str(uuid.uuid4())[:8],
            country_code=data.get("country_code", "US"),
            country_name=data.get("country_name", "United States"),
            city=data.get("city", "New York"),
            timezone=data.get("timezone", "America/New_York"),
            custom_label=data.get("custom_label"),
            is_pinned=bool(data.get("is_pinned", False)),
            style=data.get("style", "compact_digital"),
        )


# Clock style definitions for UI selection
CLOCK_STYLES = {
    "compact_digital": {
        "name": "Compact Digital",
        "description": "Minimal digital display, small footprint",
        "widget_type": "digital",
        "theme": "minimal",
        "size": "compact",
    },
    "large_digital": {
        "name": "Large Digital",
        "description": "Prominent digital display, easy to read",
        "widget_type": "digital",
        "theme": "minimal",
        "size": "large",
    },
    "analog": {
        "name": "Analog",
        "description": "Classic analog clock face with hands",
        "widget_type": "analog",
        "theme": "minimal",
        "size": "medium",
    },
    "minimal": {
        "name": "Minimal",
        "description": "Ultra-clean, text-only time display",
        "widget_type": "digital",
        "theme": "minimal",
        "size": "compact",
    },
}


DEFAULT_CLOCKS = [
    {"id": "c1", "country_code": "GB", "country_name": "United Kingdom", "city": "London", "timezone": "Europe/London"},
    {"id": "c2", "country_code": "US", "country_name": "United States", "city": "New York", "timezone": "America/New_York"},
    {"id": "c3", "country_code": "JP", "country_name": "Japan", "city": "Tokyo", "timezone": "Asia/Tokyo"},
    {"id": "c4", "country_code": "AE", "country_name": "United Arab Emirates", "city": "Dubai", "timezone": "Asia/Dubai"},
    {"id": "c5", "country_code": "AU", "country_name": "Australia", "city": "Sydney", "timezone": "Australia/Sydney"},
]

POPULAR_PRESETS = [
    {"country_code": "GB", "country_name": "United Kingdom", "city": "London", "timezone": "Europe/London"},
    {"country_code": "US", "country_name": "United States", "city": "New York", "timezone": "America/New_York"},
    {"country_code": "US", "country_name": "United States", "city": "San Francisco", "timezone": "America/Los_Angeles"},
    {"country_code": "JP", "country_name": "Japan", "city": "Tokyo", "timezone": "Asia/Tokyo"},
    {"country_code": "FR", "country_name": "France", "city": "Paris", "timezone": "Europe/Paris"},
    {"country_code": "DE", "country_name": "Germany", "city": "Berlin", "timezone": "Europe/Berlin"},
    {"country_code": "IN", "country_name": "India", "city": "New Delhi", "timezone": "Asia/Kolkata"},
    {"country_code": "SG", "country_name": "Singapore", "city": "Singapore", "timezone": "Asia/Singapore"},
    {"country_code": "AE", "country_name": "United Arab Emirates", "city": "Dubai", "timezone": "Asia/Dubai"},
    {"country_code": "AU", "country_name": "Australia", "city": "Sydney", "timezone": "Australia/Sydney"},
    {"country_code": "CH", "country_name": "Switzerland", "city": "Zurich", "timezone": "Europe/Zurich"},
    {"country_code": "BR", "country_name": "Brazil", "city": "São Paulo", "timezone": "America/Sao_Paulo"},
    {"country_code": "CA", "country_name": "Canada", "city": "Toronto", "timezone": "America/Toronto"},
    {"country_code": "HK", "country_name": "Hong Kong", "city": "Hong Kong", "timezone": "Asia/Hong_Kong"},
    {"country_code": "KR", "country_name": "South Korea", "city": "Seoul", "timezone": "Asia/Seoul"},
]


class WorldClockService:
    CLOCK_STYLES = CLOCK_STYLES
    DEFAULT_CLOCKS = DEFAULT_CLOCKS
    POPULAR_PRESETS = POPULAR_PRESETS
    SUPPORTED_TYPES = {"analog", "digital"}
    SUPPORTED_THEMES = {"minimal", "luxury", "cyberpunk", "retro_lcd", "solar"}
    _SYSTEM_COUNTRY_CACHE = None

    @classmethod
    def _system_tzdb_root(cls):
        candidates = [Path(p) for p in getattr(zoneinfo, "TZPATH", ())] 
        candidates.append(Path("/usr/share/zoneinfo"))
        for root in candidates:
            if (root / "iso3166.tab").exists():
                return root
        return None

    @classmethod
    def _load_system_countries(cls) -> Dict[str, Dict[str, Any]]:
        if cls._SYSTEM_COUNTRY_CACHE is not None:
            return cls._SYSTEM_COUNTRY_CACHE

        countries: Dict[str, Dict[str, Any]] = {}
        root = cls._system_tzdb_root()
        if root is None:
            cls._SYSTEM_COUNTRY_CACHE = countries
            return countries

        iso_path = root / "iso3166.tab"
        try:
            for raw_line in iso_path.read_text(encoding="utf-8").splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split("\t", 1)
                if len(parts) != 2:
                    continue
                code, name = parts[0].strip().upper(), parts[1].strip()
                if len(code) != 2:
                    continue
                countries[code] = {
                    "code": code,
                    "name": name,
                    "flag": country_code_to_flag(code),
                    "timezones": [],
                }
        except OSError:
            cls._SYSTEM_COUNTRY_CACHE = {}
            return cls._SYSTEM_COUNTRY_CACHE

        for table_name in ("zone1970.tab", "zone.tab"):
            table_path = root / table_name
            if not table_path.exists():
                continue
            try:
                lines = table_path.read_text(encoding="utf-8").splitlines()
            except OSError:
                continue
            for raw_line in lines:
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split("\t")
                if len(parts) < 3:
                    continue
                timezone_name = parts[2].strip()
                for code in parts[0].split(","):
                    code = code.strip().upper()
                    if len(code) != 2:
                        continue
                    entry = countries.setdefault(
                        code,
                        {
                            "code": code,
                            "name": code,
                            "flag": country_code_to_flag(code),
                            "timezones": [],
                        },
                    )
                    if timezone_name and timezone_name not in entry["timezones"]:
                        entry["timezones"].append(timezone_name)

        cls._SYSTEM_COUNTRY_CACHE = countries
        return countries

    @classmethod
    def get_all_countries(cls) -> List[Dict[str, Any]]:
        """Returns sorted list of all 249 ISO countries with code, name, and flag."""
        countries = []
        if pytz:
            for code, name in pytz.country_names.items():
                tz_list = pytz.country_timezones.get(code, [])
                if tz_list:
                    countries.append({
                        "code": code,
                        "name": name,
                        "flag": country_code_to_flag(code),
                        "timezones": tz_list,
                    })
        else:
            countries = [
                country
                for country in cls._load_system_countries().values()
                if country.get("timezones")
            ]
            if not countries:
                for p in cls.POPULAR_PRESETS:
                    countries.append({
                        "code": p["country_code"],
                        "name": p["country_name"],
                        "flag": country_code_to_flag(p["country_code"]),
                        "timezones": [p["timezone"]],
                    })
        return sorted(countries, key=lambda x: x["name"])

    @classmethod
    def get_timezones_for_country(cls, country_code: str) -> List[Dict[str, str]]:
        """Returns cities and timezones for a given country code."""
        results = []
        if pytz:
            tz_list = pytz.country_timezones.get(country_code.upper(), [])
            for tz in tz_list:
                # Clean city name from timezone string (e.g. 'America/New_York' -> 'New York')
                city = tz.split("/")[-1].replace("_", " ")
                results.append({
                    "city": city,
                    "timezone": tz,
                })
        else:
            country = cls._load_system_countries().get(country_code.upper())
            if country:
                for tz in country.get("timezones", []):
                    city = tz.split("/")[-1].replace("_", " ")
                    results.append({
                        "city": city,
                        "timezone": tz,
                    })
        return results

    @classmethod
    def search_locations(cls, query: str) -> List[Dict[str, Any]]:
        """Searches across countries, cities, and timezones."""
        q = query.strip().lower()
        if not q:
            return cls.POPULAR_PRESETS

        results = []
        seen = set()

        # 1. Search popular presets first
        for p in cls.POPULAR_PRESETS:
            if (
                q in p["city"].lower()
                or q in p["country_name"].lower()
                or q in p["timezone"].lower()
            ):
                key = (p["country_code"], p["city"])
                if key not in seen:
                    results.append(p)
                    seen.add(key)

        # 2. Search full country database
        if pytz:
            for code, name in pytz.country_names.items():
                country_match = q in name.lower()
                tz_list = pytz.country_timezones.get(code, [])
                for tz in tz_list:
                    city = tz.split("/")[-1].replace("_", " ")
                    if country_match or q in city.lower() or q in tz.lower():
                        key = (code, city)
                        if key not in seen:
                            results.append({
                                "country_code": code,
                                "country_name": name,
                                "city": city,
                                "timezone": tz,
                            })
                            seen.add(key)
                            if len(results) >= 50:
                                return results
        else:
            for code, country in cls._load_system_countries().items():
                name = str(country.get("name") or code)
                country_match = q in name.lower()
                for tz in country.get("timezones", []):
                    city = tz.split("/")[-1].replace("_", " ")
                    if country_match or q in city.lower() or q in tz.lower():
                        key = (code, city)
                        if key not in seen:
                            results.append({
                                "country_code": code,
                                "country_name": name,
                                "city": city,
                                "timezone": tz,
                            })
                            seen.add(key)
                            if len(results) >= 50:
                                return results

        return results

    @classmethod
    def get_time_info(cls, timezone_name: str, base_time: Optional[datetime] = None) -> Dict[str, Any]:
        """
        Computes real-time clock data for a given timezone.
        Includes 12h/24h strings, UTC offsets, relative time to local, and solar state.
        """
        try:
            tz = zoneinfo.ZoneInfo(timezone_name)
        except Exception:
            tz = dt_timezone.utc

        now_utc = base_time.astimezone(dt_timezone.utc) if base_time else datetime.now(dt_timezone.utc)
        target_dt = now_utc.astimezone(tz)
        local_dt = now_utc.astimezone()  # Local machine timezone

        # Relative difference in hours
        target_offset = target_dt.utcoffset()
        local_offset = local_dt.utcoffset()
        target_sec = target_offset.total_seconds() if target_offset else 0
        local_sec = local_offset.total_seconds() if local_offset else 0
        diff_hours = (target_sec - local_sec) / 3600.0

        if abs(diff_hours) < 0.05:
            rel_str = "Same time"
        elif diff_hours > 0:
            rel_str = f"+{diff_hours:.1f}h ahead".replace(".0h", "h")
        else:
            rel_str = f"{abs(diff_hours):.1f}h behind".replace(".0h", "h")

        # Solar Day / Night calculation
        hour = target_dt.hour + target_dt.minute / 60.0
        if 5.5 <= hour < 7.0:
            solar_phase = "dawn"
            is_day = True
        elif 7.0 <= hour < 18.0:
            solar_phase = "day"
            is_day = True
        elif 18.0 <= hour < 19.5:
            solar_phase = "dusk"
            is_day = False
        else:
            solar_phase = "night"
            is_day = False

        # UTC Offset string
        total_min = int(target_sec // 60)
        sign = "+" if total_min >= 0 else "-"
        abs_min = abs(total_min)
        offset_str = f"UTC{sign}{abs_min // 60:02d}:{abs_min % 60:02d}"

        # Relative date indicator (Today / Tomorrow / Yesterday)
        target_date = target_dt.date()
        local_date = local_dt.date()
        if target_date == local_date:
            day_rel = "Today"
        elif target_date > local_date:
            day_rel = "Tomorrow"
        else:
            day_rel = "Yesterday"

        return {
            "datetime": target_dt,
            "hour": target_dt.hour,
            "minute": target_dt.minute,
            "second": target_dt.second,
            "microsecond": target_dt.microsecond,
            "time_12h": target_dt.strftime("%I:%M:%S %p"),
            "time_12h_short": target_dt.strftime("%I:%M %p"),
            "time_24h": target_dt.strftime("%H:%M:%S"),
            "time_24h_short": target_dt.strftime("%H:%M"),
            "date_display": target_dt.strftime("%a, %b %d"),
            "tz_abbr": target_dt.strftime("%Z"),
            "utc_offset": offset_str,
            "offset_hours": diff_hours,
            "relative_str": rel_str,
            "day_relative": day_rel,
            "is_day": is_day,
            "solar_phase": solar_phase,
        }

    # =========================================================================
    # SETTINGS & CONFIG PERSISTENCE
    # =========================================================================

    @classmethod
    def load_clocks(cls, settings_manager: Any = None) -> List[WorldClockItem]:
        """Loads user configured world clocks from settings."""
        if settings_manager is None:
            return [WorldClockItem.from_dict(d) for d in cls.DEFAULT_CLOCKS]

        raw = settings_manager.get("world_clocks")
        if not raw or not isinstance(raw, list):
            # Return and persist defaults
            defaults = [WorldClockItem.from_dict(d) for d in cls.DEFAULT_CLOCKS]
            cls.save_clocks(settings_manager, defaults)
            return defaults

        clocks = []
        for item in raw:
            if isinstance(item, dict):
                clocks.append(WorldClockItem.from_dict(item))
        return clocks if clocks else [WorldClockItem.from_dict(d) for d in cls.DEFAULT_CLOCKS]

    @classmethod
    def save_clocks(cls, settings_manager: Any, clocks: List[WorldClockItem]) -> None:
        """Saves user configured world clocks to settings."""
        if settings_manager is None:
            return
        data = [c.to_dict() for c in clocks]
        settings_manager.set("world_clocks", data)

    @classmethod
    def get_clock_type(cls, settings_manager: Any = None) -> str:
        """Returns active clock type: 'analog' or 'digital'."""
        if settings_manager is None:
            return "analog"
        c_type = str(settings_manager.get("world_clock_type", "analog") or "analog").lower()
        return c_type if c_type in cls.SUPPORTED_TYPES else "analog"

    @classmethod
    def set_clock_type(cls, settings_manager: Any, clock_type: str) -> None:
        """Saves clock type ('analog' or 'digital')."""
        if settings_manager and clock_type in cls.SUPPORTED_TYPES:
            settings_manager.set("world_clock_type", clock_type)

    @classmethod
    def get_clock_theme(cls, settings_manager: Any = None) -> str:
        """Returns active theme: 'minimal', 'luxury', 'cyberpunk', 'retro_lcd', 'solar'."""
        if settings_manager is None:
            return "minimal"
        t = str(settings_manager.get("world_clock_theme", "minimal") or "minimal").lower()
        return t if t in cls.SUPPORTED_THEMES else "minimal"

    @classmethod
    def set_clock_theme(cls, settings_manager: Any, theme: str) -> None:
        """Saves clock theme."""
        if settings_manager and theme in cls.SUPPORTED_THEMES:
            settings_manager.set("world_clock_theme", theme)

    @classmethod
    def get_use_24h(cls, settings_manager: Any = None) -> bool:
        """Returns True if 24-hour time format is preferred."""
        if settings_manager is None:
            return False
        return bool(settings_manager.get("world_clock_24h", False))

    @classmethod
    def set_use_24h(cls, settings_manager: Any, use_24h: bool) -> None:
        if settings_manager:
            settings_manager.set("world_clock_24h", bool(use_24h))
