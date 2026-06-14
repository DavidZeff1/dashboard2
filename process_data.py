# -*- coding: utf-8 -*-
"""Parse the Gush Etzion welfare CSV exports + town geojson boundaries into data.js for the dashboard.
Every number in the output comes straight from the source files; the only computed values are
sums and ratios of those numbers, and they are flagged as computed in the dashboard."""
import csv, glob, json, math, os

BASE = os.path.dirname(os.path.abspath(__file__))

def load(fid):
    """Load rows; header keys are normalized by removing stray quote chars that the
    source files leave unescaped (e.g. למ"ס parses oddly), so lookups use quote-less names."""
    files = sorted(glob.glob(os.path.join(BASE, f'export_{fid}_*.csv')))
    if not files:
        raise FileNotFoundError(fid)
    with open(files[0], encoding='utf-8-sig') as fh:
        rows = list(csv.DictReader(fh))
    return [{(k or '').replace('"', '').strip(): v for k, v in r.items()} for r in rows]

def num(v):
    if v is None: return None
    v = str(v).strip().replace(',', '')
    if v in ('', '-'): return None
    try:
        f = float(v)
        return int(f) if f == int(f) else f
    except ValueError:
        return None

out = {}

# ---------- T20: per-town master table ----------
t20 = load('T20')
towns = []
for r in t20:
    towns.append({
        'name': r['שם ישוב/אזור'].strip(),
        'socio': num(r['אשכול  סוציו  אקונומי']),
        'pop': num(r['מספר  תושבים  למס']),
        'recipients': num(r['מספר  מקבלי שירות']),
        'families': num(r['מספר משפחות  מקבלות שירות']),
        'rec_0_19': num(r['מקבלי שירות  0-19']),  'pop_0_19': num(r['למס  0-19']),
        'rec_20_49': num(r['מקבלי שירות  20-49']), 'pop_20_49': num(r['למס  20-49']),
        'rec_50_64': num(r['מקבלי שירות  50-64']), 'pop_50_64': num(r['למס  50-64']),
        'rec_65': num(r['מקבלי שירות  65+']),      'pop_65': num(r['למס  65+']),
        'olim': num(r['עולים חדשים  מקבלי שירות']),
        'disabled': num(r['אנשים עם  מוגבלויות  מקבלי שירות']),
        'kids_risk': num(r['ילדים בסיכון  מקבלי שירות']),
    })

# ---------- T64: National-Insurance benefit recipients per town ----------
t64 = load('T64')
ben_by_town = {}
for r in t64:
    n = num(r['מקבלי גימלה'])
    if n is None: continue
    t = r['ישוב'].strip(); b = r['סוג גימלה'].strip()
    d = ben_by_town.setdefault(t, {'total': 0, 'by_type': {}, 'welfare_yes': 0})
    d['total'] += n
    d['by_type'][b] = d['by_type'].get(b, 0) + n
    if r['מקבלי שירות'].strip() == 'מקבל שירות ברווחה':
        d['welfare_yes'] += n
for t in towns:
    t['benefits'] = ben_by_town.get(t['name'], {'total': 0, 'by_type': {}, 'welfare_yes': 0})
out['towns'] = towns

# ---------- C107: age distribution vs similar authorities ----------
order = ['0-3','4-6','7-14','15-17','18-21','22-25','26-30','31-35','36-45','46-55','56-65','66-67','68-70','71-74','75+']
c107 = {r['קבוצת גיל']: (num(r['אוכלוסייה']), num(r['ממוצע ברשויות דומות'])) for r in load('C107')}
out['ages'] = [{'g': g, 'pop': c107[g][0], 'similar': c107[g][1]} for g in order]

# ---------- C108: service recipients vs national ----------
out['c108'] = [{'group': r['קבוצה'].strip(), 'pct': num(r['אחוז ברשות']), 'total': num(r['כלל האוכלוסייה']),
                'recipients': num(r['מקבלי שירות']), 'national': num(r['ממוצע ארצי']), 'similar': num(r['ממוצע רשויות דומות'])}
               for r in load('C108')]

# ---------- C109: family needs (active service-receiving families) ----------
c109 = load('C109')
out['family_needs_total'] = num(c109[0]['סך משפחות מקבלות שירות פעילות'])
needs = [{'cluster': r['אשכול'].strip(), 'need': r['שם נזקקות'].strip(), 'n': num(r['משפחות מקבלות שירות'])} for r in c109]
out['family_needs'] = sorted(needs, key=lambda x: -x['n'])

# ---------- C119: intervention goals ----------
out['goals'] = sorted([{'goal': r['יעד'].strip(), 'n': num(r['מקבלי שירות'])} for r in load('C119')], key=lambda x: -x['n'])

# ---------- C115-C118: recipient demographics ----------
out['rec_age'] = [{'g': r['קבוצת גיל'], 'n': num(r['מקבלי שירות'])} for r in load('C115')]
out['rec_gender'] = [{'g': r['מגדר'], 'n': num(r['מקבלי שירות'])} for r in load('C118')]

