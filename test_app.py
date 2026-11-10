"""Test della dashboard ARIEL: python -m unittest ariel_dashboard/test_app.py (dalla cartella del progetto)."""
import json, os, shutil, sys, tempfile, threading, time, unittest, urllib.request
import yaml

QUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, QUI)
import app
import motore

DATI = os.path.join(QUI, 'test_dati')
TEMPLATE = open(os.path.join(DATI, 'HLInputs_TEMPLATE.yaml'), encoding='utf-8').read()
VECCHIO = open(os.path.join(DATI, 'HLInputs_vecchio.yaml'), encoding='utf-8').read()


def valori_validi():
    v, _ = app.converti(VECCHIO, TEMPLATE)
    return v


class Schema(unittest.TestCase):
    def test_un_campo_per_chiave_del_template(self):
        s = app.schema(TEMPLATE)
        nomi = [c['id'] for c in s]
        self.assertEqual(len(nomi), len(set(nomi)))
        self.assertIn('flight_expected_performances/mach [-]', nomi)
        self.assertIn('H_Tail', nomi)
        self.assertEqual(len(s), 37)

    def test_limiti_dai_commenti(self):
        s = {c['id']: c for c in app.schema(TEMPLATE)}
        self.assertEqual((s['flight_expected_performances/mach [-]']['min'], s['flight_expected_performances/mach [-]']['max']), (1.5, 2.5))
        d = s['operational_scenario_characteristics/subsonic_cruise_distance [%]']
        self.assertEqual((d['min'], d['max']), (0.05, 0.10))
        self.assertEqual(s['H_Tail']['scelte'], ['0', '1'])
        self.assertEqual(s['payload/passenger_number [-]']['gruppo'], 'payload')


class Scrittura(unittest.TestCase):
    def test_converti_il_file_vecchio(self):
        v, note = app.converti(VECCHIO, TEMPLATE)
        self.assertEqual(v['vehicle_characteristics/take_off_cl_max [-]'], 1.18)
        self.assertEqual(v['vehicle_characteristics/landing_cl_max [-]'], 0.8)
        self.assertNotIn('operational_scenario_characteristics/subsonic_climb_mach [-]', v)
        self.assertTrue(any('subsonic_climb_mach' in n for n in note))
        self.assertTrue(any('take_off_cl_max' in n for n in note))

    def test_scrive_le_stesse_chiavi_del_template_e_i_valori(self):
        v = valori_validi()
        testo = app.scrivi_hl(TEMPLATE, v)
        letto = yaml.safe_load(testo)
        vuoto = yaml.safe_load(TEMPLATE)
        self.assertEqual(list(letto), list(vuoto))
        for g in vuoto:
            if isinstance(vuoto[g], dict):
                self.assertEqual(list(letto[g]), list(vuoto[g]))
        self.assertEqual(app.leggi_valori(testo), v)
        self.assertIsInstance(letto['flight_expected_performances']['sfc [(kg/s)/N]'], float)
        self.assertEqual(letto['H_Tail'], '1')
        self.assertIn('# [\\], Cruise (design) Mach number', testo)

    def test_manca_un_valore(self):
        v = valori_validi(); del v['payload/passenger_number [-]']
        with self.assertRaises(ValueError):
            app.scrivi_hl(TEMPLATE, v)


class Controlli(unittest.TestCase):
    def test_valori_del_pacchetto_validi(self):
        self.assertEqual(app.controlla(valori_validi(), app.schema(TEMPLATE)), [])

    def test_fuori_limite(self):
        v = valori_validi(); v['operational_scenario_characteristics/subsonic_cruise_altitude [m]'] = 14000
        e = app.controlla(v, app.schema(TEMPLATE))
        self.assertTrue(any('subsonic_cruise_altitude' in x for x in e))

    def test_punti_di_missione_incoerenti(self):
        s = app.schema(TEMPLATE)
        v = valori_validi(); v['operational_scenario_characteristics/supersonic_cruise_altitude [m]'] = 13000
        v['operational_scenario_characteristics/subsonic_cruise_altitude [m]'] = 13500
        self.assertTrue(any('supersonica' in x for x in app.controlla(v, s)))
        v = valori_validi(); v['operational_scenario_characteristics/2nd_segment_mach [-]'] = 0.32
        self.assertTrue(any('Mach' in x for x in app.controlla(v, s)))
        # aeroporti sotto la crociera subsonica e Mach di atterraggio sotto quello della crociera subsonica:
        # entro i limiti dei singoli campi non si possono violare (4500 < 6000 m, 0.40 < 0.50)


