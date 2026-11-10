# ARIEL Lab

Dashboard locale per ARIEL-SST (Team 3, Topic 3 IASD). Si cambiano gli input dal browser, si lancia ARIEL e si confrontano le prove salvate.
Serve la release di ARIEL-SST del 27/10/2026, quella del corso. **L'eseguibile non è in questo repository**: si prende dal pacchetto del corso.

## Cosa serve sul PC
1. Windows 10 o 11.
2. Python 3.8 o più recente ([python.org](https://www.python.org)). Durante l'installazione spunta "Add python.exe to PATH".
3. PyYAML. Apri il Prompt dei comandi e scrivi:
   ```
   pip install pyyaml
   ```
4. `ARIEL-SST.exe` della release del 27/10, dalla cartella `windows` del pacchetto del corso.

## Installazione (una volta sola)
1. Scarica il repository: pulsante verde **Code → Download ZIP**, poi estrai lo zip. Oppure usa `git clone`.
2. Nella cartella crea la sottocartella `lavoro`, se non c'è, e copiaci dentro `ARIEL-SST.exe`.
3. Copia in `inputs_iniziali` i file `HLInputs.yaml` e `StatDatabase.xlsx`. Li trovi nello zip `ARIEL_Lab` condiviso in privato dal team. **Non sono in questo repository pubblico.**

## Uso
- Fai doppio clic su **Avvia dashboard.bat**. Il browser si apre su http://127.0.0.1:8790; se la porta è occupata, usa 8791, 8792 e così via.
- La finestra nera deve restare aperta: se la chiudi, la dashboard si ferma.
- Al primo avvio la dashboard copia in `lavoro\inputs` gli input di partenza da `inputs_iniziali`. Sono gli input del pacchetto del corso, non modificati, e il database statistico del team.
- Il primo calcolo dura circa 20 s in più, perché ARIEL si avvia; poi 5–15 s per calcolo. Ogni calcolo viene salvato in `prove`.
- Al primo avvio Windows può bloccare ARIEL-SST.exe con "Windows ha protetto il PC": clicca "Ulteriori informazioni" e poi "Esegui comunque".
- **Motore ed emissioni.** La scheda ha due parti.
  - **Confronto dei motori**, in alto. Ogni colonna è una prova con il motore calcolato, cioè un velivolo con il suo motore.
    - Per ogni vincolo la pagina mostra ✅, ❌ oppure «—» se il dato non è verificabile. I vincoli sono: spinta al decollo, NOx e fumo LTO contro i limiti ICAO, diametro del fan, Tt4.
    - Il **migliore** è evidenziato: tra i candidati che rispettano i vincoli, ha il valore più basso della grandezza scelta (MTOM, combustibile, CO₂ per passeggero·km o TSFC).
    - I vincoli si cambiano in «Vincoli» e restano salvati in `lavoro\vincoli.json`.
  - **Profilo del motore**, in basso, per la prova scelta:
    - verdetto, carta d'identità del motore e tabella per fase;
    - con la CRN, anche il ciclo LTO contro i limiti ICAO.
  - **Tre pulsanti:**
    - **Analisi semplice**, circa 15 min: lancia l'opzione 3 e ferma l'exe appena il motore è progettato, senza la rete di reattori (CRN).
    - **Con CRN**, oltre un'ora: opzione 3 completa.
    - **Anello F3**: mette sfc = TSFC del motore, ricalcola il velivolo e il motore, e ripete finché la sfc cambia meno dell'1 % (al massimo 5 giri). Ogni giro diventa una prova nuova. Nel confronto compare solo l'ultimo giro.
  - **Niente calcoli doppi:** i risultati vanno in `lavoro\archivio\`, sotto un'impronta degli ingressi (input, database ed exe). Una prova con ingressi identici li riusa senza lanciare l'exe.
  - Durante un calcolo non si possono fare altri calcoli. Non chiudere la finestra nera e non sospendere il PC.
  - I risultati restano nella prova: `outputs\Layer1\Engine_and_emissions.xlsx`, `outputs\_work\Layer1\crn_case\` e `log_emissioni.txt`.

## Se qualcosa non va
- **"ARIEL-SST.exe non trovato":** manca l'eseguibile in `lavoro\`.
- **"Manca HLInputs.yaml" o "Manca StatDatabase.xlsx":** mancano i file in `inputs_iniziali` (vedi Installazione, punto 3).
- **"Manca PyYAML":** esegui `pip install pyyaml`.
- **"python non è riconosciuto":** Python non è nel PATH. Reinstallalo spuntando "Add python.exe to PATH".
- **Per tornare agli input originali:** cancella `lavoro\inputs` e riavvia.

## Test
```
python -m unittest test_app
```
I test usano un ARIEL finto (`fake_ariel.py`), quindi non serve l'eseguibile vero.
