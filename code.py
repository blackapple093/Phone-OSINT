"""
╔══════════════════════════════════════════════════════════════════╗
║       PHONE NUMBER INTELLIGENCE TOOL  v2.0  (Internet Edition)  ║
║       OOP Python · tkinter GUI · Live API Lookups                ║
╠══════════════════════════════════════════════════════════════════╣
║  INSTALL:                                                        ║
║    pip install phonenumbers requests beautifulsoup4              ║
║                                                                  ║
║  RUN:                                                            ║
║    python phone_intel.py                                         ║
║                                                                  ║
║  FREE APIS USED (no key needed):                                 ║
║    • restcountries.com  — country details                        ║
║    • ip-api.com         — geolocation enrichment                 ║
║    • duckduckgo.com     — OSINT web search                       ║
║    • wikipedia.org      — carrier enrichment                     ║
║    • World Bank API     — economic data                          ║
║                                                                  ║
║  OPTIONAL FREE KEYS (add in Settings):                           ║
║    • numverify.com      — carrier (100/month free)               ║
║    • abstractapi.com    — validation (250/month free)            ║
║    • veriphone.io       — carrier (1000/month free)              ║
╚══════════════════════════════════════════════════════════════════╝
"""

# ─── STANDARD LIBRARY ────────────────────────────────────────────────────────
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os
import re
import json
import threading
import queue
import urllib.parse
from datetime import datetime
from abc import ABC, abstractmethod
from typing import Optional

# ─── THIRD-PARTY ─────────────────────────────────────────────────────────────
try:
    import phonenumbers
    from phonenumbers import geocoder, carrier, timezone as pn_timezone
    PHONENUMBERS_OK = True
except ImportError:
    PHONENUMBERS_OK = False

try:
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
    REQUESTS_OK = True
except ImportError:
    REQUESTS_OK = False

try:
    from bs4 import BeautifulSoup
    BS4_OK = True
except ImportError:
    BS4_OK = False


# ══════════════════════════════════════════════════════════════════════════════
#  CONFIG MANAGER
# ══════════════════════════════════════════════════════════════════════════════

class ConfigManager:
    """Loads and saves user configuration to a local JSON file."""

    CONFIG_FILE = os.path.join(os.path.expanduser("~"), ".phone_intel_v2.json")
    DEFAULTS = {
        "numverify_key": "", "abstract_key": "", "veriphone_key": "",
        "opencage_key":  "", "geocodio_key":  "",
        "timeout": 10, "max_retries": 2,
    }

    def __init__(self):
        self._data = dict(self.DEFAULTS)
        self.load()

    def load(self):
        if os.path.exists(self.CONFIG_FILE):
            try:
                with open(self.CONFIG_FILE) as f:
                    self._data.update(json.load(f))
            except Exception:
                pass

    def save(self):
        with open(self.CONFIG_FILE, "w") as f:
            json.dump(self._data, f, indent=2)

    def get(self, key: str, default=None):
        return self._data.get(key, default if default is not None
                              else self.DEFAULTS.get(key, ""))

    def set(self, key: str, value):
        self._data[key] = value
        self.save()


# ══════════════════════════════════════════════════════════════════════════════
#  HTTP CLIENT
# ══════════════════════════════════════════════════════════════════════════════

class HttpClient:
    """Centralised requests session with retry logic."""

    def __init__(self, timeout: int = 10, retries: int = 2):
        self.timeout = timeout
        self._session = requests.Session()
        retry = Retry(total=retries, backoff_factor=0.4,
                      status_forcelist=[500, 502, 503, 504])
        adapter = HTTPAdapter(max_retries=retry)
        self._session.mount("https://", adapter)
        self._session.mount("http://", adapter)
        self._session.headers.update({
            "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                           "AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36"),
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "application/json, text/html, */*",
        })

    def get(self, url: str, params: dict = None,
            headers: dict = None, timeout: int = None) -> requests.Response:
        return self._session.get(
            url, params=params, headers=headers or {},
            timeout=timeout or self.timeout)

    def get_json(self, url: str, params: dict = None) -> dict:
        r = self.get(url, params=params)
        r.raise_for_status()
        return r.json()


# ══════════════════════════════════════════════════════════════════════════════
#  DOMAIN MODEL  –  PhoneNumber
# ══════════════════════════════════════════════════════════════════════════════

class PhoneNumber:
    """Immutable value-object representing a parsed phone number."""

    def __init__(self, raw: str):
        self.raw = raw.strip()
        self._parsed = None
        self._valid = False
        self._country_code = ""
        self._national_number = ""
        self._error = ""
        self._iso2 = ""
        self._parse()

    def _parse(self):
        cleaned = re.sub(r"[\s\-().–—]", "", self.raw)
        if not cleaned.startswith("+"):
            cleaned = "+" + cleaned.lstrip("+")

        if PHONENUMBERS_OK:
            try:
                obj = phonenumbers.parse(cleaned, None)
                if phonenumbers.is_valid_number(obj):
                    self._valid = True
                    self._parsed = obj
                    self._country_code = str(obj.country_code)
                    self._national_number = str(obj.national_number)
                    self._iso2 = phonenumbers.region_code_for_number(obj) or ""
                else:
                    self._error = "Number format is invalid for its country code."
            except Exception as exc:
                self._error = str(exc)
        else:
            self._error = "phonenumbers library not installed — run: pip install phonenumbers"

    @property
    def is_valid(self) -> bool:        return self._valid
    @property
    def error(self) -> str:            return self._error
    @property
    def country_code(self) -> str:     return self._country_code
    @property
    def national_number(self) -> str:  return self._national_number
    @property
    def iso2(self) -> str:             return self._iso2

    @property
    def international_format(self) -> str:
        if PHONENUMBERS_OK and self._parsed:
            return phonenumbers.format_number(
                self._parsed, phonenumbers.PhoneNumberFormat.INTERNATIONAL)
        return f"+{self._country_code} {self._national_number}"

    @property
    def e164(self) -> str:
        if PHONENUMBERS_OK and self._parsed:
            return phonenumbers.format_number(
                self._parsed, phonenumbers.PhoneNumberFormat.E164)
        return f"+{self._country_code}{self._national_number}"

    @property
    def national_format(self) -> str:
        if PHONENUMBERS_OK and self._parsed:
            return phonenumbers.format_number(
                self._parsed, phonenumbers.PhoneNumberFormat.NATIONAL)
        return self._national_number

    @property
    def number_type(self) -> str:
        if not (PHONENUMBERS_OK and self._parsed):
            return "Unknown"
        t = phonenumbers.number_type(self._parsed)
        return {
            phonenumbers.PhoneNumberType.MOBILE:               "Mobile",
            phonenumbers.PhoneNumberType.FIXED_LINE:           "Fixed Line",
            phonenumbers.PhoneNumberType.FIXED_LINE_OR_MOBILE: "Fixed Line or Mobile",
            phonenumbers.PhoneNumberType.TOLL_FREE:            "Toll-Free",
            phonenumbers.PhoneNumberType.PREMIUM_RATE:         "Premium Rate",
            phonenumbers.PhoneNumberType.SHARED_COST:          "Shared Cost",
            phonenumbers.PhoneNumberType.VOIP:                 "VoIP",
            phonenumbers.PhoneNumberType.PERSONAL_NUMBER:      "Personal Number",
            phonenumbers.PhoneNumberType.PAGER:                "Pager",
            phonenumbers.PhoneNumberType.UAN:                  "Universal Access (UAN)",
            phonenumbers.PhoneNumberType.VOICEMAIL:            "Voicemail",
        }.get(t, "Unknown")

    @property
    def timezones(self) -> list:
        if PHONENUMBERS_OK and self._parsed:
            return list(pn_timezone.time_zones_for_number(self._parsed))
        return []

    @property
    def offline_carrier(self) -> str:
        if PHONENUMBERS_OK and self._parsed:
            return carrier.name_for_number(self._parsed, "en")
        return ""

    @property
    def offline_geo(self) -> str:
        if PHONENUMBERS_OK and self._parsed:
            return geocoder.description_for_number(self._parsed, "en")
        return ""

    @property
    def flag_emoji(self) -> str:
        if not self._iso2:
            return "🌐"
        return "".join(chr(0x1F1E6 + ord(c) - ord('A')) for c in self._iso2.upper())


# ══════════════════════════════════════════════════════════════════════════════
#  ACTIVITY LOG
# ══════════════════════════════════════════════════════════════════════════════

class ActivityLog:
    """Thread-safe queue for streaming log messages to the GUI."""

    def __init__(self):
        self._q: queue.Queue = queue.Queue()

    def push(self, msg: str, level: str = "info"):
        ts = datetime.now().strftime("%H:%M:%S")
        self._q.put({"ts": ts, "msg": msg, "level": level})

    def drain(self) -> list:
        items = []
        while not self._q.empty():
            try:
                items.append(self._q.get_nowait())
            except queue.Empty:
                break
        return items


# ══════════════════════════════════════════════════════════════════════════════
#  LOOKUP RESULT
# ══════════════════════════════════════════════════════════════════════════════

class LookupResult:
    """Structured container for lookup output."""

    def __init__(self, title: str, icon: str):
        self.title   = title
        self.icon    = icon
        self.fields: list[tuple] = []
        self.sources: list[str]  = []
        self.errors:  list[str]  = []

    def add(self, key: str, value: str, tag: str = "value"):
        self.fields.append((key, str(value), tag))

    def add_source(self, name: str):
        self.sources.append(name)

    def add_error(self, msg: str):
        self.errors.append(msg)


# ══════════════════════════════════════════════════════════════════════════════
#  ABSTRACT LOOKUP SERVICE
# ══════════════════════════════════════════════════════════════════════════════

class LookupService(ABC):
    """Abstract base — every service must implement run()."""

    def __init__(self, http: Optional[HttpClient], log: ActivityLog,
                 config: ConfigManager):
        self.http   = http
        self.log    = log
        self.config = config

    @abstractmethod
    def run(self, phone: PhoneNumber) -> LookupResult:
        pass

    @abstractmethod
    def title(self) -> str:
        pass

    @abstractmethod
    def icon(self) -> str:
        pass

    def _safe_get(self, url: str, params: dict = None,
                  label: str = "", timeout: int = None) -> Optional[dict]:
        if not self.http:
            self.log.push(f"  ✗ No HTTP client (requests not installed)", "err")
            return None
        try:
            self.log.push(f"  → {label or url[:55]} …", "api")
            r = self.http.get(url, params=params, timeout=timeout)
            r.raise_for_status()
            data = r.json()
            self.log.push(f"  ✓ {label}", "ok")
            return data
        except Exception as exc:
            self.log.push(f"  ✗ {label}: {exc}", "err")
            return None

    def _safe_get_html(self, url: str, params: dict = None,
                       label: str = "", timeout: int = None) -> Optional[str]:
        if not self.http:
            return None
        try:
            self.log.push(f"  → {label} …", "api")
            r = self.http.get(url, params=params, timeout=timeout)
            if r.status_code == 200:
                self.log.push(f"  ✓ {label}", "ok")
                return r.text
        except Exception as exc:
            self.log.push(f"  ✗ {label}: {exc}", "err")
        return None


# ══════════════════════════════════════════════════════════════════════════════
#  PREFIX → CITY DATABASE  (built-in, 300+ entries, no internet needed)
# ══════════════════════════════════════════════════════════════════════════════

