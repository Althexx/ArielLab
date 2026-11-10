# Scheda «Motore ed emissioni» v2 · design (10/11/2026)

## Perché
Alex (PM, Team 3, Topic 3: Mach 1,8, 100 passeggeri) deve scegliere **il motore adatto al velivolo**, con un criterio che un esperto del corso approverebbe: TSFC basso, emissioni basse e vincoli rispettati.

Il motore lo progetta l'exe del corso con l'opzione 3: un turbofan a flussi miscelati, ottimizzato in crociera supersonica, più Cantera per le emissioni. ARIEL Lab ha già una scheda «Motore ed emissioni», che però:
- mostra **un motore alla volta**, solo come tabella del foglio Segments;
- non confronta più motori, non controlla vincoli e non indica un migliore;
- usa ogni volta l'opzione 3 completa, che dura oltre 1 h per via della CRN.

Su v0 (10/11) i dati veri hanno mostrato:
- TSFC in crociera 2,80·10⁻⁵ contro i 3,54·10⁻⁵ dati in ingresso;
- spinta al decollo disponibile 182 kN contro 286 richiesti.

Servono quindi due cose: un **confronto tra candidati** e l'**anello F3**, cioè TSFC vero → input sfc → nuovo velivolo.

## Obiettivi
1. **Profilo completo di un candidato** (vista «A»):
   - verdetto;
   - carta d'identità del motore (foglio Engine e `mftf_engine_design.xlsx`);
   - tabella per fase (Segments);
   - emissioni;
   - LTO contro limiti ICAO, solo se c'è la CRN;
   - storia dell'anello F3.
2. **Confronto tra candidati** (vista «B»): colonne affiancate, ✅/❌ per ogni vincolo, il **migliore** evidenziato.
3. **Vincoli impostati da Alex sulla pagina.** Il confronto si ricalcola subito, senza lanciare l'exe.
4. **Due livelli di calcolo:**
   - **semplice** (circa 13 min): l'opzione 3 viene fermata dopo la parte del motore, quindi senza CRN;
   - **CRN** (oltre 1 h): l'opzione 3 completa, con un pulsante, solo sui finalisti.
5. **Niente calcoli ripetuti:** a ingressi uguali si riusa il risultato salvato.
6. **Anello F3:**
   - si parte da una prova e si mette sfc = TSFC di progetto del motore;
   - si ricalcola il velivolo (opzione 2) e poi si fa l'analisi semplice;
   - si ripete finché la sfc cambia meno dell'1 %, con al massimo 5 giri;
   - ogni giro è una prova nuova.
   - **Criterio di «finito» deciso da Alex:** un anello F3 reale che converge su v1, e i test che passano.

## Non obiettivi
- Non si modifica l'exe del corso né i suoi file di ingresso oltre a `HLInputs.yaml`. Combustibile e limiti del motore (fan ≤ 1,25 m, Tt4) per ora non si cambiano: c'è una domanda aperta ai docenti.
- Non si scrive nel Registro parametri in automatico: il risultato finale si importa con il pulsante già esistente.
- Niente ottimizzazione automatica che genera candidati: i candidati sono prove create da Alex.

## Anti-obiettivi (sarebbe un fallimento anche se funziona)
- Un «migliore» scelto con un criterio nascosto: il criterio deve essere scritto sulla pagina.
- Un risultato riusato dalla cache con ingressi in realtà diversi.
- Bloccare ARIEL Lab o perdere prove se l'exe viene fermato a metà.
- Mostrare come verificato il limite ICAO quando la CRN non è stata fatta.

## Vincoli tecnici
- **Codice:** ARIEL Lab, quindi `app.py` (Python, sola libreria standard), `index.html` e `test_app.py` (unittest con `fake_ariel.py`). Ramo `esporta-control-room`.
- **Exe:** è comandato da stdin, con il menu 1–4, e **non ha un'opzione «senza CRN»**.
- **Analisi semplice:** l'exe va fermato quando sono comparsi e completi `outputs/Layer1/Engine_and_emissions.xlsx` e `outputs/_work/Layer1/crn_case/0_interface/mftf_engine_design.xlsx`. Si chiude il processo e lo si riavvia, come già fa `Ariel.chiudi()`.
  - Va verificato sulla CRN di v0 che, finendo, non riscriva `Engine_and_emissions.xlsx` con righe in più.
  - Se crea problemi, la modalità semplice si disattiva (decisione di Alex).
- **Una sola opzione 3 alla volta** (`Lab.job`): durante il calcolo gli altri calcoli restano bloccati, come oggi.
- **Testi** in italiano, brevi, con il verdetto per primo. La pagina non deve allargarsi oltre lo schermo del telefono.

