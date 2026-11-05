"""Lance Glareshield sans console, depuis n'importe quel dossier (ex. exe.xml de MSFS)."""
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
sys.argv[1:1]=['--root',str(ROOT)]

from glareshield.app import main

main()