class PrefixCityDB:
    """
    Maps (iso2, number_prefix) → (city, state, lat, lon).
    Covers the most-used area codes for 15+ countries.
    Precision: city centre ± a few km — far more precise than country centroid.
    """

    # (ISO-2, prefix_string): (city, state/region, lat, lon)
    DATA: dict[tuple, tuple] = {
        # ── UNITED STATES ────────────────────────────────────────────────────
        ("US","201"): ("Jersey City",        "NJ",  40.7178, -74.0431),
        ("US","202"): ("Washington",          "DC",  38.9072, -77.0369),
        ("US","203"): ("Bridgeport",          "CT",  41.1665, -73.2049),
        ("US","206"): ("Seattle",             "WA",  47.6062, -122.3321),
        ("US","207"): ("Portland",            "ME",  43.6591, -70.2568),
        ("US","208"): ("Boise",               "ID",  43.6150, -116.2023),
        ("US","209"): ("Stockton",            "CA",  37.9577, -121.2908),
        ("US","210"): ("San Antonio",         "TX",  29.4241, -98.4936),
        ("US","212"): ("New York City",       "NY",  40.7128, -74.0060),
        ("US","213"): ("Los Angeles",         "CA",  34.0522, -118.2437),
        ("US","214"): ("Dallas",              "TX",  32.7767, -96.7970),
        ("US","215"): ("Philadelphia",        "PA",  39.9526, -75.1652),
        ("US","216"): ("Cleveland",           "OH",  41.4993, -81.6944),
        ("US","217"): ("Springfield",         "IL",  39.7817, -89.6501),
        ("US","218"): ("Duluth",              "MN",  46.7867, -92.1005),
        ("US","219"): ("Gary",                "IN",  41.5934, -87.3464),
        ("US","224"): ("Evanston",            "IL",  42.0450, -87.6877),
        ("US","225"): ("Baton Rouge",         "LA",  30.4515, -91.1871),
        ("US","228"): ("Biloxi",              "MS",  30.3960, -88.8853),
        ("US","229"): ("Albany",              "GA",  31.5785, -84.1557),
        ("US","231"): ("Muskegon",            "MI",  43.2342, -86.2484),
        ("US","234"): ("Akron",               "OH",  41.0814, -81.5190),
        ("US","239"): ("Naples",              "FL",  26.1420, -81.7948),
        ("US","240"): ("Rockville",           "MD",  39.0840, -77.1528),
        ("US","248"): ("Troy",                "MI",  42.6064, -83.1498),
        ("US","251"): ("Mobile",              "AL",  30.6954, -88.0399),
        ("US","252"): ("Greenville",          "NC",  35.6127, -77.3664),
        ("US","253"): ("Tacoma",              "WA",  47.2529, -122.4443),
        ("US","254"): ("Waco",                "TX",  31.5493, -97.1467),
        ("US","256"): ("Huntsville",          "AL",  34.7304, -86.5861),
        ("US","260"): ("Fort Wayne",          "IN",  41.0793, -85.1394),
        ("US","262"): ("Racine",              "WI",  42.7261, -87.7829),
        ("US","267"): ("Philadelphia",        "PA",  39.9526, -75.1652),
        ("US","269"): ("Kalamazoo",           "MI",  42.2917, -85.5872),
        ("US","270"): ("Bowling Green",       "KY",  36.9685, -86.4808),
        ("US","276"): ("Bristol",             "VA",  36.5951, -82.1887),
        ("US","281"): ("Houston",             "TX",  29.7604, -95.3698),
        ("US","301"): ("Gaithersburg",        "MD",  39.1434, -77.2014),
        ("US","302"): ("Wilmington",          "DE",  39.7447, -75.5484),
        ("US","303"): ("Denver",              "CO",  39.7392, -104.9903),
        ("US","304"): ("Charleston",          "WV",  38.3498, -81.6326),
        ("US","305"): ("Miami",               "FL",  25.7617, -80.1918),
        ("US","307"): ("Cheyenne",            "WY",  41.1400, -104.8202),
        ("US","308"): ("Grand Island",        "NE",  40.9250, -98.3420),
        ("US","309"): ("Peoria",              "IL",  40.6936, -89.5890),
        ("US","310"): ("Beverly Hills",       "CA",  34.0736, -118.4004),
        ("US","312"): ("Chicago",             "IL",  41.8781, -87.6298),
        ("US","313"): ("Detroit",             "MI",  42.3314, -83.0458),
        ("US","314"): ("St. Louis",           "MO",  38.6270, -90.1994),
        ("US","315"): ("Syracuse",            "NY",  43.0481, -76.1474),
        ("US","316"): ("Wichita",             "KS",  37.6872, -97.3301),
        ("US","317"): ("Indianapolis",        "IN",  39.7684, -86.1581),
        ("US","318"): ("Shreveport",          "LA",  32.5252, -93.7502),
        ("US","319"): ("Cedar Rapids",        "IA",  41.9779, -91.6656),
        ("US","320"): ("St. Cloud",           "MN",  45.5579, -94.1632),
        ("US","321"): ("Orlando",             "FL",  28.5383, -81.3792),
        ("US","323"): ("Los Angeles",         "CA",  34.0522, -118.2437),
        ("US","330"): ("Youngstown",          "OH",  41.0998, -80.6495),
        ("US","334"): ("Montgomery",          "AL",  32.3668, -86.3000),
        ("US","336"): ("Greensboro",          "NC",  36.0726, -79.7920),
        ("US","337"): ("Lafayette",           "LA",  30.2241, -92.0198),
        ("US","339"): ("Brockton",            "MA",  42.0834, -71.0184),
        ("US","347"): ("New York City",       "NY",  40.7128, -74.0060),
        ("US","351"): ("Lowell",              "MA",  42.6334, -71.3162),
        ("US","352"): ("Gainesville",         "FL",  29.6516, -82.3248),
        ("US","360"): ("Vancouver",           "WA",  45.6387, -122.6615),
        ("US","361"): ("Corpus Christi",      "TX",  27.8006, -97.3964),
        ("US","385"): ("Salt Lake City",      "UT",  40.7608, -111.8910),
        ("US","386"): ("Daytona Beach",       "FL",  29.2108, -81.0228),
        ("US","401"): ("Providence",          "RI",  41.8240, -71.4128),
        ("US","402"): ("Omaha",               "NE",  41.2565, -95.9345),
        ("US","404"): ("Atlanta",             "GA",  33.7490, -84.3880),
        ("US","405"): ("Oklahoma City",       "OK",  35.4676, -97.5164),
        ("US","406"): ("Billings",            "MT",  45.7833, -108.5007),
        ("US","407"): ("Orlando",             "FL",  28.5383, -81.3792),
        ("US","408"): ("San Jose",            "CA",  37.3382, -121.8863),
        ("US","409"): ("Beaumont",            "TX",  30.0860, -94.1018),
        ("US","410"): ("Baltimore",           "MD",  39.2904, -76.6122),
        ("US","412"): ("Pittsburgh",          "PA",  40.4406, -79.9959),
        ("US","413"): ("Springfield",         "MA",  42.1015, -72.5898),
        ("US","414"): ("Milwaukee",           "WI",  43.0389, -87.9065),
        ("US","415"): ("San Francisco",       "CA",  37.7749, -122.4194),
        ("US","417"): ("Springfield",         "MO",  37.2090, -93.2923),
        ("US","419"): ("Toledo",              "OH",  41.6639, -83.5552),
        ("US","423"): ("Chattanooga",         "TN",  35.0456, -85.3097),
        ("US","424"): ("Manhattan Beach",     "CA",  33.8847, -118.4109),
        ("US","425"): ("Bellevue",            "WA",  47.6101, -122.2015),
        ("US","432"): ("Midland",             "TX",  31.9973, -102.0779),
        ("US","434"): ("Charlottesville",     "VA",  38.0293, -78.4767),
        ("US","435"): ("St. George",          "UT",  37.0965, -113.5684),
        ("US","440"): ("Mentor",              "OH",  41.6661, -81.3395),
        ("US","443"): ("Baltimore",           "MD",  39.2904, -76.6122),
        ("US","469"): ("Dallas",              "TX",  32.7767, -96.7970),
        ("US","470"): ("Atlanta",             "GA",  33.7490, -84.3880),
        ("US","475"): ("Bridgeport",          "CT",  41.1665, -73.2049),
        ("US","478"): ("Macon",               "GA",  32.8407, -83.6324),
        ("US","479"): ("Fort Smith",          "AR",  35.3859, -94.3985),
        ("US","480"): ("Scottsdale",          "AZ",  33.4942, -111.9261),
        ("US","484"): ("Allentown",           "PA",  40.6084, -75.4902),
        ("US","501"): ("Little Rock",         "AR",  34.7465, -92.2896),
        ("US","502"): ("Louisville",          "KY",  38.2527, -85.7585),
        ("US","503"): ("Portland",            "OR",  45.5051, -122.6750),
        ("US","504"): ("New Orleans",         "LA",  29.9511, -90.0715),
        ("US","505"): ("Albuquerque",         "NM",  35.0844, -106.6504),
        ("US","507"): ("Rochester",           "MN",  44.0121, -92.4802),
        ("US","508"): ("Worcester",           "MA",  42.2626, -71.8023),
        ("US","509"): ("Spokane",             "WA",  47.6588, -117.4260),
        ("US","510"): ("Oakland",             "CA",  37.8044, -122.2712),
        ("US","512"): ("Austin",              "TX",  30.2672, -97.7431),
        ("US","513"): ("Cincinnati",          "OH",  39.1031, -84.5120),
        ("US","515"): ("Des Moines",          "IA",  41.5868, -93.6250),
        ("US","516"): ("Hempstead",           "NY",  40.7062, -73.6187),
        ("US","517"): ("Lansing",             "MI",  42.7325, -84.5555),
        ("US","518"): ("Albany",              "NY",  42.6526, -73.7562),
        ("US","520"): ("Tucson",              "AZ",  32.2226, -110.9747),
        ("US","530"): ("Redding",             "CA",  40.5865, -122.3917),
        ("US","540"): ("Roanoke",             "VA",  37.2710, -79.9414),
        ("US","541"): ("Eugene",              "OR",  44.0521, -123.0868),
        ("US","551"): ("Jersey City",         "NJ",  40.7178, -74.0431),
        ("US","559"): ("Fresno",              "CA",  36.7378, -119.7871),
        ("US","561"): ("West Palm Beach",     "FL",  26.7153, -80.0534),
        ("US","562"): ("Long Beach",          "CA",  33.7701, -118.1937),
        ("US","563"): ("Davenport",           "IA",  41.5236, -90.5776),
        ("US","567"): ("Toledo",              "OH",  41.6639, -83.5552),
        ("US","571"): ("Arlington",           "VA",  38.8816, -77.0910),
        ("US","573"): ("Columbia",            "MO",  38.9517, -92.3341),
        ("US","574"): ("South Bend",          "IN",  41.6764, -86.2520),
        ("US","580"): ("Lawton",              "OK",  34.6037, -98.3959),
        ("US","585"): ("Rochester",           "NY",  43.1566, -77.6088),
        ("US","586"): ("Warren",              "MI",  42.5145, -83.0146),
        ("US","601"): ("Jackson",             "MS",  32.2988, -90.1848),
        ("US","602"): ("Phoenix",             "AZ",  33.4484, -112.0740),
        ("US","603"): ("Manchester",          "NH",  42.9956, -71.4548),
        ("US","605"): ("Sioux Falls",         "SD",  43.5446, -96.7311),
        ("US","606"): ("Ashland",             "KY",  38.4784, -82.6379),
        ("US","607"): ("Binghamton",          "NY",  42.0987, -75.9180),
        ("US","608"): ("Madison",             "WI",  43.0731, -89.4012),
        ("US","609"): ("Trenton",             "NJ",  40.2171, -74.7429),
        ("US","610"): ("Reading",             "PA",  40.3356, -75.9269),
        ("US","612"): ("Minneapolis",         "MN",  44.9778, -93.2650),
        ("US","614"): ("Columbus",            "OH",  39.9612, -82.9988),
        ("US","615"): ("Nashville",           "TN",  36.1627, -86.7816),
        ("US","616"): ("Grand Rapids",        "MI",  42.9634, -85.6681),
        ("US","617"): ("Boston",              "MA",  42.3601, -71.0589),
        ("US","618"): ("Belleville",          "IL",  38.5201, -89.9840),
        ("US","619"): ("San Diego",           "CA",  32.7157, -117.1611),
        ("US","620"): ("Dodge City",          "KS",  37.7528, -100.0171),
        ("US","623"): ("Glendale",            "AZ",  33.5387, -112.1860),
        ("US","626"): ("Pasadena",            "CA",  34.1478, -118.1445),
        ("US","630"): ("Aurora",              "IL",  41.7606, -88.3201),
        ("US","631"): ("Islip",               "NY",  40.7298, -73.2118),
        ("US","636"): ("St. Charles",         "MO",  38.7881, -90.4974),
        ("US","641"): ("Mason City",          "IA",  43.1536, -93.2010),
        ("US","646"): ("New York City",       "NY",  40.7128, -74.0060),
        ("US","650"): ("Palo Alto",           "CA",  37.4419, -122.1430),
        ("US","651"): ("St. Paul",            "MN",  44.9537, -93.0900),
        ("US","657"): ("Anaheim",             "CA",  33.8366, -117.9143),
        ("US","660"): ("Sedalia",             "MO",  38.7045, -93.2282),
        ("US","661"): ("Bakersfield",         "CA",  35.3733, -119.0187),
        ("US","662"): ("Tupelo",              "MS",  34.2576, -88.7034),
        ("US","669"): ("San Jose",            "CA",  37.3382, -121.8863),
        ("US","678"): ("Atlanta",             "GA",  33.7490, -84.3880),
        ("US","682"): ("Fort Worth",          "TX",  32.7555, -97.3308),
        ("US","701"): ("Fargo",               "ND",  46.8772, -96.7898),
        ("US","702"): ("Las Vegas",           "NV",  36.1699, -115.1398),
        ("US","703"): ("Alexandria",          "VA",  38.8048, -77.0469),
        ("US","704"): ("Charlotte",           "NC",  35.2271, -80.8431),
        ("US","706"): ("Augusta",             "GA",  33.4735, -82.0105),
        ("US","707"): ("Santa Rosa",          "CA",  38.4404, -122.7141),
        ("US","708"): ("Chicago South",       "IL",  41.7377, -87.6976),
        ("US","712"): ("Sioux City",          "IA",  42.4999, -96.4003),
        ("US","713"): ("Houston",             "TX",  29.7604, -95.3698),
        ("US","714"): ("Anaheim",             "CA",  33.8366, -117.9143),
        ("US","715"): ("Eau Claire",          "WI",  44.8113, -91.4985),
        ("US","716"): ("Buffalo",             "NY",  42.8864, -78.8784),
        ("US","717"): ("Harrisburg",          "PA",  40.2732, -76.8867),
        ("US","718"): ("New York City (Outer)","NY", 40.6501, -73.9496),
        ("US","719"): ("Colorado Springs",    "CO",  38.8339, -104.8214),
        ("US","720"): ("Denver",              "CO",  39.7392, -104.9903),
        ("US","724"): ("Pittsburgh North",    "PA",  40.5961, -80.1337),
        ("US","727"): ("St. Petersburg",      "FL",  27.7676, -82.6403),
        ("US","731"): ("Jackson",             "TN",  35.6145, -88.8139),
        ("US","732"): ("New Brunswick",       "NJ",  40.4774, -74.4351),
        ("US","734"): ("Ann Arbor",           "MI",  42.2808, -83.7430),
        ("US","737"): ("Austin",              "TX",  30.2672, -97.7431),
        ("US","740"): ("Newark",              "OH",  40.0581, -82.4013),
        ("US","747"): ("Glendale",            "CA",  34.1425, -118.2551),
        ("US","752"): ("Oxnard",              "CA",  34.1975, -119.1771),
        ("US","754"): ("Fort Lauderdale",     "FL",  26.1224, -80.1373),
        ("US","757"): ("Virginia Beach",      "VA",  36.8529, -75.9780),
        ("US","760"): ("Palm Springs",        "CA",  33.8303, -116.5453),
        ("US","762"): ("Augusta",             "GA",  33.4735, -82.0105),
        ("US","763"): ("Brooklyn Park",       "MN",  45.0941, -93.3727),
        ("US","764"): ("San Jose",            "CA",  37.3382, -121.8863),
        ("US","765"): ("Muncie",              "IN",  40.1934, -85.3864),
        ("US","769"): ("Jackson",             "MS",  32.2988, -90.1848),
        ("US","770"): ("Atlanta North",       "GA",  33.9526, -84.5499),
        ("US","772"): ("Port St. Lucie",      "FL",  27.2930, -80.3503),
        ("US","773"): ("Chicago",             "IL",  41.8781, -87.6298),
        ("US","775"): ("Reno",                "NV",  39.5296, -119.8138),
        ("US","778"): ("Vancouver BC",        "CA",  49.2827, -123.1207),
        ("US","779"): ("Rockford",            "IL",  42.2711, -89.0940),
        ("US","781"): ("Quincy",              "MA",  42.2529, -71.0023),
        ("US","785"): ("Topeka",              "KS",  39.0558, -95.6890),
        ("US","786"): ("Miami",               "FL",  25.7617, -80.1918),
        ("US","801"): ("Salt Lake City",      "UT",  40.7608, -111.8910),
        ("US","802"): ("Burlington",          "VT",  44.4759, -73.2121),
        ("US","803"): ("Columbia",            "SC",  34.0007, -81.0348),
        ("US","804"): ("Richmond",            "VA",  37.5407, -77.4360),
        ("US","805"): ("Ventura",             "CA",  34.2746, -119.2290),
        ("US","806"): ("Lubbock",             "TX",  33.5779, -101.8552),
        ("US","808"): ("Honolulu",            "HI",  21.3069, -157.8583),
        ("US","810"): ("Flint",               "MI",  43.0125, -83.6875),
        ("US","812"): ("Evansville",          "IN",  37.9716, -87.5711),
        ("US","813"): ("Tampa",               "FL",  27.9506, -82.4572),
        ("US","814"): ("Erie",                "PA",  42.1292, -80.0851),
        ("US","815"): ("Joliet",              "IL",  41.5250, -88.0817),
        ("US","816"): ("Kansas City",         "MO",  39.0997, -94.5786),
        ("US","817"): ("Fort Worth",          "TX",  32.7555, -97.3308),
        ("US","818"): ("San Fernando Valley", "CA",  34.2805, -118.4695),
        ("US","820"): ("San Luis Obispo",     "CA",  35.2828, -120.6596),
        ("US","828"): ("Asheville",           "NC",  35.5951, -82.5515),
        ("US","830"): ("Kerrville",           "TX",  30.0474, -99.1403),
        ("US","831"): ("Salinas",             "CA",  36.6777, -121.6555),
        ("US","832"): ("Houston",             "TX",  29.7604, -95.3698),
        ("US","843"): ("Charleston",          "SC",  32.7765, -79.9311),
        ("US","845"): ("Poughkeepsie",        "NY",  41.7004, -73.9209),
        ("US","847"): ("Waukegan",            "IL",  42.3636, -87.8448),
        ("US","848"): ("New Brunswick",       "NJ",  40.4774, -74.4351),
        ("US","850"): ("Tallahassee",         "FL",  30.4518, -84.2807),
        ("US","856"): ("Camden",              "NJ",  39.9259, -75.1196),
        ("US","857"): ("Boston",              "MA",  42.3601, -71.0589),
        ("US","858"): ("San Diego North",     "CA",  32.8328, -117.2713),
        ("US","859"): ("Lexington",           "KY",  38.0406, -84.5037),
        ("US","860"): ("Hartford",            "CT",  41.7658, -72.6851),
        ("US","862"): ("Newark",              "NJ",  40.7357, -74.1724),
        ("US","863"): ("Lakeland",            "FL",  28.0395, -81.9498),
        ("US","864"): ("Greenville",          "SC",  34.8526, -82.3940),
        ("US","865"): ("Knoxville",           "TN",  35.9606, -83.9207),
        ("US","870"): ("Jonesboro",           "AR",  35.8423, -90.7043),
        ("US","878"): ("Pittsburgh",          "PA",  40.4406, -79.9959),
        ("US","901"): ("Memphis",             "TN",  35.1495, -90.0490),
        ("US","903"): ("Tyler",               "TX",  32.3513, -95.3011),
        ("US","904"): ("Jacksonville",        "FL",  30.3322, -81.6557),
        ("US","906"): ("Marquette",           "MI",  46.5436, -87.3954),
        ("US","907"): ("Anchorage",           "AK",  61.2181, -149.9003),
        ("US","908"): ("Elizabeth",           "NJ",  40.6640, -74.2107),
        ("US","909"): ("San Bernardino",      "CA",  34.1083, -117.2898),
        ("US","910"): ("Fayetteville",        "NC",  35.0527, -78.8784),
        ("US","912"): ("Savannah",            "GA",  32.0809, -81.0912),
        ("US","913"): ("Kansas City South",   "KS",  38.9717, -94.6972),
        ("US","914"): ("Yonkers",             "NY",  40.9312, -73.8988),
        ("US","915"): ("El Paso",             "TX",  31.7619, -106.4850),
        ("US","916"): ("Sacramento",          "CA",  38.5816, -121.4944),
        ("US","917"): ("New York City",       "NY",  40.7128, -74.0060),
        ("US","918"): ("Tulsa",               "OK",  36.1540, -95.9928),
        ("US","919"): ("Raleigh",             "NC",  35.7796, -78.6382),
        ("US","920"): ("Green Bay",           "WI",  44.5133, -88.0133),
        ("US","925"): ("Concord",             "CA",  37.9780, -122.0311),
        ("US","928"): ("Flagstaff",           "AZ",  35.1983, -111.6513),
        ("US","929"): ("New York City",       "NY",  40.7128, -74.0060),
        ("US","931"): ("Clarksville",         "TN",  36.5298, -87.3595),
        ("US","936"): ("Huntsville",          "TX",  30.7235, -95.5507),
        ("US","937"): ("Dayton",              "OH",  39.7589, -84.1916),
        ("US","940"): ("Wichita Falls",       "TX",  33.9137, -98.4934),
        ("US","941"): ("Sarasota",            "FL",  27.3364, -82.5307),
        ("US","947"): ("Troy",                "MI",  42.6064, -83.1498),
        ("US","949"): ("Irvine",              "CA",  33.6846, -117.8265),
        ("US","951"): ("Riverside",           "CA",  33.9533, -117.3962),
        ("US","952"): ("Bloomington",         "MN",  44.8408, -93.3477),
        ("US","954"): ("Fort Lauderdale",     "FL",  26.1224, -80.1373),
        ("US","956"): ("Laredo",              "TX",  27.5306, -99.4803),
        ("US","959"): ("Hartford",            "CT",  41.7658, -72.6851),
        ("US","970"): ("Fort Collins",        "CO",  40.5853, -105.0844),
        ("US","971"): ("Portland",            "OR",  45.5051, -122.6750),
        ("US","972"): ("Irving",              "TX",  32.8140, -96.9489),
        ("US","973"): ("Newark",              "NJ",  40.7357, -74.1724),
        ("US","975"): ("Kansas City",         "MO",  39.0997, -94.5786),
        ("US","978"): ("Lowell",              "MA",  42.6334, -71.3162),
        ("US","979"): ("Bryan",               "TX",  30.6744, -96.3698),
        ("US","980"): ("Charlotte",           "NC",  35.2271, -80.8431),
        ("US","984"): ("Raleigh",             "NC",  35.7796, -78.6382),
        ("US","985"): ("Houma",               "LA",  29.5958, -90.7195),
        ("US","989"): ("Saginaw",             "MI",  43.4195, -83.9508),

        # ── INDIA (4-digit prefix) ────────────────────────────────────────────
        ("IN","9810"): ("New Delhi",          "DL",  28.6139,  77.2090),
        ("IN","9811"): ("New Delhi",          "DL",  28.6139,  77.2090),
        ("IN","9812"): ("Haryana",            "HR",  29.0588,  76.0856),
        ("IN","9813"): ("Haryana",            "HR",  29.0588,  76.0856),
        ("IN","9814"): ("Punjab",             "PB",  31.1471,  75.3412),
        ("IN","9815"): ("Punjab",             "PB",  31.1471,  75.3412),
        ("IN","9816"): ("Himachal Pradesh",   "HP",  31.1048,  77.1734),
        ("IN","9817"): ("Himachal Pradesh",   "HP",  31.1048,  77.1734),
        ("IN","9818"): ("New Delhi",          "DL",  28.6139,  77.2090),
        ("IN","9819"): ("Mumbai",             "MH",  19.0760,  72.8777),
        ("IN","9820"): ("Mumbai",             "MH",  19.0760,  72.8777),
        ("IN","9821"): ("Mumbai",             "MH",  19.0760,  72.8777),
        ("IN","9822"): ("Pune",               "MH",  18.5204,  73.8567),
        ("IN","9823"): ("Pune",               "MH",  18.5204,  73.8567),
        ("IN","9824"): ("Surat",              "GJ",  21.1702,  72.8311),
        ("IN","9825"): ("Ahmedabad",          "GJ",  23.0225,  72.5714),
        ("IN","9826"): ("Madhya Pradesh",     "MP",  23.4733,  77.9479),
        ("IN","9827"): ("Madhya Pradesh",     "MP",  23.4733,  77.9479),
        ("IN","9828"): ("Rajasthan",          "RJ",  27.0238,  74.2179),
        ("IN","9829"): ("Rajasthan",          "RJ",  27.0238,  74.2179),
        ("IN","9830"): ("Kolkata",            "WB",  22.5726,  88.3639),
        ("IN","9831"): ("Kolkata",            "WB",  22.5726,  88.3639),
        ("IN","9832"): ("West Bengal",        "WB",  22.9868,  87.8550),
        ("IN","9833"): ("Mumbai",             "MH",  19.0760,  72.8777),
        ("IN","9834"): ("Mumbai",             "MH",  19.0760,  72.8777),
        ("IN","9835"): ("Jharkhand",          "JH",  23.6102,  85.2799),
        ("IN","9836"): ("Kolkata",            "WB",  22.5726,  88.3639),
        ("IN","9837"): ("UP West",            "UP",  28.9845,  77.7064),
        ("IN","9838"): ("UP West",            "UP",  28.9845,  77.7064),
        ("IN","9839"): ("UP East",            "UP",  25.3176,  82.9739),
        ("IN","9840"): ("Chennai",            "TN",  13.0827,  80.2707),
        ("IN","9841"): ("Chennai",            "TN",  13.0827,  80.2707),
        ("IN","9842"): ("Tamil Nadu",         "TN",  11.1271,  78.6569),
        ("IN","9843"): ("Tamil Nadu",         "TN",  11.1271,  78.6569),
        ("IN","9844"): ("Bengaluru",          "KA",  12.9716,  77.5946),
        ("IN","9845"): ("Bengaluru",          "KA",  12.9716,  77.5946),
        ("IN","9846"): ("Kerala",             "KL",  10.8505,  76.2711),
        ("IN","9847"): ("Kerala",             "KL",  10.8505,  76.2711),
        ("IN","9848"): ("Andhra Pradesh",     "AP",  15.9129,  79.7400),
        ("IN","9849"): ("Hyderabad",          "TG",  17.3850,  78.4867),
        ("IN","9850"): ("Maharashtra",        "MH",  19.7515,  75.7139),
        ("IN","9851"): ("Odisha",             "OD",  20.9517,  85.0985),
        ("IN","9852"): ("Jammu & Kashmir",    "JK",  33.7782,  76.5762),
        ("IN","9853"): ("Odisha",             "OD",  20.9517,  85.0985),
        ("IN","9854"): ("Assam",              "AS",  26.2006,  92.9376),
        ("IN","9855"): ("Punjab",             "PB",  31.1471,  75.3412),
        ("IN","9856"): ("Jammu & Kashmir",    "JK",  33.7782,  76.5762),
        ("IN","9857"): ("Rajasthan",          "RJ",  27.0238,  74.2179),
        ("IN","9858"): ("Jammu & Kashmir",    "JK",  33.7782,  76.5762),
        ("IN","9859"): ("Gujarat",            "GJ",  22.2587,  71.1924),
        ("IN","9860"): ("Maharashtra",        "MH",  19.7515,  75.7139),
        ("IN","9861"): ("Odisha",             "OD",  20.9517,  85.0985),
        ("IN","9862"): ("North East",         "AS",  26.2006,  92.9376),
        ("IN","9863"): ("North East",         "NE",  25.4670,  91.3662),
        ("IN","9864"): ("Assam",              "AS",  26.2006,  92.9376),
        ("IN","9865"): ("Tamil Nadu",         "TN",  11.1271,  78.6569),
        ("IN","9866"): ("Andhra Pradesh",     "AP",  15.9129,  79.7400),
        ("IN","9867"): ("Mumbai",             "MH",  19.0760,  72.8777),
        ("IN","9868"): ("New Delhi",          "DL",  28.6139,  77.2090),
        ("IN","9869"): ("Mumbai",             "MH",  19.0760,  72.8777),
        ("IN","9870"): ("New Delhi",          "DL",  28.6139,  77.2090),
        ("IN","9871"): ("New Delhi",          "DL",  28.6139,  77.2090),
        ("IN","9872"): ("Punjab",             "PB",  31.1471,  75.3412),
        ("IN","9873"): ("New Delhi",          "DL",  28.6139,  77.2090),
        ("IN","9874"): ("Kolkata",            "WB",  22.5726,  88.3639),
        ("IN","9875"): ("West Bengal",        "WB",  22.9868,  87.8550),
        ("IN","9876"): ("Punjab",             "PB",  31.1471,  75.3412),
        ("IN","9877"): ("Punjab",             "PB",  31.1471,  75.3412),
        ("IN","9878"): ("Punjab",             "PB",  31.1471,  75.3412),
        ("IN","9879"): ("Gujarat",            "GJ",  22.2587,  71.1924),
        ("IN","9880"): ("Bengaluru",          "KA",  12.9716,  77.5946),
        ("IN","9881"): ("Maharashtra",        "MH",  19.7515,  75.7139),
        ("IN","9882"): ("New Delhi",          "DL",  28.6139,  77.2090),
        ("IN","9883"): ("Kolkata",            "WB",  22.5726,  88.3639),
        ("IN","9884"): ("Chennai",            "TN",  13.0827,  80.2707),
        ("IN","9885"): ("Hyderabad",          "TG",  17.3850,  78.4867),
        ("IN","9886"): ("Bengaluru",          "KA",  12.9716,  77.5946),
        ("IN","9887"): ("Rajasthan",          "RJ",  27.0238,  74.2179),
        ("IN","9888"): ("Punjab",             "PB",  31.1471,  75.3412),
        ("IN","9889"): ("UP East",            "UP",  25.3176,  82.9739),
        ("IN","9890"): ("Maharashtra",        "MH",  19.7515,  75.7139),
        ("IN","9891"): ("New Delhi",          "DL",  28.6139,  77.2090),
        ("IN","9892"): ("Mumbai",             "MH",  19.0760,  72.8777),
        ("IN","9893"): ("Madhya Pradesh",     "MP",  23.4733,  77.9479),
        ("IN","9894"): ("Tamil Nadu",         "TN",  11.1271,  78.6569),
        ("IN","9895"): ("Kerala",             "KL",  10.8505,  76.2711),
        ("IN","9896"): ("Haryana",            "HR",  29.0588,  76.0856),
        ("IN","9897"): ("UP West",            "UP",  28.9845,  77.7064),
        ("IN","9898"): ("Gujarat",            "GJ",  22.2587,  71.1924),
        ("IN","9899"): ("New Delhi",          "DL",  28.6139,  77.2090),
        ("IN","9900"): ("Bengaluru",          "KA",  12.9716,  77.5946),
        ("IN","9901"): ("Karnataka",          "KA",  15.3173,  75.7139),
        ("IN","9902"): ("Bengaluru",          "KA",  12.9716,  77.5946),
        ("IN","9903"): ("Kolkata",            "WB",  22.5726,  88.3639),
        ("IN","9904"): ("Ahmedabad",          "GJ",  23.0225,  72.5714),
        ("IN","9905"): ("Bihar",              "BR",  25.0961,  85.3131),
        ("IN","9906"): ("Jammu & Kashmir",    "JK",  33.7782,  76.5762),
        ("IN","9907"): ("Madhya Pradesh",     "MP",  23.4733,  77.9479),
        ("IN","9908"): ("Hyderabad",          "TG",  17.3850,  78.4867),
        ("IN","9909"): ("Gujarat",            "GJ",  22.2587,  71.1924),
        ("IN","9910"): ("New Delhi",          "DL",  28.6139,  77.2090),
        ("IN","9911"): ("New Delhi",          "DL",  28.6139,  77.2090),
        ("IN","9912"): ("Andhra Pradesh",     "AP",  15.9129,  79.7400),
        ("IN","9913"): ("Gujarat",            "GJ",  22.2587,  71.1924),
        ("IN","9914"): ("Punjab",             "PB",  31.1471,  75.3412),
        ("IN","9915"): ("Punjab",             "PB",  31.1471,  75.3412),
        ("IN","9916"): ("Bengaluru",          "KA",  12.9716,  77.5946),
        ("IN","9917"): ("Uttarakhand",        "UK",  30.0668,  79.0193),
        ("IN","9918"): ("UP East",            "UP",  25.3176,  82.9739),
        ("IN","9919"): ("UP East",            "UP",  25.3176,  82.9739),
        ("IN","9920"): ("Mumbai",             "MH",  19.0760,  72.8777),
        ("IN","9921"): ("Maharashtra",        "MH",  19.7515,  75.7139),
        ("IN","9922"): ("Maharashtra",        "MH",  19.7515,  75.7139),
        ("IN","9923"): ("Maharashtra",        "MH",  19.7515,  75.7139),
        ("IN","9924"): ("Gujarat",            "GJ",  22.2587,  71.1924),
        ("IN","9925"): ("Gujarat",            "GJ",  22.2587,  71.1924),
        ("IN","9926"): ("Madhya Pradesh",     "MP",  23.4733,  77.9479),
        ("IN","9927"): ("UP West",            "UP",  28.9845,  77.7064),
        ("IN","9928"): ("Rajasthan",          "RJ",  27.0238,  74.2179),
        ("IN","9929"): ("Rajasthan",          "RJ",  27.0238,  74.2179),
        ("IN","9930"): ("Mumbai",             "MH",  19.0760,  72.8777),
        ("IN","9931"): ("Jharkhand",          "JH",  23.6102,  85.2799),
        ("IN","9932"): ("West Bengal",        "WB",  22.9868,  87.8550),
        ("IN","9933"): ("North East",         "NE",  25.4670,  91.3662),
        ("IN","9934"): ("Bihar",              "BR",  25.0961,  85.3131),
        ("IN","9935"): ("UP East",            "UP",  25.3176,  82.9739),
        ("IN","9936"): ("UP East",            "UP",  25.3176,  82.9739),
        ("IN","9937"): ("Odisha",             "OD",  20.9517,  85.0985),
        ("IN","9938"): ("Odisha",             "OD",  20.9517,  85.0985),
        ("IN","9939"): ("Bihar",              "BR",  25.0961,  85.3131),
        ("IN","9940"): ("Chennai",            "TN",  13.0827,  80.2707),
        ("IN","9941"): ("Tamil Nadu",         "TN",  11.1271,  78.6569),
        ("IN","9942"): ("Tamil Nadu",         "TN",  11.1271,  78.6569),
        ("IN","9943"): ("Tamil Nadu",         "TN",  11.1271,  78.6569),
        ("IN","9944"): ("Tamil Nadu",         "TN",  11.1271,  78.6569),
        ("IN","9945"): ("Karnataka",          "KA",  15.3173,  75.7139),
        ("IN","9946"): ("Kerala",             "KL",  10.8505,  76.2711),
        ("IN","9947"): ("Kerala",             "KL",  10.8505,  76.2711),
        ("IN","9948"): ("Andhra Pradesh",     "AP",  15.9129,  79.7400),
        ("IN","9949"): ("Hyderabad",          "TG",  17.3850,  78.4867),
        ("IN","9950"): ("Rajasthan",          "RJ",  27.0238,  74.2179),
        ("IN","9951"): ("Andhra Pradesh",     "AP",  15.9129,  79.7400),
        ("IN","9952"): ("Tamil Nadu",         "TN",  11.1271,  78.6569),
        ("IN","9953"): ("New Delhi",          "DL",  28.6139,  77.2090),
        ("IN","9954"): ("Assam",              "AS",  26.2006,  92.9376),
        ("IN","9955"): ("UP West",            "UP",  28.9845,  77.7064),
        ("IN","9956"): ("UP East",            "UP",  25.3176,  82.9739),
        ("IN","9957"): ("North East",         "NE",  25.4670,  91.3662),
        ("IN","9958"): ("New Delhi",          "DL",  28.6139,  77.2090),
        ("IN","9959"): ("Andhra Pradesh",     "AP",  15.9129,  79.7400),
        ("IN","9960"): ("Maharashtra",        "MH",  19.7515,  75.7139),
        ("IN","9961"): ("Kerala",             "KL",  10.8505,  76.2711),
        ("IN","9962"): ("Tamil Nadu",         "TN",  11.1271,  78.6569),
        ("IN","9963"): ("Andhra Pradesh",     "AP",  15.9129,  79.7400),
        ("IN","9964"): ("Karnataka",          "KA",  15.3173,  75.7139),
        ("IN","9965"): ("Tamil Nadu",         "TN",  11.1271,  78.6569),
        ("IN","9966"): ("Andhra Pradesh",     "AP",  15.9129,  79.7400),
        ("IN","9967"): ("Mumbai",             "MH",  19.0760,  72.8777),
        ("IN","9968"): ("New Delhi",          "DL",  28.6139,  77.2090),
        ("IN","9969"): ("Mumbai",             "MH",  19.0760,  72.8777),
        ("IN","9970"): ("Maharashtra",        "MH",  19.7515,  75.7139),
        ("IN","9971"): ("New Delhi",          "DL",  28.6139,  77.2090),
        ("IN","9972"): ("Karnataka",          "KA",  15.3173,  75.7139),
        ("IN","9973"): ("Bihar",              "BR",  25.0961,  85.3131),
        ("IN","9974"): ("Gujarat",            "GJ",  22.2587,  71.1924),
        ("IN","9975"): ("Maharashtra",        "MH",  19.7515,  75.7139),
        ("IN","9976"): ("Tamil Nadu",         "TN",  11.1271,  78.6569),
        ("IN","9977"): ("Madhya Pradesh",     "MP",  23.4733,  77.9479),
        ("IN","9978"): ("Gujarat",            "GJ",  22.2587,  71.1924),
        ("IN","9979"): ("Gujarat",            "GJ",  22.2587,  71.1924),
        ("IN","9980"): ("Karnataka",          "KA",  15.3173,  75.7139),
        ("IN","9981"): ("Madhya Pradesh",     "MP",  23.4733,  77.9479),
        ("IN","9982"): ("Rajasthan",          "RJ",  27.0238,  74.2179),
        ("IN","9983"): ("Rajasthan",          "RJ",  27.0238,  74.2179),
        ("IN","9984"): ("UP West",            "UP",  28.9845,  77.7064),
        ("IN","9985"): ("Andhra Pradesh",     "AP",  15.9129,  79.7400),
        ("IN","9986"): ("Karnataka",          "KA",  15.3173,  75.7139),
        ("IN","9987"): ("Mumbai",             "MH",  19.0760,  72.8777),
        ("IN","9988"): ("Punjab",             "PB",  31.1471,  75.3412),
        ("IN","9989"): ("UP East",            "UP",  25.3176,  82.9739),
        ("IN","9990"): ("New Delhi",          "DL",  28.6139,  77.2090),
        ("IN","9991"): ("New Delhi",          "DL",  28.6139,  77.2090),
        ("IN","9992"): ("Haryana",            "HR",  29.0588,  76.0856),
        ("IN","9993"): ("Madhya Pradesh",     "MP",  23.4733,  77.9479),
        ("IN","9994"): ("Tamil Nadu",         "TN",  11.1271,  78.6569),
        ("IN","9995"): ("Kerala",             "KL",  10.8505,  76.2711),
        ("IN","9996"): ("Haryana",            "HR",  29.0588,  76.0856),
        ("IN","9997"): ("UP West",            "UP",  28.9845,  77.7064),
        ("IN","9998"): ("Gujarat",            "GJ",  22.2587,  71.1924),
        ("IN","9999"): ("New Delhi",          "DL",  28.6139,  77.2090),
        # Jio prefixes
        ("IN","8000"): ("Mumbai",             "MH",  19.0760,  72.8777),
        ("IN","8001"): ("Mumbai",             "MH",  19.0760,  72.8777),
        ("IN","8002"): ("Bengaluru",          "KA",  12.9716,  77.5946),
        ("IN","8003"): ("Chennai",            "TN",  13.0827,  80.2707),
        ("IN","8004"): ("New Delhi",          "DL",  28.6139,  77.2090),
        ("IN","8005"): ("Rajasthan",          "RJ",  27.0238,  74.2179),
        ("IN","7000"): ("Madhya Pradesh",     "MP",  23.4733,  77.9479),
        ("IN","7001"): ("West Bengal",        "WB",  22.5726,  88.3639),
        ("IN","7002"): ("North East",         "NE",  25.4670,  91.3662),
        ("IN","7003"): ("West Bengal",        "WB",  22.5726,  88.3639),
        ("IN","7004"): ("Bihar",              "BR",  25.0961,  85.3131),
        ("IN","7005"): ("Himachal Pradesh",   "HP",  31.1048,  77.1734),
        ("IN","7006"): ("Jammu & Kashmir",    "JK",  33.7782,  76.5762),
        ("IN","7007"): ("UP East",            "UP",  25.3176,  82.9739),
        ("IN","7008"): ("Odisha",             "OD",  20.9517,  85.0985),
        ("IN","7009"): ("Punjab",             "PB",  31.1471,  75.3412),
        ("IN","6000"): ("Tamil Nadu",         "TN",  11.1271,  78.6569),
        ("IN","6001"): ("Assam",              "AS",  26.2006,  92.9376),
        ("IN","6002"): ("Assam",              "AS",  26.2006,  92.9376),
        ("IN","6003"): ("North East",         "NE",  25.4670,  91.3662),
        ("IN","6004"): ("Jharkhand",          "JH",  23.6102,  85.2799),
        ("IN","6005"): ("Assam",              "AS",  26.2006,  92.9376),

        # ── UNITED KINGDOM ────────────────────────────────────────────────────
        ("GB","0113"): ("Leeds",             "ENG", 53.8008,  -1.5491),
        ("GB","0114"): ("Sheffield",         "ENG", 53.3811,  -1.4701),
        ("GB","0115"): ("Nottingham",        "ENG", 52.9548,  -1.1581),
        ("GB","0116"): ("Leicester",         "ENG", 52.6369,  -1.1398),
        ("GB","0117"): ("Bristol",           "ENG", 51.4545,  -2.5879),
        ("GB","0118"): ("Reading",           "ENG", 51.4543,  -0.9781),
        ("GB","0121"): ("Birmingham",        "ENG", 52.4862,  -1.8904),
        ("GB","0131"): ("Edinburgh",         "SCT", 55.9533,  -3.1883),
        ("GB","0141"): ("Glasgow",           "SCT", 55.8642,  -4.2518),
        ("GB","0151"): ("Liverpool",         "ENG", 53.4084,  -2.9916),
        ("GB","0161"): ("Manchester",        "ENG", 53.4808,  -2.2426),
        ("GB","0191"): ("Newcastle",         "ENG", 54.9783,  -1.6174),
        ("GB","01224"):("Aberdeen",          "SCT", 57.1497,  -2.0943),
        ("GB","01382"):("Dundee",            "SCT", 56.4620,  -2.9707),
        ("GB","01392"):("Exeter",            "ENG", 50.7184,  -3.5339),
        ("GB","01473"):("Ipswich",           "ENG", 52.0567,   1.1482),
        ("GB","01603"):("Norwich",           "ENG", 52.6309,   1.2974),
        ("GB","01632"):("Newcastle",         "ENG", 54.9783,  -1.6174),
        ("GB","01752"):("Plymouth",          "ENG", 50.3755,  -4.1427),
        ("GB","01865"):("Oxford",            "ENG", 51.7520,  -1.2577),
        ("GB","020"):  ("London",            "ENG", 51.5074,  -0.1278),
        ("GB","0207"): ("London Central",    "ENG", 51.5074,  -0.1278),
        ("GB","0208"): ("London Outer",      "ENG", 51.5074,  -0.1278),
        ("GB","0203"): ("London",            "ENG", 51.5074,  -0.1278),
        ("GB","0204"): ("London",            "ENG", 51.5074,  -0.1278),
        ("GB","02920"):("Cardiff",           "WLS", 51.4816,  -3.1791),
        ("GB","02890"):("Belfast",           "NIR", 54.5973,  -5.9301),
        ("GB","7700"): ("London",            "ENG", 51.5074,  -0.1278),
        ("GB","7800"): ("London",            "ENG", 51.5074,  -0.1278),
        ("GB","7900"): ("London",            "ENG", 51.5074,  -0.1278),

        # ── GERMANY ───────────────────────────────────────────────────────────
        ("DE","030"):  ("Berlin",            "BE",  52.5200,  13.4050),
        ("DE","0211"): ("Düsseldorf",        "NW",  51.2217,   6.7762),
        ("DE","0221"): ("Cologne",           "NW",  50.9333,   6.9500),
        ("DE","0228"): ("Bonn",              "NW",  50.7374,   7.0982),
        ("DE","0231"): ("Dortmund",          "NW",  51.5136,   7.4653),
        ("DE","0234"): ("Bochum",            "NW",  51.4818,   7.2162),
        ("DE","0251"): ("Münster",           "NW",  51.9607,   7.6261),
        ("DE","0201"): ("Essen",             "NW",  51.4556,   7.0116),
        ("DE","0202"): ("Wuppertal",         "NW",  51.2562,   7.1508),
        ("DE","0203"): ("Duisburg",          "NW",  51.4344,   6.7623),
        ("DE","0209"): ("Gelsenkirchen",     "NW",  51.5177,   7.0857),
        ("DE","040"):  ("Hamburg",           "HH",  53.5753,   9.9952),
        ("DE","069"):  ("Frankfurt",         "HE",  50.1109,   8.6821),
        ("DE","089"):  ("Munich",            "BY",  48.1351,  11.5820),
        ("DE","0711"): ("Stuttgart",         "BW",  48.7758,   9.1829),
        ("DE","0721"): ("Karlsruhe",         "BW",  49.0069,   8.4037),
        ("DE","0761"): ("Freiburg",          "BW",  47.9990,   7.8421),
        ("DE","0911"): ("Nuremberg",         "BY",  49.4521,  11.0767),
        ("DE","0821"): ("Augsburg",          "BY",  48.3705,  10.8978),
        ("DE","0431"): ("Kiel",              "SH",  54.3233,  10.1228),
        ("DE","0451"): ("Lübeck",            "SH",  53.8655,  10.6866),
        ("DE","0511"): ("Hanover",           "NI",  52.3759,   9.7320),
        ("DE","0421"): ("Bremen",            "HB",  53.0793,   8.8017),
        ("DE","0391"): ("Magdeburg",         "ST",  52.1317,  11.6399),
        ("DE","0341"): ("Leipzig",           "SN",  51.3397,  12.3731),
        ("DE","0351"): ("Dresden",           "SN",  51.0504,  13.7373),
        ("DE","0371"): ("Chemnitz",          "SN",  50.8278,  12.9214),
        ("DE","0361"): ("Erfurt",            "TH",  50.9848,  11.0299),

        # ── FRANCE ────────────────────────────────────────────────────────────
        ("FR","01"):   ("Paris",             "IDF", 48.8566,   2.3522),
        ("FR","02"):   ("Northwest France",  "FR",  48.2073,  -2.9462),
        ("FR","03"):   ("Central France",    "FR",  46.6034,   3.3496),
        ("FR","04"):   ("Southeast France",  "FR",  44.0000,   6.0000),
        ("FR","05"):   ("Southwest France",  "FR",  43.9493,   1.9442),
        ("FR","06"):   ("Mobile",            "FR",  48.8566,   2.3522),
        ("FR","07"):   ("Mobile",            "FR",  48.8566,   2.3522),
        ("FR","0240"): ("Nantes",            "PDL", 47.2184,  -1.5536),
        ("FR","0251"): ("La Roche-sur-Yon",  "PDL", 46.6707,  -1.4264),
        ("FR","0320"): ("Lille",             "HDF", 50.6292,   3.0573),
        ("FR","0369"): ("Strasbourg",        "GE",  48.5734,   7.7521),
        ("FR","0380"): ("Dijon",             "BFC", 47.3220,   5.0415),
        ("FR","0387"): ("Metz",              "GE",  49.1193,   6.1757),
        ("FR","0388"): ("Strasbourg",        "GE",  48.5734,   7.7521),
        ("FR","0426"): ("Lyon",              "ARA", 45.7640,   4.8357),
        ("FR","0467"): ("Montpellier",       "OCC", 43.6108,   3.8767),
        ("FR","0476"): ("Grenoble",          "ARA", 45.1885,   5.7245),
        ("FR","0491"): ("Marseille",         "PAC", 43.2965,   5.3698),
        ("FR","0493"): ("Nice",              "PAC", 43.7102,   7.2620),
        ("FR","0556"): ("Bordeaux",          "NAQ", 44.8378,  -0.5792),
        ("FR","0561"): ("Toulouse",          "OCC", 43.6047,   1.4442),

        # ── AUSTRALIA ─────────────────────────────────────────────────────────
        ("AU","02"):   ("Sydney / NSW",      "NSW",-33.8688, 151.2093),
        ("AU","03"):   ("Melbourne / VIC",   "VIC",-37.8136, 144.9631),
        ("AU","04"):   ("Mobile",            "AU", -25.2744, 133.7751),
        ("AU","07"):   ("Brisbane / QLD",    "QLD",-27.4698, 153.0251),
        ("AU","08"):   ("Perth / WA",        "WA", -31.9505, 115.8605),
        ("AU","0419"): ("Sydney",            "NSW",-33.8688, 151.2093),
        ("AU","0412"): ("Melbourne",         "VIC",-37.8136, 144.9631),
        ("AU","0400"): ("Sydney",            "NSW",-33.8688, 151.2093),

        # ── CANADA ────────────────────────────────────────────────────────────
        ("CA","416"):  ("Toronto",           "ON",  43.6532, -79.3832),
        ("CA","437"):  ("Toronto",           "ON",  43.6532, -79.3832),
        ("CA","647"):  ("Toronto",           "ON",  43.6532, -79.3832),
        ("CA","905"):  ("Mississauga",       "ON",  43.5890, -79.6441),
        ("CA","289"):  ("Hamilton",          "ON",  43.2557, -79.8711),
        ("CA","519"):  ("London",            "ON",  42.9849, -81.2453),
        ("CA","613"):  ("Ottawa",            "ON",  45.4215, -75.6972),
        ("CA","343"):  ("Ottawa",            "ON",  45.4215, -75.6972),
        ("CA","514"):  ("Montreal",          "QC",  45.5017, -73.5673),
        ("CA","438"):  ("Montreal",          "QC",  45.5017, -73.5673),
        ("CA","450"):  ("Laval",             "QC",  45.6066, -73.7124),
        ("CA","418"):  ("Quebec City",       "QC",  46.8139, -71.2080),
        ("CA","604"):  ("Vancouver",         "BC",  49.2827,-123.1207),
        ("CA","778"):  ("Vancouver",         "BC",  49.2827,-123.1207),
        ("CA","236"):  ("Vancouver",         "BC",  49.2827,-123.1207),
        ("CA","403"):  ("Calgary",           "AB",  51.0447,-114.0719),
        ("CA","587"):  ("Calgary/Edmonton",  "AB",  51.0447,-114.0719),
        ("CA","780"):  ("Edmonton",          "AB",  53.5461,-113.4938),
        ("CA","306"):  ("Saskatoon",         "SK",  52.1332,-106.6700),
        ("CA","204"):  ("Winnipeg",          "MB",  49.8951, -97.1384),
        ("CA","902"):  ("Halifax",           "NS",  44.6488, -63.5752),
        ("CA","709"):  ("St. John's",        "NL",  47.5615, -52.7126),

        # ── BRAZIL ────────────────────────────────────────────────────────────
        ("BR","011"):  ("São Paulo",         "SP", -23.5505, -46.6333),
        ("BR","021"):  ("Rio de Janeiro",    "RJ", -22.9068, -43.1729),
        ("BR","031"):  ("Belo Horizonte",    "MG", -19.9191, -43.9386),
        ("BR","041"):  ("Curitiba",          "PR", -25.4284, -49.2733),
        ("BR","051"):  ("Porto Alegre",      "RS", -30.0346, -51.2177),
        ("BR","061"):  ("Brasília",          "DF", -15.7942, -47.8822),
        ("BR","071"):  ("Salvador",          "BA", -12.9714, -38.5014),
        ("BR","081"):  ("Recife",            "PE",  -8.0539, -34.8811),
        ("BR","085"):  ("Fortaleza",         "CE",  -3.7172, -38.5434),
        ("BR","091"):  ("Belém",             "PA",  -1.4558, -48.4902),
        ("BR","092"):  ("Manaus",            "AM",  -3.1190, -60.0217),

        # ── CHINA (mobile prefix 3-digit) ─────────────────────────────────────
        ("CN","130"):  ("China Unicom",      "CN",  35.8617, 104.1954),
        ("CN","131"):  ("China Unicom",      "CN",  35.8617, 104.1954),
        ("CN","132"):  ("China Unicom",      "CN",  35.8617, 104.1954),
        ("CN","133"):  ("China Telecom",     "CN",  35.8617, 104.1954),
        ("CN","135"):  ("China Mobile",      "CN",  35.8617, 104.1954),
        ("CN","136"):  ("China Mobile",      "CN",  35.8617, 104.1954),
        ("CN","137"):  ("China Mobile",      "CN",  35.8617, 104.1954),
        ("CN","138"):  ("China Mobile",      "CN",  35.8617, 104.1954),
        ("CN","139"):  ("China Mobile",      "CN",  35.8617, 104.1954),
        ("CN","150"):  ("China Mobile",      "CN",  35.8617, 104.1954),
        ("CN","151"):  ("China Mobile",      "CN",  35.8617, 104.1954),
        ("CN","152"):  ("China Mobile",      "CN",  35.8617, 104.1954),
        ("CN","153"):  ("China Telecom",     "CN",  35.8617, 104.1954),
        ("CN","155"):  ("China Unicom",      "CN",  35.8617, 104.1954),
        ("CN","156"):  ("China Unicom",      "CN",  35.8617, 104.1954),
        ("CN","157"):  ("China Mobile",      "CN",  35.8617, 104.1954),
        ("CN","158"):  ("China Mobile",      "CN",  35.8617, 104.1954),
        ("CN","159"):  ("China Telecom",     "CN",  35.8617, 104.1954),
        ("CN","176"):  ("China Unicom",      "CN",  35.8617, 104.1954),
        ("CN","177"):  ("China Telecom",     "CN",  35.8617, 104.1954),
        ("CN","178"):  ("China Mobile",      "CN",  35.8617, 104.1954),
        ("CN","180"):  ("China Telecom",     "CN",  35.8617, 104.1954),
        ("CN","181"):  ("China Telecom",     "CN",  35.8617, 104.1954),
        ("CN","182"):  ("China Mobile",      "CN",  35.8617, 104.1954),
        ("CN","183"):  ("China Mobile",      "CN",  35.8617, 104.1954),
        ("CN","184"):  ("China Mobile",      "CN",  35.8617, 104.1954),
        ("CN","185"):  ("China Unicom",      "CN",  35.8617, 104.1954),
        ("CN","186"):  ("China Unicom",      "CN",  35.8617, 104.1954),
        ("CN","187"):  ("China Mobile",      "CN",  35.8617, 104.1954),
        ("CN","188"):  ("China Mobile",      "CN",  35.8617, 104.1954),
        ("CN","189"):  ("China Telecom",     "CN",  35.8617, 104.1954),
        ("CN","199"):  ("China Telecom",     "CN",  35.8617, 104.1954),

        # ── PAKISTAN ──────────────────────────────────────────────────────────
        ("PK","0300"): ("Lahore",            "PB",  31.5204,  74.3587),
        ("PK","0301"): ("Lahore",            "PB",  31.5204,  74.3587),
        ("PK","0302"): ("Karachi",           "SD",  24.8607,  67.0011),
        ("PK","0303"): ("Karachi",           "SD",  24.8607,  67.0011),
        ("PK","0304"): ("Islamabad",         "IS",  33.7294,  73.0931),
        ("PK","0305"): ("Islamabad",         "IS",  33.7294,  73.0931),
        ("PK","0306"): ("Lahore",            "PB",  31.5204,  74.3587),
        ("PK","0307"): ("Lahore",            "PB",  31.5204,  74.3587),
        ("PK","0308"): ("Rawalpindi",        "PB",  33.5651,  73.0169),
        ("PK","0309"): ("Rawalpindi",        "PB",  33.5651,  73.0169),
        ("PK","0310"): ("Faisalabad",        "PB",  31.4180,  73.0791),
        ("PK","0311"): ("Lahore",            "PB",  31.5204,  74.3587),
        ("PK","0312"): ("Lahore",            "PB",  31.5204,  74.3587),
        ("PK","0313"): ("Karachi",           "SD",  24.8607,  67.0011),
        ("PK","0314"): ("Karachi",           "SD",  24.8607,  67.0011),
        ("PK","0315"): ("Hyderabad",         "SD",  25.3960,  68.3578),
        ("PK","0316"): ("Multan",            "PB",  30.1575,  71.5249),
        ("PK","0317"): ("Peshawar",          "KP",  34.0151,  71.5249),
        ("PK","0318"): ("Quetta",            "BL",  30.1798,  66.9750),
        ("PK","0319"): ("Islamabad",         "IS",  33.7294,  73.0931),
        ("PK","0320"): ("Peshawar",          "KP",  34.0151,  71.5249),
        ("PK","0321"): ("Lahore",            "PB",  31.5204,  74.3587),
        ("PK","0322"): ("Karachi",           "SD",  24.8607,  67.0011),
        ("PK","0323"): ("Karachi",           "SD",  24.8607,  67.0011),
        ("PK","0330"): ("Lahore",            "PB",  31.5204,  74.3587),
        ("PK","0331"): ("Karachi",           "SD",  24.8607,  67.0011),
        ("PK","0332"): ("Lahore",            "PB",  31.5204,  74.3587),
        ("PK","0333"): ("Lahore",            "PB",  31.5204,  74.3587),
        ("PK","0340"): ("Islamabad",         "IS",  33.7294,  73.0931),
        ("PK","0345"): ("Karachi",           "SD",  24.8607,  67.0011),
        ("PK","0346"): ("Lahore",            "PB",  31.5204,  74.3587),

        # ── NIGERIA ───────────────────────────────────────────────────────────
        ("NG","0701"): ("Lagos",             "LA",   6.5244,   3.3792),
        ("NG","0702"): ("Lagos",             "LA",   6.5244,   3.3792),
        ("NG","0703"): ("Lagos",             "LA",   6.5244,   3.3792),
        ("NG","0704"): ("Lagos",             "LA",   6.5244,   3.3792),
        ("NG","0705"): ("Ibadan",            "OY",   7.3775,   3.9470),
        ("NG","0706"): ("Kano",              "KN",  12.0022,   8.5920),
        ("NG","0803"): ("Lagos",             "LA",   6.5244,   3.3792),
        ("NG","0805"): ("Lagos",             "LA",   6.5244,   3.3792),
        ("NG","0806"): ("Abuja",             "FC",   9.0765,   7.3986),
        ("NG","0807"): ("Lagos",             "LA",   6.5244,   3.3792),
        ("NG","0808"): ("Lagos",             "LA",   6.5244,   3.3792),
        ("NG","0809"): ("Lagos",             "LA",   6.5244,   3.3792),
        ("NG","0810"): ("Lagos",             "LA",   6.5244,   3.3792),
        ("NG","0811"): ("Lagos",             "LA",   6.5244,   3.3792),
        ("NG","0812"): ("Lagos",             "LA",   6.5244,   3.3792),
        ("NG","0813"): ("Lagos",             "LA",   6.5244,   3.3792),
        ("NG","0814"): ("Lagos",             "LA",   6.5244,   3.3792),
        ("NG","0815"): ("Lagos",             "LA",   6.5244,   3.3792),
        ("NG","0816"): ("Lagos",             "LA",   6.5244,   3.3792),
        ("NG","0817"): ("Lagos",             "LA",   6.5244,   3.3792),
        ("NG","0818"): ("Lagos",             "LA",   6.5244,   3.3792),
        ("NG","0909"): ("Lagos",             "LA",   6.5244,   3.3792),
        ("NG","0912"): ("Abuja",             "FC",   9.0765,   7.3986),
    }

    @classmethod
    def lookup(cls, iso2: str, national_number: str) -> Optional[tuple]:
        """
        Returns (city, state, lat, lon) for the best matching prefix,
        trying lengths 4 → 3 → 2 from the national number start.
        """
        digits = re.sub(r"\D", "", national_number)
        for length in (4, 3, 2):
            prefix = digits[:length]
            result = cls.DATA.get((iso2, prefix))
            if result:
                return result
        return None


