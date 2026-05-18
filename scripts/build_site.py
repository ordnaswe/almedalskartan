"""
Build index.html from the latest program JSON. v4.

Handles real portal schema:
- Times is a list of {Date, StartTime, EndTime} sessions
- Location is a nested object with Name, Latitude, Longitude, Description
- Accessibility is a nested object with boolean flags
- Persons is the speakers list
- Organizers is a list of strings or objects
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


def extract_times(raw):
    """Extract list of session dicts from Times field.
    Each session yields date, start, slut."""
    times = raw.get('Times')
    sessions = []
    if isinstance(times, list):
        for t in times:
            if not isinstance(t, dict):
                continue
            d = (t.get('Date') or t.get('date') or t.get('Day') or
                 t.get('StartDateTime') or t.get('Start') or '')
            s = (t.get('StartTime') or t.get('Start') or t.get('From') or t.get('startTime') or '')
            e = (t.get('EndTime') or t.get('End') or t.get('To') or t.get('endTime') or '')
            # If Date is a full datetime, take first 10 chars
            d_str = parse_date(d)
            # If StartTime is a full datetime, extract HH:MM
            s_str = fmt_time(s)
            e_str = fmt_time(e)
            # If StartTime is missing but Start is a full datetime, try extracting time from it
            if not s_str and isinstance(d, str) and 'T' in d:
                m = re.search(r'T(\d{1,2}):(\d{2})', d)
                if m:
                    s_str = f"{int(m.group(1)):02d}:{m.group(2)}"
            if d_str:
                sessions.append({'dag': d_str, 'start': s_str, 'slut': e_str})
    return sessions


def extract_location(raw):
    """Extract name, lat, lon, description from Location field."""
    loc = raw.get('Location')
    if isinstance(loc, dict):
        name = loc.get('Name') or loc.get('name') or ''
        desc = loc.get('Description') or loc.get('description') or ''
        lat_raw = loc.get('Latitude') or loc.get('latitude') or loc.get('Lat')
        lon_raw = loc.get('Longitude') or loc.get('longitude') or loc.get('Lon') or loc.get('Lng')
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
    """Build a comma-separated Swedish string from Accessibility booleans."""
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


def extract_persons(raw):
    """Build participant list from Persons field."""
    p = raw.get('Persons')
    if not isinstance(p, list):
        return []
    result = []
    for item in p:
        if isinstance(item, dict):
            n = (item.get('Name') or item.get('name') or
                 (item.get('FirstName', '') + ' ' + item.get('LastName', '')).strip())
            t = item.get('Title') or item.get('title') or item.get('Role') or ''
            o = (item.get('Organization') or item.get('Org') or
                 item.get('organization') or item.get('Company') or '')
            if n.strip() or t or o:
                result.append({'n': str(n).strip(), 't': str(t), 'o': str(o)})
    return result


def extract_organizers(raw):
    """Build organizer list."""
    o = raw.get('Organizers')
    if not o:
        return []
    if isinstance(o, list):
        out = []
        for x in o:
            if isinstance(x, dict):
                name = x.get('Name') or x.get('name')
                if name:
                    out.append(str(name).strip())
            elif x:
                out.append(str(x).strip())
        return out
    if isinstance(o, str):
        return [s.strip() for s in re.split(r'[;|]', o) if s.strip()]
    return []


def clean_url(u):
    """Strip leading/trailing markdown-style underscores from URL."""
    if not u:
        return ''
    s = str(u).strip()
    s = s.strip('_')
    return s


def normalize_event(raw):
    out = {}
    out['id'] = str(raw.get('EventId') or raw.get('Id') or '')
    out['rubrik'] = str(raw.get('Title') or '').strip()

    # Times: a list of sessions. Use the first one as the primary; later
    # we may want to emit multiple events per record.
    sessions = extract_times(raw)
    if sessions:
        out['dag'] = sessions[0]['dag']
        out['start'] = sessions[0]['start']
        out['slut'] = sessions[0]['slut']
        # Pass additional sessions for the template (if any)
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

    # Location, lat, lon, description
    plats_name, lat, lon, plats_desc = extract_location(raw)
    out['plats'] = plats_name
    out['lat'] = lat
    out['lon'] = lon
    out['platsbeskr'] = plats_desc

    # Languages may be string or list
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

    # Webcast/livestream
    digital_stream = raw.get('DigitalStream')
    if digital_stream is None:
        digital_stream = raw.get('DigitalMeeting')
    out['live'] = parse_yes_no(digital_stream)

    # Food: not directly in this schema, leave empty
    out['mat'] = parse_yes_no(raw.get('Food') or raw.get('HasFood'))

    # Eco: Environmental field
    out['eko'] = parse_yes_no(raw.get('Environmental'))

    out['med'] = extract_persons(raw)
    out['kp1n'] = str(raw.get('ContactPerson1Name') or '')
    out['kp1e'] = str(raw.get('ContactPerson1Email') or '')
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
            print("Cannot find list of events. Keys:")
            for k in raw.keys():
                print(f"  {k}")
            sys.exit(3)
    else:
        sys.exit(3)

    print(f"Raw events: {len(events_raw)}")

    # Show Times structure for first event with a Times field
    for i, e in enumerate(events_raw[:20]):
        if isinstance(e, dict) and e.get('Times'):
            print(f"Sample Times from event #{i}:")
            print(json.dumps(e['Times'], ensure_ascii=False, indent=2)[:800])
            print(f"Sample Location:")
            print(json.dumps(e.get('Location'), ensure_ascii=False, indent=2)[:400])
            break

    events = []
    skipped = {'no_rubrik': 0, 'no_dag': 0, 'sample_events_no_dag': []}
    for raw_event in events_raw:
        e = normalize_event(raw_event)
        if not e['rubrik']:
            skipped['no_rubrik'] += 1
            continue
        if not e['dag']:
            skipped['no_dag'] += 1
            if len(skipped['sample_events_no_dag']) < 3:
                skipped['sample_events_no_dag'].append({
                    'EventId': raw_event.get('EventId'),
                    'Title': raw_event.get('Title'),
                    'Times': raw_event.get('Times'),
                })
            continue
        events.append(e)

    print(f"Skipped no_rubrik: {skipped['no_rubrik']}")
    print(f"Skipped no_dag: {skipped['no_dag']}")
    if skipped['sample_events_no_dag']:
        print("First 3 events skipped for no_dag:")
        print(json.dumps(skipped['sample_events_no_dag'], ensure_ascii=False, indent=2)[:1500])
    print(f"Normalized events: {len(events)}")

    if len(events) == 0:
        print("FATAL: All events filtered out.")
        sys.exit(5)

    # Show first normalized event for sanity check
    print("First NORMALIZED event:")
    print(json.dumps(events[0], ensure_ascii=False, indent=2)[:1500])

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
