"""
Build index.html from the latest program JSON. v3.

Portal field names are PascalCase. The first version's case-insensitive
fallback had a bug; this version uses a clean primary-keys table.
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


# Confirmed field names from the actual portal JSON (PascalCase).
# Each logical field has a primary key plus a list of fallbacks.
FIELD_MAP = {
    'id': ['EventId', 'Id', 'id'],
    'rubrik': ['Title', 'title', 'Heading', 'Rubrik'],
    'dag': ['Date', 'EventDate', 'StartDate', 'date', 'Dag'],
    'start': ['StartTime', 'TimeFrom', 'Start', 'starttid'],
    'slut': ['EndTime', 'TimeTo', 'End', 'sluttid'],
    'kat': ['Category', 'kategori'],
    'typ': ['EventType', 'Type'],
    'typorg': ['OrganizationType', 'OrganizerType'],
    'amne1': ['Topic', 'Subject', 'PrimaryTopic'],
    'amne2': ['Topic2', 'Subject2', 'SecondaryTopic'],
    'plats': ['Location', 'Venue', 'Plats', 'Address'],
    'lat': ['Latitude', 'Lat'],
    'lon': ['Longitude', 'Lon', 'Lng'],
    'platsbeskr': ['LocationDescription', 'Platsbeskrivning'],
    'sprak': ['Languages', 'Language', 'Sprak'],
    'tillg': ['Accessibility', 'Tillganglighet'],
    'besk': ['Description', 'EventDescription', 'Beskrivning'],
    'info': ['AdditionalInfo', 'Info', 'SocialIssue'],
    'arr': ['Organizers', 'Organizer', 'Arrangor', 'Arrangors'],
    'web': ['Url1', 'Website', 'Url'],
    'web2': ['Url2'],
    'web3': ['Url3'],
    'fb': ['FacebookUrl', 'Facebook'],
    'x': ['XUrl', 'TwitterUrl', 'Twitter'],
    'li': ['LinkedInUrl', 'LinkedIn'],
    'live': ['LiveStream', 'IsLiveStream', 'Webbsandning'],
    'mat': ['Food', 'HasFood', 'Fortaring'],
    'eko': ['EcoCertified', 'IsEcoCertified', 'Miljodiplomerad'],
    'med': ['Participants', 'Speakers', 'Medverkande'],
    # Contact persons are flat fields in the schema, not nested
    'kp1n': ['ContactPerson1Name'],
    'kp1t': ['ContactPerson1Title'],
    'kp1o': ['ContactPerson1Org'],
    'kp1p': ['ContactPerson1Phone'],
    'kp1e': ['ContactPerson1Email'],
    'kp2n': ['ContactPerson2Name'],
    'kp2t': ['ContactPerson2Title'],
    'kp2o': ['ContactPerson2Org'],
    'kp2p': ['ContactPerson2Phone'],
    'kp2e': ['ContactPerson2Email'],
    'showmail': ['ShowEmail'],
    'showphone': ['ShowPhone'],
    'status': ['Status'],
}


def get_field(obj, logical_name):
    candidates = FIELD_MAP.get(logical_name, [logical_name])
    for key in candidates:
        if key in obj:
            return obj[key]
    return None


def parse_yes_no(value):
    if value is None:
        return None
    if isinstance(value, bool):
        return 'Ja' if value else 'Nej'
    if isinstance(value, (int, float)):
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
    if not value:
        return []
    if isinstance(value, list):
        result = []
        for item in value:
            if isinstance(item, dict):
                n = (item.get('Name') or item.get('name') or item.get('namn') or
                     item.get('FullName') or '').strip()
                t = item.get('Title') or item.get('title') or item.get('titel') or item.get('Role') or ''
                o = (item.get('Organization') or item.get('organization') or
                     item.get('organisation') or item.get('Org') or item.get('Company') or '')
                if n or t or o:
                    result.append({'n': str(n), 't': str(t), 'o': str(o)})
            elif isinstance(item, str) and item.strip():
                result.append({'n': item.strip(), 't': '', 'o': ''})
        return result
    if isinstance(value, str):
        result = []
        for entry in value.split('|'):
            parts = [p.strip() for p in entry.split(';')]
            while len(parts) < 3:
                parts.append('')
            if parts[0]:
                result.append({'n': parts[0], 't': parts[1], 'o': parts[2]})
        return result
    return []


def parse_organizers(value):
    if not value:
        return []
    if isinstance(value, list):
        out = []
        for x in value:
            if isinstance(x, dict):
                name = x.get('Name') or x.get('name') or x.get('namn')
                if name:
                    out.append(str(name))
            elif x:
                out.append(str(x))
        return out
    if isinstance(value, str):
        return [s.strip() for s in re.split(r'[;|]', value) if s.strip()]
    if isinstance(value, dict):
        name = value.get('Name') or value.get('name') or value.get('namn')
        return [str(name)] if name else []
    return [str(value)] if value else []


def parse_date(value):
    """Accept various date formats, return YYYY-MM-DD."""
    if not value:
        return ''
    if isinstance(value, str):
        # ISO datetime: take first 10 chars
        m = re.match(r'(\d{4}-\d{2}-\d{2})', value)
        if m:
            return m.group(1)
        # DD/MM/YYYY or similar
        m = re.match(r'(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})', value)
        if m:
            return f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
        return value
    return str(value)


def fmt_time(t):
    if not t:
        return ''
    s = str(t)
    m = re.search(r'(\d{1,2}):(\d{2})', s)
    if m:
        return f"{int(m.group(1)):02d}:{m.group(2)}"
    return s


def normalize_event(raw):
    out = {}
    out['id'] = str(get_field(raw, 'id') or '')
    out['rubrik'] = str(get_field(raw, 'rubrik') or '').strip()
    out['dag'] = parse_date(get_field(raw, 'dag'))
    out['start'] = fmt_time(get_field(raw, 'start'))
    out['slut'] = fmt_time(get_field(raw, 'slut'))
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
    if isinstance(raw, list):
        events_raw = raw
    elif isinstance(raw, dict):
        for key in ['events', 'data', 'items', 'results', 'programItems', 'Events']:
            if key in raw and isinstance(raw[key], list):
                events_raw = raw[key]
                break
        else:
            print("WARNING: could not find list of events. Top-level keys:")
            for k in raw.keys():
                print(f"  {k}: {type(raw[k]).__name__}")
            sys.exit(3)
    else:
        sys.exit(3)

    print(f"Raw events: {len(events_raw)}")
    if len(events_raw) == 0:
        sys.exit(4)

    # Dump union of all keys across first 200 events so we see optional fields
    all_keys = set()
    for e in events_raw[:200]:
        if isinstance(e, dict):
            all_keys.update(e.keys())
    print(f"Union of keys across first 200 events ({len(all_keys)} fields):")
    for k in sorted(all_keys):
        print(f"  {k}")

    # Show fully resolved first event
    if len(events_raw) > 0:
        first_norm = normalize_event(events_raw[0])
        print("First event NORMALIZED:")
        print(json.dumps(first_norm, ensure_ascii=False, indent=2)[:2000])

    events = []
    skipped = {'no_rubrik': 0, 'no_dag': 0, 'no_status': 0}
    for raw_event in events_raw:
        e = normalize_event(raw_event)
        # Optionally filter by Status (e.g. exclude draft/canceled)
        if not e['rubrik']:
            skipped['no_rubrik'] += 1
            continue
        if not e['dag']:
            skipped['no_dag'] += 1
            continue
        events.append(e)

    print(f"Skipped: {skipped}")
    print(f"Normalized events: {len(events)}")

    if len(events) == 0:
        print("FATAL: All events filtered out.")
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

    out = (template
           .replace('__LEAFLET_CSS__', leaflet_css)
           .replace('__LEAFLET_JS__', js_safe)
           .replace('__DATA__', data_safe))

    OUTPUT_PATH.write_text(out, encoding='utf-8')
    size_mb = len(out.encode('utf-8')) / 1024 / 1024
    print(f"Wrote {OUTPUT_PATH} ({size_mb:.2f} MB)")


if __name__ == '__main__':
    main()
