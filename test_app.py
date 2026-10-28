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


class Lavoro(unittest.TestCase):
    """ARIEL finto acceso una volta sola, due calcoli di fila; prove salvate; server HTTP."""
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp()
        os.makedirs(os.path.join(cls.dir, 'lavoro', 'inputs'))
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


if __name__ == '__main__':
    unittest.main()
