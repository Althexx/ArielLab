"""Motore ed emissioni (opzione 3 di ARIEL): lettura dei file, impronta degli ingressi, vincoli e candidato migliore.
Solo libreria standard: gli xlsx si leggono come zip di XML."""
import os, re

NX = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
# i due file che l'opzione 3 scrive prima della CRN (percorsi relativi a outputs/)
FILE_MOTORE = ('Layer1/Engine_and_emissions.xlsx', '_work/Layer1/crn_case/0_interface/mftf_engine_design.xlsx')
COMBUSTIBILI = {'POSF10325': 'Jet A', 'POSF11498': 'ATJ'}  # HyChem; ATJ non verificato, i codici ignoti restano come sono

# righe del foglio Segments di Engine_and_emissions.xlsx: (etichetta di ARIEL, gruppo, nome, unita', decimali)
RIGHE_EM = [
    ('Segment fuel, Layer 1 [kg]', 'Fase', 'Combustibile', 'kg', 0),
    ('Segment duration, mission profile [min]', 'Fase', 'Durata', 'min', 1),
    ('Did the requested input converge?', 'Fase', 'Regime richiesto raggiunto', '', 0),
    ('Net thrust [kN]', 'Motore (per motore)', 'Spinta netta', 'kN', 1),
    ('TSFC [g/(kN·s)]', 'Motore (per motore)', 'TSFC', 'g/(kN·s)', 2),
    ('Tt4 [K]', 'Motore (per motore)', 'Tt4', 'K', 0),
    ('T3 [K]', 'Motore (per motore)', 'T3', 'K', 0),
    ('P3 [bar]', 'Motore (per motore)', 'P3', 'bar', 1),
    ('Combustor FAR [-]', 'Motore (per motore)', 'FAR', '', 4),
    ('EI NOx (equilibrium)', 'Indici di emissione', 'EI NOx, equilibrio', 'g/kg', 1),
    ('EI NOx (P3T3)', 'Indici di emissione', 'EI NOx, P3-T3', 'g/kg', 1),
    ('  P3T3 NOx extrapolated outside the T3 range?', 'Indici di emissione', 'P3-T3 fuori dal campo di T3', '', 0),
    ('EI CO (P3T3)', 'Indici di emissione', 'EI CO, P3-T3', 'g/kg', 2),
    ('EI CO2 (equilibrium)', 'Indici di emissione', 'EI CO₂', 'g/kg', 0),
    ('EI H2O (equilibrium)', 'Indici di emissione', 'EI H₂O', 'g/kg', 0),
    ('CO2 (equilibrium)', 'Emissioni (tutti i motori)', 'CO₂', 'kg', 0),
    ('H2O (equilibrium)', 'Emissioni (tutti i motori)', 'H₂O', 'kg', 0),
    ('NOx (equilibrium)', 'Emissioni (tutti i motori)', 'NOx, equilibrio', 'kg', 1),
    ('NOx (P3T3)', 'Emissioni (tutti i motori)', 'NOx, P3-T3', 'kg', 1),
    ('CO (P3T3)', 'Emissioni (tutti i motori)', 'CO, P3-T3', 'kg', 1)]


