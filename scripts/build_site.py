"""
Build index.html from the latest program JSON. v6.

v6 adds: SMHI weather forecast for Visby is fetched server-side and
embedded into the HTML. Avoids CORS issues with direct browser fetches.
"""

import json
import re
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

RAW_JSON_PATH = Path("data/program.json")
TEMPLATE_PATH = Path("template/template.html")
LEAFLET_CSS_PATH = Path("template/leaflet.css")
LEAFLET_JS_PATH = Path("template/leaflet.js")
OUTPUT_PATH = Path("index.html")


def fmt_time(t):
    if not t:
        return ''
    s = str(t)
    m = re.search(r'(\d{1,2}):(\d{2})', s)
    if m:
        return f"{int(m.group(1)):02d}:{m.group(2)}"
    return s


def parse_date(value):
    if not value:
        return ''
    if isinstance(value, str):
        m = re.match(r'(\d{4}-\d{2}-\d{2})', value)
        if m:
            return m.group(1)
    return str(value)[:10]


def extract_times(raw):
    times = raw.get('Times')
    sessions = []
    if isinstance(times, list):
        for t in times:
            if not isinstance(t, dict):
                continue
            d = t.get('Date') or t.get('date') or ''
            s = t.get('StartTime') or t.get('Start') or ''
            e = t.get('EndTime') or t.get('End') or ''
            d_str = parse_date(d)
            s_str = fmt_time(s)
            e_str = fmt_time(e)
            if d_str:
                sessions.append({'dag': d_str, 'start': s_str, 'slut': e_str})
    return sessions


def extract_location(raw):
    loc = raw.get('Location')
    if isinstance(loc, dict):
        name = loc.get('Name') or ''
        desc = loc.get('Description') or ''
        lat_raw = loc.get('Latitude')
        lon_raw = loc.get('Longitude')
        try:
            lat = float(lat_raw) if lat_raw not in (None, '', 0, '0') else None
        except (TypeError, ValueError):
            lat = None
        try:
            lon = float(lon_raw) if lon_raw not in (None, '', 0, '0') else None
        except (TypeError, ValueError):
            lon = None
        return name, lat, lon, desc
    if isinstance(loc, str):
        return loc, None, None, ''
    return '', None, None, ''


def extract_accessibility(raw):
    a = raw.get('Accessibility')
    if not isinstance(a, dict):
        return ''
    labels = []
    if a.get('WheelchairVenue'):
        labels.append('Entré och lokal tillgänglig för rullstol')
    if a.get('WheelchairToilet'):
        labels.append('Toalett tillgänglig för rullstol')
    if a.get('Teleloop'):
        labels.append('Teleslinga')
    if a.get('Text'):
        labels.append('Evenemanget textas')
    if a.get('SignLanguage'):
        labels.append('Teckenspråkstolkning')
    if a.get('VisualInterpretation'):
        labels.append('Syntolkning')
    return ', '.join(labels)


def extract_environmental(raw):
    """Pull mat (food served) and eko (eco-certified) from Environmental.
    Also build a list of sustainability labels for the detail panel."""
    env = raw.get('Environmental')
    mat = None
    eko = None
    eko_labels = []
    if isinstance(env, dict):
        # Food: true means refreshments are served
        if env.get('Food') is True:
            mat = 'Ja'
        elif env.get('NoFood') is True:
            mat = 'Nej'
        # Certified marks ecology/diploma
        if env.get('Certified') is True:
            eko = 'Ja'
        # Build descriptive sustainability list for the detail panel
        if env.get('FoodEcological'):
            eko_labels.append('Ekologisk mat')
        if env.get('FoodLocallyProduced'):
            eko_labels.append('Närproducerad mat')
        if env.get('FoodEthical'):
            eko_labels.append('Etisk/Fairtrade-mat')
        if env.get('Water'):
            eko_labels.append('Kranvatten serveras')
        if env.get('Stationary'):
            eko_labels.append('Miljövänligt kontorsmaterial')
        if env.get('Print'):
            eko_labels.append('Miljövänligt tryck')
        if env.get('Flyer'):
            eko_labels.append('Reklamblad endast vid förfrågan')
        if env.get('Battery'):
            eko_labels.append('Återvunna batterier')
        if env.get('Plastic'):
            eko_labels.append('Plastsparande')
        if env.get('Recycling'):
            eko_labels.append('Återvinning')
        if env.get('Disposable'):
            eko_labels.append('Återanvändbart porslin')
        if env.get('SourceSorting'):
            eko_labels.append('Källsortering')
        if env.get('ServiceQuestion'):
            eko_labels.append('Miljöfrågat tjänsteleverantörer')
        if env.get('ServiceElectricity'):
            eko_labels.append('Grön el')
        if env.get('ServiceTravel'):
            eko_labels.append('Hållbart resande')
        if env.get('ServiceCooking'):
            eko_labels.append('Hållbar matlagning')
    return mat, eko, eko_labels