class Riepilogo(unittest.TestCase):
    def test_prova_vera(self):
        r = app.riepilogo(os.path.join(DATI, 'outputs'), open(os.path.join(DATI, 'log_ok.txt'), encoding='utf-8').read())
        self.assertTrue(r['ok'])
        self.assertEqual(r['MTOM'], 137794)
        self.assertEqual(r['OEM'], 60801)
        self.assertEqual(r['iterazioni'], 33)
        self.assertAlmostEqual(r['LD_sup'], 6.893, places=3)
        self.assertAlmostEqual(r['LD_sub'], 8.553, places=3)
        self.assertEqual(r['TW'], 0.4)
        self.assertIn('Take-off', r['attivo']); self.assertIn('Subsonic cruise', r['attivo'])
        self.assertAlmostEqual(r['T_eng'], 135.176, places=3)

    def test_errore(self):
        r = app.riepilogo('/non/esiste', 'Running...\nError: Divergency detected in MTOW iterative loop\n')
        self.assertFalse(r['ok'])
        self.assertIn('Divergency', r['errore'])
        log = ('Iteration: 9\nError: Divergency detected in MTOW iterative loop\n\n\nResults saved in: C:\\x\\outputs\n'
               'Execution time of ARIEL-SST 2.0 has been 14.587 seconds\n\n  ARIEL-SST 2.0 - course edition\n')
        self.assertEqual(app.riepilogo('/non/esiste', log)['errore'], 'Error: Divergency detected in MTOW iterative loop')
        log = "Error: mission profile inputs not valid:\n- 'a' = 1 is outside\n- the supersonic cruise must be above\n\n===\n"
        self.assertEqual(app.riepilogo('/non/esiste', log)['errore'].count('\n'), 2)

    def test_file_interni_mancanti(self):
        d = tempfile.mkdtemp(); shutil.copytree(os.path.join(DATI, 'outputs', 'Layer1'), os.path.join(d, 'Layer1'))
        r = app.riepilogo(d, 'Converged in 5 iterations')
        self.assertTrue(r['ok']); self.assertIsNone(r['LD_sup']); self.assertEqual(r['MTOM'], 137794)


class Emissioni(unittest.TestCase):
    def test_foglio_segments_vero(self):
        d = tempfile.mkdtemp(); os.makedirs(os.path.join(d, 'Layer1'))
        shutil.copy2(os.path.join(DATI, 'Engine_and_emissions.xlsx'), os.path.join(d, 'Layer1'))
        e = app.emissioni(d)
        self.assertEqual(len(e['fasi']), 10)
        self.assertEqual((e['fasi'][0], e['fasi'][-1]), ('Take-off', 'Mission total'))
        r = {x['nome']: x['v'] for x in e['righe']}
        self.assertEqual(len(r), len(app.RIGHE_EM))
        self.assertTrue(all(len(v) == 10 for v in r.values()))
        self.assertAlmostEqual(r['Combustibile'][-1], 69618.6, places=1)
        self.assertAlmostEqual(r['NOx, equilibrio'][-1], 2952.37, places=2)
        self.assertAlmostEqual(r['EI NOx, P3-T3'][5], 35.98, places=2)
        self.assertEqual(r['Regime richiesto raggiunto'][8], 'No')
        self.assertIsNone(r['Spinta netta'][-1])  # nessun totale per le grandezze del motore
        self.assertAlmostEqual(r['Spinta netta'][0], 175.75, places=2)  # non il blocco dei 3 punti supersonici
        self.assertAlmostEqual(r['Tt4'][5], 1500.0, places=1)

    def test_file_mancante(self):
        self.assertIsNone(app.emissioni('/non/esiste'))
        self.assertEqual(app._xlsx(os.path.join(DATI, 'log_ok.txt'), 'Segments'), [])


