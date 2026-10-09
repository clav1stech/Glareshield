# Instructions pour les modifications de Glareshield

- Conserver toute configuration personnelle, adresse, inventaire, nom de pièce,
  appareil, groupe, secret, relevé et journal dans `local/`, jamais dans Git.
  Les exemples et tests publics emploient des données fictives.
- Ne pas modifier les commandes du simulateur pour développer ou vérifier une
  modification. Utiliser les pilotes simulés et une racine de test distincte.
- Suivre [la politique de versionnement](docs/versioning.md).
- Pour chaque modification livrée qui change l'application, incrémenter `z`
  une fois avec `scripts/version.py bump patch --summary "Résumé du changement"`.
  Une livraison peut comprendre plusieurs fichiers et commits ; ne pas compter
  chaque fichier, étape de travail ou test comme une nouvelle version.
- Pour un ensemble important de changements, incrémenter `y` et remettre `z` à
  zéro avec `bump minor`. Décrire ce choix dans le journal des changements.
- Ne jamais incrémenter `x` sans demande explicite de l'utilisateur. Ne pas
  passer automatiquement à une version majeure pour une stabilisation ou une
  incompatibilité. `bump major` exige `--major-requested` et le commit doit
  porter le trailer `Glareshield-Major-Requested: true`.
- La documentation, les corrections d'orthographe, commentaires, tests seuls
  et tâches de maintenance sans changement de l'application ne montent pas
  la version. Si le changement touche un fichier de l'application, justifier
  l'exception avec `Glareshield-No-App-Change: <raison>` dans le commit.
- Avant publication, vérifier la version, exécuter les vérifications adaptées
  et auditer l'index avec `scripts/check_public.py`. Ne jamais publier `local/`.
- Publier les changements d'application avec leur entrée de `CHANGELOG.md`
  et un tag annoté `vX.Y.Z`. Pousser le tag après le code ; GitHub Actions crée
  la release depuis cette entrée. Ne pas remplacer un tag déjà publié.

Version de départ publiée : **0.1.0**. La règle s'applique aux prochaines
modifications ; l'historique antérieur n'est pas renuméroté.
