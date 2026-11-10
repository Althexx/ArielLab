"""Finto ARIEL-SST per i test: stesso menu, legge inputs/HLInputs.yaml, scrive outputs/ copiando un esempio vero."""
import os, shutil, sys, yaml

ESEMPIO = sys.argv[1]  # cartella con outputs/ e log_ok.txt di una prova vera
MENU = "  1  Full run\n  2  Aircraft design only\n  3  Engine only\n  4  Exit\nSelect an option [1-4]: "

def calcolo():
    v = yaml.safe_load(open(os.path.join('inputs', 'HLInputs.yaml'), encoding='utf-8'))
    if v['flight_expected_performances']['range [km]'] > 9000:
        print('Error: Divergency detected in MTOW iterative loop')
        return
    if os.path.isdir('outputs'):
        shutil.rmtree('outputs')
    shutil.copytree(os.path.join(ESEMPIO, 'outputs'), 'outputs')
    print('Iteration: 1\nMTOM=114206 [kg]\nFuel_f=48.98 %\nConverged in 33 iterations')

def motore():
    n = int(open('conteggio_opz3.txt').read()) if os.path.isfile('conteggio_opz3.txt') else 0
    open('conteggio_opz3.txt', 'w').write(str(n + 1))
    v = yaml.safe_load(open(os.path.join('inputs', 'HLInputs.yaml'), encoding='utf-8'))
    if v['payload']['passenger_number [-]'] == 99:
        print('Error: engine on-design optimisation found no feasible design')
        return
    shutil.copy2(os.path.join(ESEMPIO, 'Engine_and_emissions.xlsx'), os.path.join('outputs', 'Layer1'))
    print('Engine and emissions done')

while True:
    sys.stdout.write(MENU); sys.stdout.flush()
    scelta = sys.stdin.readline().strip()
    if scelta == '2':
        calcolo()
    elif scelta == '3':
        motore()
    elif scelta == '4' or not scelta:
        break
