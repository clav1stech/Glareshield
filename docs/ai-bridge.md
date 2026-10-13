# AI Bridge

AI Bridge constitue, au sein de Glareshield, un état de vol structuré destiné à une
assistance conversationnelle (ChatGPT, Claude ou autre). Le module lit le simulateur
en lecture seule, peut intégrer le dernier OFP SimBrief et produit un export à coller
dans une conversation. Il n'appelle aucun modèle d'IA et ne requiert aucun abonnement
API.

## Principes

- **Connexion unique.** Les variables AI Bridge sont lues par le processus SimConnect
  existant, dans sa boucle de lecture : à chaque tour, les LVars d'éclairage sont lues
  d'abord, puis au plus une variable AI Bridge arrivée à échéance. Les appels à la DLL
  restent séquentiels ; un fil de lecture parallèle provoquait des arrêts du processus
  SimConnect lors des essais réels. L'ensemble représente environ 10 lectures par
  seconde : 2 s pour la trajectoire et la configuration, 5 s pour les moteurs, 15 s pour
  le carburant, les masses et la météo, 30 s pour l'identité et l'heure.
  Une LVar déjà lue pour l'éclairage est réutilisée au lieu d'être demandée deux fois.
- **Indépendance fonctionnelle.** Le module est désactivé par défaut. Désactivé, il ne
  demande aucune variable et ne modifie ni le démarrage, ni la cadence, ni la
  reconnexion des éclairages. Ses réglages sont stockés dans `local/ai-bridge.yaml`,
  distinct de `local/config.yaml` : les modifier ne redémarre jamais les éclairages ;
  les requêtes sont transmises au processus SimConnect en cours sans reconnexion.
  Un fichier invalide désactive le module sans affecter l'éclairage.
- **Qualification des données.** Chaque valeur porte son unité, son âge et un statut :

  | Statut | Signification |
  | --- | --- |
  | `observed` | Mesure du simulateur reçue dans le délai propre à la variable |
  | `stale` | Dernière mesure connue, trop ancienne ou simulateur déconnecté |
  | `unavailable` | Jamais reçue ou invalide ; jamais remplacée par zéro |
  | `simulated` | Valeur du scénario de démonstration |
  | `derived` | Valeur calculée, accompagnée de sa méthode |

- **Séparation des valeurs de test.** Les valeurs injectées par les tests de source de
  l'éclairage (`engine.values`) ne sont jamais lues par AI Bridge, qui dispose de son
  propre stockage alimenté uniquement par le processus SimConnect. Le scénario de
  démonstration alimente un stockage distinct et marque l'export
  `data_origin: simulation_scenario`.
- **Aucune inférence de guidage.** Aucun mode FMA, alerte ECAM ou phase de vol n'est
  déduit. La route SimBrief est qualifiée de `planned` et n'est jamais présentée comme
  la route active du MCDU.

## Catalogue

Le catalogue standard comprend 30 SimVars documentées par le SDK MSFS : identité de
l'appareil, position et altitudes, vitesses, cap et route, configuration (train,
volets, aérofreins, frein de parc), moteurs, carburant et masse, vent, température,
pression et heure UTC. La route magnétique est déclarée indisponible sous 5 kt de vitesse
sol, où elle n'a pas de signification. Les noms et unités figurent dans
`src/glareshield/aibridge/catalog.py`, avec leur cadence de lecture et leur âge
maximal. Chaque variable est rattachée au niveau d'export essentiel ou détaillé.

Le Fenix A320 simule ses propres systèmes : une SimVar standard (carburant, volets,
moteurs, frein de parc notamment) peut ne pas refléter son cockpit. Ces variables sont
donc exportées avec `verification: msfs_sdk` tant que l'utilisateur ne les a pas
déclarées « validées localement » dans l'onglet **Variables IA**.

Aucune LVar Fenix n'est présumée. L'utilisateur peut en ajouter dans **Variables IA**
(nom, libellé, unité, cadence, signification des valeurs), après relevé dans une liste
vérifiée ou avec `scripts/probe_simulator.py`. Elles sont exportées avec
`verification: configured_unverified` jusqu'à confirmation de leur sens.

## Plan de vol SimBrief

L'identifiant SimBrief (nom d'utilisateur ou Pilot ID numérique) est conservé dans
`local/ai-bridge.yaml` ; aucun mot de passe n'est demandé. Le bouton **Actualiser
depuis SimBrief** interroge, sur action manuelle uniquement et au plus toutes les
15 secondes, l'adresse documentée par Navigraph :

```text
https://www.simbrief.com/api/xml.fetcher.php?username=<identifiant>&json=v2
https://www.simbrief.com/api/xml.fetcher.php?userid=<pilot id>&json=v2
```

Le résumé retient départ, destination, dégagements, indicatif, appareil, route,
niveau initial, AIRAC, carburant, masses, durées et points de route. Un champ absent
est omis, jamais estimé. Le dernier plan valide est conservé dans
`local/state/simbrief-ofp.json` ; en cas d'échec ultérieur, il reste disponible avec
un avertissement explicite. Un OFP généré depuis plus de 12 heures (seuil réglable) ou
un appareil au sol à plus de 30 NM du départ et de la destination produisent un
avertissement.

Les chemins de champs (`origin.icao_code`, `general.initial_altitude`,
`navlog.fix[].altitude_feet`, etc.) correspondent au format JSON de SimBrief tel que
connu lors du développement ; ils doivent être confirmés sur un OFP réel.

## Export

