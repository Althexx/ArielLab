"""Test della dashboard ARIEL: python -m unittest ariel_dashboard/test_app.py (dalla cartella del progetto)."""
import json, os, shutil, sys, tempfile, threading, unittest, urllib.request
import yaml

QUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, QUI)
import app

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


class Lavoro(unittest.TestCase):
    """ARIEL finto acceso una volta sola, due calcoli di fila; prove salvate; server HTTP."""
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp()
        os.makedirs(os.path.join(cls.dir, 'lavoro', 'inputs'))
        open(os.path.join(cls.dir, 'lavoro', 'inputs', 'StatDatabase.xlsx'), 'w').close()
        cls.ariel = app.Ariel([sys.executable, '-u', os.path.join(QUI, 'fake_ariel.py'), DATI], os.path.join(cls.dir, 'lavoro'))
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
        self.lab.emissioni(p['id']).join(30)
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
