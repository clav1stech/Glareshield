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

- Le clic de phase ouvre un aperçu ; « Je suis en … » est la correction déclarée,
  après laquelle la détection automatique reprend. Les valeurs vivantes
  proviennent des adaptateurs, pas de tableaux liés à un pourcentage fixe.
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

## État livré

Vol reproduit la maquette : bandeau, parcours des six phases avec l’étape en
cours, bloc Maintenant piloté par l’[étape détectée](copilot-phases.md), groupes
MCDU / FCU / checklists de la seule phase affichée, valeurs avec leur source
courte et saisie en place des inconnues, au plus trois messages radio, puis
situation, ATC, ATIS et repères à venir. Les rappels à acquitter et les
provenances détaillées de la version 1.2 ont été retirés de l’écran.

Le parcours navigateur (`tests/test_preparation_ui.cjs --browser`) vérifie sur
racine jetable et pilotes simulés : cases, saisie en place, copie radio, aperçu
et correction de phase, thèmes, 1 920 px, 780 px sans débordement, focus clavier
conservé au rafraîchissement. Le confort de lecture à distance d’un second écran
réel n’est pas mesuré par ces contrôles.
