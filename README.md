# Glareshield

Version courante : [dernière release GitHub](https://github.com/clav1stech/Glareshield/releases/latest). Voir le [journal des changements](CHANGELOG.md)
et la [politique de versionnement](docs/versioning.md) : `z` de façon autonome pour chaque
modification de l'application, `y` pour un ensemble important après accord explicite
de l'utilisateur, `x` uniquement sur sa demande explicite. Les modifications sans effet sur l'application ne
changent pas la version. Les releases GitHub sont publiées depuis les tags.

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

Dans **Affectations**, chaque fonction dispose de sa propre sélection : choisir des appareils individuellement, ou combiner groupes, portée active et exclusions. L’aperçu affiche les appareils réellement concernés. Une sélection individuelle reste indépendante de la portée active ; un groupe suit les changements de ses membres. La copie reprend les appareils actuellement sélectionnés par une autre fonction. Une sélection vide ne pilote aucun appareil. Désactiver une fonction conserve ses affectations pour la réactiver ensuite.

Les priorités s’appliquent séparément sur chaque lampe. Une lampe affectée aux alertes et au DOME reçoit le fond DOME entre les flashes ; une autre affectée aux alertes et à l’ATC reçoit le fond ATC. Les appareils retirés d’une fonction sont restaurés si aucune autre fonction ne les utilise. Modifier affectations, groupes, portées, règles, effets ou réglages conserve les connexions des sources. Modifier appareils, contrôleurs ou sources redémarre les composants de Glareshield après restauration des lampes.

Les paramètres modifiables sont répartis ainsi :

| Onglet | Paramètres |
| --- | --- |
| Règles | Nom de fonction, activation, priorité, conditions ET/OU, source, effet, son, dépendance au simulateur et à la pause |
| Effets | Couleurs, températures, luminosités, transitions, période et fraction haute des flashes, nombre de cycles, paliers DOME, fichiers et volumes sonores |
| Sources | Variables, touche PTT, intervalle de lecture, processus audio, seuil, durée minimale, maintien et délai entre contacts |
| Réglages | Cadence moteur, plafond des flashes, seuil de changement de luminosité, cadences des pilotes, délais de commande/restauration/son, reprises après erreur, actualisation des adresses et de l’interface, durée des tests |

L’intervalle de lecture s’applique aussi aux sources clavier et audio. La cadence Hue règle également le limiteur de commandes du pont. Les limites sont validées avant enregistrement ; une configuration invalide conserve la configuration précédente. Les clés et constantes internes des protocoles restent gérées par les pilotes.

Les cartes d’effets décrivent le résultat en français : couleur, flashes par seconde, luminosité, durée des phases et paliers. L’éditeur utilise des Hz et des pourcentages ; chaque réglage possède une explication. Une fréquence de 2 Hz avec une phase haute de 50 % signifie 250 ms en phase haute puis 250 ms en phase basse. Une pulsation fait varier progressivement la luminosité sur le cycle.

**Tester 3 s** est disponible sur toutes les pages de configuration, sur les cartes et dans les éditeurs. Choisir la fonction, les lampes et, pour DOME, le palier. Les effets, règles, affectations, groupes, portées et réglages en cours d’édition peuvent être essayés sans être enregistrés. Les autres fonctions conservent leurs priorités ; un test DOME peut donc être recouvert par une alerte réelle. Le test revient automatiquement à l’état courant des règles, même avec une cadence moteur basse. **Arrêter le test** interrompt immédiatement l’aperçu ou la simulation de source. Suspendre les règles arrête également les tests.

Les tests de source simulent sa valeur pendant trois secondes et utilisent les affectations enregistrées. Ils n’écrivent aucune variable dans le simulateur ; les seuils audio et les touches se vérifient avec le moniteur réel. Les tests d’appareil et de contrôleur utilisent la connexion enregistrée : enregistrer une nouvelle adresse ou ressource avant de la tester. Le test d’un son exige une sortie audio configurée ; aucune sortie n’est activée automatiquement.

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
