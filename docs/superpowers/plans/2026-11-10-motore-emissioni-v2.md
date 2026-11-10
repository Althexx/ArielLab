# Scheda «Motore ed emissioni» v2 · Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** In ARIEL Lab, confrontare velivoli candidati con il loro motore (opzione 3), con vincoli impostati da Alex, il migliore evidenziato, un'analisi semplice senza CRN, una cache per ingressi uguali e l'anello F3 (TSFC → sfc).

**Architecture:** La logica pura sta in un modulo nuovo, `motore.py`: lettura dei file del motore, impronta, vincoli e migliore. Si testa senza exe. `app.py` aggiunge a `Lab` quattro cose: fermare l'exe dopo il motore, l'archivio della cache, l'anello F3 in un thread, le rotte API. `index.html` riscrive la scheda «Motore ed emissioni» con le viste A (profilo) e B (confronto).

**Tech Stack:** Python 3 con la sola libreria standard più PyYAML (già usato); unittest; HTML/JS senza librerie.

**Spec:** `docs/superpowers/specs/2026-11-10-motore-emissioni-design.md`

## Global Constraints
- **Librerie:** solo libreria standard più PyYAML. Gli xlsx si leggono con `app._xlsx` (zipfile ed ElementTree).
- **Exe:** è l'exe del corso, menu 1–4, comandato da stdin. Non si modifica.
- **Concorrenza:** una sola opzione 3 alla volta (`Lab.job`). Durante il job, gli altri calcoli e la cancellazione di quella prova sono bloccati.
- **Compatibilità:** le prove già salvate restano leggibili. `prova.json['emissioni']` vecchio, senza `tipo`, vale come `tipo: 'crn'`.
- **Testi** in italiano, brevi, verdetto per primo. Nessuno scroll orizzontale della pagina su telefono.
- **Repository pubblico:** in `test_dati/` non vanno file del velivolo del team. Le fixture xlsx nuove si generano nel test.
- **Test:** `python -m unittest test_app` dentro `ARIEL Lab/`. Tutti verdi a ogni commit.

## Review Focus
1. **Exe fermato mentre scrive un xlsx.** Se il file è letto a metà deve risultare «file incompleto, riprova», senza mai salvare dati parziali. Test: `test_xlsx_troncato_non_si_legge` (Task 1).
2. **Cache con ingressi quasi uguali.** Un valore diverso alla 6ª cifra (3,537e-05 contro 3,5370001e-05) deve dare un'impronta diversa; l'ordine diverso delle chiavi, la stessa. Test: `test_impronta_ordine_e_cifre` (Task 2).
3. **Anello F3 senza motore:** l'opzione 3 fallisce, cioè «no feasible design». L'anello si ferma con un messaggio, `job` torna `None` e le prove dei giri restano. Test: `test_f3_si_ferma_se_il_motore_fallisce` (Task 5).
4. **Vincolo non verificabile** (NOx LTO senza CRN): mai ✅, sempre «—». Un candidato con un vincolo «—» può essere il migliore, ma la pagina lo dice. Test: `test_vincolo_senza_crn` (Task 4).
5. **Prova cancellata durante l'anello F3 o la CRN:** niente eccezioni nel thread, `job` torna `None`. Test: `test_cancella_durante_f3` (Task 5).

---

### Task 1: Lettura del motore (`motore.py`)

