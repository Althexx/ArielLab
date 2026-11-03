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
- **Motore ed emissioni.** Nella scheda "Motore ed emissioni" si sceglie una prova che converge. Il pulsante "Calcola motore ed emissioni" lancia l'opzione 3 di ARIEL sul velivolo di quella prova. ARIEL progetta il motore e calcola, fase per fase, combustibile, stato della camera di combustione, indici di emissione e kg di CO₂, H₂O, NOx e CO.
  - Il calcolo dura da decine di minuti a più di un'ora: il motore richiede circa 15 minuti, poi c'è la rete di reattori (CRN). Nel frattempo non si possono fare altri calcoli.
  - Non chiudere la finestra nera e non sospendere il PC.
  - I risultati restano nella prova: `outputs\Layer1\Engine_and_emissions.xlsx`, `outputs\Layer1\CRN_emissions\` e `log_emissioni.txt`.

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
