# Fenix A320 : variables connues

Observations réalisées en octobre 2026 avec le Fenix A320 **2.4.0.4720** (version CFM) dans
MSFS 2024, en lecture seule. Une mise à jour du Fenix peut modifier ces variables : vérifier
chaque valeur au parking avant de s'y fier. Les relevés propres à votre installation restent
dans `local/discovery/`.

## Trouver les noms

Les LVars du Fenix sont déclarées dans les fichiers de comportement de son paquet MSFS, en
particulier `SimObjects/Airplanes/FNX_32X/attachments/fnx/Part_Interior_Cockpit/model/Cockpit_Behavior.xml`,
dans des balises comme `<VAR_NAME>` que les gabarits lisent par `(L:#VAR_NAME#)`. Le paquet se
trouve dans le dossier `Community` des paquets MSFS ; pour la version Microsoft Store de MSFS
2024, son emplacement est indiqué par la ligne `InstalledPackagesPath` du fichier
`%LOCALAPPDATA%\Packages\Microsoft.Limitless_8wekyb3d8bbwe\LocalCache\UserCfg.opt`.

```powershell
local/.venv/Scripts/python.exe scripts/find_lvars.py --name fnx-aircraft-320 --filter "FCU|MIP_MASTER"
local/.venv/Scripts/python.exe scripts/find_lvars.py --name fnx-aircraft-320 --filter "^I_FCU_" --write-probe
local/.venv/Scripts/python.exe scripts/probe_simulator.py --seconds 120
```

`find_lvars.py` relève environ 1 700 noms dans le paquet Fenix ; `--write-probe` prépare la liste
lue par la sonde. La sonde enregistre chaque changement de valeur pendant que l'on manipule le
cockpit, ce qui permet d'en établir le sens.

Préfixes observés :

| Préfixe | Sens |
| --- | --- |
| `S_` | position d'un sélecteur ou d'un bouton (certains boutons poussoirs donnent un compteur d'appuis) |
| `I_` | voyant (0 éteint, 1 allumé) |
| `E_` | molette rotative : compteur de crans, pas la valeur affichée |
| `N_` | valeur analogique ou éclairage |
| `A_`, `B_` | position d'animation ou état interne |

## Éclairage

| Variable | Valeurs | Statut |
| --- | --- | --- |
| `S_OH_INT_LT_DOME` | 0 OFF, 1 DIM, 2 BRT | vérifiée |
| `I_MIP_MASTER_WARNING_CAPT` | 0 → 1 → 0 au test ANN LT | vérifiée |
| `I_MIP_MASTER_CAUTION_CAPT` | 0 → 1 → 0 au test ANN LT | vérifiée |

`examples/fenix-a320.yaml` montre une configuration complète avec ces sources, la détection
audio du client pilote IVAO (`pilot_core_msfs.exe`) et une touche d'alternat.

## AI Bridge

Le bouton **Ajouter le préréglage Fenix A320** (onglet Variables IA) ajoute ces LVars à vos
réglages privés et retire de l'export les SimVars standard qui ne suivent pas le Fenix. Chaque
variable reste « non vérifiée » tant que vous ne l'avez pas confirmée dans votre cockpit.

| Variable | Valeurs | Statut |
| --- | --- | --- |
| `I_FCU_EFIS1_FD` | 0 FD éteint, 1 allumé | vérifiée au sol |
| `S_FCU_EFIS1_BARO_STD` | 0 QNH, 1 STD | vérifiée au sol |
| `A_FC_SPEEDBRAKE` | 1 rentré, 0 armé | une observation ; échelle complète à confirmer |
| `I_FCU_AP1`, `I_FCU_AP2`, `I_FCU_ATHR` | voyants | à confirmer en vol (l'AP ne s'engage pas au sol) |
| `I_FCU_LOC`, `I_FCU_APPR`, `I_FCU_EXPED`, `I_FCU_EFIS1_LS` | voyants | à confirmer en vol |

Un voyant allumé indique que le bouton est actif, pas le mode affiché sur le FMA.

## Variables inutilisables

| Variable | Constat |
| --- | --- |
| `E_FCU_SPEED`, `E_FCU_HEADING`, `E_FCU_ALTITUDE`, `E_FCU_VS` | compteurs de crans des molettes, sans lien avec la valeur affichée |
| `S_FCU_SPEED`, `S_FCU_HEADING`, `S_FCU_ALTITUDE` | impulsions des actions tirer ou pousser |
| `S_FCU_AP1`, `S_FCU_ATHR` | compteurs d'appuis |
| `S_FC_FLAPS` | ne change pas lorsque l'on manœuvre le levier de volets |

SimVars standard que le Fenix ne tient pas à jour :

| SimVar | Constat |
| --- | --- |
| `FLAPS HANDLE INDEX` | cran 1 et FULL lus 2 |
| `SPOILERS ARMED` | reste faux aérofreins armés |
| `AUTOPILOT AIRSPEED HOLD VAR`, `AUTOPILOT HEADING LOCK DIR`, `AUTOPILOT ALTITUDE LOCK VAR`, `AUTOPILOT VERTICAL HOLD VAR`, `AUTOPILOT MASTER` et indicateurs associés | toujours 0 |

Les SimVars de position, d'altitude, de vitesse, de cap, de train, de frein de parc, de
moteurs, de carburant et de masse correspondent au cockpit sur un vol complet.

## Limites

Les valeurs sélectionnées sur le FCU (vitesse, cap, altitude, V/S), l'état géré ou sélecté,
les modes FMA, les pages et messages du MCDU et les alertes ECAM ne sont exposés par aucune
LVar ni SimVar. L'EFB et le MCDU déportés du Fenix utilisent une interface locale non
documentée, dont la description est volontairement désactivée ; Glareshield ne l'utilise pas.
Les outils tiers qui affichent ces valeurs les lisent dans la mémoire du processus Fenix.
Dans AI Bridge, les notes pilote transmettent ces informations à l'assistant.