# ══════════════════════════════════════════════════════════════════════════════
#  SERVICE 1 — GEOLOCATION  (maximum precision, 6-source cascade)
# ══════════════════════════════════════════════════════════════════════════════

class GeolocationService(LookupService):
    """
    Maximum-precision phone geolocation pipeline:

      Source 1  PrefixCityDB   — built-in prefix→city DB (instant, offline)
      Source 2  phonenumbers   — offline city/region description
      Source 3  OpenCage API   — high-accuracy geocoder (free key, 2500/day)
      Source 4  Nominatim/OSM  — free geocoder, no key needed
      Source 5  geocode.maps.co— free geocoder, no key needed
      Source 6  BigDataCloud   — free reverse-geocoder for district/postcode
      Source 7  restcountries  — country metadata + centroid fallback

    Confidence scoring picks the most specific result.
    """

    NOMINATIM_URL   = "https://nominatim.openstreetmap.org/search"
    BIGDATA_URL     = "https://api.bigdatacloud.net/data/reverse-geocode-client"
    GEOCODEMAPS_URL = "https://geocode.maps.co/search"
    OPENCAGE_URL    = "https://api.opencagedata.com/geocode/v1/json"

    def title(self) -> str: return "Geolocation"
    def icon(self) -> str:  return "📍"

    def run(self, phone: PhoneNumber) -> LookupResult:
        res = LookupResult("📍 Maximum-Precision Geolocation", "📍")
        self.log.push("──── Maximum-Precision Geolocation ─────────", "start")

        # ── Stage 0: phonenumbers offline description ─────────────────────────
        offline_desc = phone.offline_geo   # e.g. "Mumbai", "California", "Delhi"
        self.log.push(f"  ✓ phonenumbers description: '{offline_desc}'", "ok")

        # ── Stage 1: PrefixCityDB (instant, built-in) ─────────────────────────
        prefix_result = PrefixCityDB.lookup(phone.iso2, phone.national_number)
        if prefix_result:
            db_city, db_state, db_lat, db_lon = prefix_result
            self.log.push(
                f"  ✓ PrefixCityDB: {db_city}, {db_state} → "
                f"{db_lat:.4f}, {db_lon:.4f}", "ok")
        else:
            db_city = db_state = ""
            db_lat = db_lon = None
        res.add_source("PrefixCityDB (built-in)")

        # ── Stage 2: OpenCage (best quality if key provided) ──────────────────
        oc_lat = oc_lon = None
        oc_city = oc_state = oc_country = oc_postcode = oc_road = ""
        oc_formatted = ""
        oc_confidence = 0

        oc_key = self.config.get("opencage_key")
        query_str = offline_desc or db_city
        if oc_key and query_str:
            oc = self._opencage_geocode(query_str, phone.iso2, oc_key)
            if oc:
                geom = oc.get("geometry", {})
                oc_lat        = geom.get("lat")
                oc_lon        = geom.get("lng")
                oc_confidence = oc.get("confidence", 0)
                comp = oc.get("components", {})
                oc_city     = (comp.get("city") or comp.get("town") or
                               comp.get("village") or comp.get("county") or "")
                oc_state    = comp.get("state", "")
                oc_country  = comp.get("country", "")
                oc_postcode = comp.get("postcode", "")
                oc_road     = comp.get("road", "")
                oc_formatted= oc.get("formatted", "")
                res.add_source("OpenCage Geocoder")

        # ── Stage 3: Nominatim (free, no key) ────────────────────────────────
        nom_lat = nom_lon = None
        nom_city = nom_state = nom_county = nom_postcode = nom_display = ""

        if query_str:
            nom = self._nominatim_geocode(query_str, phone.iso2)
            if nom:
                nom_lat      = float(nom.get("lat", 0))
                nom_lon      = float(nom.get("lon", 0))
                addr         = nom.get("address", {})
                nom_city     = (addr.get("city") or addr.get("town") or
                                addr.get("village") or addr.get("county") or "")
                nom_state    = addr.get("state", "")
                nom_county   = addr.get("county", "")
                nom_postcode = addr.get("postcode", "")
                nom_display  = nom.get("display_name", "")
                res.add_source("Nominatim / OpenStreetMap")

        # ── Stage 4: geocode.maps.co (backup free geocoder) ──────────────────
        gm_lat = gm_lon = None
        if query_str and nom_lat is None:
            gm = self._geocodemaps_geocode(query_str, phone.iso2)
            if gm:
                gm_lat = float(gm.get("lat", 0))
                gm_lon = float(gm.get("lon", 0))
                res.add_source("geocode.maps.co")

        # ── Stage 5: Pick best coordinates (confidence cascade) ───────────────
        # Priority: OpenCage (high confidence) > Nominatim > geocode.maps.co
        #           > PrefixCityDB > country centroid
        if oc_lat is not None and oc_confidence >= 5:
            final_lat, final_lon = oc_lat, oc_lon
            precision = f"High — OpenCage (confidence {oc_confidence}/10)"
            self.log.push(f"  ★ Best coords: OpenCage {final_lat:.6f},{final_lon:.6f}", "ok")
        elif nom_lat is not None:
            final_lat, final_lon = nom_lat, nom_lon
            precision = "Good — Nominatim / OpenStreetMap"
            self.log.push(f"  ★ Best coords: Nominatim {final_lat:.6f},{final_lon:.6f}", "ok")
        elif gm_lat is not None:
            final_lat, final_lon = gm_lat, gm_lon
            precision = "Good — geocode.maps.co"
        elif db_lat is not None:
            final_lat, final_lon = db_lat, db_lon
            precision = "Good — built-in prefix database"
            self.log.push(f"  ★ Best coords: PrefixDB {final_lat:.6f},{final_lon:.6f}", "ok")
        else:
            final_lat = final_lon = None
            precision = "Country-level only (no city match)"

        # ── Stage 6: BigDataCloud reverse geocode (enrich with district) ──────
        bdc_city = bdc_locality = bdc_district = bdc_postcode_r = bdc_country_r = ""
        if final_lat is not None:
            bdc = self._bigdatacloud_reverse(final_lat, final_lon)
            if bdc:
                bdc_city      = bdc.get("city", "")
                bdc_locality  = bdc.get("locality", "")
                admin_list    = (bdc.get("localityInfo", {})
                                    .get("administrative", []))
                bdc_district  = admin_list[0].get("name", "") if admin_list else ""
                bdc_postcode_r= bdc.get("postcode", "")
                bdc_country_r = bdc.get("countryName", "")
                res.add_source("BigDataCloud (reverse)")

        # ── Stage 7: restcountries.com (country metadata) ─────────────────────
        country_meta = {}
        if phone.iso2:
            data = self._safe_get(
                f"https://restcountries.com/v3.1/alpha/{phone.iso2}",
                label="restcountries.com")
            if data and isinstance(data, list):
                country_meta = data[0]
                res.add_source("restcountries.com")

                # Use country centroid as absolute last fallback
                if final_lat is None:
                    latlng = country_meta.get("latlng", [])
                    if len(latlng) == 2:
                        final_lat, final_lon = latlng[0], latlng[1]
                        precision = "Country centroid (fallback — no city match)"

        # ── Assemble best names ───────────────────────────────────────────────
        best_city    = (oc_city or bdc_city or bdc_locality or
                        nom_city or db_city or offline_desc or "Unknown")
        best_state   = (oc_state or nom_state or db_state or "Unknown")
        best_country = (oc_country or bdc_country_r or
                        country_meta.get("name", {}).get("common", phone.iso2 or "Unknown"))
        best_postcode= (oc_postcode or nom_postcode or bdc_postcode_r or "")
        best_county  = (nom_county or bdc_district or "")
        best_full    = (oc_formatted or nom_display or "")

        # Country metadata
        capital   = (country_meta.get("capital", ["Unknown"])[0]
                     if country_meta.get("capital") else "Unknown")
        region    = country_meta.get("region", "Unknown")
        subregion = country_meta.get("subregion", "Unknown")
        population= country_meta.get("population", 0)
        area      = country_meta.get("area", 0)
        tz_rc     = country_meta.get("timezones", phone.timezones)
        maps_c    = country_meta.get("maps", {})

        tz_str = ", ".join(tz_rc[:4]) if tz_rc else "Unknown"
        if len(tz_rc) > 4: tz_str += f" (+{len(tz_rc)-4} more)"

        # ── Build map links ───────────────────────────────────────────────────
        if final_lat is not None:
            lat_s = f"{final_lat:.7f}"
            lon_s = f"{final_lon:.7f}"
            zoom  = 13 if "centroid" not in precision.lower() else 6
            gmaps_pin    = f"https://maps.google.com/?q={lat_s},{lon_s}&z={zoom}"
            gmaps_street = f"https://maps.google.com/?layer=c&cbll={lat_s},{lon_s}"
            gearth       = f"https://earth.google.com/web/@{lat_s},{lon_s},500a,1000d,35y"
            osm_pin      = (f"https://www.openstreetmap.org/?mlat={lat_s}"
                            f"&mlon={lon_s}#map={zoom}/{lat_s}/{lon_s}")
            waze         = f"https://waze.com/ul?ll={lat_s},{lon_s}&navigate=yes"
            apple_maps   = f"https://maps.apple.com/?ll={lat_s},{lon_s}&z={zoom}"
        else:
            lat_s = lon_s = "Unknown"
            gmaps_pin = gmaps_street = gearth = osm_pin = waze = apple_maps = ""

        # ── Output ────────────────────────────────────────────────────────────
        res.add("__SEP__", "📍 COORDINATES", "heading")
        res.add("Latitude (decimal)",   lat_s)
        res.add("Longitude (decimal)",  lon_s)
        if final_lat is not None:
            res.add("Latitude (DMS)",   self._to_dms(final_lat, "lat"))
            res.add("Longitude (DMS)",  self._to_dms(final_lon, "lon"))
        res.add("Precision",            precision)
        if oc_confidence:
            res.add("OpenCage Confidence", f"{oc_confidence} / 10")

        res.add("__SEP__", "🏙 LOCATION DETAIL", "heading")
        res.add("City / Area",          best_city)
        if best_county:
            res.add("District / County",best_county)
        res.add("State / Province",     best_state)
        if best_postcode:
            res.add("Postcode / ZIP",   best_postcode)
        res.add("Country",              f"{phone.flag_emoji}  {best_country}")
        res.add("Continent",            region)
        res.add("Sub-Region",           subregion)
        res.add("Capital City",         capital)
        if best_full:
            res.add("Full Address",     best_full[:140])

        res.add("__SEP__", "🌐 COUNTRY & NETWORK", "heading")
        res.add("Land Area",            f"{area:,.0f} km²" if area else "Unknown")
        res.add("Population",           f"{population:,}" if population else "Unknown")
        res.add("Timezone(s)",          tz_str)
        res.add("Number Type",          phone.number_type)
        res.add("Dialling Code",        f"+{phone.country_code}")
        res.add("ISO-2",                phone.iso2 or "Unknown")

        res.add("__SEP__", "🗺 MAP LINKS", "heading")
        if gmaps_pin:
            res.add("📍 Google Maps",       gmaps_pin,    "url")
            res.add("🛣 Google Street View",gmaps_street, "url")
            res.add("🛰 Google Earth",      gearth,       "url")
            res.add("🗺 OpenStreetMap",     osm_pin,      "url")
            res.add("🚗 Waze",              waze,         "url")
            res.add("🍎 Apple Maps",        apple_maps,   "url")
        if maps_c.get("googleMaps"):
            res.add("🌍 Country (Google Maps)", maps_c["googleMaps"], "url")

        if not oc_key:
            res.add("__SEP__", "", "divider")
            res.add("💡 Tip",
                    "Add a free OpenCage key in ⚙ Settings for higher-accuracy "
                    "geocoding (2,500 lookups/day free → opencagedata.com)", "note")

        self.log.push("Maximum-Precision Geolocation complete ✓", "done")
        return res

    # ── OpenCage geocoder ──────────────────────────────────────────────────────
    def _opencage_geocode(self, query: str, iso2: str, key: str) -> Optional[dict]:
        q = f"{query}, {iso2}" if iso2 else query
        self.log.push(f"  → OpenCage: '{q}' …", "api")
        try:
            r = self.http.get(self.OPENCAGE_URL,
                              params={"q": q, "key": key,
                                      "countrycode": iso2.lower() if iso2 else "",
                                      "limit": 1, "no_annotations": 0,
                                      "language": "en"},
                              timeout=10)
            r.raise_for_status()
            results = r.json().get("results", [])
            if results:
                self.log.push(
                    f"  ✓ OpenCage confidence={results[0].get('confidence',0)}", "ok")
                return results[0]
        except Exception as exc:
            self.log.push(f"  ✗ OpenCage: {exc}", "err")
        return None

    # ── Nominatim geocoder ────────────────────────────────────────────────────
    def _nominatim_geocode(self, query: str, iso2: str) -> Optional[dict]:
        q = f"{query}, {iso2}" if iso2 else query
        self.log.push(f"  → Nominatim: '{q}' …", "api")
        try:
            r = self.http.get(
                self.NOMINATIM_URL,
                params={"q": q, "format": "json", "addressdetails": 1,
                        "limit": 1, "countrycodes": iso2.lower() if iso2 else ""},
                headers={"User-Agent": "PhoneIntelApp/2.0 (research)"},
                timeout=10)
            results = r.json()
            if results:
                self.log.push("  ✓ Nominatim hit", "ok")
                return results[0]
            # retry without country restriction
            r2 = self.http.get(
                self.NOMINATIM_URL,
                params={"q": query, "format": "json",
                        "addressdetails": 1, "limit": 1},
                headers={"User-Agent": "PhoneIntelApp/2.0"},
                timeout=10)
            results2 = r2.json()
            if results2:
                self.log.push("  ✓ Nominatim fallback hit", "ok")
                return results2[0]
        except Exception as exc:
            self.log.push(f"  ✗ Nominatim: {exc}", "err")
        return None

    # ── geocode.maps.co ───────────────────────────────────────────────────────
    def _geocodemaps_geocode(self, query: str, iso2: str) -> Optional[dict]:
        q = f"{query}, {iso2}" if iso2 else query
        self.log.push(f"  → geocode.maps.co: '{q}' …", "api")
        try:
            r = self.http.get(self.GEOCODEMAPS_URL,
                              params={"q": q}, timeout=10)
            results = r.json()
            if results:
                self.log.push("  ✓ geocode.maps.co hit", "ok")
                return results[0]
        except Exception as exc:
            self.log.push(f"  ✗ geocode.maps.co: {exc}", "err")
        return None

    # ── BigDataCloud reverse geocode ──────────────────────────────────────────
    def _bigdatacloud_reverse(self, lat: float, lon: float) -> Optional[dict]:
        self.log.push(f"  → BigDataCloud reverse: {lat:.5f},{lon:.5f} …", "api")
        try:
            r = self.http.get(
                self.BIGDATA_URL,
                params={"latitude": lat, "longitude": lon,
                        "localityLanguage": "en"}, timeout=10)
            r.raise_for_status()
            self.log.push("  ✓ BigDataCloud hit", "ok")
            return r.json()
        except Exception as exc:
            self.log.push(f"  ✗ BigDataCloud: {exc}", "err")
        return None

    # ── DMS converter ─────────────────────────────────────────────────────────
    @staticmethod
    def _to_dms(dd: float, axis: str) -> str:
        direction = ("N" if dd >= 0 else "S") if axis == "lat" else ("E" if dd >= 0 else "W")
        dd = abs(dd)
        deg = int(dd)
        mn  = int((dd - deg) * 60)
        sec = round(((dd - deg) * 60 - mn) * 60, 3)
        return f"{deg}° {mn}' {sec}\" {direction}"