def extract_persons(raw):
    p = raw.get('Persons')
    if not isinstance(p, list):
        return []
    result = []
    for item in p:
        if isinstance(item, dict):
            n = (item.get('Name') or
                 (item.get('FirstName', '') + ' ' + item.get('LastName', '')).strip())
            t = item.get('Title') or item.get('Role') or ''
            o = item.get('Organization') or item.get('Org') or item.get('Company') or ''
            if n.strip() or t or o:
                result.append({'n': str(n).strip(), 't': str(t), 'o': str(o)})
    return result


def extract_organizers(raw):
    o = raw.get('Organizers')
    if not o:
        return []
    if isinstance(o, list):
        out = []
        for x in o:
            if isinstance(x, dict):
                name = x.get('Name')
                if name:
                    out.append(str(name).strip())
            elif x:
                out.append(str(x).strip())
        return out
    if isinstance(o, str):
        return [s.strip() for s in re.split(r'[;|]', o) if s.strip()]
    return []


def clean_url(u):
    if not u:
        return ''
    s = str(u).strip()
    s = s.strip('_')
    return s


def is_yes_string(v):
    """Return 'Ja' if value is truthy boolean/non-zero, else 'Nej'."""
    if v is None:
        return None
    if isinstance(v, bool):
        return 'Ja' if v else 'Nej'
    return 'Ja' if v else 'Nej'


def normalize_event(raw):
    out = {}
    out['id'] = str(raw.get('EventId') or '')
    out['rubrik'] = str(raw.get('Title') or '').strip()

    sessions = extract_times(raw)
    if sessions:
        out['dag'] = sessions[0]['dag']
        out['start'] = sessions[0]['start']
        out['slut'] = sessions[0]['slut']
        if len(sessions) > 1:
            out['sessions'] = sessions
    else:
        out['dag'] = ''
        out['start'] = ''
        out['slut'] = ''

    out['kat'] = str(raw.get('Category') or '')
    out['typ'] = str(raw.get('EventType') or '')
    out['typorg'] = str(raw.get('OrganizationType') or '')
    out['amne1'] = str(raw.get('Topic') or '')
    out['amne2'] = str(raw.get('Topic2') or '')

    plats_name, lat, lon, plats_desc = extract_location(raw)
    out['plats'] = plats_name
    out['lat'] = lat
    out['lon'] = lon
    out['platsbeskr'] = plats_desc

    lang = raw.get('Languages')
    if isinstance(lang, list):
        out['sprak'] = ', '.join(str(x) for x in lang if x)
    else:
        out['sprak'] = str(lang or '')

    out['tillg'] = extract_accessibility(raw)
    out['besk'] = str(raw.get('Description') or '')
    out['info'] = str(raw.get('SocialIssue') or '')
    out['arr'] = extract_organizers(raw)
    out['web'] = clean_url(raw.get('Url1') or raw.get('Url2') or raw.get('Url3'))
    out['fb'] = clean_url(raw.get('FacebookUrl'))
    out['x'] = clean_url(raw.get('XUrl'))
    out['li'] = clean_url(raw.get('LinkedInUrl'))

    # Live: digital stream or meeting
    digital_stream = raw.get('DigitalStream')
    digital_meeting = raw.get('DigitalMeeting')
    if digital_stream or digital_meeting:
        out['live'] = 'Ja'
    else:
        out['live'] = 'Nej'

    # Food and eco from Environmental object
    mat, eko, eko_labels = extract_environmental(raw)
    out['mat'] = mat
    out['eko'] = eko
    if eko_labels:
        out['ekobeskr'] = ', '.join(eko_labels)

    out['med'] = extract_persons(raw)
    out['kp1n'] = str(raw.get('ContactPerson1Name') or '')
    out['kp1e'] = str(raw.get('ContactPerson1Email') or '')
    return out



