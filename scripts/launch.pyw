"""Lance Glareshield sans console, depuis n'importe quel dossier (ex. exe.xml de MSFS)."""
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))

from glareshield.app import main

# La garde est indispensable : le worker SimConnect (multiprocessing « spawn »)
# réimporte ce fichier et ne doit pas relancer l'application.
if __name__=='__main__':
    sys.argv[1:1]=['--root',str(ROOT)]
    main()
