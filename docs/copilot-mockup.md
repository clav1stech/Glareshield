# Référence des écrans du copilote

Source fournie par le propriétaire le 29 octobre 2026 :
`docs/Glareshield Copilote.html`, titre « Glareshield Copilote ».
SHA-256 de la source examinée :
`aaa449f3ea6aac4044627a8d89928585931bbd28e3ff22dd062ce5e380cb94b5`.
Le fichier source reste hors index ; ce document constitue la référence publique
générique de ses écrans et interactions, sans reprendre son trajet ni ses valeurs.
La maquette précédemment introuvable dans #10/#11 est donc identifiée.

## Écrans retenus

| Écran | Composition et comportements |
| --- | --- |
| Navigation permanente | Rail gauche : Initialisation, Vol, Réglages ; états simulateur/éclairage/IVAO en pied ; thème auto → clair → sombre |
| Initialisation | Cartes Simulateur, SimBrief, IVAO, Éclairage, Export IA, Notes du pilote ; résumé du plan et route ; points manquants ; « Démarrer le suivi du vol » ouvre Vol |
| Vol | Bandeau indicatif/trajet/appareil, heure UTC, arrivée prévue, âge OFP ; parcours cliquable de six phases ; deux colonnes |
| Colonne actions | Bloc Maintenant : action prioritaire, justification et prochain déclencheur ; groupes MCDU/FCU/Checklists avec compteur, cases, valeurs, source, inconnus visibles ; messages radio avec déclencheur/station/mode et copie individuelle |
| Colonne situation | Altitude, vitesse sol, vario, carburant ; distance/avancement/TOD ; ATC et fréquences ; ATIS et changement de lettre/données ; événements à venir |
| Réglages | Copilote et Affichage ; Intégrations (IVAO, SimBrief, Variables IA) ; Éclairage et matériel ; Application. Accès aux pages existantes depuis leur catégorie |

La maquette passe en une colonne sous 1 180 px et adapte le rail sous 820 px.
Elle prévoit focus visible, contraste clair/sombre, police adaptée au second
écran, chiffres alignés, réduction des mouvements et conservation du défilement
après cochage. Les messages copient le texte avec un retour « Copié » ; l’échec
invite à sélectionner le texte. Il n’y a aucune émission réseau radio.

## Ce qui est une interaction de démonstration

Dans la source HTML, cliquer une phase remplace les données fictives en mémoire ;
certains boutons affichent seulement un toast, les réglages segmentés ne sont
pas persistés, les cases automatiques sont désactivées et les phases passées
peuvent apparaître terminées sans action. Il n’y a ni connexion, ni moteur,
ni persistance, ni interprétation d’OFP. Les polices sont référencées sur un
service externe ; leur chargement n’est pas une obligation du produit.

Les identifiants courts `pre/dep/climb/cruise/desc/app` et les clés
`phase.indexGroupe.indexÉtape` appartiennent au prototype. Leur correspondance
de contrat est `preflight/departure/climb/cruise/descent/arrival` ; les étapes
de production ont des identifiants stables indépendants de leur position.

## Arbitrages qui priment sur les exemples de la maquette

- Le clic de phase est une correction déclarée ; les valeurs vivantes proviennent
  des adaptateurs, pas de tableaux liés à un pourcentage fixe.
- Toute case reste modifiable à la main, y compris une case automatiquement
  détectée ; décocher reste prioritaire. Avancer la phase ne termine rien.
- La piste active du MCDU n’est pas observable actuellement : confirmation
  manuelle. « APPR armé » et « LOC capturé » ne se déduisent jamais d’un voyant.
  La stabilité de l’ILS ne se déduit pas non plus des seuls signaux disponibles.
- Altitude OFP prévue et altitude autorisée sont distinctes. Une publication
  ATIS ne signifie pas écoutée ; les notes libres ne sont pas une clairance.
- TOD, minima, performances, fréquences et configurations illustratives ne
  deviennent pas des constantes. Sans source, afficher `<…>`. Le poste manquant
  reste un emplacement, sans question bloquante.
- L’éclairage indisponible et une intégration optionnelle désactivée ne bloquent
  pas le suivi. Les vrais prérequis et avertissements seront définis dans #12/#13.
- « Copier » prépare un message ; le pilote choisit quand et où l’émettre.

## Points restant à éprouver

La navigation Initialisation / Vol / Réglages est livrée par #12. Initialisation
réutilise les imports, notes et exports ; Vol reste un écran d’attente du service
de session. La lecture SimConnect active, connectée et récente et une télémétrie
AI Bridge récente sont les prérequis affichés pour le suivi réel ; OFP, IVAO et
éclairage sont facultatifs. Le bouton de démarrage demeure désactivé tant que
le service n’est pas livré. Le mode démonstration ne confirme aucun vol réel.

Le parcours des pages, l’import, les exports, les notes, le focus clavier après
rafraîchissement, les thèmes et les grandes polices sont testés avec une racine
jetable et des pilotes simulés (`tests/test_preparation.py`,
`tests/test_preparation_ui.cjs`). Les préférences persistent dans
`local/display.json` sans reconfiguration du moteur. Les états d’erreur,
périmés, désactivés et de démonstration ont des tests distincts. Le comportement
du futur bandeau Vol sur un second écran reste à éprouver lors de #16/#20.
La source suffit à identifier le dessin et ses interactions ; elle ne constitue
pas un test d’intégration de l’application. Le [contrat de données](copilot-contract.md)
fixe les règles de procédure qui remplacent ses simulations visuelles.