# SMHI Open Data forecast endpoint.
# Migrated from pmp3g/version/2 (deprecated 2026-03-31, returns 404)
# to snow1g/version/1.
SMHI_URL = (
    "https://opendata-download-metfcst.smhi.se/api/category/snow1g/version/1/"
    "geotype/point/lon/18.2948/lat/57.6348/data.json"
)
ALMEDAL_DAYS = [
    '2026-06-22', '2026-06-23', '2026-06-24', '2026-06-25', '2026-06-26',
]

# Sentinel value used by SNOW1gv1 for missing measurements.
SMHI_MISSING = 9999


def smhi_symbol_to_icon(wsymb2):
    """Map SMHI symbol code (1-27) to a short Unicode symbol.
    Symbol codes are unchanged between pmp3g and snow1g."""
    if wsymb2 is None:
        return ''
    if wsymb2 == 1:
        return '\u2600'  # ☀
    if wsymb2 in (2, 3):
        return '\u26c5'  # ⛅
    if wsymb2 in (4, 5, 6):
        return '\u2601'  # ☁
    if wsymb2 == 7:
        return '\U0001f32b'  # 🌫
    if 8 <= wsymb2 <= 10:
        return '\U0001f326'  # 🌦
    if wsymb2 == 11:
        return '\u26c8'  # ⛈
    if 12 <= wsymb2 <= 14:
        return '\U0001f327'  # 🌧
    if 15 <= wsymb2 <= 17:
        return '\u2744'  # ❄
    if 18 <= wsymb2 <= 20:
        return '\U0001f326'  # 🌦
    if 21 <= wsymb2 <= 22:
        return '\u26c8'  # ⛈
    if 23 <= wsymb2 <= 27:
        return '\u2744'  # ❄
    return ''


def _smhi_value(entry_data, key):
    """Read a parameter from a SNOW1gv1 entry's data object.
    Returns None if missing or if value equals the 9999 sentinel.
    Defensive: works whether entry_data[key] is a number or a list."""
    if not isinstance(entry_data, dict):
        return None
    val = entry_data.get(key)
    if val is None:
        return None
    if isinstance(val, list):
        if not val:
            return None
        val = val[0]
    try:
        num = float(val)
    except (TypeError, ValueError):
        return None
    if num == SMHI_MISSING:
        return None
    return num


def fetch_smhi_weather():
    """Fetch SMHI forecast and extract:
    - byDay: noon-UTC entry per Almedalsveckan day (when available)
    - now: closest entry to current time (always available)
    Returns {} on any error (weather is enhancement, not critical)."""
    try:
        req = urllib.request.Request(SMHI_URL, headers={
            'User-Agent': 'Almedalskartan/1.0 (build-time fetch; +https://almedalskartan.se)',
        })
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode('utf-8'))
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, TimeoutError) as e:
        print(f"WARNING: SMHI weather fetch failed: {e}")
        return {}

    time_series = data.get('timeSeries', [])
    print(f"SMHI: {len(time_series)} time entries")

    # Diagnostic: log the structure of the first entry so we can verify
    # field names against SMHI's actual response. Remove once stable.
    if time_series:
        first = time_series[0]
        print(f"SMHI DEBUG: first entry top-level keys: {sorted(first.keys())}")
        if isinstance(first.get('data'), dict):
            print(f"SMHI DEBUG: first entry data keys: {sorted(first['data'].keys())}")
        else:
            print(f"SMHI DEBUG: first entry has no 'data' object, raw entry: {first}")
        # Also show top-level keys of the full response on first call
        print(f"SMHI DEBUG: response top-level keys: {sorted(data.keys())}")

    by_day = {}
    now_entry = None
    best_delta = None
    now_utc = datetime.now(timezone.utc)

    for ts in time_series:
        # SNOW1gv1 uses "time"; fall back to "validTime" defensively.
        valid_time = ts.get('time') or ts.get('validTime') or ''
        if len(valid_time) < 13:
            continue
        date_str = valid_time[:10]
        try:
            hour = int(valid_time[11:13])
        except ValueError:
            continue

        # SNOW1gv1: flat data object with human-readable parameter names.
        entry_data = ts.get('data') or {}
        t_val = _smhi_value(entry_data, 'air_temperature')
        wsymb_val = _smhi_value(entry_data, 'symbol_code')

        if t_val is None:
            continue

        # Noon UTC entry per Almedalsveckan day (12:00 UTC = 14:00 CEST)
        if hour == 12 and date_str in ALMEDAL_DAYS:
            by_day[date_str] = {
                'temp': round(t_val),
                'icon': smhi_symbol_to_icon(int(wsymb_val)) if wsymb_val is not None else '',
            }

        # Closest-to-now entry for the Visby header widget
        try:
            entry_time = datetime.fromisoformat(valid_time.replace('Z', '+00:00'))
            delta = abs((entry_time - now_utc).total_seconds())
            if best_delta is None or delta < best_delta:
                best_delta = delta
                now_entry = {
                    'temp': round(t_val),
                    'icon': smhi_symbol_to_icon(int(wsymb_val)) if wsymb_val is not None else '',
                }
        except ValueError:
            continue

    print(f"SMHI: byDay={by_day}, now={now_entry}")
    return {'byDay': by_day, 'now': now_entry}
    return {'byDay': by_day, 'now': now_entry}