Trois modes répondent à trois usages, dans une même conversation avec l'assistant :

| Mode | Quand | Contenu |
| --- | --- | --- |
| **Briefing** | une fois, au sol | plan complet (route, SID, STAR, points de route avec altitude et carburant prévus, carburant, masses, METAR, horaires) et état de l'avion |
| **Point en vol** | aussi souvent que nécessaire | trajectoire, configuration, LVars configurées, destination et STAR prévues, avancement sur la route ; complète le briefing déjà transmis |
| **Complet** | diagnostic | toutes les variables avec leur source et leur vérification, plan intégral avec coordonnées |

Le mode automatique choisit le briefing au sol ou sans donnée, le point en vol une fois
l'appareil en l'air. Briefing et point en vol n'exportent que les variables marquées
« briefing et vol » ; les autres ne figurent que dans l'export complet.

L'avancement (`derived.route_progress`) situe la position observée par rapport aux
points de route de l'OFP : prochain point, cinq points suivants, distance restante le
long de la route et, si l'OFP le fournit, écart entre le carburant observé et le
carburant prévu à bord interpolé à la position. C'est un calcul géométrique sur la
route prévue, qui ne reflète pas une modification faite au MCDU.

Les **notes pilote** (2 000 caractères, `local/state/pilot-notes.json`) transmettent ce
que le simulateur ne fournit pas : STAR et VIA saisis au MCDU, piste, ATIS, clairance,
messages. Elles figurent dans chaque export sous `pilot_notes`, qualifiées de
déclarations du pilote.

L'onglet **Export IA** propose :

- **Copier pour un chat IA** : courte consigne invitant l'assistant à s'en tenir aux
  valeurs fournies, suivie du JSON compact ;
- **Copier le JSON seul**, **Télécharger le fichier JSON** (emplacement choisi dans le
  navigateur) et **Enregistrer dans local/exports**.

Le schéma est identifié par `schema: glareshield.flight_context/2`. Briefing et point
en vol listent les champs indisponibles par leur seul nom ; le mode complet ajoute la
source, la vérification et les notes de chaque variable. Les tailles sont plafonnées
(30 000, 8 000 et 60 000 caractères) ; un raccourcissement des points de route ou des
notes est signalé par `waypoints_truncated` ou `truncated`.

## Démonstration sans simulateur

Le scénario de démonstration rejoue un vol fictif d'A320 (parking, roulage, décollage,
montée, croisière, descente, approche, atterrissage) et un OFP fictif peut être chargé
dans **Plan de vol**. Ces données servent à éprouver l'affichage et l'export ; elles ne
constituent pas une validation de l'intégration avec MSFS ou le Fenix.

## Accès local et préparation MCP

Les routes `/api/ai/*` exigent le jeton de session, y compris en lecture, en plus de la
restriction à la boucle locale. Aucune route n'écrit dans le cockpit.

`AIBridge` (`service.py`) est la seule source des vues : l'interface, l'export et un
futur serveur MCP appellent les mêmes méthodes, qui correspondent aux outils envisagés :

| Méthode | Outil MCP envisagé |
| --- | --- |
| `snapshot(level)` | `get_flight_snapshot` |
| `flight_plan()` | `get_flight_plan` |
| `available_variables()` | `get_available_variables` |

## Premiers essais sur MSFS 2024 et Fenix

Constats d'une session au parking (Fenix A320 CFM) :

- les 30 variables sont reçues ; position, heure, frein de parc, moteurs, carburant
  et masse correspondent au cockpit ;
- `FLAPS HANDLE INDEX` ne suit pas le levier du Fenix (cran 1 et FULL lus 2) : ne pas
  l'exporter tant qu'une LVar Fenix vérifiée ne le remplace pas ;
- `SPOILERS ARMED` reste faux avec les aérofreins armés : même conclusion que pour
  les volets ;
- l'import SimBrief réel (`json=v2`) fournit l'heure de génération et les horaires en
  ISO 8601, les durées en `HH:MM:SS` et les points de route en liste directe ;
  le parseur accepte ce format et l'ancien (`json=1`) ;
- après passage à la lecture séquentielle, aucune déconnexion n'a été observée,
  y compris sur un vol complet de près de deux heures ;
- les noms de LVars figurent dans les fichiers de comportement du paquet Fenix ;
  les voyants du FCU et de l'EFIS se lisent, mais les valeurs sélectionnées (vitesse,
  cap, altitude, vitesse verticale) et les modes FMA ne sont pas exposés : les molettes
  ne donnent qu'un compteur de crans ; les relevés restent dans `local/discovery/` ;
- les pages et messages du MCDU et les alertes ECAM ne sont pas accessibles ;
  l'interface locale de l'EFB Fenix n'est pas documentée et n'est pas utilisée.

## Validation restant à réaliser sur MSFS 2024 et Fenix

1. Activer AI Bridge avec la configuration personnelle et vérifier que les éclairages
   conservent cadence, reconnexion et comportement en pause.
2. Vérifier sur une session longue l'absence de déconnexion SimConnect et de latence
   perceptible de l'éclairage avec AI Bridge actif.
3. Contrôler au parking puis en vol chaque SimVar du catalogue face au cockpit du
   Fenix, puis cocher « Validée » ou décocher « Exporter ».
4. Confirmer en vol les voyants AP, A/THR, LOC et APPR configurés localement.
5. Trouver une source fiable pour le levier de volets et l'armement des aérofreins.
6. Coller un export dans un assistant et ajuster le contenu essentiel si nécessaire.
