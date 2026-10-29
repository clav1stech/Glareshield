# Sessions du copilote

Livré avec l’[issue 13](https://github.com/clav1stech/Glareshield/issues/13),
en version 1.2.2. Le suivi se démarre depuis Initialisation ou Vol, se termine
et se reprend explicitement. Une session active est reprise automatiquement
après navigation, rafraîchissement et redémarrage de l’application. Son état
appartient au service `SessionService`, pas à la page ni au stockage navigateur.

## Identité du suivi et du plan

Chaque suivi possède un identifiant local aléatoire, un univers (`demo` ou
`simconnect`), un profil et sa révision. Le lien à SimBrief suit cette règle,
également affichée dans Initialisation :

- Avec `ofp_id`, cet identifiant définit le plan. Un nouvel import identique
  conserve toutes les cases, déclarations, phases et informations de rappel.
- Un contenu différent pour le même identifiant est une correction : les cases
  restent cochées ou décochées, la révision du plan augmente et les déclarations
  sont marquées à vérifier. Leurs valeurs et leur provenance restent visibles.
- Sans `ofp_id`, l’identité est le hachage du vol (indicatif et numéro), des codes
  départ/destination et de l’heure de départ prévue. La date de génération et
  celle d’import ne définissent pas cette identité. Modifier ces éléments
  identitaires ouvre donc un nouveau suivi ; les autres corrections le conservent.
- Un nouvel identifiant de plan termine et archive le suivi actif, puis ouvre
  un suivi vide. L’interface signale ce changement. Aucun historique n’est effacé.
- Sans plan, le suivi fonctionne. Le premier plan du même univers s’y attache,
  conserve les cases et fait vérifier les déclarations existantes. Retirer un
  plan ne supprime pas son lien historique ni la progression. Réimporter un
  autre plan applique la règle précédente.
- Un suivi terminé reste terminé lors d’un import. Reprendre le suivi applique
  alors les règles du plan courant ; Démarrer après une fin crée un nouveau suivi.

Un OFP de démonstration n’est jamais attaché à un suivi SimConnect, et un OFP
SimBrief n’est jamais attaché à la démonstration. Changer de mode retrouve le
dernier suivi de cet univers ; l’autre reste conservé. Aucun plan n’est requis.
Le démarrage SimConnect exige AI Bridge activé et une connexion récente hors
pause. Reprendre un suivi existant reste possible pendant une déconnexion pour
consulter ou compléter les gestes manuels ; les observations ne sont pas actuelles.

## Actions et déclarations

Les cases sont indexées par identifiant stable d’étape. Cocher **ou décocher**
est un geste manuel durable, prioritaire sur toute validation détectée. La
provenance, la mesure détectée et une contradiction éventuelle restent visibles.
Une phase forcée ne modifie aucune case. Depuis la version 1.2.3,
« Revenir en automatique » retire explicitement ce choix et reprend le
[moteur de phases](copilot-phases.md), avec de nouvelles temporisations.

Les formulaires proposent des saisies distinctes :

| Saisie | Contexte et référence |
| --- | --- |
| Clairance | Type, station/origine, valeur reçue, unité éventuelle et référence |
| Piste, SID, STAR ou approche retenue | Départ ou arrivée, choix et référence ; ce choix n’est pas une autorisation |
| ATIS effectivement consulté | Aérodrome, lettre, version du bulletin, référence et heure de consultation saisie |
| Performance manuelle | Valeur numérique, unité, référence EFB/OFP, appareil, piste, masse, configuration et météo |

Chaque déclaration conserve un identifiant, une révision, l’heure de saisie,
l’heure déclarée (heure de saisie par défaut), la référence et le contexte.
Une nouvelle valeur du même champ remplace explicitement la précédente, qui
reste dans l’historique avec sa date de révocation. Les choix départ et arrivée,
ainsi que les ATIS de différents aérodromes, ont des portées séparées. Un bouton
permet de révoquer une déclaration. Un changement de choix, d’ATIS ou de
clairance demande de confirmer les performances ; un nouveau contexte de
performance invalide également les autres performances liées à l’ancien contexte.
Une correction du plan fait vérifier toutes les déclarations conservées.

Les notes libres existantes restent indépendantes : ni parsing, ni déduction
de clairance, de performance ou de consultation ATIS. Les valeurs du plan sont
prévues ; l’import ne produit aucune déclaration du pilote.

## Persistance et récupération

Les deux fichiers privés sont `local/copilot/sessions-demo.json` et
`local/copilot/sessions-simconnect.json`, schéma `glareshield.copilot_session/1`.
Ils contiennent le suivi courant et les suivis archivés. Une écriture atomique
précède la mise à jour en mémoire : un échec laisse le dernier état intact et
est signalé. La limite de 8 Mio bloque explicitement une nouvelle écriture,
sans tronquer l’historique. Les données ne doivent jamais être ajoutées à Git.

Un fichier absent donne un état vide. Un fichier illisible, ancien, trop
grand ou incohérent reste intact ; l’interface signale le problème et
bloque les modifications du suivi concerné. « Réinitialiser le suivi » demande
une confirmation puis conserve ses octets dans un fichier privé
`sessions-<univers>-preserved-<identifiant>.json` avant de créer le suivi vide.
Si la sauvegarde échoue, la réinitialisation échoue également.

Pour un fichier valide, la réinitialisation archive le suivi courant puis
ouvre un suivi vide. C’est aussi la règle de migration d’un profil dont
l’identifiant ou la révision a changé : afficher et conserver l’ancien état,
exiger une réinitialisation explicite, sans transfert implicite des cases.

## Intégration et limites

AI Bridge possède l’unique service de session. Les imports synchronisent ce
service quel que soit l’écran affiché. Les API `/api/ai/session` réutilisent le
jeton de session HTTP et les restrictions d’hôte existants, pour les lectures
comme pour les écritures. Chaque geste précise l’identifiant de suivi et
l’univers affichés : un ancien onglet reçoit un conflit HTTP 409 si le suivi
a changé, au lieu d’affecter le nouveau vol.

Le service évalue les règles `observed` du profil depuis la version 1.2.6 ;
voir les [conditions de validation par appareil](copilot-contract.md#validation-des-étapes).
L’ancien point d’injection interne `record_detection` est remplacé par cette
évaluation des données qualifiées. Aucune API publique ne permet de fabriquer
une détection. `remember` conserve les références et horodatages des rappels.
Les preuves persistent comme historique ; elles exigent une reconfirmation
après redémarrage, une connexion récente hors pause et un âge inférieur ou
égal à 8 s (ou le délai plus court du champ) pour être présentées comme actuelles.

Le lot initial 1.2.2 ne calculait ni phase, ni performances, ni validation automatique
à partir de la télémétrie. Le moteur de phases est raccordé depuis la 1.2.3.
Aucun client SimConnect ou IVAO supplémentaire, aucune écriture
cockpit et aucune reconfiguration des ressources d’éclairage. Les exports
`glareshield.flight_context/3` et les notes conservent leur contrat actuel.

Les tests `test_copilot_session.py` utilisent des racines temporaires et des
plans fictifs. Le parcours Edge de `test_preparation_ui.cjs --browser` vérifie
les cases, déclarations, navigation, rechargement, phase forcée, fin/reprise et
la conservation de l’identité des ressources du moteur sur le serveur simulé
décrit dans le README.