def _xlsx(p, foglio):
    """Righe di un foglio xlsx come liste di testi (celle vuote = ''); [] se il file manca o non si legge."""
    import xml.etree.ElementTree as ET, zipfile
    try:
        z = zipfile.ZipFile(p)
        ss = [''.join(t.text or '' for t in si.iter(NX + 't')) for si in ET.fromstring(z.read('xl/sharedStrings.xml')).iter(NX + 'si')] \
            if 'xl/sharedStrings.xml' in z.namelist() else []
        rid = next(s.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id')
                   for s in ET.fromstring(z.read('xl/workbook.xml')).iter(NX + 'sheet') if s.get('name') == foglio)
        f = next(r.get('Target') for r in ET.fromstring(z.read('xl/_rels/workbook.xml.rels')) if r.get('Id') == rid).lstrip('/')
        righe = []
        for r in ET.fromstring(z.read(f if f.startswith('xl/') else 'xl/' + f)).iter(NX + 'row'):
            riga = []
            for c in r.iter(NX + 'c'):
                col = 0
                for ch in re.match(r'[A-Z]+', c.get('r')).group():
                    col = col * 26 + ord(ch) - 64
                v, t = c.find(NX + 'v'), c.get('t')
                x = ''.join(e.text or '' for e in c.iter(NX + 't')) if t == 'inlineStr' else \
                    '' if v is None else ss[int(v.text)] if t == 's' else v.text
                riga += [''] * (col - 1 - len(riga)) + [x]
            righe.append(riga)
        return righe
    except (OSError, KeyError, StopIteration, ValueError, zipfile.BadZipFile, ET.ParseError):
        return []


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return x or None


def segmenti(dir_out):
    """Tabella per fase di Engine_and_emissions.xlsx (foglio Segments); None se il file non c'e'."""
    righe = _xlsx(os.path.join(dir_out, 'Layer1', 'Engine_and_emissions.xlsx'), 'Segments')
    if not righe:
        return None
    fasi, per = righe[0][1:], {}
    for r in righe:  # la prima volta: in fondo al foglio i 3 punti supersonici ripetono le etichette del motore
        if r:
            per.setdefault(r[0], r[1:])
    return {'fasi': fasi, 'righe': [{'gruppo': g, 'nome': n, 'u': u, 'd': d,
                                     'v': [_num(x) for x in (per[k] + [''] * len(fasi))[:len(fasi)]]}
                                    for k, g, n, u, d in RIGHE_EM if k in per]}


def _tabella(righe):
    """{etichetta colonna A: [colonne seguenti]} alla prima occorrenza."""
    out = {}
    for r in righe:
        if r and r[0]:
            out.setdefault(r[0].strip(), r[1:])
    return out


def _fogli(dir_out):
    eng = _tabella(_xlsx(os.path.join(dir_out, FILE_MOTORE[0]), 'Engine'))
    mf = os.path.join(dir_out, FILE_MOTORE[1])
    return eng, _tabella(_xlsx(mf, 'All Variables')), _xlsx(mf, 'Constraints'), _tabella(_xlsx(mf, 'Combustion Chamber'))


def carta(dir_out):
    """Carta d'identita' del motore progettato dall'opzione 3; None se un file manca o non si legge (anche se troncato)."""
    eng, var, cons, cc = _fogli(dir_out)
    if not eng or not var:
        return None
    e = lambda k: _num((eng.get(k) or [None])[0])
    fuel = (cc.get('fuel species') or [''])[0]
    return {'mach': e('Design point: Mach [-]'), 'quota': e('Design point: altitude [m]'),
            'Fn_crociera': e('Design point: required thrust per engine [kN]'), 'n_motori': e('Number of engines [-]'),
            'BPR': e('Bypass ratio BPR [-]'), 'OPR': e('Overall pressure ratio OPR [-]'),
            'Tt4': e('Turbine inlet temperature Tt4 [K]'), 'fan': e('Fan diameter [m]'),
            'portata': e('Air mass flow per engine [kg/s]'), 'TSFC': _num((var.get('Objective 1: TSFC') or [None])[0]),
            'combustibile': '%s (%s)' % (COMBUSTIBILI[fuel], fuel) if fuel in COMBUSTIBILI else fuel or None,
            'vincoli': [{'nome': r[0], 'valore': _num(r[1]), 'limite': _num(r[3]) if _num(r[3]) != '-' else None,
                         'minimo': _num(r[2]) if _num(r[2]) != '-' else None, 'stato': r[4]}
                        for r in cons[1:] if len(r) >= 5 and r[0]]}


