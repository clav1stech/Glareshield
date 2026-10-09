# Glareshield

Application Windows reliant un simulateur de vol à des éclairages connectés. Interface en français, page web locale et icône dans la barre système. Toute la configuration personnelle reste sous `local/`.

## Fonctionnement

- SimConnect en lecture seule, reconnexion automatique et détection de pause.
- Hue v2 avec certificat épinglé, commandes groupées et reprise des scènes dynamiques.
- Nanoleaf : couleurs, températures et restauration du mode ou de l’effet initial.
- Deux couches : MW prime sur MC pour le clignotement ; ATC prime sur DOME pour le fond fixe. Le creux du clignotement laisse voir le fond.
- PTT par lecture passive de la touche configurée ; réception par niveau audio du processus choisi sur toutes les sorties Windows.
- Groupes imbriqués, exclusions, portées persistantes, règles ET/OU et effets modifiables depuis l’interface.
- Snapshots durables avant le premier pilotage, restauration à la fin des règles et à l’arrêt, reprise après arrêt brutal.

L’exemple vise 2 Hz pour les alertes, avec un plafond de 2 Hz. La cadence physique dépend du pont, des commandes nécessaires et du réseau. La luminosité basse sert de repli lorsqu’aucun fond fixe n’est actif.

AirPlay est un pilote optionnel expérimental. Il reste inactif sans sortie et son associés aux règles. Aucune sortie sonore PC n’est prévue. La réception et le comportement des paires d’enceintes doivent être vérifiés avant activation.

## Installation et lancement

Installer [uv](https://docs.astral.sh/uv/getting-started/installation/), puis depuis la racine du projet :

```powershell
./scripts/setup.cmd
New-Item -ItemType Directory -Force local
if (!(Test-Path local/config.yaml)) { Copy-Item examples/demo.yaml local/config.yaml }
./scripts/start.cmd
```

Conserver une configuration locale déjà existante. La copie de démonstration utilise uniquement des appareils et sources simulés.

Ouvrir **http://127.0.0.1:8777** depuis le navigateur ou l’icône système. Le lancement n’ouvre pas automatiquement de fenêtre. Le menu « Quitter et restaurer les lampes » termine proprement l’application. Un second lancement sur le même port est refusé avant connexion au matériel.

Pour lancer avec une console :

```powershell
$env:PYTHONPATH='src'
local/.venv/Scripts/python.exe -m glareshield.app
```

Python 3.13, l’environnement, les relevés, les fichiers audio et les journaux restent sous `local/`. Les dépendances sont figées dans `requirements.txt`.

## Configuration

Les onglets permettent de gérer appareils, contrôleurs, groupes, portées, sources, effets, règles et paramètres. Les modifications sont validées puis appliquées sans relancer l’application. Le tableau de bord affiche connexions, pause, variables, niveaux audio, règles actives et erreurs. Les tests de source sont temporaires et ne modifient aucune commande du simulateur.

Dans « Contrôleurs », découvrir, appairer puis importer les appareils. Hue nécessite le bouton du pont ; Nanoleaf nécessite la fenêtre API du constructeur. Les clés sont conservées dans `local/secrets/`. Affecter ensuite les appareils aux groupes et portées souhaités. Les adresses Hue et Nanoleaf sont résolues par identifiant stable et réactualisées ; un cache privé sert de repli. Une adresse manuelle reste possible.

Relever les noms de variables dans les fichiers du constructeur ou une liste vérifiée, puis vérifier leur sens réel au parking. Une variable acceptée par SimConnect ne prouve pas qu’elle représente la fonction attendue.

La source clavier lit uniquement le code de touche Windows configuré, sans interception ni injection. Une condition OU permet d’utiliser le même fond fixe sur réception ou émission PTT.

La détection audio distingue les processus, mais **ne distingue pas voix, notifications et autres sons d’un même processus**. Régler seuil, durée minimale, maintien et délai entre contacts dans « Sources », en observant le niveau au tableau de bord.

## Outils et vérification

```powershell
local/.venv/Scripts/python.exe scripts/discover.py
local/.venv/Scripts/python.exe scripts/pair_lights.py hue
local/.venv/Scripts/python.exe scripts/pair_lights.py nanoleaf --model MODELE
local/.venv/Scripts/python.exe scripts/probe_audio.py --seconds 30
local/.venv/Scripts/python.exe scripts/probe_simulator.py --seconds 30
$env:PYTHONPATH='src'
local/.venv/Scripts/python.exe -m glareshield.cli demo
local/.venv/Scripts/python.exe -m pytest -q
```

La sonde simulateur lit `local/discovery/probe-variables.json`, liste de noms de LVars. Les bancs `scripts/test_hue.py` et `scripts/test_nanoleaf.py` modifient les éclairages puis restaurent leurs états ; les utiliser lorsque cette modification est souhaitée. Les rapports et checkpoints restent privés.

## Confidentialité et publication

`src/`, `tests/`, `examples/`, `scripts/` et `docs/` contiennent uniquement du contenu générique ou fictif. `local/` regroupe l’installation personnelle et est exclu de Git. Les fichiers publics sont autorisés explicitement.

Après préparation des seuls fichiers relus :

```powershell
local/.venv/Scripts/python.exe scripts/check_public.py
git diff --cached --check
```

L’audit refuse les chemins non autorisés, les adresses de réseau privé, les chemins utilisateur et les identifiants ou secrets connus présents dans l’index. Une relecture reste nécessaire. Ne jamais ajouter `local/`, même à un dépôt privé.

Voir [l’architecture](docs/architecture.md), [la découverte](docs/discovery.md) et [la séparation des données](docs/privacy.md).