# ---------- C120/C121: case openings 24 months; C122: closings 12 months ----------
def months(fid, cols):
    rows = load(fid)
    return [{'ym': r['YearMonth 1'], 'date': r['תאריך'], **{k: num(r[c]) for k, c in cols.items()}} for r in rows]
open_cols = {'new': 'משפחות מקבלות שירות חדשות שלא היו מוכרות בעבר בר...',
             'known': 'משפחות מקבלות שירות חדשות שהיו מוכרות בעבר ברווח...',
             'total': 'סהכ פתיחות תיקים החודש'}
openings = months('C121', open_cols) + months('C120', open_cols)
openings.sort(key=lambda x: x['ym'])
out['openings'] = openings
out['closings'] = months('C122', {'n': 'משפחות מקבלות שירות שנסגר להן התיק'})

# ---------- T33: budget by domain ----------
out['budget'] = sorted([{'domain': r['תחום'].strip(), 'gross': num(r['הקצאה כוללת ברוטו']),
                         'net': num(r['הקצאה כוללת  נטו']), 'pct': num(r['אחוז מסהכ'])} for r in load('T33')],
                        key=lambda x: -x['gross'])
out['budget_total_gross'] = sum(b['gross'] for b in out['budget'])
out['budget_total_net'] = sum(b['net'] for b in out['budget'])

# ---------- C132/C133: NI benefits council-wide ----------
out['ni_types'] = [{'type': r['Benefit_Descr'], 'n': num(r['מקבלי גימלה'])} for r in load('C132')]
c133 = load('C133')[0]
out['ni_total'] = {'month': c133['חודש'], 'people': num(c133['מקבלי גימלאות']), 'benefits': num(c133['כמות גימלאות'])}

# ---------- Seniors ----------
out['senior_forecast'] = [{'y': r['שנה'], 'n': num(r['תחזית אוכלוסייה'])} for r in load('C134')]
out['senior_pyramid'] = [{'gender': r['מגדר'], 'g': r['קבוצת גיל'], 'n': num(r['מספר אזרחים וותיקים'])} for r in load('C135')]
out['senior_function'] = [{'level': r['רמת תפקוד'], 'n': num(r['מספר אזרחים ותיקים'])} for r in load('C142')]
out['senior_needs'] = [{'need': r['נזקקות'].strip(), 'n': num(r['רשומים ברווחה'])} for r in load('C141')]
c144 = load('C144')[0]
out['ariri'] = {'authority': num(c144['מספר ערירים לפי הרשות לנצלש']),
                'no_children': num(c144['חשש לבדידות ללא ילדים לפי מ. הרווחה']),
                'children_elsewhere': num(c144['חשש לבדידות עם ילדים בישוב אחר לפי מ. הרווחה'])}
t83 = load('T83')[0]
out['supportive'] = {'name': t83['שם המסגרת'], 'beneficiaries': num(t83['נהנים']), 'households': num(t83['סך בתי אב (בל + רווחה)']),
                     'capacity': num(t83['תפוסה מקסימלית']), 'occupancy': num(t83['אחוז תפוסה']),
                     'survivors': num(t83['ניצולי שואה (בל + רווחה)'])}
out['clubs'] = [{'name': r['שם המסגרת'], 'program': r['תוכנית'], 'n': num(r['מספר מושמים']),
                 'avg_age': num(r['גיל ממוצע']), 'pct_ariri': num(r['אחוז עריריים'])} for r in load('T89')]
# T65: nursing-law levels, authority vs national
t65 = load('T65')
lvl_cols = ['חצי סיעוד','מקבלי סיעוד ברמה 1','מקבלי סיעוד ברמה 2','מקבלי סיעוד ברמה 3','מקבלי סיעוד ברמה 4','מקבלי סיעוד ברמה 5','מקבלי סיעוד ברמה 6']
def pct(v):
    v = str(v).strip().replace('%','')
    return num(v)
out['nursing'] = {'levels': [c.replace('מקבלי סיעוד ברמה ','רמה ') for c in lvl_cols],
                  'counts': [num(t65[0][c]) for c in lvl_cols],
                  'pct_authority': [pct(t65[1][c]) for c in lvl_cols],
                  'pct_national': [pct(t65[2][c]) for c in lvl_cols]}
# C151/C153: senior programs budget plan vs execution
out['senior_budget'] = [{'program': r['תכנית'].strip(), 'reg': r['Sub_Regulation_Name'].strip(),
                         'plan': num(r['תכנון']), 'exec': num(r['ביצוע']), 'prev': num(r['ביצוע אשתקד'])}
                        for r in load('C153') if r['תכנית'].strip() and (num(r['תכנון']) or num(r['ביצוע']) or num(r['ביצוע אשתקד']))]

