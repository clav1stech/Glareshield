# Séparation des données

## Partie publique

Le code, les tests, les scripts et la documentation doivent être indépendants des appareils réellement présents. Les exemples utilisent des identifiants fictifs et des groupes abstraits. Aucun inventaire, nom de pièce réel, nom de machine, chemin utilisateur, adresse réseau, identifiant matériel, jeton ou journal personnel ne doit y figurer.

## Partie privée

Toutes les données d’une installation restent sous `local/` :

```text
local/
  planning/       # plan original et notes privées
  discovery/     # relevés du matériel et résultats de tests
  config/        # appareils, groupes, portées et règles personnels
  secrets/       # clés et jetons d’appairage
  state/         # snapshots et cache de découverte
  logs/          # journaux d’exécution
  sounds/        # fichiers audio personnels
```

Ces dossiers sont locaux ; leur contenu ne doit pas être copié dans la documentation publique. Les futurs composants de persistance devront respecter cette séparation. Un dépôt privé ne remplace pas cette règle.

## Suivi Git

Le `.gitignore` exclut tout à la racine, puis autorise explicitement les fichiers publics relus. Les futurs chemins publics seront autorisés au fur et à mesure du développement. `local/` demeure exclu.

Avant chaque publication : vérifier les fichiers suivis, le diff, les nouveaux exemples et les métadonnées de commit. Ne jamais utiliser `git add -f` pour des données privées. `.gitignore` ne retire pas un fichier déjà suivi et ne protège pas contre l’ajout d’informations personnelles dans un fichier public.
