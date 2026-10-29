# Rappels du suivi de vol

Depuis 1.2.7, les règles de `a320.json` sont évaluées dans le service métier.
Le profil privé peut les remplacer comme les procédures. Aucun rappel ne
commande le cockpit, ne coche une procédure ou ne crée une notification Windows.

| Rappel | Déclencheur embarqué |
| --- | --- |
| Préparation arrivée | Croisière et destination prévue à 180 NM ou moins en orthodromie, pendant 5 s ; ou TOD explicitement fourni dans les 15 prochaines minutes |
| Descente | Phase descente confirmée ou déclarée pendant 3 s ; aucune clairance déduite |
| 10 000 ft montant/descendant | Altitude vraie MSL : 3 s avant le seuil moins/plus 200 ft, puis 3 s de l’autre côté ; aucun FL100 supposé |
| ATIS acquis | Première publication actuelle disponible pour une position utile ; ce n’est pas un changement ni une écoute |
| ATIS modifié | Lettre différente ou texte différent à lettre identique, séparément |
| Présence ATC | Événement pertinent du flux IVAO partagé ; rapprochement ne signifie pas couverture certaine |

La distance est un **indice de préparation**, pas une estimation du TOD. Elle
réutilise position fraîche et OFP actuel. Un direct ou un déroutement peut la
rendre moins pertinente. Sans ces entrées, la condition manquante est affichée.
Le scénario nominal atteint cet indice en croisière avant sa descente à 1 000 s.

Un TOD fourni peut être déclaré via `selection.tod_utc`, avec une date ISO 8601
incluant son fuseau (`2026-01-01T12:30:00Z` est un exemple fictif), une référence
explicite et le contexte `stage: arrival`. Le champ figure dans le formulaire
de sélection de Vol. Une valeur invalide, révoquée, invalidée ou déclarée depuis
plus de 12 h laisse le TOD inconnu. Aucun TOD MCDU n’est lu ; aucun TOD
géométrique n’est fabriqué. La source et la méthode restent visibles.

Les temporisations sont continues : pause, perte de connexion, échantillon
périmé, retour d’horloge ou trou supérieur à 8 s remettent à zéro les attentes.
Un franchissement doit être observé des deux côtés ; une reprise en dessous
de 10 000 ft ne prouve pas un franchissement pendant la panne. Après redémarrage,
les temporisations et armements repartent à zéro.

Les événements déclenchés et leur acquittement persistent dans la session
privée. Un rappel reste présent jusqu’à son acquittement, y compris lorsque
les déclenchements sont suspendus. Acquitter ne signifie pas exécuter la
procédure ou annoncer un ATIS. Un même rappel de seuil n’est créé qu’une fois
par session. Les changements réseau conservent leur identité et leur curseur ;
une perte réseau ne fabrique aucune déconnexion ATC. Une publication différente
après une reprise reste une différence constatée, sans prétendre dater son
changement. Les notifications externes existantes ne sont jamais rappelées.

En phase critique (départ, arrivée hors parking, montée/descente sous 10 000 ft
AGL ou hauteur inconnue), seul le rappel le plus prioritaire de priorité ≥ 80
est affiché. Les autres sont maintenus et comptés comme différés. Ailleurs,
les cinq premiers apparaissent. Le premier peut prendre la place de l’action
dans « Maintenant » selon sa priorité ; les cases restent intactes.