# ---------- T26: placements inside vs outside the council, by admin ----------
t26 = load('T26')
inside = sum(num(r['מספר מושמים  ברשות הנבחרת']) or 0 for r in t26)
outside = sum(num(r['מספר מושמים  ברשויות אחרות']) or 0 for r in t26)
out['placements_inout'] = {'inside': inside, 'outside': outside}
by_admin = {}
for r in t26:
    a = r['מינהל'].strip()
    d = by_admin.setdefault(a, {'inside': 0, 'outside': 0, 'pay': 0})
    d['inside'] += num(r['מספר מושמים  ברשות הנבחרת']) or 0
    d['outside'] += num(r['מספר מושמים  ברשויות אחרות']) or 0
    d['pay'] += num(r['סכום  לתשלום']) or 0
out['placements_by_admin'] = [{'admin': k, **v} for k, v in sorted(by_admin.items(), key=lambda kv: -(kv[1]['inside']+kv[1]['outside']))]

# ---------- T27: where Gush Etzion residents are placed (by hosting authority) ----------
t27 = load('T27')
by_auth = {}
for r in t27:
    # GE residents appear in 'ברשות הנבחרת' when the framework sits in Gush Etzion,
    # and in 'ברשויות אחרות' when it sits elsewhere — one of the two is always 0
    n = (num(r['מספר מושמים  ברשות הנבחרת']) or 0) + (num(r['מספר מושמים  ברשויות אחרות']) or 0)
    if n == 0: continue
    a = r['רשות  מסגרת/שלוחה'].strip()
    by_auth[a] = by_auth.get(a, 0) + n
out['placed_by_authority'] = sorted([{'authority': k, 'n': v} for k, v in by_auth.items()], key=lambda x: -x['n'])

# ---------- T30: frameworks operating for the council ----------
t30 = load('T30')
fw = []
for r in t30:
    fw.append({'name': r['שם מסגרת'].strip(), 'program': r['תוכנית'].strip(), 'type': r['סוג מסגרת'].strip(),
               'arrangement': r['סוג סידור'].strip(), 'admin': r['מינהל'].strip(),
               'total': num(r['סהכ  מושמים']) or 0, 'local': num(r['מספר מושמים  ברשות נבחרת']) or 0,
               'other': num(r['מספר מושמים  מרשויות אחרות']) or 0})
out['frameworks'] = sorted(fw, key=lambda x: -x['total'])

# ---------- GeoJSON: close LineStrings into polygons ----------
GEO_NAMES = {
    'alon_shvut': 'אלון שבות', 'elazar': 'אלעזר', 'bat_ayin': 'בת עין', 'har_gilo': 'הר גילה',
    'kfar_etzion': 'כפר עציון', 'karmei_tzur': 'כרמי צור', 'migdal_oz': 'מגדל עוז',
    'maale_amos': 'מעלה עמוס', 'neve_daniel': 'נווה דניאל', 'nokdim': 'נוקדים',
    'rosh_tzurim': 'ראש צורים', 'tekoa': 'תקוע', 'metzad': 'אספר', 'ibei_hanachal': 'איבי הנחל',
}
features = []
for key, heb in GEO_NAMES.items():
    gj = json.load(open(os.path.join(BASE, 'gush_geojson', f'{key}.geojson')))
    rings = []
    for feat in gj['features']:
        g = feat['geometry']
        if g['type'] == 'LineString':
            ring = list(g['coordinates'])
            if ring[0] != ring[-1]:
                ring.append(ring[0])
            rings.append([ring])
    geom = {'type': 'Polygon', 'coordinates': rings[0]} if len(rings) == 1 else \
           {'type': 'MultiPolygon', 'coordinates': rings}
    features.append({'type': 'Feature', 'properties': {'key': key, 'name': heb}, 'geometry': geom})
out['geojson'] = {'type': 'FeatureCollection', 'features': features}

with open(os.path.join(BASE, 'data.js'), 'w', encoding='utf-8') as fh:
    fh.write('window.DASH = ')
    json.dump(out, fh, ensure_ascii=False)
    fh.write(';')

# ---- console summary for verification ----
print('towns:', len(towns), 'pop sum (T20):', sum(t['pop'] for t in towns), 'recipients sum:', sum(t['recipients'] for t in towns))
print('budget gross total:', round(out['budget_total_gross'], 2), 'net:', round(out['budget_total_net'], 2))
print('placements inside/outside (T26):', inside, outside)
print('placed by authority top5:', out['placed_by_authority'][:5])
print('openings months:', len(openings), openings[0]['date'], '→', openings[-1]['date'], 'total 12m last:', sum(o['total'] for o in openings[-12:]))
print('closings 12m total:', sum(c['n'] for c in out['closings']))
print('frameworks:', len(fw), 'local placements in them:', sum(f['local'] for f in fw))
print('ni total:', out['ni_total'])
print('senior forecast 2026/2035:', out['senior_forecast'][0], out['senior_forecast'][-1])
print('benefits per town total:', sum(t['benefits']['total'] for t in towns))
EOF_MARKER = None
