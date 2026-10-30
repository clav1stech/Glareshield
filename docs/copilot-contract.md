# Contrat du copilote A320

Référence de l’[issue 11](https://github.com/clav1stech/Glareshield/issues/11),
première étape de l’[issue 10](https://github.com/clav1stech/Glareshield/issues/10).
Base examinée : `claude/ivao-network`, commit `d0b5046` de la PR #9,
application 1.1.2, export `glareshield.flight_context/3`. La maquette fournie est
décrite dans [la référence publique des écrans](copilot-mockup.md).

Ce lot livre le contrat, un profil et leur validation. Il n’active aucun suivi,
ne modifie aucun export et n’implémente ni moteur de phases, ni écran, ni collecte
supplémentaire. Les règles ci-dessous sont les obligations des consommateurs à
implémenter dans les issues suivantes. Simulation uniquement, lecture seule du
cockpit ; aucune émission radio ou action sur le matériel par le chargeur.

## Arbitrages

- Procédures normales A320 embarquées en JSON, dérivées de [SKILL.md](SKILL.md),
  sections 4, 5 et 7. Aucun modèle IA, service payant ou génération à l’exécution.
  Il s’agit d’un aide-mémoire générique de simulation, pas d’une checklist
  constructeur exhaustive ni d’une procédure d’exploitation réelle.
- Une personnalisation est un profil complet sous `local/copilot/profile.json`,
  incluant les checklists utilisateur. Pas de fusion implicite de listes, de
  code embarqué ou d’import distant. Les données d’une installation restent
  privées, selon [privacy.md](privacy.md).
- Les performances sont saisies manuellement, avec référence et contexte
  (EFB, OFP ou document cité). Pas de calcul de V1/VR/V2/FLEX/VAPP.
- Les notes libres restent du texte. Seuls des champs structurés explicitement
  renseignés par le pilote alimentent une clairance, une écoute ATIS ou une
  performance. Une suggestion issue du plan reste étiquetée « prévu ».
- Une action manuelle, cochée **ou décochée**, prime sur l’automatisme. Changer de
  phase ne coche aucune étape. Une observation contradictoire reste visible.

## Artefacts et consommation

| Artefact | Contrat |
| --- | --- |
| `src/glareshield/copilot/a320.json` | Profil `glareshield.copilot_profile/1`, révision 1 |
| `src/glareshield/copilot/contract.py` | Modèles stricts, validation des références, chargeur avec repli |
| `examples/copilot-six-phases.json` | Six sorties illustratives fictives, une par phase, sans moteur exécuté |
| `Profile.model_json_schema()` | Schéma JSON générable depuis les mêmes modèles que le chargeur |
| `QualifiedValue.model_json_schema()` | Enveloppe commune des valeurs résolues par le futur adaptateur |

```python
from pathlib import Path
from glareshield.copilot.contract import load_profile

loaded = load_profile(Path("."))
profile = loaded.profile
for phase in profile.phases:
    for group in phase.groups:
        for step in group.steps:
            # Le rendu affiche ces données ; le moteur résoudra leurs sources.
            labels = [profile.values[key].label for key in step.expected]
```

Le profil donne `id`, `revision`, appareil, périmètre, référence des procédures,
table `sources`, table `values` et six `phases` ordonnées. Chaque phase contient
un déclencheur, des groupes typés `mcdu`, `fcu`, `checklist`, et des messages radio.
Une étape fournit un identifiant stable, un libellé, les valeurs attendues,
une priorité de 0 à 100, un déclencheur et une condition de validation.

Les identifiants de phases, groupes, étapes et messages sont uniques dans le
profil. `sources` et `values` ont leurs espaces de noms distincts. Un réordonnancement
ne change pas les identifiants. Une modification de sens crée un nouvel identifiant
et augmente `revision` ; la migration de progression relève de #13. Le rendu
n’utilise jamais les index de tableau pour persister une case.

Un déclencheur est un OU de clauses ET (`any_of`), composées de comparaisons
`eq`, `lt`, `lte`, `gt`, `gte`, et d’un maintien continu `hold_s`. Une entrée
inconnue ou périmée ne satisfait aucune comparaison, y compris `eq false`.
Depuis la refonte de Vol, « Maintenant » dépend de l’étape détectée
([phases](copilot-phases.md)) : `copilot/cockpit.py` associe à chaque étape une
liste ordonnée de groupes ou d’étapes du profil, et affiche le premier qui
contient une case non cochée. Les messages radio proposés sont aussi choisis
par étape. Les déclencheurs d’étape du profil restent du contexte ; seules les
validations observables évaluent leurs règles.
Une valeur manquante garde l’étape visible avec son emplacement, sans question.
Le prochain déclencheur est affiché avec son libellé, sans inventer d’échéance.

Le modèle de vue transmet au rendu : phase effective et sa qualification,
action Maintenant et contexte, prochain déclencheur, groupes d’étapes résolues
(valeur, unité, source, état et raison), messages déjà sélectionnés, situation,
conflits et avertissements. Le moteur porte toute logique de procédure,
d’arbitrage, d’ordonnancement et de réseau ; le rendu parcourt ces collections,
échappe le texte, affiche et transmet les gestes manuels. Aucun `eval`, accès
arbitraire à un objet ou HTML issu d’un profil n’est autorisé.

## Sources et valeurs qualifiées

Le [contexte réseau livré en 1.2.4](copilot-network.md) raccorde désormais les
publications METAR structurées, les positions candidates et les événements IVAO
à la session. Il précise les limites et remplace les mentions prospectives de
#15 ci-dessous. L’écran Vol et ses messages radio consomment cette même section.
Les règles `reminders` d’un profil restent acceptées pour compatibilité mais
ne sont plus évaluées.

Une source décrit un chemin d’adaptateur, sa nature, son type (`number`, `bool`,
`string`), l’unité **normalisée** et
son éventuel âge maximal. Les chemins sont des données, pas des expressions.
`flight_plan.*` et `telemetry.*` désignent le contexte existant ; `pilot.*`,
`publications.*`, `events.*`, `computed.*` et `session.*` sont des espaces internes
aux adaptateurs, pas des champs du document d’export `/3`. Par exemple,
`flight_plan.alternates.primary.icao` désigne le premier dégagement (l’export
conserve sa liste), et `publications.arrival.qnh` reste inconnu tant qu’aucune
valeur structurée et vérifiée n’existe. Le lecteur METAR reste borné aux groupes
reconnus ; le texte ATIS libre n’est pas interprété. Aucun second client réel
IVAO ou SimConnect n’est créé.

| Donnée | Source existante / future | Nature, qualification et limite |
| --- | --- | --- |
| Trajet, route, SID/STAR, piste, niveau, carburant, masses | `flight_plan` du dernier OFP | `planned` ; âge de génération et d’import, avertissements conservés ; aucune autorisation implicite |
| Position, vitesse sol, vario, altitude, au sol | `telemetry.position`, `telemetry.speed` | `observed` ou `simulated` ; limites du catalogue (8 s pour ces signaux) |
| Configuration train, frein, volets, calage | Catalogue et LVars configurées | Observation ; auto-validation seulement après vérification locale du sens pour cet appareil |
| Valeurs FCU sélectionnées, route active MCDU, TOD MCDU | Absentes de la collecte actuelle | Déclaration structurée du pilote ou `<…>` ; aucun compteur de crans converti en valeur |
| Clairance, code, transfert, altitude/cap/vitesse autorisés | `pilot.clearance.*` futur | `declared` ; référence à la déclaration, contexte et révision ; jamais OFP ou texte libre |
| Piste et approche retenues | Déclaration pilote puis OFP comme proposition | Deux natures visibles ; publier une piste dans un ATIS ne constitue pas une clairance |
| Contrôleurs, fréquences, ATIS | Cache `ivao` existant | `published` ; état/âge du flux et `matched_by` conservés ; distance ≠ couverture certaine |
| QNH, vent, température de destination | Déclaration sourcée ou publication structurée future | `declared` / `published` ; ne pas confondre avec la météo MSFS ou celle de l’OFP |
| Lettre d’ATIS réellement écoutée | `pilot.atis.heard_letter` futur | `declared` ; liée à l’aérodrome et à la version de l’ATIS ; téléchargement ≠ écoute |
| V1, VR, V2, FLEX, VAPP, configuration, THR RED/ACC | `pilot.performance.*` futur | `declared` ; référence EFB/OFP et contexte obligatoires, aucun calcul |
| Phase, écarts et avancement | Moteur futur + calculs géométriques existants | `calculated`, statut `derived`, méthode et entrées nommées ; jamais FMA/ECAM |

Chaque valeur résolue respecte `QualifiedValue` : `value`, `unit` (ou `null`),
`nature`, `status`, `source`, `reference`, `age_s`, `max_age_s`, `verification`,
et, pour un calcul, `method` et `inputs`. `reference` identifie l’OFP, le bulletin,
la mesure ou la déclaration ; ces identifiants de session restent sous `local/`.
L’adaptateur conserve aussi les horodatages d’origine dans les enregistrements
sources. `age_s` se calcule depuis la mesure ou la déclaration, jamais depuis
le dernier rafraîchissement d’écran. Pour IVAO, âge de récupération et âge du
bulletin restent deux informations distinctes ; une dérivation conserve ses
entrées, et devient périmée dès qu’une entrée nécessaire l’est.

`available` qualifie une valeur prévue, publiée ou déclarée ; `observed`,
`simulated` et `derived` gardent leur sens actuel. `stale` et `unavailable`
s’appliquent à toutes les natures. Inconnu = `value: null`, `status: unavailable`,
affiché avec le `placeholder` explicite `<…>` de la valeur attendue. Ni zéro,
ni `false`, ni chaîne vide ne remplacent une absence. Une constante de procédure
(`ON`, `STD`, `EFFECTUÉE`) n’est jamais une observation : elle décrit une réponse.

Normaliser explicitement les masses OFP en kg à partir de `weight_unit`
(lb × 0,45359237), sans réécrire l’export. Une unité inconnue interdit cette
conversion. Altitudes en ft et niveaux FL restent distincts ; aucune conversion
QNH/STD n’est inventée. Les sources d’une même valeur attendue doivent avoir
la même unité. Le seuil 1 200 s des publications structurées du profil est une
limite de proposition à l’affichage ; un flux périmé l’emporte immédiatement.
Les déclarations sans durée fixe restent attachées à leur contexte, pas valables
indéfiniment : nouvelle clairance, nouveau vol, changement de piste, masse ou
météo invalident les valeurs concernées et demandent une nouvelle confirmation.

## Déclarations et conflits

Les formulaires de #13 stockent sous `local/` une déclaration identifiée,
horodatée et révisée, avec champ, valeur, unité, référence, contexte et éventuelle
révocation. Leur enveloppe résolue est `QualifiedValue(nature="declared", …)`.

| Déclaration | Contenu requis |
| --- | --- |
| Clairance | Type (départ, montée, descente, approche, piste, roulage, transfert), valeurs reçues, station ou origine de la déclaration, heure ; révocation/remplacement explicite |
| Piste / SID / STAR / approche | Départ ou arrivée, piste/procédure choisie, référence ; distinct de « autorisé » |
| ATIS écouté | Aérodrome, lettre/version ou référence du texte, heure d’écoute déclarée |
| Performances | Valeur, unité, référence EFB/OFP, appareil, piste, masse, configuration et météo associées ; validation humaine si l’un change |
| TOD MCDU | Valeur explicitement lue et unité, heure et référence ; distance déclarée datée, jamais présentée comme distance actuelle calculée |

Il n’y a pas de hiérarchie universelle qui écrase les données :

- Pour une instruction autorisée, seules les déclarations de clairance sont
  éligibles. Sans déclaration valide, `<altitude autorisée>` même si l’OFP donne
  FL350. Une SID publiée ne constitue pas à elle seule une autorisation.
- Pour une préparation de route, la déclaration choisie prévaut sur la
  proposition OFP ; conserver cette dernière et signaler l’écart. L’ATIS et le
  vent fournissent du contexte, pas une résolution automatique du conflit.
- Pour décrire le cockpit, l’observation fraîche décrit le signal mesuré ; une
  déclaration différente ne la remplace pas. Afficher les deux et l’écart.
- Pour l’écoute ATIS, seule la déclaration compte. Lettre publiée P et lettre
  écoutée O créent `atis_changed` ; ne jamais réécrire O en P.
- Une déclaration périmée ou révoquée n’est pas remplacée silencieusement par
  un plan dans un champ de clairance. Une note libre ne modifie aucun champ.

Un conflit est un enregistrement avec type, candidats qualifiés, raison et
résolution explicite ou absence de résolution. Les exemples des six phases
illustrent notamment une altitude inconnue, une performance absente et un
changement d’ATIS non confirmé par le pilote.

## Six phases visibles et déclencheurs

Le [moteur livré en 1.2.3](copilot-phases.md) précise ces propositions,
notamment le départ par mouvement observé et le retour au sol après un vol
interrompu. Ses paramètres sont regroupés dans `PhaseThresholds` ; les
déclencheurs du profil destinés aux procédures ne sont pas exécutés par ce moteur.

Ces seuils sont des choix de première version pour la simulation, modifiables
en données. Ils ne décrivent aucun mode de guidage.

| Identifiant stable | Entrée proposée | Contenu principal |
| --- | --- | --- |
| `preflight` — Prévol | Démarrage explicite de session au poste | INIT A/B, F-PLN prévu, PERF TAKE OFF manuelle, FCU initial, avant mise en route, demande de clairance |
| `departure` — Départ | Pilote prêt pour mise en route/repoussage/roulage | Confrontation clairance/F-PLN, FCU autorisé, après mise en route, roulage, avant décollage, séquence radio |
| `climb` — Montée | En vol, vario > 300 ft/min pendant 8 s | STD à l’altitude de transition, altitude autorisée, levier train, après décollage, contact départ/centre |
| `cruise` — Croisière | En vol, écart au niveau prévu ≤ 1 000 ft, vario entre −300 et +300 ft/min pendant 30 s | Arrivée MCDU préparée avant TOD, PERF APPR, RAD NAV, carburant, briefing et demande de descente |
| `descent` — Descente | Croisière déjà atteinte, en vol, vario < −300 ft/min pendant 15 s | Actualisation arrivée/ATIS, QNH au niveau de transition déclaré, approche et transfert |
| `arrival` — Arrivée | Croisière déjà atteinte, ≤ 60 NM destination, ≤ 10 000 ft AGL, vario ≤ 0 pendant 8 s ; puis maintien au sol | Approche, vérification APPR distincte du FMA, train, atterrissage, remise des gaz, piste dégagée, parking, sécurisation |

La phase calculée est `derived`, avec méthode, entrées, âge et raisons. Le pilote
peut forcer une phase (`declared`) et désactiver/reprendre l’avancement automatique.
Le moteur #14 conserve la dernière phase en cas de manque ou de pause, signale
l’incertitude et remet à zéro les temporisations sur interruption des conditions.
L’avancement automatique reste vers l’avant, choisit la phase admissible la plus
avancée si plusieurs déclencheurs sont vrais, et ne coche rien. Sur un vol court,
une descente sans croisière détectée ou un déroutement, la correction manuelle
reste disponible ; pas de classification certaine inventée.

Les `events.*` manuels sont des gestes déclarés du pilote (prêt à rouler, au
point d’arrêt, piste dégagée, transfert reçu…), jamais une clairance déduite.
`transition_up` / `transition_down` nécessitent un seuil déclaré et une mesure
fraîche cohérente avec sa référence altimétrique ; sinon ils restent inconnus.
`before_tod` n’est calculable qu’avec un TOD fourni et actuel ; pas depuis le
simple « 42 NM » de la maquette. Les événements sont réévalués et dédupliqués par
le moteur, pas par le profil ni le rendu. Le TOD affiché vient uniquement du
point `TOD` du journal de navigation de l’OFP.

## Validation des étapes

`manual` est la règle par défaut. `observed` donne un signal sémantique et une
égalité attendue ; l’adaptateur #17 ne le lie qu’à une source dont le sens
a été validé localement pour l’appareil. Une SimVar SDK acceptée ne suffit pas.
La source doit être actuelle, connectée, non en pause et du bon univers de
session. Un signal `simulated` ne valide qu’une session de démonstration.

Les signaux autorisés sont limités à la position du levier de train, au frein
de parc, au sélecteur STD et au cran de volets. Le levier train ne prouve pas le
verrouillage ; la ligne du profil le précise. Volets et calage restent manuels
si leur correspondance Fenix n’est pas validée. Une perte de source retire la
confirmation automatique actuelle et conserve l’historique avec sa raison ;
elle ne transforme pas une case en geste manuel. Les gestes manuels prévalent
dans les deux sens, même lors d’un retour de données ou d’un changement de phase.

APPR est **manuel** dans ce profil : un voyant ne prouve ni armement, ni capture,
ni stabilité d’une approche. Les FMA, ECAM, pages MCDU, FCU sélectionné et
clairances ne disposent d’aucune règle d’auto-validation. Les identifiants des
signaux admissibles sont bornés par le schéma ; un profil ne peut ajouter du
code ou un signal FMA à la liste.

Depuis la version 1.2.6, le service métier évalue ces règles dans la phase
courante. Les déclencheurs supplémentaires non observables et les temporisations
de procédure restent manuels ; seuls les déclencheurs de phase simples sont
pris en charge. La ligne STD confirme exclusivement la position du sélecteur CDB,
jamais le franchissement de l’altitude de transition. Le rendu n’évalue aucune
règle et n’envoie aucune commande au cockpit.

En SimConnect, la case « Validée » du catalogue ne suffit pas : ajouter une
correspondance `copilot_bindings` dans `local/ai-bridge.yaml`, uniquement après
avoir confirmé la source et son sens pour le titre exact de l’appareil. Exemple
**fictif**, à adapter localement sans le recopier comme validation du Fenix :

```yaml
copilot_bindings:
  - signal: gear_handle_down
    key: gear_handle_down
    variable: GEAR HANDLE POSITION
    origin: simvar
    aircraft_title: A320 fictif
    values: {"0": false, "1": true}
```

Le champ doit aussi être marqué validé dans les réglages AI Bridge (`validated`
pour une SimVar, `validated: true` sur la LVar). Une LVar STD peut être reliée à
`baro_std` avec sa propre correspondance numérique ; une clé portant un nom
familier ne prouve jamais son sens. La source exacte, son origine et le titre
récent doivent correspondre ; une mesure antérieure à la dernière observation
du titre est refusée. Plusieurs correspondances pour le même signal/appareil
suspendent la détection. Les SimVars standard de volets et d’aérofreins connues
comme incorrectes restent exclues, même marquées validées. Le profil embarqué
ne contient aucune auto-validation des volets ni du voyant APPR.

La démonstration utilise exclusivement son propre magasin de télémétrie et
ses correspondances connues pour les leviers/frein ; elle n’exige et ne crée
aucune validation d’une source réelle. Ses preuves portent l’origine
`scenario`, distincte de `simconnect`. Les tests d’éclairage sont exclus.

Une condition devenue fausse retire la coche automatique et crée une
observation contradictoire ; une source perdue/périmée ou une sortie de phase
retire la confirmation actuelle. La dernière preuve et chaque transition
restent dans l’historique privé. Le rafraîchissement d’une mesure identique
n’ajoute pas d’événement et ne réécrit pas le suivi. Après reprise, une preuve
persistée attend de nouvelles données fiables. Un geste manuel, coché ou
décoché, reste prioritaire ; une observation contraire est signalée sans le
modifier. L’interface présente l’origine, la source, l’heure de détection,
l’heure de mesure et les raisons d’une confirmation suspendue.

## Radio

Chaque gabarit porte un identifiant, un déclencheur, une priorité, les rôles de
stations candidats, deux variantes voix (français/anglais) avec collationnement,
et éventuellement une ligne UNICOM anglaise. Les paramètres `{nom}` doivent
référencer `values` ; formats, conversions et accès à des attributs sont interdits.
Le gabarit affiche les emplacements `<…>` non résolus ; un collationnement est
une aide à compléter **après réception**, jamais une réponse ATC prédite.

La sélection et la langue relèvent de #15/#19 : réutiliser le cache IVAO, exclure
les observateurs, distinguer `controllers: null` (inconnu) de `[]` (aucune position
retenue). La couverture descendante DEL/GND/TWR/APP-DEP/CTR reste conditionnelle
à la couverture réelle. Si elle est incertaine ou si le flux est périmé,
présenter voix et texte avec le doute, sans déclarer UNICOM certain.

Selon les règles du skill, voix française pour les positions françaises (LF et
territoires explicitement reconnus), anglaise ailleurs, indicatif inclus ;
station inconnue = `<station>`. UNICOM reste en anglais, sur une ligne avec
aérodrome au début et à la fin, sans indicatif ajouté par le gabarit. La fréquence
122.800 est une référence du skill, pas une fréquence ATC inventée. Rappeler
de lire avant d’émettre ; aucun envoi automatique et aucune annonce continue
en croisière. Les collationnements utilisent uniquement les valeurs reçues,
notamment piste, altitude, cap, vitesse, code, QNH et fréquence concernés.

## Personnalisation invalide et compatibilité

`load_profile(root, previous=None)` lit au plus 1 Mio dans le chemin privé fixe.
Un JSON invalide, une version inconnue, une clé dupliquée, un type incorrect,
une référence/unité invalide ou un signal automatique interdit est signalé par
`errors`. Le profil entier est refusé. Le dernier profil validé fourni par
l’appelant reste utilisé ; à défaut, le profil embarqué. Supprimer le fichier
revient au profil embarqué. Rien n’est écrit par le chargeur. Une personnalisation
ne désactive ni l’application ni les éclairages. L’interface affiche les erreurs
sans publier le contenu privé et conserve le dernier profil valide.

`glareshield.flight_context/3` conserve strictement son sens et ses champs ;
le contrat de profil et l’enveloppe copilote sont séparés. Les exports briefing,
flight et full ne gagnent aucun champ dans ce lot. Une extension future additive
pourra ajouter une section facultative explicitement versionnée, ignorée des
anciens lecteurs ; toute suppression, renommage ou changement de sens impose
un nouveau numéro de schéma, une migration et des tests de compatibilité. Ne pas
remplacer `pilot_notes` par des déclarations structurées sans transition.

Les seuls calculs admis sont la phase opérationnelle, l’écart à l’altitude
prévue, les franchissements documentés, la distance orthodromique à destination,
l’avancement le long de l’OFP et la comparaison de carburant déjà décrits dans
[ai-bridge.md](ai-bridge.md). Tous conservent méthode et provenance. Le TOD réel
MCDU demeure absent ; **aucune estimation TOD n’est ajoutée en première version**.
Un futur TOD estimé exigera formule, hypothèses, incertitude et un identifiant
distinct du TOD fourni. Aucun FMA/ECAM ou autre état de système absent n’est déduit.

## État livré et limites

Les interfaces, sessions, étapes, adaptation IVAO, observations et radio
sont raccordées. Le [guide](copilot-guide.md) et la [matrice de recette](copilot-acceptance.md)
décrivent leur vérification de bout en bout sur fixtures hors réseau.
Les correspondances réelles de calage/volets restent à valider par appareil.
TOD MCDU, FCU sélectionné et performances restent absents de la télémétrie
actuelle ; aucun état FMA/ECAM n’est déduit. Nom parlé de station inconnu :
`<station>`, même si son indicatif technique est publié. Le profil embarqué et
les fixtures ne prouvent pas la fiabilité des signaux du cockpit réel et ne
lancent aucune commande pour la vérifier.

Les tests de ce lot valident le profil, ses références, la consommation par
parcours générique, les six exemples, les qualifications, les rejets et le repli
sur une racine temporaire distincte. Ils n’accèdent ni à la configuration
personnelle, ni au réseau, ni au simulateur ou aux pilotes matériels.
