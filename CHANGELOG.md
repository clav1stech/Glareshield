# Journal des changements

La politique est décrite dans [docs/versioning.md](docs/versioning.md).

## [1.2.3] - 2026-10-29

- Issue #14 : moteur indépendant des six phases de vol, indices, méthode,
  incertitudes et prochain déclencheur affichés dans Vol.
- Confirmation continue et hystérésis ; paliers conservés, interruptions et
  données périmées suspendant les transitions concernées. Sous-états de roulage,
  décollage, approche, atterrissage, parking et remise des gaz.
- Correction manuelle persistante et retour explicite en automatique ;
  cases, déclarations et rappels conservés. Réutilisation de la géométrie de
  route prévue, sans déduction de FMA, ECAM ou TOD MCDU ni commande cockpit.
- Tests déterministes sur données fictives et parcours Edge en racine isolée.

## [1.2.2] - 2026-10-29

- Issue #13 : sessions de vol persistantes, déclarations pilote et priorité des gestes manuels
- Démarrage, reprise, fin et réinitialisation depuis Initialisation / Vol ;
  cases par identifiant stable, phase forcée et informations de rappel sous
  `local/copilot/`, dans des suivis séparés pour démonstration et SimConnect.
- Même OFP : progression conservée. Correction du plan : déclarations à vérifier.
  Nouveau plan : suivi précédent archivé et nouveau suivi vide, avec règle visible.
- Saisies explicites de clairance, piste/approche, ATIS effectivement consulté
  avec heure déclarée, et performances manuelles sourcées et contextualisées.
  Révisions et révocations conservées ; aucune interprétation des notes libres.
- Un geste manuel coché ou décoché prime sur une détection ; preuves et conflits
  restent visibles. Les détections historiques exigent une nouvelle confirmation.
- Fichier ancien ou invalide conservé, récupération explicite avec sauvegarde,
  écritures atomiques et refus des gestes issus d’un ancien suivi ou univers.
  API protégées par la session locale existante, sans écriture cockpit.
- Validation : 211 tests Python et parcours Edge sur serveur simulé isolé,
  avec vérification de la conservation des ressources du moteur d’éclairage.

## [1.2.1] - 2026-10-29

- Issue #12 : navigation permanente Initialisation / Vol / Réglages ; toutes les
  pages existantes restent accessibles depuis les cinq catégories de réglages.
- Initialisation rassemble les états du simulateur, d’AI Bridge, de SimBrief,
  d’IVAO et de l’éclairage, l’import manuel de l’OFP, son résumé et sa route,
  les notes pilote et les exports IA existants. Les manques pour le suivi réel
  sont distingués des intégrations facultatives et des données de démonstration.
- État SimConnect observé séparé de l’activité du moteur simulé, erreurs et
  données périmées signalées ; perte de connexion de l’interface rendue explicite.
- Thèmes automatique, clair et sombre et trois tailles de texte, conservés dans
  `local/display.json` sans reconnecter SimConnect ni redémarrer les éclairages.
  Focus clavier conservé lors des rafraîchissements et brouillons des notes
  conservés pendant les changements de page.
- Vol présente un état d’attente explicite ; « Démarrer le suivi du vol » reste
  désactivé jusqu’au raccordement du service de session. Aucune déduction de
  phase ni modification des règles d’éclairage.
- Validation avec pilotes simulés et racine jetable : navigation, import,
  notes, exports, affichage, clavier et conservation des ressources du moteur.

## [1.2.0] - 2026-10-29

- Contrat du futur copilote A320 : profil embarqué validable, six phases,
  étapes et messages radio décrits en données, sources et déclarations distinctes.
- Chargement des profils personnalisés privés avec validation stricte et repli
  sur le dernier profil valide ou le profil embarqué en cas d’erreur.
- Exemples fictifs des six phases, référence de la maquette fournie et limites
  de déduction documentées. Aucun moteur de suivi ou nouvel écran activé ;
  les exports `glareshield.flight_context/3` conservent leur comportement.

Version mineure choisie avec l’accord explicite de l’utilisateur pour le socle
du copilote : contrat commun, procédures en données et validation des profils.

## [1.1.2] - 2026-10-26

- Fusion de la 1.0.2 (stop.cmd, premier lancement à vide) dans la ligne 1.1
- Les versions 1.1.0 et 1.1.1 avaient été construites sans le code de la 1.0.2 publiée le
  14/10 ; cette version est la première à contenir à la fois l'intégration IVAO et
  `scripts/stop.cmd`, le démarrage à vide sans configuration et les corrections de `start.cmd`.
