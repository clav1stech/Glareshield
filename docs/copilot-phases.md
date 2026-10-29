# Phases du copilote

Livré pour l’[issue 14](https://github.com/clav1stech/Glareshield/issues/14),
en version 1.2.3. `copilot/phases.py` est un moteur indépendant du rendu :
il reçoit des mesures qualifiées, l’état de connexion, le plan prévu et un
état de session. Il ne reçoit jamais le nom de phase du scénario, les moteurs,
les volets, une page MCDU ou un mode de guidage. Aucun client ni commande
simulateur supplémentaire. Les cases, déclarations et rappels sont indépendants.

## Déclencheurs

Les paramètres sont regroupés dans `PhaseThresholds`, injectables dans le
moteur. Les déclencheurs de procédure du profil restent des données pour les
futures étapes/actions ; cette version ne les exécute pas comme des règles
arbitraires de classification. Les seuils ci-dessous précisent ceux proposés
dans le contrat initial, avec deux compléments : mouvement au sol pour le
départ et retour au sol après un vol interrompu.

| Phase | Conditions continues | Confirmation |
| --- | --- | --- |
| Prévol | Suivi démarré et appareil observé au sol | Immédiate |
| Départ | Au sol, vitesse sol > 3 kt, ou geste explicite « Prêt pour le départ » | 5 s pour le mouvement ; immédiate pour le geste |
| Montée | En vol, vario > 300 ft/min | 8 s |
| Croisière | En vol, vario de −300 à +300 ft/min inclus, écart à l’altitude prévue de −1 000 à +1 000 ft inclus | 30 s |
| Descente | Croisière déjà confirmée, en vol, vario < −300 ft/min | 15 s |
| Arrivée | Croisière déjà confirmée, en vol, destination prévue ≤ 60 NM en orthodromie, hauteur ≤ 10 000 ft AGL et vario ≤ 0 | 8 s |
| Arrivée après retour au sol | En vol précédemment confirmé puis état au sol continu, même sans croisière ni destination | 5 s |

Seule la phase admissible **confirmée** la plus avancée est retenue. Une phase
ne recule jamais automatiquement. Cette hystérésis conserve montée/descente
pendant leurs paliers et empêche l’oscillation de l’affichage. Toute sortie d’un
seuil remet sa confirmation à zéro. Un palier de montée proche du niveau prévu
pendant 30 s peut néanmoins être classé croisière : c’est une limite explicite
de l’heuristique, corrigible par le pilote.

La comparaison de croisière utilise l’altitude MSL en ft et
`flight_plan.cruise.initial_altitude_ft`. Ce rapprochement géométrique n’est
pas une conversion QNH/STD, ni une lecture du niveau FCU. Son approximation
est signalée dans les indices. Les autres unités sont kt pour la vitesse sol,
ft/min pour le vario, ft AGL pour la hauteur et degrés pour la position.

## Sous-états

| Sous-état | Conditions | Confirmation |
| --- | --- | --- |
| Parking | Au sol, vitesse sol ≤ 1 kt | 10 s |
| Roulage | Au sol, vitesse sol > 3 kt ; après vol, < 30 kt ; après décollage interrompu, < 60 kt | 5 s |
| Décollage | Phase départ et vitesse sol ≥ 80 kt au sol, ou en vol | 3 s |
| Approche | Phase arrivée, en vol, vario ≤ 0 | 8 s |
| Atterrissage | Retour au sol après un vol confirmé, vitesse sol ≥ 40 kt | 5 s |
| Remise des gaz | Phase arrivée, en vol, vario > 300 ft/min | 8 s |

La bande 1–3 kt conserve le sous-état précédent. Après l’atterrissage, une
vitesse sol < 30 kt et un mouvement confirmé donnent le roulage ; la bande
30–40 kt conserve le sous-état. Après un décollage interrompu, le roulage exige
une vitesse < 60 kt ; la bande 60–80 kt conserve le sous-état. L’arrêt
confirmé donne le parking. Un bref signal au sol ou un vario bruité ne change
pas immédiatement le sous-état. La remise des gaz conserve la phase arrivée,
puis une nouvelle approche peut être confirmée. Aucun geste effectué n’est effacé.

## Fraîcheur et incertitude

L’adaptateur réutilise le catalogue et `TelemetryStore` existants, en respectant
les variables désactivées et les erreurs de mesure. Un champ doit avoir le bon
type, la bonne unité, le statut `observed` ou `simulated` et un âge ≤ 8 s.
L’état au sol est toujours requis ; la vitesse sol l’est au sol et le vario
l’est en vol. Une déconnexion, pause, absence de message depuis plus de 8 s,
session inactive ou profil incompatible suspend les transitions et remet
toutes les temporisations à zéro. Un intervalle d’évaluation > 8 s ou un retour
de l’horloge en arrière remet aussi les confirmations à zéro.

Une entrée complémentaire absente ou périmée interdit les transitions qui
l’utilisent : sans altitude ou niveau prévu, pas de confirmation de croisière ;
sans position, destination ou hauteur AGL, pas de confirmation d’arrivée en vol.
Les autres déductions restent possibles, avec une incertitude affichée. Un plan
dont la date est absente ou dépasse la limite d’âge OFP configurée n’alimente
plus les transitions qui en dépendent. La dernière phase croisière/arrivée en
vol devient `stale` si ses entrées complémentaires manquent. Le plan reste une
prévision dont la date et les avertissements sont affichés dans les écrans de
préparation ; il n’est jamais traité comme une mesure du cockpit.

Un démarrage en montée ou près du niveau de croisière peut rejoindre directement
la phase correspondante après confirmation. Un démarrage en descente sans
croisière connue conserve une phase non confirmée et demande une correction
manuelle. Un vol court sans croisière conserve cette même limite. Au redémarrage,
la phase et ses indices historiques persistent ; les temporisations repartent
à zéro et les mesures doivent être fraîches.

Le résultat fournit `effective` et `automatic` selon `QualifiedValue` : phase
calculée de nature `calculated`, statut `derived`, méthode, entrées, âge et
référence ; dernière phase `stale` sur interruption, ou valeur `null` et
`unavailable` avant confirmation. Les listes `evidence` et `uncertainty`,
le sous-état et `next_trigger` expliquent le résultat sans échéance inventée.
Les FMA, ECAM, TOD MCDU et trajectoires actives ne sont jamais déduits.

## Route prévue et correction manuelle

Le moteur réutilise `aibridge.context.derived` : distance directe à la destination
et `route_progress` sur les points de l’OFP. Les distances réutilisées sont
arrondies au NM par cet adaptateur existant. L’arrivée utilise la distance directe,
pas une prétendue distance de route active. Le prochain point géométrique et
la distance restante prévue sont affichés comme contexte. Un direct, un écart
à la route, une route avec boucles ou un déroutement peut fausser l’avancement.
Sans plan, ces calculs sont absents ; aucune trajectoire de remplacement n’est créée.

Dans Vol, choisir une phase puis « Enregistrer la phase » produit une valeur
`declared`. Le choix et sa date persistent dans la session privée, y compris
après rechargement ou redémarrage. Il suspend l’avancement automatique sans
écraser la dernière phase calculée. « Revenir en automatique » retire explicitement
le choix et reprend depuis cette dernière phase calculée, avec de nouvelles
temporisations. Une correction ne modifie jamais les cases ni les rappels.
Les commandes conservent les contrôles de jeton, d’univers et de session de #13.

Les messages SimConnect alimentent le moteur même lorsque Vol n’est pas ouvert.
Le scénario et la détection de péremption sont également évalués lors de la
lecture de session. Seuls les changements d’état sont persistés sous
`local/copilot/`, avec un événement historique lors d’un changement de phase.
Les anciens fichiers `/1` restent lisibles grâce aux valeurs initiales du nouvel
état ; une erreur d’écriture conserve le dernier état et est signalée.

Les tests `test_copilot_phases.py` utilisent exclusivement des données fictives,
une horloge contrôlée et des racines temporaires. Le parcours complet des 1 500 s
du scénario ne transmet que les mesures autorisées au moteur, jamais ses noms
de phases. Le parcours navigateur existant vérifie aussi le mode manuel,
le retour automatique et la conservation des gestes.