def scrivi_xlsx(path, fogli):
    """xlsx minimo (solo libreria standard): {foglio: [[cella, ...], ...]}; testo come inlineStr, numeri come numeri."""
    import zipfile
    from xml.sax.saxutils import escape
    os.makedirs(os.path.dirname(path), exist_ok=True)
    col = lambda i: chr(65 + i)
    with zipfile.ZipFile(path, 'w') as z:
        z.writestr('[Content_Types].xml', '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
        sh = ''.join('<sheet name="%s" sheetId="%d" r:id="rId%d"/>' % (escape(n), i + 1, i + 1) for i, n in enumerate(fogli))
        z.writestr('xl/workbook.xml', '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                   'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>%s</sheets></workbook>' % sh)
        z.writestr('xl/_rels/workbook.xml.rels', '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">%s</Relationships>'
                   % ''.join('<Relationship Id="rId%d" Target="worksheets/sheet%d.xml"/>' % (i + 1, i + 1) for i in range(len(fogli))))
        for i, righe in enumerate(fogli.values()):
            rr = ''
            for r, riga in enumerate(righe):
                cc = ''
                for c, x in enumerate(riga):
                    ref = '%s%d' % (col(c), r + 1)
                    cc += ('<c r="%s"><v>%r</v></c>' % (ref, x)) if isinstance(x, (int, float)) else \
                          ('<c r="%s" t="inlineStr"><is><t>%s</t></is></c>' % (ref, escape(str(x))))
                rr += '<row r="%d">%s</row>' % (r + 1, cc)
            z.writestr('xl/worksheets/sheet%d.xml' % (i + 1),
                       '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>%s</sheetData></worksheet>' % rr)


TSFC_DATI = 27.48175942267465e-6  # TSFC del foglio Engine di test_dati, in kg/(N s)
ENGINE_V0 = [['Engine designed by the on-design model'], [], ['Design point: Mach [-]', 1.8], ['Design point: altitude [m]', 16000],
             ['Design point: required thrust per engine [kN]', 52.859], ['Number of engines [-]', 4],
             ['Bypass ratio BPR [-]', 0.2182], ['Overall pressure ratio OPR [-]', 17.71], ['Turbine inlet temperature Tt4 [K]', 1500],
             ['Fan diameter [m]', 1.2498], ['Air mass flow per engine [kg/s]', 94.75], ['TSFC at the design point [g/(kN·s)]', 27.98034]]


def motore_v0(d, tsfc_engine=27.98034, tsfc_mftf=2.798034e-05):
    """Cartella outputs/ con i due file del motore, numeri di v0 (10/11)."""
    eng = [r if not r or not str(r[0]).startswith('TSFC') else [r[0], tsfc_engine] for r in ENGINE_V0]
    scrivi_xlsx(os.path.join(d, 'Layer1', 'Engine_and_emissions.xlsx'), {'Segments': [['', 'Take-off']], 'Engine': eng, 'Notes': [[]]})
    scrivi_xlsx(os.path.join(d, '_work', 'Layer1', 'crn_case', '0_interface', 'mftf_engine_design.xlsx'), {
        'All Variables': [['Parameter', 'Value', 'Unit'], ['Objective 1: TSFC', tsfc_mftf, 'kg/(N.s)']],
        'Constraints': [['Constraint', 'Value', 'Lower limit', 'Upper limit', 'Status', 'Source'],
                        ['D_fan (fan tip, matched) [m]', 1.2498, '-', 1.25, 'OK', 'installation limit']],
        'Combustion Chamber': [['Parameter', 'Value', 'Unit'], ['fuel species', 'POSF10325', '-']]})
    return d


class Motore(unittest.TestCase):
    def setUp(self):
        self.out = motore_v0(tempfile.mkdtemp())

    def test_carta_del_motore(self):
        c = motore.carta(self.out)
        self.assertAlmostEqual(c['BPR'], 0.2182, 4); self.assertEqual(c['combustibile'], 'Jet A (POSF10325)')
        self.assertAlmostEqual(c['TSFC'], 2.798034e-05, 10)
        self.assertEqual((c['mach'], c['quota'], c['n_motori']), (1.8, 16000, 4))
        self.assertAlmostEqual(c['Fn_crociera'], 52.859, 3); self.assertAlmostEqual(c['fan'], 1.2498, 4)
        self.assertEqual(c['vincoli'][0]['nome'], 'D_fan (fan tip, matched) [m]'); self.assertEqual(c['vincoli'][0]['limite'], 1.25)

    def test_tsfc_coerente_tra_i_fogli(self):
        self.assertAlmostEqual(motore.tsfc_si(self.out), 2.798034e-05, 10)

    def test_tsfc_incoerente_ferma(self):
        motore_v0(self.out, tsfc_engine=279.8034)
        with self.assertRaises(ValueError):
            motore.tsfc_si(self.out)

    def test_xlsx_troncato_non_si_legge(self):
        f = os.path.join(self.out, motore.FILE_MOTORE[1])
        b = open(f, 'rb').read(); open(f, 'wb').write(b[:200])
        self.assertIsNone(motore.carta(self.out))

    def test_file_mancante(self):
        self.assertIsNone(motore.carta('/non/esiste'))


class Impronta(unittest.TestCase):
    def test_impronta_ordine_e_cifre(self):
        d = tempfile.mkdtemp(); db, exe = os.path.join(d, 'db.xlsx'), os.path.join(d, 'x.exe')
        open(db, 'wb').write(b'database'); open(exe, 'wb').write(b'exe')
        a = motore.impronta({'x': 1, 'y': 3.537e-05}, db, exe); b = motore.impronta({'y': 3.537e-05, 'x': 1}, db, exe)
        c = motore.impronta({'x': 1, 'y': 3.5370001e-05}, db, exe)
        self.assertEqual(a, b); self.assertNotEqual(a, c)
        open(db, 'wb').write(b'database 2')
        self.assertNotEqual(a, motore.impronta({'x': 1, 'y': 3.537e-05}, db, exe))


def prova_motore(pid, MTOM, Fn_to, T_eng, crn=False, fan=1.2498, tt4=1500.0):
    """Prova con emissioni come le salva il Lab (numeri di v0 dove non indicato)."""
    R = 'flight_expected_performances/range [km]'
    return {'id': pid, 'nome': pid, 'data': '', 'valori': {'payload/passenger_number [-]': 100, R: 6300, 'x': pid},
            'riepilogo': {'ok': True, 'MTOM': MTOM, 'T_eng': T_eng},
            'emissioni': {'ok': True, 'tipo': 'crn' if crn else 'semplice', 'fasi': ['Take-off', 'Cruise', 'Mission total'],
                          'righe': [{'nome': 'Spinta netta', 'v': [Fn_to, 52.86, None]}, {'nome': 'Tt4', 'v': [1412.0, tt4, None]},
                                    {'nome': 'Combustibile', 'v': [6695.0, 59367.0, 114045.0]}, {'nome': 'CO₂', 'v': [1.0, 2.0, 357809.0]}],
                          'carta': {'fan': fan, 'TSFC': 2.798e-05},
                          'lto': {'NOx_gkN': 93.0, 'NOx_limite': 83.2} if crn else None}}


class Vincoli(unittest.TestCase):
    def test_vincoli_v0(self):
        g = motore.grandezze(prova_motore('v0', 224103, 182.18, 285.8))
        self.assertAlmostEqual(g['spinta_decollo'], 0.6374, 4)
        self.assertAlmostEqual(g['co2_pkm'], 357809 / (100 * 6300), 6)
        self.assertEqual((g['fuel'], g['tt4'], g['MTOM']), (114045.0, 1500.0, 224103))
        v = motore.verifica(g, motore.VINCOLI0)
        self.assertEqual((v['spinta_decollo'], v['fan'], v['tt4']), (False, True, True))

    def test_vincolo_senza_crn(self):
        g = motore.grandezze(prova_motore('a', 200000, 300, 285.8))
        self.assertIsNone(g['nox_lto']); self.assertIsNone(motore.verifica(g, motore.VINCOLI0)['nox_lto'])
        best, testo = motore.migliore([prova_motore('a', 200000, 300, 285.8)], motore.VINCOLI0)
        self.assertEqual(best, 'a'); self.assertIn('NOx LTO', testo); self.assertIn('CRN', testo)
        g = motore.grandezze(prova_motore('c', 200000, 300, 285.8, crn=True))
        self.assertAlmostEqual(g['nox_lto'], 93 / 83.2, 6); self.assertFalse(motore.verifica(g, motore.VINCOLI0)['nox_lto'])

    def test_migliore_scarta_chi_viola(self):
        a, b = prova_motore('A', 200000, 182.18, 285.8), prova_motore('B', 224000, 300, 285.8)
        self.assertEqual(motore.migliore([a, b], motore.VINCOLI0)[0], 'B')
        self.assertEqual(motore.migliore([a], motore.VINCOLI0)[0], None)
        c = prova_motore('C', 210000, 300, 285.8)
        self.assertEqual(motore.migliore([a, b, c], motore.VINCOLI0, 'MTOM')[0], 'C')


def crn_v0(d):
    """Risultati CRN di v0 (10/11): fogli Summary e 'LTO and ICAO limits' di crn_emissions_results.xlsx."""
    nota = 'partial LTO cycle, phases missing: Descent, Taxi; totals over Take-off, Climb, Approach'
    scrivi_xlsx(os.path.join(d, motore.FILE_CRN), {
        'Summary': [['Item', 'Value'], ['LTO cycle', nota], ['F00 [kN]', 200.1791], ['pi_oo', 25.47689]],
        'LTO and ICAO limits': [['Species', 'Dp_g_selected', 'Dp_F00_selected', 'Dp_F00_baseline', 'ICAO_limit', 'ratio_selected', 'Note'],
                                ['NOx', 8656.0, 43.24136, 46.53, 97.65408, 0.44280, nota], ['CO', 772.5, 3.85922, 4.55, 162.06175, 0.02381, nota],
                                ['UHC', 101.9, 0.50896, 0.58, 16.73225, 0.03042, nota], ['SN max', '', 23.46264, 23.46, 19.57120, 1.19883, 'smoke number']]})
    return d


class LTO(unittest.TestCase):
    def test_lto_contro_icao(self):
        l = motore.lto(crn_v0(tempfile.mkdtemp()))
        self.assertAlmostEqual(l['F00_kN'], 200.1791, 4); self.assertAlmostEqual(l['OPR00'], 25.47689, 5)
        self.assertAlmostEqual(l['NOx_limite'], 36 + 2.42 * 25.47689, 3)  # limite ICAO dei motori supersonici
        self.assertAlmostEqual(l['NOx_gkN'] / l['NOx_limite'], 0.4428, 4)
        self.assertAlmostEqual(l['SN'] / l['SN_limite'], 1.1988, 4)
        self.assertIn('Descent', l['parziale'])

    def test_lto_senza_crn(self):
        self.assertIsNone(motore.lto('/non/esiste'))

    def test_grandezze_con_crn(self):
        p = prova_motore('v0', 224103, 182.18, 285.8, crn=True)
        p['emissioni']['lto'] = motore.lto(crn_v0(tempfile.mkdtemp()))
        g = motore.grandezze(p)
        self.assertAlmostEqual(g['spinta_decollo'], 200.1791 / 285.8, 4)  # con la CRN: F00 statica contro statica
        self.assertAlmostEqual(g['nox_lto'], 0.4428, 4); self.assertAlmostEqual(g['fumo'], 1.1988, 4)
        v = motore.verifica(g, motore.VINCOLI0)
        self.assertEqual((v['nox_lto'], v['fumo']), (True, False))


class Lavoro(unittest.TestCase):
    """ARIEL finto acceso una volta sola, due calcoli di fila; prove salvate; server HTTP."""
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp()
        os.makedirs(os.path.join(cls.dir, 'lavoro', 'inputs'))
        open(os.path.join(cls.dir, 'lavoro', 'inputs', 'StatDatabase.xlsx'), 'w').close()
        # il finto ARIEL copia questo mftf_engine_design.xlsx; TSFC coerente con il foglio Engine di test_dati (27.4818 g/(kN s))
        mf = motore_v0(os.path.join(cls.dir, 'fixture'), tsfc_mftf=TSFC_DATI)
        os.environ['FAKE_MFTF'] = os.path.join(mf, motore.FILE_MOTORE[1])
        cls.ariel = app.Ariel([sys.executable, '-u', os.path.join(QUI, 'fake_ariel.py'), DATI], os.path.join(cls.dir, 'lavoro'))
        cls.ariel.stabile = 0.5  # secondi in cui i file del motore non devono cambiare (exe vero: 5)
        cls.lab = app.Lab(TEMPLATE, cls.ariel, os.path.join(cls.dir, 'lavoro'), os.path.join(cls.dir, 'prove'), valori_validi())

    @classmethod
    def tearDownClass(cls):
        cls.ariel.chiudi()

    def test_1_due_calcoli_con_lo_stesso_processo(self):
        p1 = self.lab.calcola(valori_validi(), 'base', 'nota')
        self.assertTrue(p1['riepilogo']['ok'], p1)
        pid = self.ariel.proc.pid
        v = valori_validi(); v['flight_expected_performances/range [km]'] = 9500
        p2 = self.lab.calcola(v, 'lungo', '')
        self.assertFalse(p2['riepilogo']['ok'])
        self.assertEqual(self.ariel.proc.pid, pid)
        ids = [p['id'] for p in self.lab.prove()]
        self.assertEqual(ids[:2], [p2['id'], p1['id']])
        self.assertTrue(os.path.isfile(os.path.join(self.lab.dir_prove, p1['id'], 'outputs', 'Layer1', 'Matching Chart.png')))
        self.assertEqual(self.lab.prova(p2['id'])['valori']['flight_expected_performances/range [km]'], 9500)

    def test_2_input_non_valido_non_lancia(self):
        v = valori_validi(); v['flight_expected_performances/mach [-]'] = 3
        p = self.lab.calcola(v, 'mach3', '')
        self.assertFalse(p['riepilogo']['ok']); self.assertIn('mach', p['riepilogo']['errore'])

    def test_3_rinomina_riferimento_cancella(self):
        p = self.lab.calcola(valori_validi(), 'da togliere', '')
        self.lab.aggiorna(p['id'], {'nome': 'nuovo', 'nota': 'n', 'rif': True})
        q = self.lab.prova(p['id'])
        self.assertEqual((q['nome'], q['nota'], q['rif']), ('nuovo', 'n', True))
        self.assertEqual(sum(1 for x in self.lab.prove() if x['rif']), 1)
        self.lab.cancella(p['id'])
        self.assertNotIn(p['id'], [x['id'] for x in self.lab.prove()])

    def test_4_server(self):
        srv = app.server(self.lab, 0)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        base = 'http://127.0.0.1:%d' % srv.server_address[1]
        try:
            self.assertIn(b'ARIEL', urllib.request.urlopen(base + '/').read())
            st = json.loads(urllib.request.urlopen(base + '/api/stato').read())
            self.assertEqual(len(st['schema']), 37)
            req = urllib.request.Request(base + '/api/calcola', json.dumps({'valori': valori_validi(), 'nome': 'http', 'nota': ''}).encode(), {'Content-Type': 'application/json'})
            p = json.loads(urllib.request.urlopen(req).read())
            self.assertEqual(p['riepilogo']['MTOM'], 137794)
            img = urllib.request.urlopen(base + '/prove/%s/outputs/Layer1/Matching%%20Chart.png' % p['id']).read()
            self.assertEqual(img[:4], b'\x89PNG')
            with self.assertRaises(urllib.error.HTTPError):
                urllib.request.urlopen(base + '/prove/../app.py')
        finally:
            srv.shutdown()

    def _prova_ok(self):
        return self.lab.calcola(valori_validi(), 'export', 'nota export')

    def test_5_esporta(self):
        pid = self._prova_ok()['id']
        e = app.esporta(self.lab, pid)
        self.assertEqual(e['tool'], 'ARIEL-SST'); self.assertEqual(e['formato'], 1)
        self.assertEqual(e['prova'], {'id': pid, 'nome': 'export', 'data': self.lab.prova(pid)['data'], 'nota': 'nota export'})
        self.assertEqual(e['db'], 'StatDatabase.xlsx')
        self.assertIn('maximum_take-off_mass_[kg]', e['results']); self.assertIn('range', e['hl'])
        self.assertEqual(e['hl']['range'], 6000); self.assertEqual(e['hl']['H_Tail'], '1'); self.assertIn('sfc', e['hl'])
        self.assertEqual(e['hl']['subsonic_cruise_distance'], 0.1)
        self.assertIn('Take-off', e['mission'])
        self.assertEqual(e['log'], {'Fuel_f': 48.98, 'iterazioni': 33, 'converge': True})
        self.assertIsInstance(e['log']['converge'], bool)
        # quello che la vista Prova mostra oltre a results.yaml: vincoli, efficienza, T/W di progetto
        self.assertEqual(e['matching_chart']['8. T/W supersonic cruise [-]'], 0.35)
        self.assertAlmostEqual(e['efficienza']['supersonic_cruise']['E'], 6.8934, places=3)
        self.assertEqual(e['progetto'], {'TW': 0.4, 'attivo': 'Take-off = Subsonic cruise'})

    def test_6_esporta_server(self):
        pid = self._prova_ok()['id']
        srv = app.server(self.lab, 0)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            r = urllib.request.urlopen('http://127.0.0.1:%d/api/esporta/%s' % (srv.server_address[1], pid))
            self.assertEqual(r.status, 200)
            self.assertIn('application/json', r.headers['Content-Type'])
            self.assertEqual(r.headers['Content-Disposition'], 'attachment; filename="ariel_%s.json"' % pid)
            self.assertEqual(json.loads(r.read())['prova']['id'], pid)
        finally:
            srv.shutdown()

    def test_7_esporta_prova_inesistente(self):
        srv = app.server(self.lab, 0)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        base = 'http://127.0.0.1:%d' % srv.server_address[1]
        try:
            for url in ("/api/esporta/nonc-e", "/api/esporta/..%2F..%2Fapp.py"):
                with self.assertRaises(urllib.error.HTTPError) as c:
                    urllib.request.urlopen(base + url)
                self.assertEqual(c.exception.code, 404)
                self.assertIn('errore', json.loads(c.exception.read()))
        finally:
            srv.shutdown()

    def test_8_motore_ed_emissioni(self):
        p = self._prova_ok()
        t = self.lab.emissioni(p['id'])  # None se gli stessi ingressi sono gia' nell'archivio (test_10 gira prima)
        if t:
            t.join(30)
        q = self.lab.prova(p['id'])
        self.assertTrue(q['emissioni']['ok'], q['emissioni'])
        self.assertEqual(q['emissioni']['fasi'][-1], 'Mission total')
        d = os.path.join(self.lab.dir_prove, p['id'])
        self.assertTrue(os.path.isfile(os.path.join(d, 'outputs', 'Layer1', 'Engine_and_emissions.xlsx')))
        self.assertIn('Engine and emissions done', open(os.path.join(d, 'log_emissioni.txt'), encoding='utf-8').read())
        self.assertIsNone(self.lab.job)
        self.assertEqual(q['valori'], p['valori'])

    def test_9_emissioni_che_falliscono_e_blocchi(self):
        v = valori_validi(); v['payload/passenger_number [-]'] = 99
        p = self.lab.calcola(v, 'motore impossibile', '')
        self.lab.emissioni(p['id']).join(30)
        e = self.lab.prova(p['id'])['emissioni']
        self.assertFalse(e['ok']); self.assertIn('no feasible design', e['errore'])
        v = valori_validi(); v['flight_expected_performances/range [km]'] = 9500
        with self.assertRaises(ValueError):  # nessun velivolo convergente
            self.lab.emissioni(self.lab.calcola(v, 'non converge', '')['id'])
        self.lab.job = {'id': p['id'], 'inizio': 0}
        try:
            r = self.lab.calcola(valori_validi(), 'durante', '')
            self.assertIsNone(r['id']); self.assertIn('motore ed emissioni', r['riepilogo']['errore'])
            with self.assertRaises(ValueError):
                self.lab.emissioni(p['id'])
        finally:
            self.lab.job = None

    def test_10_emissioni_server(self):
        pid = self._prova_ok()['id']
        srv = app.server(self.lab, 0)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        base = 'http://127.0.0.1:%d' % srv.server_address[1]
        post = lambda u: urllib.request.urlopen(urllib.request.Request(base + u, b'{}', {'Content-Type': 'application/json'}))
        try:
            self.lab.job = {'id': pid, 'inizio': 0}
            try:
                for u in ('cancella', 'emissioni'):  # durante il calcolo: niente cancellazione, niente secondo calcolo
                    with self.assertRaises(urllib.error.HTTPError) as c:
                        post('/api/prova/%s/%s' % (pid, u))
                    self.assertEqual(c.exception.code, 400)
            finally:
                self.lab.job = None
            self.assertEqual(json.loads(post('/api/prova/%s/emissioni' % pid).read()), {'ok': True})
            for _ in range(300):
                if not self.lab.job:
                    break
                threading.Event().wait(0.1)
            st = json.loads(urllib.request.urlopen(base + '/api/stato').read())
            self.assertIsNone(st['job'])
            self.assertTrue(next(p for p in st['prove'] if p['id'] == pid)['emissioni']['ok'])
        finally:
            srv.shutdown()


    def _opz3(self):
        f = os.path.join(self.lab.dir_lavoro, 'conteggio_opz3.txt')
        return int(open(f).read()) if os.path.isfile(f) else 0

    def test_11_riuso_tra_prove_uguali(self):
        v = valori_validi(); v['crew/crew_number [-]'] = 7  # ingressi unici per questo test
        p1, p2 = self.lab.calcola(v, 'cache 1', ''), self.lab.calcola(v, 'cache 2', '')
        self.lab.emissioni(p1['id']).join(30)
        n = self._opz3()
        t = self.lab.emissioni(p2['id'])
        if t:
            t.join(30)
        self.assertEqual(self._opz3(), n)  # l'exe non e' stato lanciato
        e = self.lab.prova(p2['id'])['emissioni']
        self.assertTrue(e['ok']); self.assertEqual(e['riusato_da'], p1['id'])
        d = os.path.join(self.lab.dir_prove, p2['id'])
        self.assertTrue(os.path.isfile(os.path.join(d, 'outputs', 'Layer1', 'Engine_and_emissions.xlsx')))
        self.assertTrue(os.path.isfile(os.path.join(d, 'log_emissioni.txt')))

    def test_12_semplice_non_vale_come_crn(self):
        v = valori_validi(); v['crew/crew_number [-]'] = 8
        p = self.lab.calcola(v, 'tipo', '')
        self.lab.emissioni(p['id']).join(30)
        imp = self.lab.prova(p['id'])['emissioni']['impronta']
        f = os.path.join(self.lab.archivio, imp, 'emissioni.json')
        e = json.load(open(f, encoding='utf-8')); e['tipo'] = 'semplice'; json.dump(e, open(f, 'w', encoding='utf-8'))
        q = self.lab.calcola(v, 'tipo 2', '')
        self.assertIsNone(self.lab.dal_archivio(q['id'], 'crn'))
        self.assertEqual(self.lab.dal_archivio(q['id'], 'semplice')['riusato_da'], p['id'])


    def _crn(self, sec):
        f = os.path.join(self.lab.dir_lavoro, 'fake_crn_sec.txt')
        if sec is None:
            os.path.isfile(f) and os.remove(f)
        else:
            open(f, 'w').write(str(sec))

    def test_13_semplice_si_ferma_prima_della_crn(self):
        v = valori_validi(); v['crew/crew_number [-]'] = 9
        p = self.lab.calcola(v, 'semplice', '')
        self._crn(60)
        try:
            t0 = time.time(); self.lab.emissioni(p['id'], 'semplice').join(60)
            self.assertLess(time.time() - t0, 30)
        finally:
            self._crn(None)
        e = self.lab.prova(p['id'])['emissioni']
        self.assertTrue(e['ok'], e); self.assertEqual(e['tipo'], 'semplice')
        self.assertAlmostEqual(e['carta']['TSFC'], TSFC_DATI, 12)  # dal mftf della fixture
        d = os.path.join(self.lab.dir_prove, p['id'], 'outputs', '_work', 'Layer1', 'crn_case')
        self.assertTrue(os.path.isfile(os.path.join(d, '0_interface', 'mftf_engine_design.xlsx')))
        self.assertFalse(os.path.exists(os.path.join(d, '4_crn_emissions')))
        self.assertTrue(self.lab.calcola(valori_validi(), 'dopo', '')['riepilogo']['ok'])  # exe riavviato

    def test_14_crn_completa(self):
        v = valori_validi(); v['crew/crew_number [-]'] = 10
        p = self.lab.calcola(v, 'crn', '')
        self._crn(1)
        try:
            self.lab.emissioni(p['id'], 'crn').join(60)
        finally:
            self._crn(None)
        e = self.lab.prova(p['id'])['emissioni']
        self.assertEqual(e['tipo'], 'crn')
        self.assertTrue(os.path.isfile(os.path.join(self.lab.dir_prove, p['id'], 'outputs', '_work', 'Layer1', 'crn_case',
                                                    '4_crn_emissions', 'results', 'crn_emissions_results.xlsx')))


    def test_15_vincoli_e_motori_server(self):
        srv = app.server(self.lab, 0)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        base = 'http://127.0.0.1:%d' % srv.server_address[1]
        post = lambda u, d: urllib.request.urlopen(urllib.request.Request(base + u, json.dumps(d).encode(), {'Content-Type': 'application/json'}))
        try:
            self.assertEqual(json.loads(urllib.request.urlopen(base + '/api/vincoli').read())[0]['id'], 'spinta_decollo')
            with self.assertRaises(urllib.error.HTTPError) as c:
                post('/api/vincoli', [{'id': 'fan', 'nome': 'Fan', 'max': 'tanto'}])
            self.assertEqual(c.exception.code, 400)
            nuovi = [dict(x) for x in motore.VINCOLI0]; nuovi[2]['max'] = 1.3
            post('/api/vincoli', nuovi)
            self.assertEqual(json.loads(urllib.request.urlopen(base + '/api/vincoli').read())[2]['max'], 1.3)
            m = json.loads(urllib.request.urlopen(base + '/api/motori?criterio=MTOM').read())
            self.assertIn('migliore', m); self.assertIn('testo', m)
            self.assertTrue(all('verifica' in x and 'grandezze' in x and 'diversi' in x for x in m['candidati']))
            self.assertTrue(m['candidati'])
        finally:
            srv.shutdown()


    def test_16_f3_converge(self):
        v = valori_validi(); v['crew/crew_number [-]'] = 11
        p = self.lab.calcola(v, 'f3', '')
        self.lab.f3(p['id']).join(120)
        self.assertIsNone(self.lab.job)
        f = self.lab.prova(p['id'])['f3_esito']
        self.assertEqual(f['esito'], 'converge', f)
        self.assertAlmostEqual(f['sfc'][0], 3e-05, 12); self.assertAlmostEqual(f['sfc'][-1], TSFC_DATI, 12)
        figli = [x for x in self.lab.prove() if (x.get('f3') or {}).get('padre') == p['id']]
        self.assertEqual(len(figli), 1); self.assertEqual(figli[0]['f3']['giro'], 1)
        self.assertAlmostEqual(figli[0]['valori']['flight_expected_performances/sfc [(kg/s)/N]'], TSFC_DATI, 12)
        ids = [c['id'] for c in self.lab.motori()['candidati']]  # nel confronto solo l'ultimo giro dell'anello
        self.assertIn(figli[0]['id'], ids); self.assertNotIn(p['id'], ids)

    def test_17_f3_si_ferma_se_il_motore_fallisce(self):
        v = valori_validi(); v['payload/passenger_number [-]'] = 99; v['crew/crew_number [-]'] = 12
        p = self.lab.calcola(v, 'f3 ko', '')
        self.lab.f3(p['id']).join(120)
        self.assertIsNone(self.lab.job)
        f = self.lab.prova(p['id'])['f3_esito']
        self.assertTrue(f['esito'].startswith('fermato'), f); self.assertIn('no feasible design', f['esito'])

    def test_18_cancella_durante_f3(self):
        v = valori_validi(); v['crew/crew_number [-]'] = 13
        p = self.lab.calcola(v, 'f3 cancellata', '')
        t = self.lab.f3(p['id'])
        self.lab.cancella(p['id'])
        t.join(120)
        self.assertIsNone(self.lab.job)


if __name__ == '__main__':
    unittest.main()


class Prepara(unittest.TestCase):
    def test_su_un_altro_pc_usa_gli_input_iniziali(self):
        d = tempfile.mkdtemp()
        try:
            lav = os.path.join(d, 'lavoro')
            os.makedirs(lav)
            open(os.path.join(lav, 'ARIEL-SST.exe'), 'w').close()
            ini = os.path.join(d, 'inputs_iniziali')
            os.makedirs(ini)
            shutil.copy2(os.path.join(DATI, 'HLInputs_vecchio.yaml'), os.path.join(ini, 'HLInputs.yaml'))
            open(os.path.join(ini, 'StatDatabase.xlsx'), 'w').close()
            vecchi = (app.LAVORO, app.CORSO_INPUTS, app.INIZIALI)
            app.LAVORO, app.CORSO_INPUTS, app.INIZIALI = lav, os.path.join(d, 'non_esiste'), ini
            try:
                app.prepara()
                for f in ('HLInputs.yaml', 'StatDatabase.xlsx'):
                    self.assertTrue(os.path.isfile(os.path.join(lav, 'inputs', f)), f)
                os.remove(os.path.join(lav, 'inputs', 'StatDatabase.xlsx'))
                os.remove(os.path.join(ini, 'StatDatabase.xlsx'))
                with self.assertRaises(SystemExit):
                    app.prepara()
            finally:
                app.LAVORO, app.CORSO_INPUTS, app.INIZIALI = vecchi
        finally:
            shutil.rmtree(d)
