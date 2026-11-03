"""Dashboard locale per ARIEL-SST: cambia gli input, lancia ARIEL (opzione 2), salva e confronta le prove.
Su una prova salvata lancia anche motore ed emissioni (opzione 3): dura molto di piu', da decine di minuti in su.

Avvio: doppio clic su 'Avvia dashboard.bat' (oppure: python app.py). Si apre http://127.0.0.1:8790 nel browser.
ARIEL resta acceso tra un calcolo e l'altro: il primo dura circa 20 s in piu' (avvio), poi 5-15 s a calcolo secondo il carico del PC.
"""
import csv, io, json, os, re, shutil, subprocess, sys, threading, time, webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse
try:
    import yaml
except ImportError:
    sys.exit('Manca PyYAML: apri il Prompt dei comandi e scrivi  pip install pyyaml  poi riavvia.')

QUI = os.path.dirname(os.path.abspath(__file__))
IASD = os.path.join(os.path.expanduser('~'), 'Desktop', 'PROF CLAUDIO', 'Integrated aerospace systems design')
# da dove si copia ARIEL al primo avvio: la copia in IASD/ARIEL (gli originali restano sul Desktop)
CORSO_EXE = os.path.join(IASD, 'ARIEL', 'New ARIEL Release', 'windows', 'ARIEL-SST.exe')
CORSO_TEMPLATE = os.path.join(IASD, 'ARIEL', 'New ARIEL Release', 'HLInputs_TEMPLATE.yaml')
CORSO_INPUTS = os.path.join(IASD, 'ARIEL', 'Topic_3_Mach1.8_Airliner_100pax', 'Topic_3_Mach1.8_Airliner_100pax', 'windows', 'inputs')
LAVORO = os.path.join(QUI, 'lavoro')
INIZIALI = os.path.join(QUI, 'inputs_iniziali')
PROVE = os.path.join(QUI, 'prove')
PORTA = 8790
PROMPT = b'Select an option [1-4]:'
# chiavi nuove della release del 27/10: valori del pacchetto del corso, sono scelte di progetto
NUOVI = {'vehicle_characteristics/take_off_cl_max [-]': 1.18, 'vehicle_characteristics/landing_cl_max [-]': 0.8}
INTERI = ('passenger_number', 'crew_number', 'number_engines')
O = 'operational_scenario_characteristics/'


# ---------------------------------------------------------------- input: schema, lettura, scrittura, controlli
def _righe(template):
    """(gruppo, chiave, commento, indice di riga) per ogni valore del template."""
    gruppo = None
    for i, r in enumerate(template.splitlines()):
        if not r.strip() or r.lstrip().startswith('#') or ':' not in r:
            continue
        chiave, resto = r.split(':', 1)
        comm = resto.split('#', 1)[1].strip() if '#' in resto else ''
        if not r[0].isspace():
            if not resto.strip():
                gruppo = chiave.strip(); continue
            gruppo = None
        yield gruppo, chiave.strip(), comm, i


def schema(template):
    campi = []
    for g, k, comm, _ in _righe(template):
        c = {'id': '%s/%s' % (g, k) if g else k, 'gruppo': g or 'configurazione', 'chiave': k, 'commento': comm,
             'unita': (re.findall(r'\[([^\]]*)\]', k) or [''])[-1], 'min': None, 'max': None, 'scelte': None,
             'intero': any(x in k for x in INTERI), 'positivo': 'positive' in comm}
        m = re.search(r'\[(-?[\d.]+)\s*to\s*(-?[\d.]+)\]', comm.replace('−', '-').replace(' 000', '000'))
        if m:
            c['min'], c['max'] = float(m.group(1)), float(m.group(2))
        m = re.search(r'\[(\d+)%-(\d+)%\]', comm)
        if m:
            c['min'], c['max'] = int(m.group(1)) / 100, int(m.group(2)) / 100
        if "['0']" in comm:
            c['scelte'] = re.findall(r"\['(\w+)'\]", comm)
        campi.append(c)
    return campi


