# Contexte réseau du copilote

Livré en 1.2.4 pour l’[issue 15](https://github.com/clav1stech/Glareshield/issues/15),
dans le suivi de #10. Le collecteur de la PR #9 (`claude/ivao-network`), déjà
intégré à la ligne 1.1, reste l’unique `IVAOService` : Whazzup, ATIS, météo,
temporisations, limites de fréquence, erreurs, cache et notifications existantes.
Le contrat #11 et la session #13 sont réutilisés ; les phases viennent de #14.

## Accès commun

`AIBridge.flight_network` est l’unique adaptateur métier (`NetworkContext`).
`SessionService.view()` l’appelle avec la phase effective et les déclarations de
la session. `GET /api/ai/session` expose cette vue dans `network`, schéma
`glareshield.copilot_network/1`. Vol lit cette section. Les moteurs de rappels #18
et de radio #19 consomment la même section, ou appellent ce même service
avec les mêmes phase et session, sans client réseau ni copie persistante du cache.
Ces moteurs ne sont pas encore livrés ; ce lot établit leur point d’accès commun.
Les exports `glareshield.flight_context/3` et la page Réseau IVAO restent compatibles.

Toutes ces lectures utilisent les données déjà collectées. Un rendu ne lance ni
`refresh`, ni `fetch`, ni téléchargement d’ATIS. Le cache reste en mémoire ; les
déclarations et leurs révisions restent dans `local/copilot/`. Les plans et
déclarations de l’autre univers (démonstration / SimConnect) sont exclus de la
vue du suivi. Les publications IVAO gardent leur nature publiée, même en démonstration.

| Champ | Sens |
| --- | --- |
| `state: disabled` | Intégration désactivée, positions inconnues (`null`) |
| `state: unknown` | Intégration active, aucun Whazzup valide reçu, positions `null` |
| `state: empty` | Whazzup actuel reçu, aucune position candidate retenue, positions `[]` |
| `state: current` | Whazzup actuel, positions candidates présentes |
| `state: stale` | Échec de récupération ou données anciennes ; dernière liste conservée, même vide |
| `feeds` | Provenance, URL, récupération, âge de récupération et de publication du flux, erreur éventuelle |
| `positions` | Indicatif, type, fréquence publiée si connue, `matched_by`, provenance, phases utiles, couverture non confirmée |
| `atis` | Texte et lettre téléchargés, référence du texte, horodatages, âge, méthode de rapprochement et changements |
| `weather` | METAR/TAF par aérodrome, texte, état de publication, provenance et lecture des valeurs METAR |
| `publications.departure/arrival` | QNH, température et vent du METAR IVAO correspondant, sous enveloppes qualifiées |
| `used_station` | Déclaration explicite du pilote ; sa présence publiée est distinguée dans `used_station_state` |
| `pilot_atis` | Déclarations consultées/annoncées distinctes et comparaison éventuelle de lettre |
| `events` | Lecture non consommatrice du flux d’événements du collecteur |

`empty` ne signifie pas qu’il n’existe aucun contrôleur sur tout le réseau ni
qu’UNICOM est requis. Les états des trois flux restent indépendants : un Whazzup
périmé ne rend pas automatiquement un METAR récent périmé, et inversement.
Une phase inconnue ne produit pas de classement courant/suivant inventé ; une
phase ancienne garde son statut dans `phase_status` pour les futurs consommateurs.

## Positions et station utilisée

La sélection réutilise `airports_of_interest`, `match`, `rank` et les rayons IVAO
existants. Aucun deuxième algorithme de secteurs n’est ajouté. Les observateurs
sont exclus. La vue de suivi ne tronque pas les positions retenues comme un export
limité en taille. Une station explicitement déclarée est incluse même si elle est
lointaine ; son absence du flux actuel est signalée sans supprimer la déclaration.

`useful_for` vaut `current` et/ou `next`, d’après les rôles des gabarits radio du
profil, pour la phase courante et la suivante. Le départ est associé à l’origine,
l’arrivée à la destination ; les centres restent candidats en route. Les autres
positions sélectionnées sont conservées avec une liste de phases utiles vide.
Les dégagements et aérodromes manuels restent consultables dans les publications.
Le déroutement opérationnel et l’adaptation aux sous-états restent à raccorder.

Chaque `matched_by` est conservé. Ni proximité, ni portée publiée, ni préfixe OACI
ne prouvent la couverture réelle ; `coverage` reste `unconfirmed`, y compris
après déclaration pilote. Le champ historique `covers` d’un ATIS voisin décrit
un rapprochement technique, pas une certification de couverture. Aucun contrôleur,
transfert ou fréquence n’est choisi automatiquement comme certain.

Vol permet de déclarer `kind=station`, `field=station.callsign`, avec indicatif,
phase de déclaration et référence. La déclaration peut être remplacée ou révoquée,
elle survit au redémarrage et une correction d’OFP l’invalide comme les autres
déclarations de contexte. Elle ne règle aucune radio et ne transmet rien.

## Publications et ATIS réellement consulté

Le texte ATIS libre n’est pas interprété (`reading_status: not_interpreted`).
Sa lettre et son texte restent téléchargés, sans cocher d’étape, déclarer une
écoute ou annoncer une lettre au contrôleur. Les saisies `atis.heard_letter` et
`atis.announced_letter` ont chacune leur heure, référence, aérodrome, version et
révision ; l’une ne crée jamais l’autre. Une station peut être précisée dans le
contexte de déclaration pour lever une ambiguïté entre plusieurs ATIS.

La comparaison n’est disponible que pour un unique ATIS associé par préfixe à
l’aérodrome déclaré, actuel, et deux lettres explicites. Elle vaut `same_letter`,
`different_letter` ou `unknown`. Une même lettre ne prouve pas que le texte n’a
pas changé ; sa référence et les événements de modification du texte sont conservés.
Un ATIS rapproché uniquement par distance ne confirme pas celui de l’aérodrome.

L’extraction METAR accepte uniquement les groupes reconnus de l’observation,
avant tendance/remarques : `Qdddd` en hPa, température signée en °C, groupe de vent
avec unité explicite KT/MPS conservé en texte. Pas de conversion `Axxxx`, de lecture
du TAF en conditions actuelles, ni de déduction depuis les phrases ATIS. Groupe
absent, doublon ou valeur ambiguë, texte tronqué ou format inconnu donnent
`value: null`, `status: unavailable`. Le statut de lecture (`parsed`, `missing`,
`ambiguous`, `truncated`, `unsupported`) et le texte source sont toujours joints.
Une date d’observation absente interdit de proposer une valeur actuelle.

Ces valeurs sont `QualifiedValue(nature=published)`, source `ivao.metar`, avec
référence, unité et âge. La limite de proposition est 1 200 s, conformément au
profil embarqué. L’âge retenu conserve le plus ancien des instants nécessaires
(récupération et publication). Une erreur ou un flux périmé l’emporte immédiatement.
Un Whazzup fraîchement téléchargé dont `updatedAt` est ancien reste périmé.
Les textes et anciennes valeurs restent lisibles avec leur état ; une péremption
n’est jamais masquée par l’heure de rendu. La météo OFP et les conditions observées
MSFS restent dans leurs sources existantes ; aucune fusion ni comparaison implicite.

## Événements pour les rappels

`IVAOService.event_view(after=0)` expose le flux commun. Les événements sont
produits pendant la collecte par les mécanismes existants `track_presence` et
`track_atis` : `connected`, `disconnected`, `atis_new`, `atis_changed` (lettre
ou texte). Le premier téléchargement sert de référence ; il ne crée pas une
rafale de connexions. Un échec de téléchargement ne crée pas de déconnexions.
Un contrôleur déjà en ligne qui entre seulement dans le rayon n’est pas annoncé
comme nouvellement connecté. Présence : positions suivies par le mécanisme
existant, y compris les centres sur la route ; ATIS : changements du cache global.
Les rappels filtrent par position/contexte et vérifient la fraîcheur.

Chaque événement porte une séquence et une date de détection. `stream_id` change
au redémarrage ; `latest_sequence`, `oldest_sequence` et `gap` permettent à chaque
consommateur de gérer son propre curseur et une interruption. Le tampon conserve
au plus 256 événements en mémoire et est vidé à la désactivation. Il ne garantit
pas le rejeu après redémarrage ou débordement. Changer de flux ou rencontrer `gap`
impose de repartir de l’état courant, sans supposer que tous les événements ont
été observés. Les rappels persistants restent du ressort de #18 et de la session.

La lecture ne consomme rien et renvoie des copies. Elle ne déclenche aucune
notification. L’overlay existant garde ses préférences et reste l’unique mécanisme
de notification de présence ; le moteur ne le double pas pour le même
événement. Le flux existe même si les notifications overlay sont désactivées.

Les tests hors réseau couvrent les quatre états d’indisponibilité, la fraîcheur
de chaque source, les publications ambiguës, les événements, leurs curseurs et
leur débordement, les déclarations persistantes, la séparation des univers et
l’absence de téléchargement pendant les lectures de pages. Toutes les données
sont fictives et les racines de test sont distinctes de l’installation.
