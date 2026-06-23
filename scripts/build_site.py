"""
Build index.html from the latest program JSON.

v7: Weather is now fetched client-side directly from SMHI in the browser.
Removed all server-side SMHI fetch logic and the __WEATHER_DATA__ placeholder.
This avoids hourly Netlify rebuilds that were consuming build credits.
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
    # Cancelled events keep showing in the program but are flagged. The official
    # export uses Status 'Inställd' for these; only set the flag when cancelled so
    # the data stays small (the template treats a missing flag as not cancelled).
    if str(raw.get('Status') or '').strip().lower() == 'inställd':
        out['installt'] = True
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

    out = (template
           .replace('__LEAFLET_CSS__', leaflet_css)
           .replace('__LEAFLET_JS__', js_safe)
           .replace('__DATA__', data_safe))

    OUTPUT_PATH.write_text(out, encoding='utf-8')
    size_mb = len(out.encode('utf-8')) / 1024 / 1024
    print(f"Wrote {OUTPUT_PATH} ({size_mb:.2f} MB)")


if __name__ == '__main__':
    main()
