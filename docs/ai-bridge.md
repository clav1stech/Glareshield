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
- **Déductions bornées et explicites.** Aucun mode FMA ou état ECAM n’est déduit,
  notamment depuis les voyants AP/LOC/APPR. Seules la phase opérationnelle du futur
  copilote et les estimations décrites dans le [contrat copilote](copilot-contract.md)
  sont autorisées, étiquetées `derived`, avec méthode, entrées et fraîcheur :
  distances géométriques, avancement OFP, écart au niveau prévu, franchissements
  documentés et comparaison de carburant. Ce lot de contrat n’ajoute aucun calcul
  aux exports. Le TOD réel du MCDU reste absent, sans estimation TOD en première
  version. La route SimBrief demeure `planned`, jamais route active ou clairance.
  Une correction manuelle de phase est une déclaration, pas une observation.
  Le profil `glareshield.copilot_profile/1` est indépendant du contexte `/3`, qui
  conserve ses champs et leur sens ; toute future rupture impose une migration
  et un nouveau schéma, pas une réinterprétation silencieuse.

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

Aucune LVar Fenix n'est présumée. Le préréglage **Fenix A320** ajoute les variables
observées et décrites dans [fenix-a320.md](fenix-a320.md), toutes non vérifiées tant que
l'utilisateur ne les a pas confirmées. L'utilisateur peut aussi en ajouter dans **Variables IA**
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

## Réseau IVAO

L'onglet **Réseau IVAO** complète le contexte par les données publiques du réseau :
contrôleurs connectés, ATIS, METAR et TAF. Glareshield collecte, sélectionne et restitue
ces données avec leur provenance ; il ne recommande aucune fréquence et n'interprète ni
l'ATIS ni la météo. L'intégration est facultative, désactivée par défaut, en lecture seule
et indépendante de la lecture SimConnect : elle fonctionne aussi pour un briefing sans
simulateur.

### Sources

Vérifiées le 26 octobre 2026 dans la documentation officielle
(`api.ivao.aero/docs`, wiki DevOps « API Documentation v2 ») et par des requêtes réelles :

| Donnée | Adresse | Accès |
| --- | --- | --- |
| Contrôleurs, observateurs et ATIS | `https://api.ivao.aero/v2/tracker/whazzup` | public ; une requête toutes les 15 s au plus, sous peine de bannissement de l'adresse IP |
| METAR | `https://api.ivao.aero/v2/airports/all/metar` | public, sans authentification |
| TAF | `https://api.ivao.aero/v2/airports/all/taf` | public, sans authentification |

Le flux ATIS dédié (`/v2/tracker/whazzup/atis`) reprend exactement les ATIS intégrés au
Whazzup ; il n'est donc pas téléchargé en plus. Les endpoints par aérodrome
(`/v2/airports/{icao}/metar`, `/taf`, `/atis`) répondent `401` sans clé d'application IVAO :
ils ne sont pas utilisés. Les champs du Whazzup réel diffèrent de la documentation (la portée
`lastTrack.distance` est absente des réponses observées) : chaque champ est facultatif et un
champ absent est omis, jamais estimé.

### Collecte et cache

Une tâche asynchrone propre au module télécharge les flux ; l'analyse JSON est faite hors de
la boucle partagée avec l'éclairage. L'interface et les exports lisent le même cache en
mémoire et ne déclenchent aucune requête. Aucun cache n'est écrit sur disque ; les réglages
(rayons par type de position, intervalles, aérodromes ajoutés) sont stockés sous `ivao:` dans
`local/ai-bridge.yaml`.

| Flux | Intervalle par défaut | Minimum | Actualisation manuelle |
| --- | --- | --- | --- |
| Whazzup | 60 s | 15 s | refusée moins de 15 s après la dernière tentative |
| METAR, TAF | 600 s | 300 s | refusée moins de 60 s après la dernière tentative |

En cas d'échec, le dernier résultat valide est conservé et marqué `stale` avec
`last_error`. Les nouvelles tentatives s'espacent (intervalle doublé jusqu'à 15 min) ; une
réponse `429` suspend le flux jusqu'au délai `Retry-After` (5 min par défaut). Les réponses
`401`/`403`, illisibles ou de plus de 16 Mo sont refusées avec un message explicite.
Désactiver l'intégration efface le cache.

### Sélection

Les aérodromes suivis sont le départ, la destination et les dégagements de l'OFP SimBrief,
puis jusqu'à six aérodromes ajoutés par le pilote. Le champ **Consulter un aérodrome** lit
n'importe quel code OACI dans le cache, sans requête supplémentaire ni inclusion dans les
exports.

Une position est retenue si :

