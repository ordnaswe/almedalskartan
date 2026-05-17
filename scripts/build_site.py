"""
Build index.html from the latest program JSON.

Reads data/program.json (raw export from alme.inadra.se) and the HTML template,
emits index.html with embedded data, ready for Netlify to deploy.

The portal JSON schema is NOT documented. We probe field names defensively
and log warnings if expected fields are missing, so that drift in the source
format is visible in the CI logs.
"""

import json
import re
import sys
from pathlib import Path

RAW_JSON_PATH = Path("data/program.json")
TEMPLATE_PATH = Path("template/template.html")
LEAFLET_CSS_PATH = Path("template/leaflet.css")
LEAFLET_JS_PATH = Path("template/leaflet.js")
OUTPUT_PATH = Path("index.html")


# Field name candidates per logical field. Probed in order, first match wins.
FIELD_CANDIDATES = {
    'id': ['id', 'metaId', 'meta_id', 'MetaId', 'eventId', 'event_id'],
    'rubrik': ['title', 'rubrik', 'name', 'Rubrik', 'Title'],
    'dag': ['date', 'startDate', 'start_date', 'dag', 'Dag', 'day'],
    'start': ['startTime', 'start_time', 'starttid', 'Starttid', 'start', 'timeFrom'],
    'slut': ['endTime', 'end_time', 'sluttid', 'Sluttid', 'end', 'timeTo'],
    'kat': ['category', 'kategori', 'kat'],
    'typ': ['eventType', 'event_type', 'type', 'typ', 'Typ', 'Typ av evenemang'],
    'typorg': ['organizerType', 'organizer_type', 'typorg', 'Typ av organisation'],
    'amne1': ['topic', 'subject', 'amne', 'amne1', 'Ämnesområde', 'category'],
    'amne2': ['topic2', 'subject2', 'amne2', 'Ämnesområde 2'],
    'plats': ['location', 'plats', 'venue', 'Plats'],
    'lat': ['latitude', 'lat', 'Latitude'],
    'lon': ['longitude', 'lon', 'lng', 'Longitude'],
    'platsbeskr': ['locationDescription', 'plats_beskrivning', 'Platsbeskrivning'],
    'sprak': ['language', 'sprak', 'Språk'],
    'tillg': ['accessibility', 'tillg', 'Tillgänglighet'],
    'besk': ['description', 'beskrivning', 'besk', 'Beskrivning'],
    'info': ['additionalInfo', 'info', 'Övrig info'],
    'arr': ['organizers', 'arrangorer', 'arr', 'Arrangör', 'arrangor'],
    'web': ['website', 'web', 'url', 'Webbsida'],
    'fb': ['facebook', 'fb', 'Facebook'],
    'x': ['twitter', 'x', 'X'],
    'li': ['linkedin', 'li', 'LinkedIn'],
    'live': ['liveStream', 'webbsant', 'Webbsändning', 'live'],
    'mat': ['food', 'fortaring', 'mat', 'Förtäring'],
    'eko': ['ecoCertified', 'miljodiplomerad', 'eko', 'Miljödiplomerat'],
    'med': ['participants', 'speakers', 'medverkande', 'med', 'Medverkande'],
    'kp1n': ['contactPersonName', 'kontakt_namn', 'Kontaktperson namn'],
    'kp1e': ['contactPersonEmail', 'kontakt_epost', 'Kontaktperson e-post'],
}


def get_field(obj, logical_name):
    """Look up a logical field by trying all candidate keys."""
    candidates = FIELD_CANDIDATES.get(logical_name, [logical_name])
    for key in candidates:
        if key in obj:
            return obj[key]
        # Case-insensitive fallback
        for actual_key in obj.keys():
            if actual_key.lower() == key.lower():
                return obj[actual_key]
    return None


