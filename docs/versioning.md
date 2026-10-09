# Politique de versionnement

La version est `x.y.z`, avec des entiers sans zéro initial. Sa source unique est
`project.version` dans `pyproject.toml` ; le tag Git associé est `vX.Y.Z`.

| Modification livrée | Incrémentation | Exemple |
| --- | --- | --- |
| Changement du comportement ou de l'interface, ajout, correction fonctionnelle | `z + 1` | `0.1.0` → `0.1.1` |
| Ensemble important de changements | `y + 1`, `z = 0` | `0.1.4` → `0.2.0` |
| Version majeure demandée explicitement par l'utilisateur | `x + 1`, `y = z = 0` | `0.2.3` → `1.0.0` |
| Documentation, orthographe, commentaires, tests seuls ou maintenance sans effet sur l'application | Aucune | `0.1.4` → `0.1.4` |

Une livraison constitue un changement, même si elle contient plusieurs fichiers
ou commits. Des modifications distinctes livrées successivement ont chacune
leur incrémentation. Une configuration personnelle dans `local/` ne constitue
pas une version du code et reste privée.

Le passage à une version majeure n'est jamais automatique. Le choix d'une
version mineure s'applique à un ensemble important et est décrit dans le
journal. Cette politique suit la demande du propriétaire ; elle ne suppose
pas qu'une incompatibilité impose à elle seule un changement de `x`.

## Préparer une livraison

Après les modifications de l'application, avant de les publier :

```powershell
local/.venv/Scripts/python.exe scripts/version.py bump patch --summary "Résumé de la modification"
# Pour un ensemble important : remplacer patch par minor.
local/.venv/Scripts/python.exe scripts/version.py check
```

L'outil modifie la version et ajoute une entrée datée dans `CHANGELOG.md`.
Relire et compléter cette entrée, exécuter les vérifications adaptées, puis
préparer uniquement les fichiers publics et vérifier leur index :

```powershell
local/.venv/Scripts/python.exe scripts/check_public.py
git diff --cached --check
git commit -m "Description de la modification"
git push origin main
git tag -a vX.Y.Z -m "Glareshield X.Y.Z"
git push origin vX.Y.Z
```

Remplacer `X.Y.Z` par la version effective affichée avec `scripts/version.py current`.
La release GitHub est créée automatiquement depuis le journal des changements.
Les archives source GitHub contiennent uniquement les fichiers suivis par Git.
Une publication de documentation seule ne crée pas de nouveau tag ni de release.

Une correction d'orthographe dans un fichier source se justifie par le trailer
`Glareshield-No-App-Change: correction de texte sans changement fonctionnel`.
Ce trailer est une déclaration à relire, pas une preuve automatique de l'absence
de changement. Chaque commit source concerné doit porter sa justification.
Pour vérifier une telle exception avant commit, utiliser
`scripts/version.py check --no-app-change "Correction d'orthographe seule"` ;
le trailer reste nécessaire au contrôle GitHub.

Pour une version majeure explicitement demandée, employer
`bump major --major-requested --summary "Résumé"` et ajouter au commit le trailer
`Glareshield-Major-Requested: true`.
Avant ce commit, la vérification locale utilise `check --major-requested`.

## Contrôle automatique

GitHub Actions vérifie les push sur `main`, les pull requests et les tags de
version. Il refuse un changement d'application non justifié sans augmentation
de version, une version qui recule, un tag qui ne correspond pas au projet,
une version majeure sans déclaration de demande explicite et un journal de
changements manquant. Les versions et contrôles de publication emploient
uniquement les fichiers publics ; aucun relevé de l'installation n'est envoyé.

La première release est **0.1.0**. Elle regroupe l'état déjà développé ; la
politique s'applique ensuite sans créer de versions rétroactives.