# ══════════════════════════════════════════════════════════════════════════════
#  SERVICE 2 — COUNTRY DETAILS
# ══════════════════════════════════════════════════════════════════════════════

class CountryDetailsService(LookupService):

    def title(self) -> str: return "Country Details"
    def icon(self) -> str:  return "🌍"

    def run(self, phone: PhoneNumber) -> LookupResult:
        res = LookupResult("Phone Country Details", "🌍")
        self.log.push("──── Country Details ───────────────────────", "start")

        if not phone.iso2:
            res.add("Error", "Cannot determine country ISO code.", "warn")
            return res

        # ── restcountries.com ────────────────────────────────────────────────
        data = self._safe_get(
            f"https://restcountries.com/v3.1/alpha/{phone.iso2}",
            label="restcountries.com")

        if data and isinstance(data, list):
            c = data[0]
            res.add_source("restcountries.com")
            flag_e  = phone.flag_emoji
            name_c  = c.get("name", {}).get("common", "Unknown")
            name_o  = c.get("name", {}).get("official", "")
            cap_lst = c.get("capital", [])
            capital = cap_lst[0] if cap_lst else "Unknown"
            region  = c.get("region", "Unknown")
            subreg  = c.get("subregion", "Unknown")
            pop     = c.get("population", 0)
            area    = c.get("area", 0)
            tld_lst = c.get("tld", [])
            tld     = ", ".join(tld_lst) if tld_lst else "Unknown"
            curr    = c.get("currencies", {})
            curr_s  = ", ".join(
                f"{v.get('name',k)} ({v.get('symbol','')})"
                for k, v in curr.items()) if curr else "Unknown"
            langs   = c.get("languages", {})
            lang_s  = ", ".join(sorted(langs.values())) if langs else "Unknown"
            idd     = c.get("idd", {})
            call_c  = idd.get("root","") + (idd.get("suffixes",[""])[0])
            tz_lst  = c.get("timezones", [])
            tz_s    = ", ".join(tz_lst[:5]) + (
                f" (+{len(tz_lst)-5} more)" if len(tz_lst) > 5 else "")
            borders = c.get("borders", [])
            bord_s  = ", ".join(borders) if borders else "None (island / no land borders)"
            car     = c.get("car", {})
            drive   = car.get("side", "?").capitalize()
            demonym = c.get("demonyms", {}).get("eng", {}).get("m", "Unknown")
            latlng  = c.get("latlng", [])
            coords  = f"{latlng[0]}°, {latlng[1]}°" if len(latlng)==2 else "Unknown"
            un      = "Yes" if c.get("unMember") else "No"
            indep   = "Yes" if c.get("independent") else "No"
            lock    = "Yes" if c.get("landlocked") else "No (coastal)"
            sow     = c.get("startOfWeek", "monday").capitalize()
            gini    = c.get("gini", {})
            gini_s  = (f"{list(gini.values())[0]} ({list(gini.keys())[0]})"
                       if gini else "Unknown")
            maps    = c.get("maps", {})
            coat    = c.get("coatOfArms", {}).get("svg", "")

            res.add("Country Name",        f"{flag_e}  {name_c}")
            res.add("Official Name",        name_o or name_c)
            res.add("ISO Alpha-2",          phone.iso2)
            res.add("ISO Alpha-3",          c.get("cca3", "Unknown"))
            res.add("UN Numeric Code",      c.get("ccn3", "Unknown"))
            res.add("Capital City",         capital)
            res.add("Continent",            region)
            res.add("Sub-Region",           subreg)
            res.add("Coordinates",          coords)
            res.add("Land Area",            f"{area:,.0f} km²" if area else "Unknown")
            res.add("Population",           f"{pop:,}" if pop else "Unknown")
            res.add("Currency",             curr_s)
            res.add("Official Language(s)", lang_s)
            res.add("Demonym",              demonym)
            res.add("Calling Code",         call_c or f"+{phone.country_code}")
            res.add("Top-Level Domain",     tld)
            res.add("Timezone(s)",          tz_s or "Unknown")
            res.add("Bordering Countries",  bord_s)
            res.add("Driving Side",         drive)
            res.add("Landlocked",           lock)
            res.add("UN Member",            un)
            res.add("Independent",          indep)
            res.add("Week Starts",          sow)
            res.add("Gini Index",           gini_s)
            if maps.get("googleMaps"):
                res.add("Google Maps",       maps["googleMaps"], "url")
            if maps.get("openStreetMaps"):
                res.add("OpenStreetMap",     maps["openStreetMaps"], "url")
        else:
            res.add("Error", "Could not retrieve country data from restcountries.com", "warn")
            res.add("Country Code",  f"+{phone.country_code}")
            res.add("ISO-2",         phone.iso2)

        # ── World Bank API ────────────────────────────────────────────────────
        wb = self._safe_get(
            f"https://api.worldbank.org/v2/country/{phone.iso2}?format=json",
            label="World Bank API")
        if wb and isinstance(wb, list) and len(wb) > 1 and wb[1]:
            wb_d = wb[1][0]
            res.add_source("World Bank")
            income = wb_d.get("incomeLevel", {}).get("value", "")
            lend   = wb_d.get("lendingType", {}).get("value", "")
            reg_wb = wb_d.get("region", {}).get("value", "")
            if income: res.add("Income Level", income)
            if lend:   res.add("Lending Type",  lend)
            if reg_wb: res.add("WB Region",     reg_wb)

        self.log.push("Country Details lookup complete ✓", "done")
        return res