def tsfc_si(dir_out):
    """TSFC del punto di progetto in kg/(N*s), controllato tra mftf (kg/(N.s)) ed Engine (g/(kN*s)): 1 g/(kN*s) = 1e-6 kg/(N*s)."""
    eng, var, _, _ = _fogli(dir_out)
    a = _num((var.get('Objective 1: TSFC') or [None])[0])
    b = _num(next((v[0] for k, v in eng.items() if k.startswith('TSFC at the design point')), None))
    if not isinstance(a, float) or not isinstance(b, float):
        raise ValueError('TSFC del motore non trovato nei file dell\'opzione 3')
    if abs(a - b * 1e-6) > 1e-3 * a:
        raise ValueError('TSFC incoerente tra i file: %.4g kg/(N s) contro %.4g g/(kN s)' % (a, b))
    return a


def impronta(valori, db_path, exe_path):
    """sha256 degli ingressi dell'opzione 3: valori (chiavi in ordine, cifre esatte), byte del database, dimensione dell'exe."""
    import hashlib, json
    h = hashlib.sha256(json.dumps(valori, sort_keys=True).encode('utf-8'))
    with open(db_path, 'rb') as f:
        h.update(f.read())
    h.update(str(os.path.getsize(exe_path)).encode())
    return h.hexdigest()


# ---------------------------------------------------------------- vincoli e candidato migliore
VINCOLI0 = [{'id': 'spinta_decollo', 'nome': 'Spinta al decollo disponibile / richiesta', 'min': 1.0},
            {'id': 'nox_lto', 'nome': 'NOx LTO / limite ICAO', 'max': 1.0},
            {'id': 'fumo', 'nome': 'Fumo (SN) / limite ICAO', 'max': 1.0},
            {'id': 'fan', 'nome': 'Diametro del fan [m]', 'max': 1.25},
            {'id': 'tt4', 'nome': 'Tt4 massimo [K]', 'max': 1500}]
CRITERI = {'MTOM': 'MTOM', 'fuel': 'combustibile di missione', 'co2_pkm': 'CO₂ per passeggero·km', 'TSFC': 'TSFC di crociera'}


def _riga(e, nome):
    return next((r['v'] for r in e.get('righe') or [] if r['nome'] == nome), [])


def grandezze(prova):
    """Grandezze per il confronto, da prova.json (riepilogo, valori, emissioni). None dove manca il dato."""
    e, r, v = prova.get('emissioni') or {}, prova.get('riepilogo') or {}, prova.get('valori') or {}
    fasi, carta, lto = e.get('fasi') or [], e.get('carta') or {}, e.get('lto') or {}
    num = lambda x: x if isinstance(x, (int, float)) and not isinstance(x, bool) else None
    fn = _riga(e, 'Spinta netta')
    fn_to = num(fn[fasi.index('Take-off')]) if 'Take-off' in fasi and fasi.index('Take-off') < len(fn) else None
    tt4 = [x for x in map(num, _riga(e, 'Tt4')) if x is not None]
    co2, fuel = _riga(e, 'CO₂'), _riga(e, 'Combustibile')
    pax, rng = v.get('payload/passenger_number [-]'), v.get('flight_expected_performances/range [km]')
    disp = lto.get('F00_kN') or fn_to  # con la CRN: F00 statica al livello del mare, come la spinta richiesta
    rap = lambda a, b: lto[a] / lto[b] if lto.get(a) is not None and lto.get(b) else None
    return {'spinta_decollo': disp / r['T_eng'] if disp and r.get('T_eng') else None,
            'Fn_decollo': fn_to, 'F00': lto.get('F00_kN'), 'T_richiesta': r.get('T_eng'),
            'nox_lto': rap('NOx_gkN', 'NOx_limite'), 'fumo': rap('SN', 'SN_limite'),
            'fan': carta.get('fan'), 'tt4': max(tt4) if tt4 else None,
            'co2_pkm': num(co2[-1]) / (pax * rng) if co2 and num(co2[-1]) and pax and rng else None,
            'fuel': num(fuel[-1]) if fuel else None, 'MTOM': r.get('MTOM'), 'TSFC': carta.get('TSFC')}