def leggi_valori(testo):
    d, v = yaml.safe_load(testo) or {}, {}
    for k, x in d.items():
        if isinstance(x, dict):
            v.update({'%s/%s' % (k, kk): xx for kk, xx in x.items()})
        else:
            v[k] = str(x) if k in ('H_Tail', 'Canard') else x
    return v


def converti(testo, template):
    """Valori di un HLInputs.yaml (anche della release vecchia) sulle chiavi del template nuovo, con le note."""
    vecchi, note, v = leggi_valori(testo), [], {}
    for c in schema(template):
        if c['id'] in vecchi:
            v[c['id']] = vecchi[c['id']]
        elif c['id'] in NUOVI:
            v[c['id']] = NUOVI[c['id']]
            note.append('aggiunta %s = %s (valore del pacchetto del corso: e\' una scelta di progetto)' % (c['chiave'], NUOVI[c['id']]))
        else:
            note.append('manca %s' % c['chiave'])
    ids = {c['id'] for c in schema(template)}
    note += ['tolta %s (ora la calcola ARIEL)' % k.split('/')[-1] for k in vecchi if k not in ids]
    return v, note


def _fmt(x):
    if isinstance(x, str):
        return "'%s'" % x
    if isinstance(x, bool):
        raise ValueError('valore non numerico')
    if isinstance(x, int):
        return str(x)
    s = repr(float(x))
    return ('%.12f' % x).rstrip('0').rstrip('.') if 'e' in s else s  # PyYAML legge 3e-05 come testo


def scrivi_hl(template, valori):
    righe = template.splitlines()
    for g, k, comm, i in _righe(template):
        cid = '%s/%s' % (g, k) if g else k
        if cid not in valori:
            raise ValueError('manca il valore di %s' % cid)
        pre = righe[i].split(':', 1)[0]
        righe[i] = '%s: %s%s' % (pre, _fmt(valori[cid]), ('  # ' + comm) if comm else '')
    return '\n'.join(righe) + '\n'


def controlla(v, sch):
    err = []
    for c in sch:
        x = v.get(c['id'])
        if x is None or x == '':
            err.append('%s: manca il valore' % c['id']); continue
        if c['scelte']:
            if str(x) not in c['scelte']:
                err.append('%s: deve essere %s' % (c['id'], ' o '.join(c['scelte'])))
            continue
        if isinstance(x, bool) or not isinstance(x, (int, float)):
            err.append('%s: non e\' un numero' % c['id']); continue
        if c['min'] is not None and not c['min'] <= x <= c['max']:
            err.append('%s = %s: fuori dall\'intervallo %s - %s' % (c['id'], x, c['min'], c['max']))
        if c['positivo'] and x <= 0:
            err.append('%s: deve essere positivo' % c['id'])
        if c['intero'] and x != int(x):
            err.append('%s: deve essere intero' % c['id'])
    if err:
        return err
    a = lambda k: v[O + k]
    # regole della release del 27/10 (presentazione, slide 13)
    if not a('subsonic_cruise_altitude [m]') > max(a('take_off_altitude [m]'), a('landing_altitude [m]')):
        err.append('La crociera subsonica deve stare sopra i due aeroporti')
    if not a('supersonic_cruise_altitude [m]') > a('subsonic_cruise_altitude [m]'):
        err.append('La crociera supersonica deve stare sopra la crociera subsonica')
    if not a('take_off_mach [-]') <= a('2nd_segment_mach [-]') <= a('subsonic_cruise_mach [-]'):
        err.append('Il Mach non deve scendere: decollo <= 2o segmento <= crociera subsonica')
    if not a('landing_mach [-]') < a('subsonic_cruise_mach [-]'):
        err.append('Il Mach di atterraggio deve essere sotto quello della crociera subsonica')
    return err


# ---------------------------------------------------------------- uscite di ARIEL
def _y(p):
    try:
        return yaml.safe_load(open(p, encoding='utf-8')) or {}
    except (OSError, yaml.YAMLError):
        return {}