# ══════════════════════════════════════════════════════════════════════════════
#  SERVICE 3 — SERVICE PROVIDER
# ══════════════════════════════════════════════════════════════════════════════

class ServiceProviderService(LookupService):

    def title(self) -> str: return "Service Provider"
    def icon(self) -> str:  return "📡"

    def run(self, phone: PhoneNumber) -> LookupResult:
        res = LookupResult("Service Provider / Carrier", "📡")
        self.log.push("──── Service Provider ───────────────────────", "start")

        carrier_name = phone.offline_carrier or ""
        line_type    = phone.number_type
        country_str  = phone.iso2
        location_str = phone.offline_geo
        valid_str    = "Yes"
        res.add_source("phonenumbers (offline)")

        # ── numverify.com (optional key) ─────────────────────────────────────
        nv_key = self.config.get("numverify_key")
        if nv_key:
            data = self._safe_get(
                "http://apilayer.net/api/validate",
                params={"access_key": nv_key, "number": phone.e164, "format": 1},
                label="numverify.com")
            if data and not data.get("error"):
                carrier_name = data.get("carrier", carrier_name) or carrier_name
                line_type    = data.get("line_type", line_type) or line_type
                country_str  = data.get("country_name", "") or country_str
                location_str = data.get("location", location_str) or location_str
                valid_str    = "Yes" if data.get("valid") else "No"
                res.add_source("numverify.com")

        # ── AbstractAPI (optional key) ────────────────────────────────────────
        abs_key = self.config.get("abstract_key")
        if abs_key:
            data = self._safe_get(
                "https://phonevalidation.abstractapi.com/v1/",
                params={"api_key": abs_key, "phone": phone.e164},
                label="AbstractAPI")
            if data and data.get("valid"):
                carrier_name = data.get("carrier", carrier_name) or carrier_name
                country_str  = data.get("country", {}).get("name", country_str)
                line_type    = data.get("type", line_type) or line_type
                res.add_source("AbstractAPI")

        # ── Veriphone.io (optional key) ───────────────────────────────────────
        vp_key = self.config.get("veriphone_key")
        if vp_key:
            data = self._safe_get(
                "https://api.veriphone.io/v2/verify",
                params={"phone": phone.e164, "key": vp_key},
                label="veriphone.io")
            if data and data.get("status") == "success":
                carrier_name = data.get("carrier", carrier_name) or carrier_name
                country_str  = data.get("country", country_str)
                line_type    = data.get("phone_type", line_type) or line_type
                res.add_source("veriphone.io")

        # ── Wikipedia carrier enrichment ──────────────────────────────────────
        wiki_summary = ""
        if carrier_name:
            wiki_summary = self._wiki_carrier(carrier_name)

        # ── Network tech inference ────────────────────────────────────────────
        lt = (line_type or "").lower()
        if   "mobile" in lt: net = "GSM / 3G / LTE / 5G"
        elif "fixed"  in lt: net = "PSTN / Copper / Fibre"
        elif "voip"   in lt: net = "VoIP (Internet-based)"
        elif "toll"   in lt: net = "Toll-Free (Freephone)"
        elif "pager"  in lt: net = "Paging Network"
        else:                net = "Unknown"

        # ── Fields ───────────────────────────────────────────────────────────
        res.add("Carrier / Operator",   carrier_name or "Unknown — add API key in Settings")
        res.add("Network Technology",   net)
        res.add("Line / Number Type",   line_type or "Unknown")
        res.add("Number Valid",         valid_str)
        res.add("Country",              country_str or "Unknown")
        res.add("Location",             location_str or "Unknown")
        res.add("Dialling Code",        f"+{phone.country_code}")
        res.add("National Format",      phone.national_format)
        res.add("International Format", phone.international_format)
        res.add("E.164",                phone.e164)
        if wiki_summary:
            res.add("Carrier Info",     wiki_summary, "note")
        if not nv_key and not abs_key and not vp_key:
            res.add("", "", "divider")
            res.add("Tip",
                    "Add a free API key in ⚙ Settings for detailed carrier data", "note")

        self.log.push("Service Provider lookup complete ✓", "done")
        return res

    def _wiki_carrier(self, carrier_name: str) -> str:
        """Fetch a brief Wikipedia summary for the carrier."""
        try:
            slug = carrier_name.replace(" ", "_")
            url  = f"https://en.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(slug)}"
            r = self.http.get(url, timeout=6)
            if r.status_code == 200:
                d = r.json()
                extract = d.get("extract", "")
                if extract:
                    sentences = re.split(r'(?<=[.!?]) +', extract)
                    return " ".join(sentences[:2])[:250]
        except Exception:
            pass
        return ""