def verifica(gr, vincoli):
    """{id vincolo: True | False | None}; None = grandezza non disponibile (per esempio NOx LTO senza CRN)."""
    out = {}
    for c in vincoli:
        x = gr.get(c['id'])
        out[c['id']] = None if x is None else \
            (c.get('min') is None or x >= c['min']) and (c.get('max') is None or x <= c['max'])
    return out


def migliore(prove, vincoli, criterio='MTOM'):
    """(id del migliore | None, testo che spiega il criterio). Migliore = minimo del criterio tra chi non viola nessun vincolo."""
    nomi = {c['id']: c['nome'] for c in vincoli}
    ok = []
    for p in prove:
        g = grandezze(p)
        v = verifica(g, vincoli)
        if False not in v.values() and g.get(criterio) is not None:
            ok.append((g[criterio], p['id'], [k for k, x in v.items() if x is None]))
    if not ok:
        return None, 'Nessun candidato rispetta tutti i vincoli verificabili.'
    x, pid, non = min(ok)
    testo = 'Minimo %s tra %d candidat%s che rispettano i vincoli.' % (CRITERI.get(criterio, criterio), len(ok), 'o' if len(ok) == 1 else 'i')
    if non:
        testo += ' Non verificat%s: %s (serve la CRN o il dato manca).' % ('o' if len(non) == 1 else 'i', ', '.join(nomi.get(k, k) for k in non))
    return pid, testo


def controlla_vincoli(vincoli):
    """Solleva ValueError se un vincolo non ha id/nome o ha min/max non numerici."""
    if not isinstance(vincoli, list):
        raise ValueError('i vincoli devono essere una lista')
    for c in vincoli:
        if not isinstance(c, dict) or not c.get('id') or not c.get('nome'):
            raise ValueError('vincolo senza id o nome')
        for k in ('min', 'max'):
            if c.get(k) is not None and (isinstance(c[k], bool) or not isinstance(c[k], (int, float))):
                raise ValueError('%s di "%s" non e\' un numero' % (k, c['nome']))
    return vincoli


# ---------------------------------------------------------------- CRN: ciclo LTO contro i limiti ICAO (Annex 16 Vol. II)
FILE_CRN = '_work/Layer1/crn_case/4_crn_emissions/results/crn_emissions_results.xlsx'
GRAFICO_LTO = '_work/Layer1/crn_case/4_crn_emissions/results/figures/04_LTO_vs_ICAO_limits.png'


def lto(dir_out):
    """Dp/F00 del ciclo LTO e limiti ICAO dalla CRN (fogli Summary e 'LTO and ICAO limits'); None senza CRN.
    I limiti sono quelli scritti dall'exe (NOx = 36 + 2,42*pi00 per i motori supersonici)."""
    f = os.path.join(dir_out, FILE_CRN)
    s, t = _tabella(_xlsx(f, 'Summary')), _tabella(_xlsx(f, 'LTO and ICAO limits'))
    if not s or not t:
        return None
    v = lambda k, i: _num((t.get(k) or [None] * 5)[i])  # colonne dopo la specie: Dp_g, Dp/F00, baseline, limite, rapporto
    return {'F00_kN': _num(s.get('F00 [kN]', [None])[0]), 'OPR00': _num(s.get('pi_oo', [None])[0]),
            'NOx_gkN': v('NOx', 1), 'NOx_limite': v('NOx', 3), 'CO_gkN': v('CO', 1), 'CO_limite': v('CO', 3),
            'HC_gkN': v('UHC', 1), 'HC_limite': v('UHC', 3), 'SN': v('SN max', 1), 'SN_limite': v('SN max', 3),
            'parziale': (s.get('LTO cycle') or [''])[0] if 'partial' in (s.get('LTO cycle') or [''])[0] else None,
            'grafico': GRAFICO_LTO if os.path.isfile(os.path.join(dir_out, GRAFICO_LTO)) else None}