- Le journal rattache l'intégration IVAO à la 1.1.0 : l'entrée qui portait le numéro 1.0.2 par
  erreur est supprimée, la 1.0.2 du 14/10 reste celle de `stop.cmd`.

## [1.1.1] - 2026-10-26

- Sélection IVAO limitée au plan de vol et ATIS des approches voisines
- Les tours et approches survolées sans lien avec le plan ne sont plus exportées ni notifiées
  (seuls les centres le sont par leur distance à l'appareil) ; une approche voisine qui couvre
  un aérodrome suivi reste retenue ; sans aérodrome suivi, l'ancien critère s'applique.
- `airports[].online_positions` : positions en ligne portant l'OACI de chaque aérodrome suivi.
- ATIS d'une approche voisine qui couvre un aérodrome suivi joint aux exports briefing et vol
  (`covers`), avec les rôles de l'aérodrome couvert.

## [1.1.0] - 2026-10-26

- Notification au premier plan quand une position IVAO suivie se connecte ou se déconnecte
- Version mineure choisie avec l'accord explicite du propriétaire : nouvelle fonction visible
  (bande de notification), nouveau module `overlay.py`, nouveaux réglages `ivao.notifications`
  et `ivao.notification_seconds`, nouvelle route `POST /api/ai/ivao/notify-test`.
- Intégration IVAO facultative, désactivée par défaut et en lecture seule, développée avant la
  1.0.2 du 14/10 (`stop.cmd`, premier lancement à vide) et publiée ici, sans le code de celle-ci
  (présent à partir de la 1.1.2) :
  - Onglet Réseau IVAO : contrôleurs connectés, ATIS, METAR et TAF des aérodromes de l'OFP
    SimBrief et d'aérodromes ajoutés, consultation ponctuelle d'un autre aérodrome,
    actualisation manuelle et état de chaque flux.
  - Sources publiques sans authentification : Whazzup v2 (une requête toutes les 15 s au plus)
    et fichiers globaux METAR et TAF ; collecte dans une tâche propre, cache en mémoire partagé
    par l'interface et les exports, dernier résultat valide conservé et signalé en cas d'échec.
  - Exports : schéma `glareshield.flight_context/3` avec une section `ivao` séparée de la
    télémétrie, du plan et des notes pilote ; critères de sélection explicites avec un rayon
    par type de position (30 NM pour DEL, GND et TWR, 80 NM pour APP et DEP, 400 NM pour CTR
    et FSS), observateurs distincts, âge des bulletins distinct de l'âge de récupération, changements
    d'ATIS signalés, réductions décrites dans `ivao.truncated`.
- Bande de notification toujours au premier plan, sans focus ni clic, visible par-dessus un
  simulateur fenêtré ou en plein écran sans bordure (désactivée par défaut) ; bouton de test
  dans Réglages IVAO. Non vérifiée en plein écran exclusif.
- Positions suivies : mêmes critères que les exports, plus les centres proches des points de
  route de l'OFP ; première récupération sans notification, observateurs exclus.

Version mineure approuvée explicitement par l’utilisateur.

## [1.0.2] - 2026-10-14

- Ajout de scripts/stop.cmd pour arrêter une instance Glareshield lancée sans icône
- start.cmd installe l'environnement s'il est absent et garde la fenêtre ouverte en cas d'échec
- Premier lancement sans configuration : démarrage à vide sur l'onglet Contrôleurs, où la découverte et l'appairage Hue/Nanoleaf se font par boutons ; l'appairage lance la découverte si nécessaire

## [1.0.1] - 2026-10-13

Publication des connaissances génériques sur le Fenix A320 acquises pendant les essais ;
aucune donnée de l'installation personnelle n'est incluse.

- Préréglage Fenix A320 dans Variables IA : ajoute les LVars observées, toutes à valider
  par l'utilisateur, et retire de l'export les SimVars standard qui ne suivent pas le Fenix.
- `docs/fenix-a320.md` : variables d'éclairage et d'AI Bridge avec leur statut, variables
  inutilisables, emplacement des noms dans le paquet et limites connues.
- `examples/fenix-a320.yaml` : configuration d'exemple avec les sources Fenix et IVAO.
- `scripts/find_lvars.py` relève les LVars déclarées dans le paquet d'un avion ; la sonde
  simulateur lit aussi des SimVars standard.

## [1.0.0] - 2026-10-13

Version majeure explicitement demandée par l'utilisateur. Première version stable
de Glareshield avec AI Bridge, validée sur un vol réel de près de deux heures sans
déconnexion SimConnect ni perturbation de l'éclairage.

- Éclairage et AI Bridge partagent une connexion SimConnect unique, en lecture seule.
- Consignes pour assistants IA dans `docs/SKILL.md` : lecture des exports, attentes
  selon la phase de vol, checklists, phraséologie ATC ou UNICOM, questions limitées
  au nécessaire.
- Limites connues : le Fenix n'expose ni les valeurs du FCU, ni les modes FMA, ni le
  MCDU ou l'ECAM ; volets et armement des aérofreins restent sans variable fiable.

## [0.1.4] - 2026-10-13

Exports organisés par phase de vol, après un premier vol complet avec AI Bridge.

- Trois modes remplacent essentiel et détaillé : briefing au sol, point en vol et
  complet, avec choix automatique selon que l'appareil est au sol ou en l'air.
- Avancement sur la route prévue : prochains points, distance restante et carburant
  comparé au plan, présentés comme valeurs calculées.
- Notes pilote incluses dans les exports pour ce que le simulateur ne fournit pas
  (saisies MCDU, valeurs FCU, clairances, ATIS).

## [0.1.3] - 2026-10-13

Import SimBrief vérifié avec un OFP réel.

- Format `json=v2` pris en charge (horaires ISO 8601, durées `HH:MM:SS`, points de
  route en liste) ; l'ancien format reste accepté.
- SID et STAR ajoutées au résumé du plan.

## [0.1.2] - 2026-10-13

Corrections issues des premiers essais réels au parking sur MSFS 2024 et Fenix A320.

- Variables AI Bridge lues dans la boucle SimConnect, après les LVars d'éclairage et
  au plus une par tour : supprime les arrêts du processus observés avec un fil de
  lecture parallèle. Cadences réduites à environ 10 lectures par seconde.
- Hue : une scène dynamique rappelée par Glareshield, que le pont déclare ensuite
  inactive, est de nouveau identifiée ; les lampes concernées ne restent plus en erreur.
- Armement des aérofreins ajouté au catalogue ; route magnétique déclarée
  indisponible sous 5 kt de vitesse sol.

## [0.1.1] - 2026-10-13

Module AI Bridge et refonte de l'interface, développés et éprouvés avec des pilotes
et données simulés uniquement.

- AI Bridge : SimVars standard lues par la connexion SimConnect existante ; LVars Fenix
  configurables localement.
- Valeurs qualifiées par unité, âge et statut (observée, périmée, indisponible,
  simulée, calculée) ; les valeurs de test de l'éclairage ne sont jamais exportées.
- Import manuel du dernier OFP SimBrief, résumé planifié, conservation du dernier
  plan valide et avertissements d'ancienneté ou d'incohérence.
- Export JSON versionné, essentiel ou détaillé, à copier pour un assistant IA,
  télécharger ou enregistrer dans `local/exports`.
- Scénario de vol et OFP fictifs pour éprouver le module sans simulateur.
- Module désactivé par défaut ; réglages séparés dans `local/ai-bridge.yaml`,
  appliqués sans redémarrer les éclairages ; routes protégées par le jeton de session.
- Interface refondue : navigation latérale par module, tableau de bord synthétique,
  messages non bloquants, thèmes sombre et clair, affichage mobile.

## [0.1.0] - 2026-10-09

Première publication de l'application existante et point de départ du versionnement.

- Application Windows locale, interface française et icône système.
- Lecture du simulateur, détection audio par processus et lecture passive du PTT.
- Éclairages Hue et Nanoleaf, restauration durable de leur état initial.
- Affectations indépendantes par fonction, groupes, portées et exclusions.
- Flashes MW prioritaires sur MC, superposés au fond ATC prioritaire sur DOME.
- Paramètres modifiables et descriptions lisibles des effets et réglages.
- Aperçus de trois secondes avant enregistrement, arrêt manuel et retour aux règles normales.
- Extinction Nanoleaf corrigée ; reconnexion de l'interface et renouvellement de session.
- Configuration personnelle et secrets exclus du dépôt.
- Politique `x.y.z`, contrôle de version et publication des releases depuis les tags.