# ══════════════════════════════════════════════════════════════════════════════
#  SERVICE 4 — REGISTERED USER / OSINT
# ══════════════════════════════════════════════════════════════════════════════

class RegisteredUserService(LookupService):

    def title(self) -> str: return "Registered User"
    def icon(self) -> str:  return "👤"

    def run(self, phone: PhoneNumber) -> LookupResult:
        res = LookupResult("Registered User / OSINT Lookup", "👤")
        self.log.push("──── Registered User / OSINT ───────────────", "start")

        number_enc   = urllib.parse.quote(phone.e164)
        number_plain = phone.e164.lstrip("+")

        # ── DuckDuckGo Instant Answers ────────────────────────────────────────
        ddg_abstract = ""
        ddg_entity   = ""
        data = self._safe_get(
            "https://api.duckduckgo.com/",
            params={"q": phone.international_format, "format": "json",
                    "no_redirect": "1", "no_html": "1", "skip_disambig": "1"},
            label="DuckDuckGo Instant Answers")
        if data:
            ddg_abstract = data.get("Abstract", "") or data.get("Answer", "")
            ddg_entity   = data.get("Entity", "")
            res.add_source("DuckDuckGo Instant Answers")

        # ── DuckDuckGo HTML search ────────────────────────────────────────────
        search_hits: list[tuple] = []
        if BS4_OK:
            html = self._safe_get_html(
                "https://html.duckduckgo.com/html/",
                params={"q": f'"{phone.e164}" OR "{phone.international_format}"'},
                label="DuckDuckGo Search Scrape",
                timeout=12)
            if html:
                soup = BeautifulSoup(html, "html.parser")
                titles_el   = soup.select(".result__a")
                snippets_el = soup.select(".result__snippet")
                for t_el, s_el in zip(titles_el[:7], snippets_el[:7]):
                    title   = t_el.get_text(strip=True)[:80]
                    snippet = s_el.get_text(strip=True)[:200]
                    if snippet:
                        search_hits.append((title, snippet))
                res.add_source("DuckDuckGo Search")

        # ── Spam/Scam DB scrape ───────────────────────────────────────────────
        spam_info = self._check_spam(phone)

        # ── ShouldIAnswer.com ─────────────────────────────────────────────────
        sia_info = self._check_shouldianswer(phone)

        # ── Assemble fields ───────────────────────────────────────────────────
        res.add("Phone Number",      phone.international_format)
        res.add("E.164",             phone.e164)

        # DuckDuckGo instant
        if ddg_abstract:
            res.add("Web Abstract",  ddg_abstract[:220])
        if ddg_entity:
            res.add("Entity Type",   ddg_entity)

        # Spam / scam
        res.add("__SEP__", "SPAM / SCAM STATUS", "heading")
        if spam_info or sia_info:
            if spam_info.get("risk"):
                res.add("⚠  Risk Level",    spam_info["risk"],    "warn")
            if spam_info.get("label"):
                res.add("⚠  Spam Label",    spam_info["label"],   "warn")
            if sia_info.get("rating"):
                res.add("Community Rating", sia_info["rating"])
            if sia_info.get("reports"):
                res.add("Report Count",     sia_info["reports"])
        else:
            res.add("Status", "No public spam reports found at query time", "good")

        # Web search results
        res.add("__SEP__", "WEB SEARCH RESULTS", "heading")
        if search_hits:
            for i, (title, snippet) in enumerate(search_hits, 1):
                res.add(f"Result {i}", title)
                res.add("  ↳", snippet, "note")
        else:
            res.add("Web Results",
                    "No public web mentions found (number may be private)", "muted")

        # Deep links
        res.add("__SEP__", "DEEP LINKS & OSINT TOOLS", "heading")
        res.add("Truecaller",
                f"https://www.truecaller.com/search/{phone.iso2.lower()}/{number_plain}",
                "url")
        res.add("Sync.me",
                f"https://sync.me/search/?number={number_enc}", "url")
        res.add("WhoCallsMe",
                f"https://www.whocallsme.com/Phone-Number.aspx/{number_plain}", "url")
        res.add("SpyDialer",
                f"https://spydialer.com/default.aspx?phone={number_plain}", "url")
        res.add("ShouldIAnswer",
                f"https://www.shouldianswer.com/phone-number/{number_plain}", "url")
        res.add("CallerID Test",
                f"https://calleridtest.com/lookup?phone={number_enc}", "url")
        res.add("Google Search",
                f"https://google.com/search?q=%22{number_enc}%22", "url")

        res.add("__SEP__", "", "divider")
        res.add("⚖  Legal Notice",
                "This tool only surfaces publicly available data. Accessing private "
                "subscriber records without consent is illegal.", "note")

        self.log.push("Registered User lookup complete ✓", "done")
        return res

    def _check_spam(self, phone: PhoneNumber) -> dict:
        """Scrape hiya.com for risk data."""
        if not BS4_OK:
            return {}
        try:
            url  = f"https://hiya.com/phoneNumber/{phone.e164.lstrip('+')}"
            html = self._safe_get_html(url, label="hiya.com", timeout=8)
            if html:
                soup = BeautifulSoup(html, "html.parser")
                risk_el  = soup.find(class_=re.compile(r"risk|spam|label", re.I))
                if risk_el:
                    return {"risk": risk_el.get_text(strip=True)}
        except Exception:
            pass
        return {}

    def _check_shouldianswer(self, phone: PhoneNumber) -> dict:
        """Scrape shouldianswer.com for community rating."""
        if not BS4_OK:
            return {}
        try:
            url  = (f"https://www.shouldianswer.com/phone-number/"
                    f"{phone.e164.lstrip('+')}")
            html = self._safe_get_html(url, label="shouldianswer.com", timeout=8)
            if html:
                soup    = BeautifulSoup(html, "html.parser")
                rat_el  = soup.select_one(".global_note")
                rep_el  = soup.select_one(".nb_eval")
                result  = {}
                if rat_el: result["rating"]  = rat_el.get_text(strip=True)
                if rep_el: result["reports"] = rep_el.get_text(strip=True)
                return result
        except Exception:
            pass
        return {}