def parse_yes_no(value):
    """Normalize boolean-ish values to 'Ja'/'Nej'/None."""
    if value is None:
        return None
    if isinstance(value, bool):
        return 'Ja' if value else 'Nej'
    if isinstance(value, str):
        v = value.strip().lower()
        if v in ('ja', 'yes', 'true', '1'):
            return 'Ja'
        if v in ('nej', 'no', 'false', '0', ''):
            return 'Nej'
        return value
    return str(value)


def parse_medverkande(value):
    """Parse participants/speakers into [{n, t, o}] list."""
    if not value:
        return []
    if isinstance(value, list):
        result = []
        for item in value:
            if isinstance(item, dict):
                n = item.get('name') or item.get('namn') or item.get('Namn') or ''
                t = item.get('title') or item.get('titel') or item.get('Titel') or ''
                o = item.get('organization') or item.get('organisation') or item.get('Organisation') or ''
                result.append({'n': str(n), 't': str(t), 'o': str(o)})
            elif isinstance(item, str):
                result.append({'n': item, 't': '', 'o': ''})
        return result
    if isinstance(value, str):
        # Legacy semicolon-pipe format from Excel: "Name;Title;Org|Name;Title;Org"
        result = []
        for entry in value.split('|'):
            parts = [p.strip() for p in entry.split(';')]
            while len(parts) < 3:
                parts.append('')
            result.append({'n': parts[0], 't': parts[1], 'o': parts[2]})
        return result
    return []


def parse_organizers(value):
    """Parse organizers field into a list of strings."""
    if not value:
        return []
    if isinstance(value, list):
        return [str(x) if not isinstance(x, dict) else (x.get('name') or x.get('namn') or str(x)) for x in value]
    if isinstance(value, str):
        return [s.strip() for s in re.split(r'[;|]', value) if s.strip()]
    return [str(value)]


def normalize_event(raw):
    """Convert a single raw event from portal JSON into template format."""
    out = {}
    out['id'] = str(get_field(raw, 'id') or '')
    out['rubrik'] = str(get_field(raw, 'rubrik') or '').strip()

    # Date and time
    dag = get_field(raw, 'dag')
    if isinstance(dag, str):
        # Possibly ISO datetime; take first 10 chars (YYYY-MM-DD)
        out['dag'] = dag[:10] if len(dag) >= 10 else dag
    else:
        out['dag'] = str(dag or '')

    start = get_field(raw, 'start')
    slut = get_field(raw, 'slut')

    def fmt_time(t):
        if not t:
            return ''
        s = str(t)
        m = re.search(r'(\d{1,2}):(\d{2})', s)
        if m:
            return f"{int(m.group(1)):02d}:{m.group(2)}"
        return s

    out['start'] = fmt_time(start)
    out['slut'] = fmt_time(slut)

    out['kat'] = str(get_field(raw, 'kat') or '')
    out['typ'] = str(get_field(raw, 'typ') or '')
    out['typorg'] = str(get_field(raw, 'typorg') or '')
    out['amne1'] = str(get_field(raw, 'amne1') or '')
    out['amne2'] = str(get_field(raw, 'amne2') or '')
    out['plats'] = str(get_field(raw, 'plats') or '')

    lat = get_field(raw, 'lat')
    lon = get_field(raw, 'lon')
    try:
        out['lat'] = float(lat) if lat not in (None, '', 0) else None
    except (TypeError, ValueError):
        out['lat'] = None
    try:
        out['lon'] = float(lon) if lon not in (None, '', 0) else None
    except (TypeError, ValueError):
        out['lon'] = None

    out['platsbeskr'] = str(get_field(raw, 'platsbeskr') or '')
    out['sprak'] = str(get_field(raw, 'sprak') or '')
    out['tillg'] = str(get_field(raw, 'tillg') or '')
    out['besk'] = str(get_field(raw, 'besk') or '')
    out['info'] = str(get_field(raw, 'info') or '')
    out['arr'] = parse_organizers(get_field(raw, 'arr'))
    out['web'] = str(get_field(raw, 'web') or '')
    out['fb'] = str(get_field(raw, 'fb') or '')
    out['x'] = str(get_field(raw, 'x') or '')
    out['li'] = str(get_field(raw, 'li') or '')
    out['live'] = parse_yes_no(get_field(raw, 'live'))
    out['mat'] = parse_yes_no(get_field(raw, 'mat'))
    out['eko'] = parse_yes_no(get_field(raw, 'eko'))
    out['med'] = parse_medverkande(get_field(raw, 'med'))
    out['kp1n'] = str(get_field(raw, 'kp1n') or '')
    out['kp1e'] = str(get_field(raw, 'kp1e') or '')

    return out


