# Recette du Copilote — issues #10 à #20

Recette du 29 octobre 2026. Version de préparation : **1.2.9**. Chaque sous-issue
#18, #19 et #20 a reçu son incrément de patch demandé : 1.2.7, 1.2.8, 1.2.9.
Aucun changement de version mineure ni publication n’est déclenché par cette
recette. Les tags existants restent inchangés.

## Couverture des critères de #10

| Critère | Vérification reproductible | Résultat / limite |
| --- | --- | --- |
| Initialisation / Vol / Réglages et éclairage accessible | `test_preparation.py`, parcours `test_preparation_ui.cjs --browser` : toutes les catégories et pages existantes | Navigation, clavier et identité des ressources vérifiés |
| Initialisation : simulateur, éclairage, IVAO, SimBrief, export | `test_preparation.py`, `test_aibridge_web.py`, assertions de statut JS | États manquants, erreur, démonstration et exports distingués |
| Vol actualisé, cases, valeurs sourcées et radio copiable | `test_copilot_flight.py`, `test_copilot_observations.py`, `test_copilot_radio.py`, copie réelle du parcours Edge | Rafraîchissement sans perte de focus/cible, origine/heure et copie exacte vérifiés ; copier n’émet rien |
| Phase déduite et corrigeable | `test_copilot_phases.py`, `test_copilot_acceptance.py` | Treize étapes dans l’ordre, démarrage en vol, correction pilote, pause et remise des gaz vérifiés |
| Lisibilité second écran, clair/sombre | Parcours Edge aux résolutions ci-dessous, captures locales, taille agrandie | Mise en page et absence de débordement vérifiées ; distance physique et confort individuel non mesurés |
| Démonstration et pilotes fictifs sans réseau ni matériel | `test_copilot_acceptance.py` : 1 560 s rejouées avec horloge contrôlée ; transport qui refuse toute requête | Vol complet, Maintenant par étape, messages, validations et parking final vérifiés |
| Aucune donnée personnelle dans Git | `test_privacy.py`, audit d’un index temporaire par `scripts/check_public.py` | Chemins publics explicites, données/tests fictifs et racines privées isolées |

## Scénarios transversaux

- Le vol nominal traverse les treize étapes sauf la remise des gaz, dans l’ordre.
  « Préparer l’arrivée avant le TOD » est l’action affichée en croisière, avant
  la descente du scénario à 1 000 s. Le parking est confirmé dans la minute finale.
- Les tests rejouent décochage manuel face à une détection, correction de phase
  suivie de la reprise automatique, fin/reprise, redémarrage, même OFP, OFP
  corrigé et nouveau vol.
  Les preuves persistées n’autorisent jamais seules une détection actuelle.
- Pause, déconnexion/reconnexion, données absentes/périmées, horloge inversée
  et trous de télémétrie remettent les temporisations à zéro. Une remise des gaz
  conserve la phase arrivée et les cases ; le message reste un texte à choisir.
- IVAO désactivé, inconnu et périmé restent distincts. Les fixtures produisent
  première acquisition ATIS, lettre modifiée, texte modifié à lettre identique,
  connexions/déconnexions réelles du scénario et panne sans fausse déconnexion.
- Les acquittements persistent. Les événements ne sont pas renotifiés à chaque
  rendu ; le moteur ne rappelle pas l’overlay existant. Un débordement du flux
  repart de l’état courant sans inventer les événements manqués.
- Les tests moteur/runtime couvrent priorités, aperçus temporaires, restauration,
  affectations et conservation des connexions. `test_telemetry_source.py`
  vérifie le processus SimConnect partagé et l’exclusion des tests d’éclairage.
  Le navigateur vérifie que modes, thèmes et imports conservent les identités
  moteur, simulateur, pilotes et tâches. Aucune commande cockpit n’est modifiée.

## Conditions de recette visuelle

Microsoft Edge en mode automatisé sans fenêtre, zoom standard : 1 440 × 1 080
et 1 920 × 1 080, thèmes clair/sombre ; parcours réduit à 780 × 1 000. Vérifications
clavier de navigation, focus conservé au rafraîchissement, clic maintenu pendant
un rafraîchissement, brouillons conservés, contraste des statuts, détection,
copie radio et état de perte/reprise de connexion HTTP. Captures dans
`local/ui-test/`. Aucune validation à distance physique ou sur cockpit réel
n’est déduite de ces contrôles.

## Préparation de publication

La version vient de `pyproject.toml` et les trois entrées sont dans `CHANGELOG.md`.
Exécuter les tests, `scripts/version.py check`, `git diff --check`, puis préparer
uniquement les chemins publics et auditer leur index avec `scripts/check_public.py`.
L’audit de préparation utilise un index temporaire afin de préserver l’index
de travail existant. Les données de recette et captures restent sous `local/`.

La publication reste une action distincte : commit du code et du journal,
push du code, création d’un tag annoté correspondant à la version livrée, puis
push de ce tag. Ne jamais déplacer un tag publié. Les scripts de recette
n’exécutent ni commit, ni push, ni création de tag.