# ══════════════════════════════════════════════════════════════════════════════
#  RESULT EXPORTER
# ══════════════════════════════════════════════════════════════════════════════

class ResultExporter:

    @staticmethod
    def build_text(phone: PhoneNumber, results: list) -> str:
        sep  = "=" * 65
        thin = "─" * 65
        lines = [
            sep,
            "      PHONE NUMBER INTELLIGENCE REPORT  v2.0",
            "      Internet-Powered Deep Research",
            sep,
            f"  Number (input)  : {phone.raw}",
            f"  International   : {phone.international_format}",
            f"  E.164           : {phone.e164}",
            f"  ISO-2           : {phone.iso2}",
            f"  Number Type     : {phone.number_type}",
            f"  Generated       : {datetime.now().strftime('%Y-%m-%d  %H:%M:%S')}",
            sep, "",
        ]
        for r in results:
            lines += [f"  {r.icon}  {r.title}", "  " + thin]
            for key, val, tag in r.fields:
                if key == "__SEP__":
                    lines += ["", f"  ◆  {val}", "  " + "·"*40]
                    continue
                if key.startswith("─") or tag in ("divider",):
                    lines.append("")
                    continue
                lines.append(f"  {key:<30}  {val}")
            if r.sources:
                lines += ["", f"  Sources: {', '.join(r.sources)}"]
            if r.errors:
                for e in r.errors:
                    lines.append(f"  ⚠  {e}")
            lines += ["", ""]
        lines += [sep, "  End of Report", sep]
        return "\n".join(lines)

    @staticmethod
    def save(text: str, filepath: str):
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(text)


# ══════════════════════════════════════════════════════════════════════════════
#  SETTINGS DIALOG
# ══════════════════════════════════════════════════════════════════════════════

class SettingsDialog(tk.Toplevel):

    CLR  = {"bg":"#0D1117","surface":"#161B22","surface2":"#1C2333",
            "border":"#30363D","accent":"#58A6FF","text":"#E6EDF3",
            "muted":"#8B949E","accent2":"#3FB950","warning":"#F0883E"}
    FONT = "Consolas"

    def __init__(self, parent, config: ConfigManager):
        super().__init__(parent)
        self.config = config
        self.title("⚙  API Keys & Settings")
        self.geometry("580x640")
        self.configure(bg=self.CLR["bg"])
        self.resizable(False, False)
        self.grab_set()
        self._entries: dict = {}
        self._build()

    def _field(self, parent, label: str, sub: str, key: str, ph: str):
        tk.Label(parent, text=label, font=(self.FONT, 10),
                 fg=self.CLR["text"], bg=parent["bg"]).pack(
                     anchor="w", padx=18, pady=(10, 1))
        tk.Label(parent, text=sub, font=(self.FONT, 8),
                 fg=self.CLR["muted"], bg=parent["bg"]).pack(
                     anchor="w", padx=22, pady=(0, 2))
        var = tk.StringVar(value=self.config.get(key))
        e = tk.Entry(parent, textvariable=var,
                     font=(self.FONT, 11),
                     bg=self.CLR["surface2"], fg=self.CLR["text"],
                     insertbackground=self.CLR["accent"],
                     relief="flat", bd=0,
                     highlightthickness=1,
                     highlightbackground=self.CLR["border"],
                     highlightcolor=self.CLR["accent"],
                     show="*" if "key" in key.lower() else "")
        e.pack(fill="x", padx=18, ipady=7, ipadx=8)

        show_var = tk.BooleanVar(value=False)
        def toggle():
            e.config(show="" if show_var.get() else "*")
        tk.Checkbutton(parent, text="Show key", variable=show_var,
                       command=toggle, font=(self.FONT, 8),
                       fg=self.CLR["muted"], bg=parent["bg"],
                       selectcolor=self.CLR["surface2"],
                       activebackground=parent["bg"],
                       activeforeground=self.CLR["accent"],
                       bd=0).pack(anchor="e", padx=18)

        self._entries[key] = var

    def _build(self):
        tk.Label(self, text="⚙  API Keys & Settings",
                 font=(self.FONT, 14, "bold"),
                 fg=self.CLR["accent"], bg=self.CLR["bg"]).pack(pady=14)

        f = tk.Frame(self, bg=self.CLR["surface"])
        f.pack(fill="x", padx=14, pady=(0, 8))

        self._field(f, "numverify.com API Key  (Carrier lookup)",
                    "Free: 100 req/month  →  https://numverify.com",
                    "numverify_key", "Paste key here …")
        self._field(f, "AbstractAPI Phone Key  (Validation + carrier)",
                    "Free: 250 req/month  →  https://abstractapi.com",
                    "abstract_key", "Paste key here …")
        self._field(f, "Veriphone.io API Key  (Phone verification)",
                    "Free: 1000 req/month  →  https://veriphone.io",
                    "veriphone_key", "Paste key here …")
        self._field(f, "OpenCage Geocoder Key  (📍 High-precision lat/lng)",
                    "Free: 2,500 lookups/day  →  https://opencagedata.com",
                    "opencage_key", "Paste key here …")

        note = tk.Frame(self, bg="#0A2A0A")
        note.pack(fill="x", padx=14, pady=(0, 10))
        tk.Label(note,
                 text=("  ✓  Without any keys, the tool still uses:\n"
                       "     phonenumbers · PrefixCityDB · restcountries.com\n"
                       "     DuckDuckGo · Wikipedia · Nominatim · BigDataCloud\n"
                       "  ★  OpenCage key = highest-accuracy lat/lng geocoding\n"
                       "  ★  Add carrier keys for richer operator data"),
                 font=(self.FONT, 9), fg=self.CLR["accent2"],
                 bg=note["bg"], justify="left").pack(padx=6, pady=8)

        row = tk.Frame(self, bg=self.CLR["bg"])
        row.pack(pady=8)
        tk.Button(row, text="  ✓  Save Settings  ",
                  font=(self.FONT, 11, "bold"),
                  bg=self.CLR["accent"], fg="#0D1117",
                  relief="flat", padx=16, pady=8, cursor="hand2",
                  command=self._save).pack(side="left", padx=8)
        tk.Button(row, text="  Cancel  ",
                  font=(self.FONT, 11),
                  bg=self.CLR["surface2"], fg=self.CLR["muted"],
                  relief="flat", padx=16, pady=8, cursor="hand2",
                  command=self.destroy).pack(side="left")

    def _save(self):
        for key, var in self._entries.items():
            self.config.set(key, var.get().strip())
        messagebox.showinfo("Saved", "API keys saved successfully!", parent=self)
        self.destroy()


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN APPLICATION  –  PhoneIntelApp
# ══════════════════════════════════════════════════════════════════════════════

WELCOME = """
  Welcome to Phone Number Intelligence Tool  v2.0

  ── How to Use ──────────────────────────────────────────────────────
  1.  Type a phone number (with country code) in the box above
  2.  Press  🔍 Analyse  or hit  Enter  to validate the number
  3.  Click any of the 4 lookup buttons for live internet research
  4.  Watch the  🛰 Activity Log  (right panel) for real-time status
  5.  Use  💾 Save  or  📄 Save All  to export the report as .txt

  ── Live Sources (free, no key required) ─────────────────────────────
  ✓  PrefixCityDB          — built-in 300+ area-code → city database
  ✓  phonenumbers          — offline parsing, geo, carrier, timezone
  ✓  Nominatim / OSM       — free geocoder (city-level lat/lng)
  ✓  geocode.maps.co       — backup free geocoder
  ✓  BigDataCloud          — free reverse geocode (district, postcode)
  ✓  restcountries.com     — rich country details (30+ fields)
  ✓  World Bank API        — income level, economic classification
  ✓  DuckDuckGo            — OSINT web search & instant answers
  ✓  Wikipedia API         — carrier background information
  ✓  ShouldIAnswer.com     — community spam/scam ratings

  ── Optional Free API Keys (add in ⚙ Settings) ──────────────────────
  ★  opencagedata.com  — highest-accuracy geocoding   (2500/day free)
  ★  numverify.com     — deep carrier data             (100/month free)
  ★  abstractapi.com   — phone validation              (250/month free)
  ★  veriphone.io      — carrier + validation        (1000/month free)

  ── Examples ─────────────────────────────────────────────────────────
  +1 202 555 0173        (United States)
  +44 7911 123456        (United Kingdom)
  +91 98765 43210        (India)
  +49 30 12345678        (Germany)
  +86 138 0013 8000      (China)
  +234 803 000 0000      (Nigeria)
  +55 11 91234 5678      (Brazil)
  ─────────────────────────────────────────────────────────────────────
"""