def main():
    raw = json.loads(RAW_JSON_PATH.read_text(encoding='utf-8'))
    if isinstance(raw, list):
        events_raw = raw
    elif isinstance(raw, dict):
        for key in ['events', 'data', 'items', 'results', 'programItems', 'Events']:
            if key in raw and isinstance(raw[key], list):
                events_raw = raw[key]
                break
        else:
            sys.exit(3)
    else:
        sys.exit(3)

    print(f"Raw events: {len(events_raw)}")
    if not events_raw:
        sys.exit(4)

    # Stats
    mat_yes = 0
    mat_no = 0
    mat_none = 0
    eko_yes = 0
    eko_none = 0
    live_yes = 0
    live_no = 0

    events = []
    for raw_event in events_raw:
        e = normalize_event(raw_event)
        if not e['rubrik'] or not e['dag']:
            continue
        events.append(e)

        if e.get('mat') == 'Ja':
            mat_yes += 1
        elif e.get('mat') == 'Nej':
            mat_no += 1
        else:
            mat_none += 1
        if e.get('eko') == 'Ja':
            eko_yes += 1
        else:
            eko_none += 1
        if e.get('live') == 'Ja':
            live_yes += 1
        else:
            live_no += 1

    print(f"Normalized events: {len(events)}")
    print(f"Mat: Ja={mat_yes}, Nej={mat_no}, ej angivet={mat_none}")
    print(f"Miljödiplom (eko): Ja={eko_yes}, ej angivet={eko_none}")
    print(f"Webbsänt (live): Ja={live_yes}, Nej={live_no}")

    if not events:
        sys.exit(5)

    topic_counts = {}
    for e in events:
        if e.get('amne1'):
            topic_counts[e['amne1']] = topic_counts.get(e['amne1'], 0) + 1
        if e.get('amne2'):
            topic_counts[e['amne2']] = topic_counts.get(e['amne2'], 0) + 1

    topics = sorted(topic_counts.items(), key=lambda x: -x[1])

    data_obj = {'events': events, 'topics': topics}

    template = TEMPLATE_PATH.read_text(encoding='utf-8')
    leaflet_css = LEAFLET_CSS_PATH.read_text(encoding='utf-8')
    leaflet_js = LEAFLET_JS_PATH.read_text(encoding='utf-8')

    data_json = json.dumps(data_obj, ensure_ascii=False, separators=(',', ':'))

    def safe_for_script_block(s):
        s = s.replace('\u2028', '\\u2028').replace('\u2029', '\\u2029')
        s = re.sub(r'</(\s*script)', r'<\\/\1', s, flags=re.IGNORECASE)
        return s

    data_safe = safe_for_script_block(data_json)
    js_safe = safe_for_script_block(leaflet_js)

    # Fetch SMHI weather forecast for Visby
    weather_data = fetch_smhi_weather()
    weather_json = json.dumps(weather_data, ensure_ascii=False, separators=(',', ':'))

    out = (template
           .replace('__LEAFLET_CSS__', leaflet_css)
           .replace('__LEAFLET_JS__', js_safe)
           .replace('__DATA__', data_safe)
           .replace('__WEATHER_DATA__', weather_json))

    OUTPUT_PATH.write_text(out, encoding='utf-8')
    size_mb = len(out.encode('utf-8')) / 1024 / 1024
    print(f"Wrote {OUTPUT_PATH} ({size_mb:.2f} MB)")


if __name__ == '__main__':
    main()
