# Journal des changements

La politique est décrite dans [docs/versioning.md](docs/versioning.md).

## [0.1.1] - 2026-10-13

Module AI Bridge et refonte de l'interface, développés et éprouvés avec des pilotes
et données simulés uniquement.

- AI Bridge : SimVars standard lues par la connexion SimConnect existante ; LVars Fenix
  configurables localement.
- Valeurs qualifiées par unité, âge et statut (observée, périmée, indisponible,
  simulée, calculée) ; les valeurs de test de l'éclairage ne sont jamais exportées.
- Import manuel du dernier OFP SimBrief, résumé planifié, conservation du dernier
  plan valide et avertissements d'ancienneté ou d'incohérence.
- Export JSON versionné, essentiel ou détaillé, à copier pour un assistant IA,
  télécharger ou enregistrer dans `local/exports`.
- Scénario de vol et OFP fictifs pour éprouver le module sans simulateur.
- Module désactivé par défaut ; réglages séparés dans `local/ai-bridge.yaml`,
  appliqués sans redémarrer les éclairages ; routes protégées par le jeton de session.
- Interface refondue : navigation latérale par module, tableau de bord synthétique,
  messages non bloquants, thèmes sombre et clair, affichage mobile.

## [0.1.0] - 2026-10-09

Première publication de l'application existante et point de départ du versionnement.

- Application Windows locale, interface française et icône système.
- Lecture du simulateur, détection audio par processus et lecture passive du PTT.
- Éclairages Hue et Nanoleaf, restauration durable de leur état initial.
- Affectations indépendantes par fonction, groupes, portées et exclusions.
- Flashes MW prioritaires sur MC, superposés au fond ATC prioritaire sur DOME.
- Paramètres modifiables et descriptions lisibles des effets et réglages.
- Aperçus de trois secondes avant enregistrement, arrêt manuel et retour aux règles normales.
- Extinction Nanoleaf corrigée ; reconnexion de l'interface et renouvellement de session.
- Configuration personnelle et secrets exclus du dépôt.
- Politique `x.y.z`, contrôle de version et publication des releases depuis les tags.