def riepilogo(dir_out, log):
    m = re.search(r'Converged in (\d+) iterations', log)
    righe = log.splitlines()
    i = next((j for j, r in enumerate(righe) if 'Error' in r or 'error:' in r.lower()), None)
    if i is not None or not m:
        coda = []
        for r in ([] if i is None else righe[i:i + 30]):  # il messaggio finisce alla prima riga vuota
            if not r.strip():
                break
            coda.append(r)
        return {'ok': False, 'errore': '\n'.join(coda).strip() or 'ARIEL non ha convergito (nessun "Converged" nel log)'}
    res = _y(os.path.join(dir_out, 'Layer1', 'results.yaml'))
    db = os.path.join(dir_out, '_work', 'Layer1', 'Databases')
    eff, mc = _y(os.path.join(db, 'debug_eff_layer1.yaml')), _y(os.path.join(db, 'MatchingChartData.yaml'))
    tw = {re.sub(r'^\d+\.\s*T/W\s*|\s*\[-\]$', '', k).capitalize(): float(x) for k, x in mc.items() if 'T/W' in k}
    TW = max(tw.values()) if tw else max(res.get('T/W_sub[-]', 0), res.get('T/W_sup[-]', 0)) or None
    E = lambda s: (eff.get(s) or {}).get('E')
    return {'ok': True, 'iterazioni': int(m.group(1)),
            'MTOM': res.get('maximum_take-off_mass_[kg]'), 'OEM': res.get('operative_empty_mass_[kg]'),
            'carburante': res.get('fuel_capacity_[kg]'), 'S': res.get('wing_area_[m2]'),
            'WS': res.get('W/S_Landing_[kg/m2]'), 'TW': TW,
            'attivo': ' = '.join(k for k, x in tw.items() if x == TW) or None,
            'vincoli': tw or None, 'LD_sup': E('supersonic_cruise'), 'LD_sub': E('subsonic_cruise'),
            'T_eng': res['T/engines_[N]'] / 1000 if 'T/engines_[N]' in res else None,
            'apertura': res.get('wingspan_[m]'), 'A': res.get('wing_aspect_ratio_[-]'),
            'freccia': res.get('wing_sweep_angle_[deg]'), 'L_fus': res.get('fuselage_length_[m]')}


# ---------------------------------------------------------------- motore ed emissioni (opzione 3)
NX = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
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
    """Righe di un foglio xlsx come liste di testi (celle vuote = ''), con la sola libreria standard."""
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


def emissioni(dir_out):
    """Tabella per fase di Engine_and_emissions.xlsx (foglio Segments); None se il file non c'e'."""
    righe = _xlsx(os.path.join(dir_out, 'Layer1', 'Engine_and_emissions.xlsx'), 'Segments')
    if not righe:
        return None
    fasi, per = righe[0][1:], {}
    for r in righe:  # la prima volta: in fondo al foglio i 3 punti supersonici ripetono le etichette del motore
        if r:
            per.setdefault(r[0], r[1:])

    def num(x):
        try:
            return float(x)
        except ValueError:
            return x or None
    return {'fasi': fasi, 'righe': [{'gruppo': g, 'nome': n, 'u': u, 'd': d,
                                     'v': [num(x) for x in (per[k] + [''] * len(fasi))[:len(fasi)]]}
                                    for k, g, n, u, d in RIGHE_EM if k in per]}