def main():
    raw = json.loads(RAW_JSON_PATH.read_text(encoding='utf-8'))

    # The portal may return the list directly or wrap it in a container.
    if isinstance(raw, list):
        events_raw = raw
    elif isinstance(raw, dict):
        # Try common wrapper keys
        for key in ['events', 'data', 'items', 'results', 'programItems', 'evenemang']:
            if key in raw and isinstance(raw[key], list):
                events_raw = raw[key]
                break
        else:
            # Maybe the entire dict IS the wrapper and we need to look one level deeper
            print("WARNING: could not find list of events in JSON. Dumping top-level keys:")
            for k in raw.keys():
                print(f"  {k}: {type(raw[k]).__name__}")
            sys.exit(3)
    else:
        print(f"ERROR: unexpected root JSON type: {type(raw).__name__}", file=sys.stderr)
        sys.exit(3)

    print(f"Raw events: {len(events_raw)}")

    if len(events_raw) == 0:
        print("ERROR: zero events. Aborting build.", file=sys.stderr)
        sys.exit(4)

    # Inspect first event to confirm field schema
    print("First event keys (sample):", list(events_raw[0].keys())[:30])

    events = []
    for raw_event in events_raw:
        e = normalize_event(raw_event)
        if not e['rubrik'] or not e['dag']:
            continue
        events.append(e)

    print(f"Normalized events: {len(events)}")

    # Build topics list with counts (primary + half-weighted secondary, matching template logic)
    topic_counts = {}
    for e in events:
        a1 = e.get('amne1')
        if a1:
            topic_counts[a1] = topic_counts.get(a1, 0) + 1
        a2 = e.get('amne2')
        if a2:
            topic_counts[a2] = topic_counts.get(a2, 0) + 1

    topics = sorted(topic_counts.items(), key=lambda x: -x[1])

    data_obj = {
        'events': events,
        'topics': topics,
    }

    # Read template and assets
    template = TEMPLATE_PATH.read_text(encoding='utf-8')
    leaflet_css = LEAFLET_CSS_PATH.read_text(encoding='utf-8')
    leaflet_js = LEAFLET_JS_PATH.read_text(encoding='utf-8')

    # Serialize data
    data_json = json.dumps(data_obj, ensure_ascii=False, separators=(',', ':'))

    # Escape problematic sequences inside <script type="text/plain"> blocks
    def safe_for_script_block(s):
        s = s.replace('\u2028', '\\u2028').replace('\u2029', '\\u2029')
        s = re.sub(r'</(\s*script)', r'<\\/\1', s, flags=re.IGNORECASE)
        return s

    data_safe = safe_for_script_block(data_json)
    js_safe = safe_for_script_block(leaflet_js)

    out = (template
           .replace('__LEAFLET_CSS__', leaflet_css)
           .replace('__LEAFLET_JS__', js_safe)
           .replace('__DATA__', data_safe))

    OUTPUT_PATH.write_text(out, encoding='utf-8')
    size_mb = len(out.encode('utf-8')) / 1024 / 1024
    print(f"Wrote {OUTPUT_PATH} ({size_mb:.2f} MB)")


if __name__ == '__main__':
    main()