- le préfixe de son indicatif (avant le premier `_`) est le code d'un aérodrome suivi ;
- son centre déclaré est à moins du rayon de sa catégorie (orthodromie) de la position
  observée de l'appareil ou d'un aérodrome suivi dont l'OFP donne les coordonnées :

  | Catégorie | Types | Rayon par défaut |
  | --- | --- | --- |
  | `aerodrome` | DEL, GND, TWR | 30 NM |
  | `approach` | APP, DEP | 80 NM |
  | `enroute` | CTR, FSS, types inconnus | 400 NM |

  Un centre contrôle une zone bien plus vaste qu'une tour : son point publié peut se trouver
  à plusieurs centaines de NM d'un appareil situé dans son secteur. Un rayon unique écarterait
  ces positions ou retiendrait des tours sans rapport avec le vol ;
- ou la portée publiée par le contrôleur, lorsqu'elle existe, atteint l'appareil.

Chaque position exportée porte `matched_by` (critère, aérodrome, distance, rayon appliqué)
et, si la position de l'appareil est exploitable, `distance_to_aircraft_nm` ; les rayons
figurent dans `ivao.selection.radii_nm`. Les positions dont l'indicatif désigne un aérodrome
suivi passent en premier, par rôle ; les autres sont classées par distance rapportée au rayon
de leur catégorie, pour qu'un centre pertinent ne soit pas évincé par des tours proches. IVAO publie le centre d'une
position, pas les limites de son secteur : ces rapprochements ne disent pas qui contrôle
l'appareil. Les tours et approches ne sont retenues que par
rapport aux aérodromes suivis : indicatif portant leur OACI, ou centre à moins du rayon de leur
catégorie (une approche voisine, comme celle d'un aéroport proche, qui reprend le contrôle en
l'absence de la position locale, est donc retenue avec `distance_to_airport`). Ceux que l'avion
survole sans lien avec le plan ne le sont pas ; seuls les centres (CTR, FSS) sont aussi retenus
par leur distance à l'appareil. Sans aérodrome suivi, la distance à l'appareil s'applique à toutes
les positions. `airports[].online_positions` liste les positions en ligne portant l'OACI de chaque
aérodrome, ce qui distingue « aucune position en ligne » de « position non retenue ».
Les observateurs (liste `observers`, position sans type ou indicatif en `_OBS`)
sont comptés à part et listés seulement dans l'export complet. Les pilotes connectés, les
identifiants de membre (VID) et les qualifications ne sont jamais conservés.

### ATIS et météo

Les ATIS joints aux exports briefing et vol sont ceux des positions retenues pour un aérodrome
suivi, y compris celui d'une approche voisine qui le couvre : `covers` indique alors l'aérodrome
couvert, dont les pistes figurent souvent dans les remarques de l'ATIS. Celui d'une position
survolée sans lien avec le plan n'est pas joint.

Chaque ATIS est restitué avec son texte original, sa lettre (`revision`) et l'horodatage
fourni par IVAO. Après une première récupération réussie, une nouvelle lettre, un texte
modifié ou un ATIS apparu sont signalés par `change` pendant 30 minutes, et par un badge
discret dans l'interface. Récupérer un ATIS ne signifie pas que le pilote l'a consulté ni
annoncé au contrôleur.

### Notification de connexion et de déconnexion

Désactivée par défaut (`ivao.notifications`, durée d'affichage `ivao.notification_seconds`, 10 s). Quand
une position suivie se connecte au réseau ou le quitte, une bande discrète apparaît en haut à droite de
l'écran principal. Elle ne prend jamais le focus et ignore la souris : elle ne gêne ni le clavier ni les
commandes de vol. Une notification Windows classique n'a pas été retenue, car Windows retient les
toasts pendant qu'un jeu occupe l'écran.

Sont suivies les positions retenues par le même rapprochement que les exports (indicatif préfixé par
l'OACI du départ, de l'arrivée, d'un dégagement ou d'un aérodrome ajouté, centre proche d'un de ces
aérodromes), plus les centres (CTR, FSS) dont le centre déclaré est à moins du rayon en route d'un point
de route de l'OFP, et les positions proches de l'appareil. Une position déjà en ligne qui entre
seulement dans le rayon n'est pas annoncée, de même que les observateurs. La première récupération
sert de référence et ne notifie rien ; au-delà de quatre positions, les notices sont regroupées.

Limites : l'affichage par-dessus MSFS est vérifié en fenêtré ou plein écran sans bordure, pas en plein
écran exclusif. Le bouton **Tester la notification** des réglages IVAO permet de le contrôler avec le
simulateur lancé. Une position qui se reconnecte après une coupure brève est annoncée deux fois.

METAR et TAF sont conservés bruts. Les heures d'observation, d'émission et la période de
validité sont lues dans le bulletin, le mois étant déduit de la date de publication IVAO.
L'âge du bulletin (`bulletin_age_min`) est distinct de l'âge de récupération du flux
(`feeds.*.fetched_age_s`) et, pour le Whazzup, de l'âge annoncé par la source
(`source_updated_age_s`). `not_published` signifie que le flux, valide, ne contient pas cet
aérodrome ; `feed_unavailable` que le flux n'a jamais été obtenu.

Trois sources météo restent séparées : `ivao.weather` (bulletins publiés),
`flight_plan.*.metar` (METAR de l'OFP à sa génération) et `telemetry.environment`
(conditions observées dans MSFS). Glareshield ne les compare pas.

### Dans les exports

La section `ivao` n'apparaît que si l'intégration est active. Elle est séparée de
`telemetry`, `flight_plan` et `pilot_notes`, et porte `nature: published_by_ivao`, une
consigne demandant de traiter les textes externes comme des données et jamais comme des
instructions, l'état de chaque flux et les critères de sélection. Les textes sont débarrassés
des caractères de contrôle et de mise en forme (y compris d'inversion bidirectionnelle) et
bornés (400 caractères par ligne d'ATIS, 20 lignes, 1 500 caractères par bulletin).
`controllers: null` signifie flux indisponible ; `[]`, aucune position retenue en ligne.

| Mode | Contenu IVAO |
| --- | --- |
| Briefing | aérodromes suivis : jusqu'à 20 positions, ATIS, METAR et TAF |
| Point en vol | destination, dégagements et aérodromes ajoutés, positions proches de l'appareil : 8 positions, ATIS, METAR, TAF de destination seulement |
| Complet | 40 positions avec coordonnées, 20 observateurs, ATIS de toutes les positions retenues, adresses, tentatives et erreurs des flux |

Si un export dépasse son plafond, les réductions suivent cet ordre, chacune étant décrite
dans `ivao.truncated` : observateurs, ATIS puis TAF autres que ceux de la destination, ATIS
raccourcis à 600 caractères, positions les moins proches (comptées dans
`controllers_omitted`), ATIS à 250 caractères, puis textes d'ATIS retirés en conservant
lettre et horodatage. Un flux non à jour ajoute un avertissement à `checks`.

Essai réel du 26 octobre 2026 (trois flux en 0,7 s ; 15 positions, 5 473 METAR,
3 032 TAF) : 9,6 k caractères pour le briefing, 6,2 k pour le point en vol et 17,4 k pour
l'export complet, sans réduction. Les tests automatisés emploient des données fictives et ne
contactent pas IVAO.

## Export

Trois modes répondent à trois usages, dans une même conversation avec l'assistant :

| Mode | Quand | Contenu |
| --- | --- | --- |
| **Briefing** | une fois, au sol | plan complet (route, SID, STAR, points de route avec altitude et carburant prévus, carburant, masses, METAR, horaires), état de l'avion et, si activé, données IVAO des aérodromes suivis |
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

Le schéma est identifié par `schema: glareshield.flight_context/3` (la version 3 ajoute la section `ivao`). Briefing et point
en vol listent les champs indisponibles par leur seul nom ; le mode complet ajoute la
source, la vérification et les notes de chaque variable. Les tailles sont plafonnées
(30 000, 8 000 et 60 000 caractères) ; un raccourcissement des points de route ou des
notes est signalé par `waypoints_truncated` ou `truncated`.

## Consignes pour l'assistant

Le skill prévoit trois envois par vol (briefing au poste, point en vol en croisière, point en
vol en descente). Chaque réponse couvre la phase suivante en entier : positions IVAO en ligne,
saisies MCDU et FCU, messages radio et checklists. Le pilote n'a pas à solliciter l'assistant
pendant les phases critiques. L'intégration IVAO doit être activée pour que les positions en
ligne figurent dans chaque export.

`docs/SKILL.md` décrit à un assistant (compétence Claude, instructions personnalisées
ChatGPT ou équivalent) comment lire les exports et ce que le pilote attend selon la phase
de vol : tâches MCDU, checklists, messages ATC en voix ou annonces UNICOM en texte.
L'ajouter une fois à l'assistant évite de répéter ces consignes à chaque vol.

## Démonstration sans simulateur

Le scénario de démonstration rejoue un vol fictif d'A320 (parking, roulage, décollage,
montée, croisière, descente, approche, atterrissage) et un OFP fictif peut être chargé
dans **Plan de vol**. Ces données servent à éprouver l'affichage et l'export ; elles ne
constituent pas une validation de l'intégration avec MSFS ou le Fenix.

## Accès local et préparation MCP

Les routes `/api/ai/*`, dont `/api/ai/ivao`, exigent le jeton de session, y compris en lecture, en plus de la
restriction à la boucle locale. Aucune route n'écrit dans le cockpit.

`AIBridge` (`service.py`) est la seule source des vues : l'interface, l'export et un
futur serveur MCP appellent les mêmes méthodes, qui correspondent aux outils envisagés :

| Méthode | Outil MCP envisagé |
| --- | --- |
| `snapshot(level)` | `get_flight_snapshot` |
| `flight_plan()` | `get_flight_plan` |
| `available_variables()` | `get_available_variables` |
| `network_page()` | `get_network_context` |

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