# ---------------------------------------------------------------- ARIEL acceso
class Ariel:
    """ARIEL-SST con stdin/stdout rediretti: resta acceso, ogni calcolo = '2' (o '3') e attesa del menu."""
    def __init__(self, cmd, cwd):
        self.cmd, self.cwd, self.proc, self.buf, self.lock = cmd, cwd, None, bytearray(), threading.Lock()

    def _leggi(self, p):
        while True:
            b = p.stdout.read1(4096)
            if not b:
                break
            self.buf.extend(b)

    def _attendi(self, n, sec):
        t = time.time() + sec
        while time.time() < t:
            if self.buf.count(PROMPT) >= n:
                return True
            if self.proc.poll() is not None:
                return False
            time.sleep(0.1)
        return False

    def avvia(self):
        self.buf = bytearray()
        self.proc = subprocess.Popen(self.cmd, cwd=self.cwd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT, env=dict(os.environ, PYTHONUNBUFFERED='1'),
                                     creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        threading.Thread(target=self._leggi, args=(self.proc,), daemon=True).start()
        return self._attendi(1, 120)

    def pronto(self):
        return self.proc is not None and self.proc.poll() is None and self.buf.count(PROMPT) >= 1

    def scalda(self):
        with self.lock:
            if self.proc is None or self.proc.poll() is not None:
                self.avvia()

    def calcola(self, sec=180, opzione=b'2'):
        with self.lock:
            if self.proc is None or self.proc.poll() is not None or not self._attendi(1, 120):
                self.chiudi()
                if not self.avvia():
                    log = self.buf.decode('utf-8', 'replace'); self.chiudi()
                    return log + '\n[dashboard] Error: ARIEL non si e\' avviato'
            n, da = self.buf.count(PROMPT), len(self.buf)
            self.proc.stdin.write(opzione + b'\n'); self.proc.stdin.flush()
            ok = self._attendi(n + 1, sec)
            log = self.buf[da:].decode('utf-8', 'replace')
            if not ok:
                self.chiudi()
                log += '\n[dashboard] Error: ARIEL non ha risposto entro %d s; verra\' riavviato' % sec
            return log

    def chiudi(self):
        p, self.proc = self.proc, None
        if p and p.poll() is None:
            try:
                p.stdin.write(b'4\n'); p.stdin.flush(); p.wait(10)
            except Exception:
                p.kill()


# ---------------------------------------------------------------- prove salvate
class Lab:
    def __init__(self, template, ariel, dir_lavoro, dir_prove, valori, note=()):
        self.template, self.sch, self.ariel = template, schema(template), ariel
        self.dir_lavoro, self.dir_prove, self.valori0, self.note = dir_lavoro, dir_prove, valori, list(note)
        self.job = None  # {'id', 'inizio'} della prova di cui ARIEL sta calcolando motore ed emissioni
        os.makedirs(dir_prove, exist_ok=True)

    def _p(self, pid):
        if not re.fullmatch(r'[\w.\-]+', pid or ''):
            raise KeyError(pid)
        return os.path.join(self.dir_prove, pid)

    def calcola(self, valori, nome, nota):
        err = controlla(valori, self.sch)
        if self.job:  # l'opzione 3 usa gli input e gli output della cartella di lavoro
            err = ['ARIEL sta calcolando motore ed emissioni: aspetta che finisca.']
        if err:
            return {'id': None, 'nome': nome, 'valori': valori, 'riepilogo': {'ok': False, 'errore': '\n'.join(err)}}
        testo = scrivi_hl(self.template, valori)
        open(os.path.join(self.dir_lavoro, 'inputs', 'HLInputs.yaml'), 'w', encoding='utf-8').write(testo)
        t0 = time.time()
        log = self.ariel.calcola()
        out = os.path.join(self.dir_lavoro, 'outputs')
        r = riepilogo(out, log)
        r['secondi'] = round(time.time() - t0, 1)
        base = '%s_%s' % (datetime.now().strftime('%Y-%m-%d_%H%M%S'), re.sub(r'[^\w\-]+', '-', nome or 'prova').strip('-')[:40])
        pid, k = base, 2
        while os.path.exists(os.path.join(self.dir_prove, pid)):
            pid, k = '%s-%d' % (base, k), k + 1
        d = self._p(pid); os.makedirs(d)
        open(os.path.join(d, 'HLInputs.yaml'), 'w', encoding='utf-8').write(testo)
        open(os.path.join(d, 'log.txt'), 'w', encoding='utf-8').write(log)
        if r['ok']:
            shutil.copytree(out, os.path.join(d, 'outputs'))
        rif = r['ok'] and not any(p['rif'] for p in self.prove())
        p = {'id': pid, 'nome': nome or 'prova', 'nota': nota or '', 'data': datetime.now().strftime('%d/%m/%Y %H:%M:%S'),
             'ts': time.time(), 'rif': rif, 'valori': valori, 'riepilogo': r}
        json.dump(p, open(os.path.join(d, 'prova.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        return p

    def prova(self, pid):
        return json.load(open(os.path.join(self._p(pid), 'prova.json'), encoding='utf-8'))

    def prove(self):
        out = []
        for n in os.listdir(self.dir_prove):
            try:
                out.append(self.prova(n))
            except (OSError, ValueError, KeyError):
                pass
        return sorted(out, key=lambda p: -p['ts'])

    def aggiorna(self, pid, campi):
        p = self.prova(pid)
        if campi.get('rif'):
            for q in self.prove():
                if q['rif'] and q['id'] != pid:
                    q['rif'] = False
                    json.dump(q, open(os.path.join(self._p(q['id']), 'prova.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        p.update({k: campi[k] for k in ('nome', 'nota', 'rif') if k in campi})
        json.dump(p, open(os.path.join(self._p(pid), 'prova.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        return p

    def cancella(self, pid):
        shutil.rmtree(self._p(pid))

    def emissioni(self, pid, sec=6 * 3600):
        """Avvia in un thread l'opzione 3 di ARIEL (motore ed emissioni) sul velivolo della prova."""
        if self.job:
            raise ValueError('ARIEL sta gia\' calcolando motore ed emissioni')
        if not self.prova(pid)['riepilogo'].get('ok'):
            raise ValueError('la prova non converge: non c\'e\' un velivolo su cui progettare il motore')
        self.job = {'id': pid, 'inizio': time.time()}
        t = threading.Thread(target=self._emissioni, args=(pid, sec), daemon=True)
        t.start()
        return t

    def _emissioni(self, pid, sec):
        try:
            d, out = self._p(pid), os.path.join(self.dir_lavoro, 'outputs')
            # l'opzione 3 parte dall'ultimo velivolo calcolato: si rimette in lavoro/ quello della prova
            shutil.copy2(os.path.join(d, 'HLInputs.yaml'), os.path.join(self.dir_lavoro, 'inputs', 'HLInputs.yaml'))
            if os.path.isdir(out):
                shutil.rmtree(out)
            shutil.copytree(os.path.join(d, 'outputs'), out)
            for vecchio in ('Engine_and_emissions.xlsx', 'CRN_emissions'):  # risultati di un giro precedente
                f = os.path.join(out, 'Layer1', vecchio)
                if os.path.isdir(f):
                    shutil.rmtree(f)
                elif os.path.isfile(f):
                    os.remove(f)
            t0 = time.time()
            log = self.ariel.calcola(sec, b'3')
            open(os.path.join(d, 'log_emissioni.txt'), 'w', encoding='utf-8').write(log)
            e = emissioni(out)
            if e:
                shutil.copytree(out, os.path.join(d, 'outputs'), dirs_exist_ok=True)
                e.update(ok=True)
            else:
                err = [r for r in log.splitlines() if 'error' in r.lower()]
                e = {'ok': False, 'errore': '\n'.join(err[:10]) or 'ARIEL non ha scritto Engine_and_emissions.xlsx'}
            e.update(secondi=round(time.time() - t0), data=datetime.now().strftime('%d/%m/%Y %H:%M'))
            p = self.prova(pid)  # riletta: nome e nota possono essere cambiati durante il calcolo
            p['emissioni'] = e
            json.dump(p, open(os.path.join(d, 'prova.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        except (OSError, KeyError, ValueError):
            pass  # prova cancellata durante il calcolo
        finally:
            self.job = None

    def esporta(self, pid):
        """Una prova nel formato che legge la Control Room (formato 1)."""
        p, d = self.prova(pid), self._p(pid)
        log = open(os.path.join(d, 'log.txt'), encoding='utf-8').read()
        f, it = re.findall(r'Fuel_f=\s*([\d.]+)\s*%', log), re.search(r'Converged in (\d+) iterations', log)
        dbs = sorted(x for x in os.listdir(os.path.join(self.dir_lavoro, 'inputs')) if x.lower().endswith('.xlsx'))
        nome = lambda k: re.sub(r'\s*\[[^\]]*\]$', '', k).split('/')[-1]  # l'unita' puo' contenere '/'
        return {'tool': 'ARIEL-SST', 'formato': 1, 'prova': {k: p.get(k) for k in ('id', 'nome', 'data', 'nota')},
                'db': dbs[0] if dbs else None, 'hl': {nome(k): x for k, x in p['valori'].items()},
                'results': _y(os.path.join(d, 'outputs', 'Layer1', 'results.yaml')),
                'mission': _y(os.path.join(d, 'outputs', 'MissionProfile.yaml')),
                'log': {'Fuel_f': float(f[-1]) if f else None, 'iterazioni': int(it.group(1)) if it else None, 'converge': bool(it)}}

    def stato(self):
        pr = self.prove()
        return {'schema': self.sch, 'valori': pr[0]['valori'] if pr else self.valori0, 'note': self.note,
                'prove': pr, 'ariel_pronto': self.ariel.pronto(), 'job': self.job}

    def csv(self, ids):
        pr = [self.prova(i) for i in ids]
        ris = ['MTOM', 'OEM', 'carburante', 'S', 'WS', 'TW', 'attivo', 'LD_sup', 'LD_sub', 'T_eng', 'iterazioni']
        f = io.StringIO(); w = csv.writer(f, delimiter=';')
        w.writerow(['voce'] + [p['nome'] for p in pr])
        for c in self.sch:
            w.writerow([c['id']] + [p['valori'].get(c['id']) for p in pr])
        for k in ris:
            w.writerow([k] + [p['riepilogo'].get(k) for p in pr])
        return f.getvalue()


def esporta(lab, pid):
    return lab.esporta(pid)


# ---------------------------------------------------------------- server HTTP (solo 127.0.0.1)
def server(lab, porta):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _invia(self, corpo, tipo='application/json; charset=utf-8', codice=200, extra=()):
            if isinstance(corpo, (dict, list)):
                corpo = json.dumps(corpo, ensure_ascii=False)
            if isinstance(corpo, str):
                corpo = corpo.encode('utf-8')
            self.send_response(codice); self.send_header('Content-Type', tipo)
            self.send_header('Content-Length', str(len(corpo))); self.send_header('Cache-Control', 'no-store')
            for k, x in extra:
                self.send_header(k, x)
            self.end_headers(); self.wfile.write(corpo)

        def _json(self):
            n = int(self.headers.get('Content-Length') or 0)
            return json.loads(self.rfile.read(n) or b'{}')

        def do_GET(self):
            u = urlparse(self.path); p = unquote(u.path)
            try:
                if p == '/':
                    return self._invia(open(os.path.join(QUI, 'index.html'), encoding='utf-8').read(), 'text/html; charset=utf-8')
                if p == '/api/stato':
                    return self._invia(lab.stato())
                if p == '/api/csv':
                    ids = parse_qs(u.query).get('ids', [''])[0].split(',')
                    return self._invia(lab.csv(ids), 'text/csv; charset=utf-8', extra=[('Content-Disposition', 'attachment; filename="prove_ariel.csv"')])
                m = re.fullmatch(r'/api/esporta/([\w.\-]+)', p)
                if m:
                    return self._invia(lab.esporta(m.group(1)), extra=[('Content-Disposition', 'attachment; filename="ariel_%s.json"' % m.group(1))])
                if p.startswith('/prove/'):
                    f = os.path.realpath(os.path.join(lab.dir_prove, p[len('/prove/'):]))
                    if f.startswith(os.path.realpath(lab.dir_prove) + os.sep) and os.path.isfile(f):
                        tipo = 'image/png' if f.endswith('.png') else 'text/plain; charset=utf-8'
                        return self._invia(open(f, 'rb').read(), tipo)
                self._invia({'errore': 'non trovato'}, codice=404)
            except (KeyError, OSError) as e:
                self._invia({'errore': str(e)}, codice=404)

        def do_POST(self):
            p = unquote(urlparse(self.path).path)
            try:
                if p == '/api/calcola':
                    d = self._json()
                    return self._invia(lab.calcola(d['valori'], d.get('nome', ''), d.get('nota', '')))
                m = re.fullmatch(r'/api/prova/([\w.\-]+)(/cancella|/emissioni)?', p)
                if m and m.group(2) == '/emissioni':
                    lab.emissioni(m.group(1)); return self._invia({'ok': True})
                if m and m.group(2):
                    if lab.job and lab.job['id'] == m.group(1):
                        raise ValueError('ARIEL sta calcolando motore ed emissioni di questa prova')
                    lab.cancella(m.group(1)); return self._invia({'ok': True})
                if m:
                    return self._invia(lab.aggiorna(m.group(1), self._json()))
                self._invia({'errore': 'non trovato'}, codice=404)
            except (KeyError, OSError, ValueError) as e:
                self._invia({'errore': str(e)}, codice=400)

    return ThreadingHTTPServer(('127.0.0.1', porta), H)


# ---------------------------------------------------------------- avvio
def prepara():
    """Cartella di lavoro con una copia di ARIEL e degli input del corso; valori di partenza."""
    tpl_p = CORSO_TEMPLATE if os.path.isfile(CORSO_TEMPLATE) else os.path.join(QUI, 'test_dati', 'HLInputs_TEMPLATE.yaml')
    template = open(tpl_p, encoding='utf-8').read()
    os.makedirs(os.path.join(LAVORO, 'inputs'), exist_ok=True)
    exe = os.path.join(LAVORO, 'ARIEL-SST.exe')
    if not os.path.isfile(exe):
        if not os.path.isfile(CORSO_EXE):  # su un altro PC l'eseguibile si mette a mano in lavoro/
            sys.exit('ARIEL-SST.exe non trovato. Copia ARIEL-SST.exe (release del 27/10, cartella windows) in:\n  %s\npoi riavvia.' % exe)
        shutil.copy2(CORSO_EXE, exe)
    # su un altro PC la cartella del corso non c'è: input del pacchetto e database del team da inputs_iniziali/
    src = CORSO_INPUTS if os.path.isdir(CORSO_INPUTS) else INIZIALI
    for f in ('StatDatabase.xlsx', 'HLInputs.yaml'):
        if not os.path.isfile(os.path.join(LAVORO, 'inputs', f)):
            if not os.path.isfile(os.path.join(src, f)):
                sys.exit('Manca %s. Copialo (dallo zip ARIEL_Lab del team) in:\n  %s\npoi riavvia.' % (f, INIZIALI))
            shutil.copy2(os.path.join(src, f), os.path.join(LAVORO, 'inputs', f))
    valori, note = converti(open(os.path.join(LAVORO, 'inputs', 'HLInputs.yaml'), encoding='utf-8').read(), template)
    return template, exe, valori, note


def main():
    template, exe, valori, note = prepara()
    ariel = Ariel([exe], LAVORO)
    lab = Lab(template, ariel, LAVORO, PROVE, valori, note)
    threading.Thread(target=ariel.scalda, daemon=True).start()  # ARIEL si scalda mentre si apre la pagina
    for porta in range(PORTA, PORTA + 10):
        try:
            srv = server(lab, porta); break
        except OSError:
            continue
    url = 'http://127.0.0.1:%d' % srv.server_address[1]
    print('Dashboard ARIEL su %s  (chiudi questa finestra per fermarla)' % url)
    if '--no-browser' not in sys.argv:
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        ariel.chiudi()


if __name__ == '__main__':
    main()