## Decisioni prese (da Alex)
- Entrambe le viste, A e B: confronto di più motori più il profilo completo di ognuno.
- Prima l'analisi semplice, la CRN dopo e solo sui finalisti. Fermare l'exe è una prova: si disattiva se crea problemi.
- Dati salvati in modo da non rifare un calcolo con gli stessi parametri.
- Vincoli e limiti decisi da Alex sulla pagina.
- **Un candidato è un velivolo con il suo motore** (decisione del 10/11). L'exe deriva il motore dal velivolo, cioè da punto e spinta di crociera, con combustibile e limiti fissi. I candidati differiscono quindi per gli input del velivolo: numero di motori, quote e Mach, range e così via. Il confronto mostra anche **quali input differiscono** tra i candidati. Pista e CL di decollo cambiano solo la spinta richiesta, non il motore. Quando si saprà cambiare combustibile e limiti, diventeranno altri candidati.

## Decisioni mie (da controllare)
1. **Impronta della cache:** sha256 di `HLInputs.yaml` normalizzato (le chiavi in ordine), più i byte di `StatDatabase.xlsx` e la dimensione dell'exe. Il tipo (semplice/CRN) è salvato a parte. Un risultato CRN vale anche come semplice, non il contrario.
2. **TSFC usato nell'anello F3:** il TSFC del punto di progetto, cioè la crociera supersonica (foglio Engine, riga «TSFC at the design point»), convertito in kg/(N·s). La crociera supersonica è il 94 % della rotta, e ARIEL accetta una sola sfc.
3. **Spinta al decollo, in v1 prudente:** si confrontano direttamente la Fn del segmento Take-off (Segments) e la `T/engines_[N]` di `results.yaml`, che è statica al livello del mare. Si mostrano entrambi i numeri. La correzione con il lapse di Mattingly alla condizione di decollo si rimanda.
4. **Vincoli di partenza**, modificabili, salvati in `lavoro/vincoli.json`:
   - spinta al decollo disponibile/richiesta ≥ 1,0;
   - NOx LTO ≤ limite ICAO, cioè 36 + 2,42·OPR. È verificabile solo con la CRN, altrimenti compare «—, serve la CRN»;
   - diametro del fan ≤ 1,25 m;
   - Tt4 massimo ≤ 1500 K.
5. **Il migliore:** tra i candidati che rispettano tutti i vincoli verificabili, quello con il minimo della grandezza scelta in un menu: MTOM (default), combustibile di missione, CO₂ per volo o TSFC di crociera.
6. **Grandezze calcolate dalla pagina:**
   - margine di spinta al decollo;
   - NOx LTO/limite (solo con la CRN);
   - CO₂ per passeggero·km = CO₂ totale / (passeggeri × range);
   - combustibile di missione (riga «Segment fuel», ultima colonna).

7. **Anello F3 nel confronto:** i giri sono raggruppati sotto la prova di partenza (`f3: {padre, giro}` in `prova.json`). Nel confronto compare solo l'ultimo giro; gli altri restano visibili nella storia F3 del profilo.
8. **Anello che non converge:** dopo 5 giri si ferma e lo dice («non converge: sfc …→…»). Non conta come «finito».
9. **Unità del TSFC:** si legge il valore già in kg/(N·s) da `mftf_engine_design.xlsx`, foglio All Variables, riga «Objective 1: TSFC» (v0: 2,798·10⁻⁵). Come controllo, deve coincidere con il foglio Engine [g/(kN·s)] × 10⁻⁶ entro lo 0,1 %; altrimenti l'anello si ferma con un errore.
10. **Cache condivisa:** un archivio indicizzato per impronta. Una prova con ingressi identici a una già calcolata riceve una copia del risultato, senza lanciare l'exe, e la pagina scrive «riusato da <prova>».
11. **v1:** è la prova che nasce da v0 con le decisioni del team, cioè crociera subsonica ottimizzata e ingressi aggiornati. Su v1 si fa l'anello F3 di accettazione.
12. **CRN di v0:** il job in corso copia gli output nella cartella della prova quando finisce. Le celle NOx/OPR della CRN si esplorano lì, senza rilanciarla.

## Lasciato a chi costruisce
- Il formato preciso delle schede e dei grafici: si riusa lo stile di `index.html`. Con la CRN il grafico LTO è il PNG `04_LTO_vs_ICAO_limits.png`, già prodotto dall'exe.
- Come rilevare che i due xlsx sono «completi»: per esempio un file presente e stabile per qualche secondo, e leggibile con `_xlsx`.
- Dove leggere i NOx LTO (Dp/F00) e l'OPR al decollo nei risultati della CRN, cioè `crn_emissions_results.xlsx`, da esplorare sul file vero di v0.
- Nomi delle rotte API e struttura di `prova.json['emissioni']`, mantenendo compatibili le prove già salvate.