**Files:**
- Create: `motore.py`
- Modify: `test_app.py` (classe nuova `Motore`, più l'helper `scrivi_xlsx`)

**Interfaces:**
- Consumes: `app._xlsx(path, foglio) -> list[list[str]]`, che restituisce `[]` se il file non si legge. *Va spostata in `motore.py` e `app.py` la importa da lì, per evitare l'import circolare.*
- Produces:
  - `motore.carta(dir_out) -> dict | None`: chiavi `BPR, OPR, Tt4, fan, portata, TSFC, Fn_crociera, mach, quota, n_motori, combustibile, vincoli` (lista di `{nome, valore, limite, stato}`). `None` se manca un file o se un file è incompleto;
  - `motore.tsfc_si(dir_out) -> float`: kg/(N·s), dal foglio All Variables di `mftf_engine_design.xlsx`, riga `Objective 1: TSFC`. Solleva `ValueError` se differisce dal foglio Engine [g/(kN·s)] × 1e-6 per più dello 0,1 %;
  - `motore.segmenti(dir_out)`: è l'attuale `app.emissioni`, spostata qui;
  - `motore.FILE_MOTORE = ('Layer1/Engine_and_emissions.xlsx', '_work/Layer1/crn_case/0_interface/mftf_engine_design.xlsx')`.

- [ ] **Step 1: Test che falliscono.** `scrivi_xlsx(path, {foglio: [[...], ...]})` scrive un xlsx minimo (sharedStrings vuoto, celle `inlineStr` e numeriche). Le fixture usano i numeri veri di v0, che sono numeri e non file del team:
  - Engine: `Design point: Mach [-]` 1.8, `altitude [m]` 16000, `required thrust per engine [kN]` 52.859, `Bypass ratio BPR [-]` 0.2182, `Overall pressure ratio OPR [-]` 17.71, `Turbine inlet temperature Tt4 [K]` 1500, `Fan diameter [m]` 1.2498, `TSFC at the design point [g/(kN·s)]` 27.98034;
  - All Variables: `Objective 1: TSFC` 2.798034e-05;
  - Constraints: `D_fan (fan tip, matched) [m]` con limite superiore 1.25, stato OK;
  - Combustion Chamber: `fuel species` POSF10325.

```python
def test_carta_del_motore(self):
    c = motore.carta(self.out)
    self.assertAlmostEqual(c['BPR'], 0.2182, 4); self.assertEqual(c['combustibile'], 'Jet A (POSF10325)')
    self.assertAlmostEqual(c['TSFC'], 2.798034e-05, 10)
def test_tsfc_coerente_tra_i_fogli(self):
    self.assertAlmostEqual(motore.tsfc_si(self.out), 2.798034e-05, 10)
def test_tsfc_incoerente_ferma(self):   # Engine con 279.8 (fattore 10) -> ValueError
def test_xlsx_troncato_non_si_legge(self):  # primi 200 byte del file -> carta() is None
```

- [ ] **Step 2:** Run `python -m unittest test_app.Motore -v`. Expected: FAIL `No module named 'motore'`.
- [ ] **Step 3: Implementare `motore.py`.** Spostare `_xlsx`, `RIGHE_EM` ed `emissioni` (rinominata `segmenti`), e lasciare in `app.py` l'alias `emissioni = motore.segmenti` per i test esistenti. Il combustibile si mappa con `{'POSF10325': 'Jet A', 'POSF11498': 'ATJ'}`, e i codici sconosciuti si mostrano così come sono.
- [ ] **Step 4:** Run `python -m unittest test_app -v`. Expected: tutti PASS, compresi `Emissioni` e `test_8`–`test_10`.
- [ ] **Step 5: Commit** `git commit -m "Motore: carta d'identità e TSFC dai file dell'opzione 3"`

### Task 2: Impronta e archivio (cache)

**Files:** Modify `motore.py`, `app.py` (`Lab`), `test_app.py`

**Interfaces:**
- Produces:
  - `motore.impronta(valori: dict, db_path: str, exe_path: str) -> str`: sha256 di `json.dumps(valori, sort_keys=True)`, più i byte del database, più la dimensione dell'exe;
  - `Lab.archivio = os.path.join(dir_lavoro, 'archivio')`. Ogni voce è `archivio/<impronta>/` e contiene `emissioni.json` e la copia di `outputs/Layer1` e `outputs/_work/Layer1/crn_case`;
  - `Lab.dal_archivio(pid, tipo) -> dict | None`: se c'è una voce con la stessa impronta e un tipo sufficiente (CRN ⊇ semplice), la copia nella prova e restituisce `emissioni` con `riusato_da`.

- [ ] **Step 1: Test che falliscono.**

```python
def test_impronta_ordine_e_cifre(self):
    a = motore.impronta({'x': 1, 'y': 3.537e-05}, DB, EXE); b = motore.impronta({'y': 3.537e-05, 'x': 1}, DB, EXE)
    c = motore.impronta({'x': 1, 'y': 3.5370001e-05}, DB, EXE)
    self.assertEqual(a, b); self.assertNotEqual(a, c)
def test_riuso_tra_prove_uguali(self):   # Lavoro: due prove con gli stessi valori; emissioni sulla prima;
    # sulla seconda lab.emissioni(..., 'semplice') non lancia l'exe (contatore di fake_ariel invariato)
    # e prova.json['emissioni']['riusato_da'] == id della prima
def test_semplice_non_vale_come_crn(self):
```

- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3: Implementare.** `fake_ariel.py` scrive in `outputs/conteggio_opz3.txt` quante volte ha eseguito l'opzione 3, così il test può leggerlo.
- [ ] **Step 4:** Run tutti i test. Expected: PASS.
- [ ] **Step 5: Commit** `"Motore: impronta degli ingressi e archivio per non ricalcolare"`

### Task 3: Analisi semplice (exe fermato prima della CRN)

**Files:** Modify `app.py` (`Ariel`, `Lab.emissioni`, `Lab._emissioni`), `fake_ariel.py`, `test_app.py`

**Interfaces:**
- Produces:
  - `Ariel.calcola_fino_a(file: list[str], sec: int, opzione=b'3') -> str`: manda l'opzione e attende che tutti i file esistano, abbiano dimensione stabile per 5 s e si leggano con `_xlsx`. Poi chiama `self.chiudi()` (kill) e restituisce il log. Se il timeout scade, si comporta come `calcola`;
  - `Lab.emissioni(pid, tipo='semplice'|'crn', sec=6*3600)`, con default `'semplice'`;
  - `prova.json['emissioni']` guadagna `tipo`, `impronta` e `carta` (Task 1).
- **`fake_ariel.py`, opzione 3:** copia i due xlsx; se la variabile d'ambiente `FAKE_CRN_SEC` è impostata, «fa la CRN» (sleep), scrive `crn_emissions_results.xlsx` e solo dopo torna al menu.

- [ ] **Step 1: Test che falliscono.**

```python
def test_semplice_si_ferma_prima_della_crn(self):   # FAKE_CRN_SEC=60: emissioni(pid,'semplice') finisce in < 20 s,
    # e['tipo']=='semplice', manca crn_emissions_results.xlsx, poi un calcolo opzione 2 funziona (exe riavviato)
def test_crn_completa(self):   # FAKE_CRN_SEC=1: tipo 'crn' e il file CRN c'è
```

- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3: Implementare.** In `_emissioni`, a fine calcolo, si salva nell'archivio (Task 2).
- [ ] **Step 4:** Run tutti i test. Expected: PASS.
- [ ] **Step 5: Commit** `"Motore: analisi semplice senza CRN"`
- [ ] **Step 6: Prova vera (da fare a mano, una volta).** Sulla prova v0 la CRN completa è già nella cartella della prova. Lanciare `semplice` su una copia di v0 e confrontare il foglio Segments con quello della CRN: devono essere identici. Se non lo sono, scriverlo in `Decisioni/Da_rivedere.md` e mettere `'crn'` come default (decisione di Alex: «se fa casini lo disattiviamo»).

### Task 4: Vincoli, grandezze calcolate e migliore

**Files:** Modify `motore.py`, `app.py` (rotte), `test_app.py`

**Interfaces:**
- Produces:
  - `motore.VINCOLI0 = [{'id':'spinta_decollo','nome':'Spinta al decollo disponibile / richiesta','min':1.0}, {'id':'nox_lto','nome':'NOx LTO / limite ICAO','max':1.0}, {'id':'fan','nome':'Diametro del fan [m]','max':1.25}, {'id':'tt4','nome':'Tt4 massimo [K]','max':1500}]`;
  - `motore.grandezze(prova: dict) -> dict`: `spinta_decollo` = Fn del segmento Take-off / (`T_eng` del riepilogo); `nox_lto` = None senza CRN; `fan`; `tt4` = massimo della riga Tt4; `co2_pkm` = CO₂ totale / (passeggeri × range); `fuel` = ultima colonna di «Segment fuel»; `MTOM`; `TSFC`;
  - `motore.verifica(gr, vincoli) -> dict[id, True | False | None]`;
  - `motore.migliore(prove, vincoli, criterio='MTOM') -> (id | None, testo)`: tra i candidati senza `False`, il minimo del criterio. Il testo spiega, per esempio: «minimo MTOM tra 3 candidati che rispettano i vincoli; NOx LTO non verificato (serve la CRN)»;
  - **rotte:** `GET /api/vincoli` (default se `lavoro/vincoli.json` manca) e `POST /api/vincoli` per salvarli, con controllo: `min` e `max` numerici;
  - `GET /api/motori` → `[{id, nome, data, emissioni.tipo, grandezze, verifica, diversi}]` più `{migliore, testo}`. `diversi` = gli input che differiscono dal primo candidato.

- [ ] **Step 1: Test che falliscono.**

```python
def test_vincoli_v0(self):   # grandezze con Fn decollo 182.18, T_eng 285.8 -> spinta 0.637 -> False; fan 1.2498 -> True
def test_vincolo_senza_crn(self):   # verifica['nox_lto'] is None; migliore lo dichiara nel testo
def test_migliore_scarta_chi_viola(self):   # A (MTOM 200 t, spinta False) e B (224 t, ok) -> migliore B
def test_vincoli_server(self):   # POST con max non numerico -> 400; GET dopo POST -> valori salvati
```

- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3: Implementare.**
- [ ] **Step 4:** Run tutti i test. Expected: PASS.
- [ ] **Step 5: Commit** `"Motore: vincoli, grandezze e candidato migliore"`

### Task 5: Anello F3

**Files:** Modify `app.py` (`Lab.f3`, `Lab._f3`, rotta), `test_app.py`

**Interfaces:**
- Consumes: `motore.tsfc_si`, `Lab.calcola`, `Lab.emissioni` (tipo `'semplice'`, chiamata sincrona interna: va estratta come `Lab._motore(pid, tipo)`).
- Produces:
  - `Lab.f3(pid, giri=5, tol=0.01)`: in un thread, `job = {'id', 'inizio', 'f3': {'giro', 'sfc'}}`;
  - ogni giro: sfc ← `tsfc_si`; poi `calcola(valori, nome='<nome> F3-<k>')`, con `prova['f3'] = {'padre': pid0, 'giro': k, 'sfc': [...]}`; poi `_motore(nuovo, 'semplice')`;
  - stop quando |Δsfc|/sfc < tol (`f3['esito'] = 'converge'`), oppure dopo i giri (`'non converge'`), oppure se il velivolo o il motore falliscono (`'fermato: <errore>'`). L'esito si scrive nella prova di partenza: `prova['f3_esito']`;
  - **rotta:** `POST /api/prova/<id>/f3`.

- [ ] **Step 1: Test che falliscono** (con `fake_ariel`: il TSFC del file è fisso, quindi l'anello converge al giro 2).

```python
def test_f3_converge(self):   # giro 1: sfc 3.537e-05 -> 2.798034e-05; giro 2 invariata -> 'converge', 2 prove figlie
def test_f3_si_ferma_se_il_motore_fallisce(self):   # passenger_number 99 -> esito 'fermato: ...', job None
def test_cancella_durante_f3(self):   # cancella la prova padre a meta' -> nessuna eccezione, job None
```

- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3: Implementare.**
- [ ] **Step 4:** Run tutti i test. Expected: PASS.
- [ ] **Step 5: Commit** `"Motore: anello F3 (TSFC del motore -> sfc)"`

### Task 6: Risultati della CRN (LTO contro ICAO)

**Files:** Modify `motore.py`, `test_app.py`

**Interfaces:**
- Produces `motore.lto(dir_out) -> dict | None`: `{'OPR00', 'F00_kN', 'NOx_gkN', 'NOx_limite', 'CO_gkN', 'CO_limite', 'HC_gkN', 'HC_limite', 'grafico': '<percorso relativo di 04_LTO_vs_ICAO_limits.png>'}`. I limiti si calcolano: NOx `36 + 2.42*OPR00`, CO `4550*OPR00**-1.03`, HC `140*0.92**OPR00`. `grandezze()['nox_lto']` = NOx_gkN / NOx_limite.

- [ ] **Step 1: Esplorare** `prove/2026-11-10_130424_v0-registro-37-input/outputs/_work/Layer1/crn_case/4_crn_emissions/results/crn_emissions_results.xlsx`, che esiste quando la CRN di v0 finisce. Annotare in `motore.py` i nomi dei fogli e delle righe di Dp/F00 e di π00.
- [ ] **Step 2: Test che fallisce**, con una fixture generata (`scrivi_xlsx`) con quei nomi di righe e i valori letti su v0: `test_lto_contro_icao` controlla il rapporto NOx/limite e che il limite NOx sia 36 + 2,42·π00.
- [ ] **Step 3: Implementare.** **Step 4:** tutti i test PASS. **Step 5: Commit** `"Motore: verifica LTO contro i limiti ICAO dalla CRN"`

### Task 7: Pagina (viste A e B)

**Files:** Modify `index.html` (sezione «motore ed emissioni», righe 230–255 circa), `test_app.py` (`test_4_server`: la pagina contiene `id="vincoli"` e `id="confronto"`)

**Interfaces:** Consumes `GET /api/motori`, `GET/POST /api/vincoli`, `POST /api/prova/<id>/emissioni {tipo}`, `POST /api/prova/<id>/f3`, `GET /prove/...png`.

- [ ] **Step 1: Test che fallisce** (`test_4_server`, le due id nella pagina). Run: FAIL.
- [ ] **Step 2: Vista B (in alto).**
  - **Editor dei vincoli:** una riga per vincolo, con min/max modificabili, salvati con POST.
  - **Menu del criterio:** MTOM, combustibile, CO₂/pkm, TSFC.
  - **Tabella:** una colonna per candidato, con ✅/❌/«—» per vincolo e il migliore evidenziato (★, sfondo verde). Il testo del criterio sta sotto la tabella. In fondo, la riga «input diversi».
  - Sui telefoni la tabella scorre dentro un contenitore, non la pagina.
- [ ] **Step 3: Vista A (clic su una colonna).**
  - **Verdetto in 3 righe:** TSFC contro sfc data, spinta al decollo, NOx LTO.
  - **Carta d'identità** del motore.
  - **Tabella Segments**, quella esistente.
  - **Grafico LTO**, se c'è la CRN.
  - **Storia F3:** sfc per giro ed esito.
  - **Pulsanti:** «Analisi semplice (~13 min)», «CRN (oltre 1 h)», «Anello F3». Sono disabilitati durante un job, e si mostra «riusato da …» quando vale.
- [ ] **Step 4: Verifica nel browser.** Avviare ARIEL Lab e aprire la scheda: le viste mostrano v0, con i numeri di Task 4. Controllare la larghezza di 375 px.
- [ ] **Step 5:** tutti i test PASS. **Commit** `"Scheda Motore ed emissioni v2: confronto, vincoli, profilo"`

### Task 8: Pulizia e documentazione
**Files:** `.gitignore` (aggiungere `.superpowers/`), `README.md` (sezione «Motore ed emissioni»), il CLAUDE.md del corso (paragrafo ARIEL Lab: scheda v2, archivio, numero di test).
- [ ] Aggiornare i file, eseguire tutti i test, **Commit** `"Documentazione della scheda Motore ed emissioni v2"`.
- [ ] **Accettazione (criterio di Alex):** su **v1** (v0 più decisioni del team e crociera subsonica ottimizzata), lanciare «Anello F3» con l'exe vero. Deve convergere (|Δsfc| < 1 %) in 5 giri o meno, con i test verdi. Scrivere l'esito in `Registro parametri/Decisioni/Da_rivedere.md`.