class PhoneIntelApp:

    CLR  = {"bg":"#0D1117","surface":"#161B22","surface2":"#1C2333",
            "border":"#30363D","accent":"#58A6FF","accent2":"#3FB950",
            "accent3":"#F0883E","accent4":"#BC8CFF","text":"#E6EDF3",
            "muted":"#8B949E","danger":"#F85149","warning":"#F0E68C",
            "log_bg":"#080C12"}
    FONT = "Consolas"

    def __init__(self):
        self.root    = tk.Tk()
        self.config  = ConfigManager()
        self.log     = ActivityLog()
        self._http:          Optional[HttpClient]   = None
        self._services:      Optional[list]         = None
        self._phone:         Optional[PhoneNumber]  = None
        self._last_results:  list[LookupResult]     = []
        self._busy           = False

        self._setup_window()
        self._build_ui()
        self._poll_log()

    def _http_client(self) -> Optional[HttpClient]:
        if self._http is None and REQUESTS_OK:
            self._http = HttpClient(
                timeout  = int(self.config.get("timeout", 10)),
                retries  = int(self.config.get("max_retries", 2)))
        return self._http

    def _get_services(self) -> list:
        if self._services is None:
            h = self._http_client()
            self._services = [
                GeolocationService(h, self.log, self.config),
                CountryDetailsService(h, self.log, self.config),
                ServiceProviderService(h, self.log, self.config),
                RegisteredUserService(h, self.log, self.config),
            ]
        return self._services

    # ── Window ────────────────────────────────────────────────────────────────
    def _setup_window(self):
        self.root.title("Phone Number Intelligence Tool  v2.0  —  Internet Edition")
        self.root.geometry("1100x800")
        self.root.minsize(900, 680)
        self.root.configure(bg=self.CLR["bg"])

    # ── Full UI ───────────────────────────────────────────────────────────────
    def _build_ui(self):
        self._build_header()
        self._build_input()
        self._build_buttons()

        pane = tk.PanedWindow(self.root, orient="horizontal",
                              bg=self.CLR["bg"], bd=0,
                              sashwidth=5, sashrelief="flat")
        pane.pack(fill="both", expand=True, padx=14, pady=(10, 0))
        self._build_results(pane)
        self._build_log(pane)
        self._build_footer()

    # ── Header ────────────────────────────────────────────────────────────────
    def _build_header(self):
        h = tk.Frame(self.root, bg=self.CLR["surface"], pady=12)
        h.pack(fill="x")

        l = tk.Frame(h, bg=h["bg"])
        l.pack(side="left", padx=18)
        tk.Label(l, text="📱  PHONE NUMBER INTELLIGENCE  v2.0",
                 font=(self.FONT, 17, "bold"),
                 fg=self.CLR["accent"], bg=h["bg"]).pack(anchor="w")
        tk.Label(l,
                 text="Live Internet Edition  ·  Geolocation · Country · "
                      "Carrier · OSINT  ·  Multi-source Research",
                 font=(self.FONT, 9), fg=self.CLR["muted"], bg=h["bg"]).pack(
                     anchor="w", pady=(2, 0))

        r = tk.Frame(h, bg=h["bg"])
        r.pack(side="right", padx=18)
        tk.Button(r, text="  ⚙  Settings / API Keys  ",
                  font=(self.FONT, 10),
                  bg=self.CLR["surface2"], fg=self.CLR["accent"],
                  relief="flat", padx=12, pady=6, cursor="hand2",
                  command=self._open_settings).pack()

        # Missing libs bar
        missing = []
        if not PHONENUMBERS_OK:   missing.append("phonenumbers")
        if not REQUESTS_OK:       missing.append("requests")
        if not BS4_OK:            missing.append("beautifulsoup4")
        if missing:
            bar = tk.Frame(self.root, bg="#2D1500", pady=5)
            bar.pack(fill="x")
            tk.Label(bar,
                     text=f"⚠  Missing:  pip install {' '.join(missing)}",
                     font=(self.FONT, 9), fg=self.CLR["warning"],
                     bg=bar["bg"]).pack()

    # ── Input ─────────────────────────────────────────────────────────────────
    def _build_input(self):
        f = tk.Frame(self.root, bg=self.CLR["surface"], pady=10)
        f.pack(fill="x", padx=14, pady=(10, 0))

        tk.Label(f, text="Phone Number  (include country code  e.g.  +91 98765 43210)",
                 font=(self.FONT, 10), fg=self.CLR["muted"],
                 bg=f["bg"]).pack(anchor="w", padx=14)

        row = tk.Frame(f, bg=f["bg"])
        row.pack(fill="x", padx=14, pady=(6, 4))

        self._entry_var = tk.StringVar()
        self._entry = tk.Entry(row, textvariable=self._entry_var,
                               font=(self.FONT, 16, "bold"),
                               bg=self.CLR["surface2"], fg=self.CLR["text"],
                               insertbackground=self.CLR["accent"],
                               relief="flat", bd=0,
                               highlightthickness=2,
                               highlightbackground=self.CLR["border"],
                               highlightcolor=self.CLR["accent"])
        self._entry.pack(side="left", fill="x", expand=True, ipady=9, ipadx=12)
        self._entry.bind("<Return>", lambda _: self._on_analyse())

        self._analyse_btn = self._mk_btn(
            row, "  🔍  Analyse  ", self._on_analyse,
            self.CLR["accent"], "#0D1117", bold=True, ml=10)
        self._mk_btn(row, " ✕ ", self._on_clear,
                     self.CLR["surface2"], self.CLR["muted"], ml=6)

        self._status_var = tk.StringVar(value="Enter a phone number and press Analyse.")
        self._status_lbl = tk.Label(f, textvariable=self._status_var,
                                    font=(self.FONT, 9),
                                    fg=self.CLR["muted"], bg=f["bg"], anchor="w")
        self._status_lbl.pack(fill="x", padx=14, pady=(2, 6))

    # ── Lookup Buttons ────────────────────────────────────────────────────────
    def _build_buttons(self):
        f = tk.Frame(self.root, bg=self.CLR["bg"])
        f.pack(fill="x", padx=14, pady=(10, 0))

        tk.Label(f, text="SELECT  LOOKUP  TYPE",
                 font=(self.FONT, 8, "bold"),
                 fg=self.CLR["muted"], bg=self.CLR["bg"]).pack(
                     anchor="w", pady=(0, 6))

        row = tk.Frame(f, bg=self.CLR["bg"])
        row.pack(fill="x")

        data = [
            ("📍", "Geolocation",    self.CLR["accent"]),
            ("🌍", "Country Details", self.CLR["accent2"]),
            ("📡", "Service Provider",self.CLR["accent3"]),
            ("👤", "Registered User", self.CLR["accent4"]),
        ]
        services = self._get_services()
        self._lookup_btns: list[tk.Button] = []
        for i, ((ico, ttl, col), svc) in enumerate(zip(data, services)):
            btn = tk.Button(row,
                            text=f"  {ico}  {ttl}  ",
                            font=(self.FONT, 11, "bold"),
                            bg=self.CLR["surface"], fg=col,
                            activebackground=col, activeforeground="#0D1117",
                            relief="flat", bd=0, cursor="hand2",
                            padx=12, pady=12, state="disabled",
                            command=lambda s=svc: self._on_lookup(s))
            btn.pack(side="left", expand=True, fill="x",
                     padx=(0, 8) if i < 3 else 0)
            btn.bind("<Enter>", lambda e, b=btn, c=col: b.config(
                bg=c, fg="#0D1117"))
            btn.bind("<Leave>", lambda e, b=btn, c=col: b.config(
                bg=self.CLR["surface"], fg=c))
            self._lookup_btns.append(btn)

    # ── Result Panel ──────────────────────────────────────────────────────────
    def _build_results(self, pane):
        fr = tk.Frame(pane, bg=self.CLR["bg"])
        pane.add(fr, minsize=580, stretch="always")

        hbar = tk.Frame(fr, bg=self.CLR["surface"], pady=8)
        hbar.pack(fill="x")
        self._result_title_var = tk.StringVar(value="Results will appear here")
        tk.Label(hbar, textvariable=self._result_title_var,
                 font=(self.FONT, 12, "bold"),
                 fg=self.CLR["text"], bg=hbar["bg"]).pack(side="left", padx=14)

        self._save_all_btn = self._mk_btn(
            hbar, " 📄 Save All ", self._on_save_all,
            self.CLR["surface2"], self.CLR["accent2"],
            side="right", state="disabled", mr=8)
        self._save_btn = self._mk_btn(
            hbar, "  💾 Save  ", self._on_save,
            self.CLR["accent2"], "#0D1117", bold=True,
            side="right", state="disabled")

        self._progress = ttk.Progressbar(fr, mode="indeterminate")
        style = ttk.Style()
        style.theme_use("default")
        style.configure("TProgressbar",
                        troughcolor=self.CLR["surface"],
                        background=self.CLR["accent"], thickness=3)

        tf = tk.Frame(fr, bg=self.CLR["border"])
        tf.pack(fill="both", expand=True, pady=(2, 0))

        sb = tk.Scrollbar(tf, bg=self.CLR["surface"],
                          troughcolor=self.CLR["surface2"],
                          relief="flat", bd=0, width=10)
        sb.pack(side="right", fill="y")

        self._result_text = tk.Text(
            tf, font=(self.FONT, 11),
            bg=self.CLR["bg"], fg=self.CLR["text"],
            insertbackground=self.CLR["accent"],
            relief="flat", bd=0, wrap="word",
            state="disabled", padx=20, pady=14,
            spacing1=2, spacing2=1,
            yscrollcommand=sb.set, highlightthickness=0,
            selectbackground=self.CLR["surface2"])
        self._result_text.pack(side="left", fill="both", expand=True)
        sb.config(command=self._result_text.yview)

        T = self._result_text
        T.tag_configure("heading",    foreground=self.CLR["accent"],
                        font=(self.FONT, 11, "bold"))
        T.tag_configure("subheading", foreground=self.CLR["accent3"],
                        font=(self.FONT, 10, "bold"))
        T.tag_configure("key",        foreground=self.CLR["muted"],
                        font=(self.FONT, 10))
        T.tag_configure("value",      foreground=self.CLR["text"],
                        font=(self.FONT, 10, "bold"))
        T.tag_configure("muted",      foreground=self.CLR["muted"])
        T.tag_configure("divider",    foreground=self.CLR["surface2"])
        T.tag_configure("warn",       foreground=self.CLR["warning"])
        T.tag_configure("good",       foreground=self.CLR["accent2"])
        T.tag_configure("url",        foreground=self.CLR["accent4"],
                        underline=True, font=(self.FONT, 10))
        T.tag_configure("note",       foreground=self.CLR["accent3"],
                        font=(self.FONT, 9, "italic"))
        T.tag_configure("source",     foreground=self.CLR["accent2"],
                        font=(self.FONT, 9))
        T.tag_configure("error",      foreground=self.CLR["danger"])

    # ── Activity Log ──────────────────────────────────────────────────────────
    def _build_log(self, pane):
        fr = tk.Frame(pane, bg=self.CLR["bg"])
        pane.add(fr, minsize=240, stretch="never")

        hbar = tk.Frame(fr, bg=self.CLR["surface"], pady=8)
        hbar.pack(fill="x")
        tk.Label(hbar, text="  🛰  Activity Log",
                 font=(self.FONT, 10, "bold"),
                 fg=self.CLR["accent"], bg=hbar["bg"]).pack(side="left")
        self._mk_btn(hbar, " Clear ", self._clear_log,
                     self.CLR["surface2"], self.CLR["muted"],
                     side="right", mr=4)

        tf = tk.Frame(fr, bg=self.CLR["border"])
        tf.pack(fill="both", expand=True, pady=(2, 0))
        sb = tk.Scrollbar(tf, bg=self.CLR["surface"],
                          troughcolor=self.CLR["log_bg"],
                          relief="flat", bd=0, width=8)
        sb.pack(side="right", fill="y")
        self._log_text = tk.Text(
            tf, font=(self.FONT, 9),
            bg=self.CLR["log_bg"], fg=self.CLR["muted"],
            relief="flat", bd=0, wrap="word",
            state="disabled", padx=10, pady=10,
            yscrollcommand=sb.set, highlightthickness=0)
        self._log_text.pack(side="left", fill="both", expand=True)
        sb.config(command=self._log_text.yview)

        L = self._log_text
        L.tag_configure("ts",    foreground="#3D4450")
        L.tag_configure("info",  foreground=self.CLR["muted"])
        L.tag_configure("start", foreground=self.CLR["accent"],
                        font=(self.FONT, 9, "bold"))
        L.tag_configure("api",   foreground=self.CLR["accent4"])
        L.tag_configure("ok",    foreground=self.CLR["accent2"])
        L.tag_configure("done",  foreground=self.CLR["accent2"],
                        font=(self.FONT, 9, "bold"))
        L.tag_configure("err",   foreground=self.CLR["danger"])
        L.tag_configure("warn",  foreground=self.CLR["warning"])

    # ── Footer ────────────────────────────────────────────────────────────────
    def _build_footer(self):
        f = tk.Frame(self.root, bg=self.CLR["surface"], pady=6)
        f.pack(fill="x", side="bottom")
        tk.Label(f,
                 text="Phone Number Intelligence v2.0  ·  Internet Edition  ·  "
                      "Sources: phonenumbers · restcountries.com · DuckDuckGo "
                      "· Wikipedia · World Bank  ·  Not for illegal use.",
                 font=(self.FONT, 8), fg=self.CLR["muted"],
                 bg=f["bg"]).pack()

    # ── Event Handlers ────────────────────────────────────────────────────────
    def _on_analyse(self):
        raw = self._entry_var.get().strip()
        if not raw:
            self._status("⚠  Please enter a phone number.", self.CLR["warning"])
            return

        phone = PhoneNumber(raw)
        if not phone.is_valid:
            self._status(f"✗  {phone.error}", self.CLR["danger"])
            self._write(
                "⚠  Invalid Phone Number\n\n"
                f"  Input  : {raw}\n"
                f"  Error  : {phone.error}\n\n"
                "  Tips:\n"
                "    • Always start with + and the country code\n"
                "    • Examples:\n"
                "        +1 202 555 0173\n"
                "        +44 7911 123456\n"
                "        +91 98765 43210", clear=True)
            for b in self._lookup_btns: b.configure(state="disabled")
            return

        self._phone = phone
        self._last_results.clear()
        self._status(f"✓  Valid — {phone.international_format}", self.CLR["accent2"])
        for b in self._lookup_btns: b.configure(state="normal")
        self._save_btn.configure(state="disabled")
        self._save_all_btn.configure(state="disabled")

        self.log.push(
            f"Number validated: {phone.international_format} "
            f"| type={phone.number_type} | iso={phone.iso2}", "info")

        self._write(
            f"✅  Phone Number Validated\n\n"
            f"  Input              :  {phone.raw}\n"
            f"  International      :  {phone.international_format}\n"
            f"  E.164              :  {phone.e164}\n"
            f"  National Format    :  {phone.national_format}\n"
            f"  Country Code       :  +{phone.country_code}\n"
            f"  ISO-2              :  {phone.iso2}\n"
            f"  Flag               :  {phone.flag_emoji}\n"
            f"  Offline Location   :  {phone.offline_geo or 'Unknown'}\n"
            f"  Number Type        :  {phone.number_type}\n"
            f"  Timezone(s)        :  {', '.join(phone.timezones) or 'Unknown'}\n"
            f"  Offline Carrier    :  {phone.offline_carrier or 'Unknown'}\n\n"
            f"  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"  Click a lookup button above for live internet data ↑\n",
            clear=True,
            title=f"  {phone.flag_emoji}  {phone.international_format}")

    def _on_lookup(self, service: LookupService):
        if not self._phone or self._busy:
            return
        self._start_lookup(lambda: service.run(self._phone),
                           f"{service.icon()}  {service.title()}")

    def _start_lookup(self, fn, title_hint: str):
        self._busy = True
        for b in self._lookup_btns: b.configure(state="disabled")
        self._analyse_btn.configure(state="disabled")
        self._progress.pack(fill="x", padx=14, pady=3)
        self._progress.start(12)

        def worker():
            try:
                result = fn()
                self.root.after(0, lambda r=result: self._finish_lookup(r))
            except Exception as exc:
                self.log.push(f"Fatal error: {exc}", "err")
                self.root.after(0, self._unlock)

        threading.Thread(target=worker, daemon=True).start()

    def _finish_lookup(self, result: LookupResult):
        self._last_results = [result]
        self._display_result(result)
        self._result_title_var.set(f"  {result.icon}  {result.title}")
        self._status(f"✓  {result.title} complete.", self.CLR["accent2"])
        self._save_btn.configure(state="normal")
        self._save_all_btn.configure(state="normal")
        self._unlock()

    def _unlock(self):
        self._busy = False
        self._progress.stop()
        self._progress.pack_forget()
        for b in self._lookup_btns: b.configure(state="normal")
        self._analyse_btn.configure(state="normal")

    def _on_save(self):
        if not self._phone or not self._last_results:
            return
        self._save_file(self._last_results)

    def _on_save_all(self):
        if not self._phone or self._busy:
            return
        self._status("Fetching all lookups for full report …", self.CLR["accent3"])

        def all_lookups():
            results = []
            for svc in self._get_services():
                try:
                    results.append(svc.run(self._phone))
                except Exception as exc:
                    self.log.push(f"Error in {svc.title()}: {exc}", "err")
            return results

        self._start_lookup(all_lookups, "Full Report")

        # Override the finish to also save
        orig_finish = self._finish_lookup
        def finish_and_save(results):
            self._last_results = results if isinstance(results, list) else [results]
            self._unlock()
            self._save_btn.configure(state="normal")
            self._save_all_btn.configure(state="normal")
            self._status("All lookups done — choose a save location.", self.CLR["accent2"])
            self._save_file(self._last_results)
        self._finish_lookup = finish_and_save

        def restore_finish():
            import time; time.sleep(0.1)
            self._finish_lookup = orig_finish
        threading.Thread(target=restore_finish, daemon=True).start()

    def _save_file(self, results):
        default = (f"phone_intel_{self._phone.national_number}"
                   f"_{datetime.now():%Y%m%d_%H%M%S}.txt")
        path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text Files", "*.txt"), ("All Files", "*.*")],
            initialfile=default,
            title="Save Phone Intelligence Report")
        if not path:
            return
        text = ResultExporter.build_text(self._phone, results)
        ResultExporter.save(text, path)
        self.log.push(f"Report saved → {path}", "ok")
        messagebox.showinfo("Saved", f"Report saved:\n{path}")

    def _on_clear(self):
        self._entry_var.set("")
        self._phone = None
        self._last_results.clear()
        for b in self._lookup_btns: b.configure(state="disabled")
        self._save_btn.configure(state="disabled")
        self._save_all_btn.configure(state="disabled")
        self._result_title_var.set("Results will appear here")
        self._write(WELCOME, clear=True)
        self._status("Enter a number and press Analyse.", self.CLR["muted"])

    def _open_settings(self):
        SettingsDialog(self.root, self.config)

    def _clear_log(self):
        self._log_text.configure(state="normal")
        self._log_text.delete("1.0", "end")
        self._log_text.configure(state="disabled")

    # ── Display Helpers ───────────────────────────────────────────────────────
    def _status(self, msg: str, colour: str = None):
        self._status_var.set(msg)
        self._status_lbl.configure(fg=colour or self.CLR["muted"])

    def _write(self, text: str, clear: bool = False, title: str = None):
        t = self._result_text
        t.configure(state="normal")
        if clear:
            t.delete("1.0", "end")
        if title:
            self._result_title_var.set(title)
        t.insert("end", text)
        t.configure(state="disabled")

    def _display_result(self, result: LookupResult):
        t = self._result_text
        t.configure(state="normal")
        t.delete("1.0", "end")

        t.insert("end", f"\n  {result.icon}  {result.title}\n", "heading")
        t.insert("end", "  " + "━" * 58 + "\n\n", "divider")

        for key, val, tag in result.fields:
            if key == "__SEP__":
                t.insert("end", f"\n  ◆  {val}\n", "subheading")
                t.insert("end", "  " + "·" * 45 + "\n", "divider")
                continue
            if tag == "divider" or key.startswith("─"):
                t.insert("end", "\n", "divider")
                continue
            if tag == "heading":
                t.insert("end", f"\n  ◆  {key}\n", "subheading")
                continue
            t.insert("end", f"  {key:<28}", "key")
            t.insert("end", f"  {val}\n", tag)

        if result.sources:
            t.insert("end", "\n  " + "━" * 58 + "\n", "divider")
            t.insert("end", f"  📡 Sources:  {', '.join(result.sources)}\n", "source")
        if result.errors:
            for err in result.errors:
                t.insert("end", f"  ⚠  {err}\n", "error")

        t.insert("end", "\n  💾  Use Save / Save All above to export this report.\n",
                 "note")
        t.configure(state="disabled")
        t.see("1.0")

    def _poll_log(self):
        items = self.log.drain()
        if items:
            L = self._log_text
            L.configure(state="normal")
            for item in items:
                L.insert("end", f"[{item['ts']}] ", "ts")
                L.insert("end", item["msg"] + "\n", item["level"])
            L.configure(state="disabled")
            L.see("end")
        self.root.after(150, self._poll_log)

    def _mk_btn(self, parent, text, command, bg, fg,
                bold=False, ml=0, mr=0, side="left",
                state="normal") -> tk.Button:
        b = tk.Button(parent, text=text, command=command,
                      font=(self.FONT, 10, "bold" if bold else "normal"),
                      bg=bg, fg=fg, activebackground=fg,
                      activeforeground=bg, relief="flat", bd=0,
                      cursor="hand2", padx=12, pady=6, state=state)
        b.pack(side=side, padx=(ml, mr) if (ml or mr) else 4, pady=6)
        return b

    def run(self):
        self._write(WELCOME, clear=True)
        self.root.mainloop()


# ══════════════════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    app = PhoneIntelApp()
    app.run()
