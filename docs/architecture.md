# Architecture

Processus Python asynchrone, interface HTTP limitée à la boucle locale, page web sans compilation front-end et icône système. Les appels bloquants SimConnect sont isolés dans un processus supervisé ; les mesures audio utilisent un thread COM dédié.

## Composants

- Configuration : validation stricte, sauvegarde atomique et séparation des secrets.
- Modèle : appareils, groupes imbriqués, portées, sources, effets et règles.
- Sources : simulateur, activité audio par processus et commandes simulées.
- Moteur : priorités distinctes entre clignotements et fonds fixes, superposition, rendu différentiel, limitation de cadence et restauration des états.
- Pilotes : découverte, capture d’état, application et restauration.
- Interface : configuration, sondes, tests manuels et état des connexions. La page est servie sans compilation : `index.html`, `app.css`, `app.js` pour l'éclairage et `ai.js` pour AI Bridge.
- AI Bridge (`aibridge/`) : catalogue de SimVars, stockage horodaté des observations, scénario de démonstration, résumé SimBrief et document de contexte versionné. Le module lit les variables par la connexion SimConnect existante, dans la boucle de lecture, après les LVars d'éclairage et au plus une par tour, et conserve ses réglages dans `local/ai-bridge.yaml`. Une intégration IVAO facultative (`aibridge/ivao.py`) télécharge dans sa propre tâche les flux publics Whazzup, METAR et TAF ; l'interface et les exports lisent son cache en mémoire. Voir [AI Bridge](ai-bridge.md).
- Copilote (`copilot/`) : profil A320 validé en données, session persistante,
  détection d'étape (`phases.py`), résolution des valeurs, observations
  qualifiées et modèle de l'écran Vol (`cockpit.py` : Maintenant, groupes,
  radio, situation, ATC et ATIS filtrés). `session.py` orchestre ces services ;
  `copilot.js` dessine Vol et transmet les gestes, en conservant le focus au
  rafraîchissement. La radio lit le même adaptateur réseau, sans émission.
  Les écritures atomiques et historiques restent sous `local/copilot/`.
- Recette hors réseau : `DemoNetwork` fournit des fixtures au même adaptateur
  IVAO dans un cache séparé, sans tâche ni téléchargement. Le scénario fournit
  la télémétrie dans son magasin distinct jusqu’au parking. Les réglages et le
  cache réels restent séparés. Voir le [guide](copilot-guide.md) et la
  [matrice de recette](copilot-acceptance.md).

Les appareils, groupes, variables, couleurs, seuils et affectations sont configurables. Les noms et valeurs des variables du simulateur doivent être vérifiés dans chaque installation. L’application lit le simulateur ; elle ne fournit aucune commande d’écriture vers le cockpit, y compris dans AI Bridge.

Les snapshots conservent la définition de l’appareil pour permettre une récupération même après modification de la configuration. Le pilote Hue reprend les scènes dynamiques identifiées et invalide les états affectés afin que les règles encore actives soient réappliquées. Les erreurs n’exposent pas les URL contenant des jetons.

## Ordre de réalisation

0. Découverte et validation des intégrations.
1. Socle, pilotes simulés et tests du moteur.
2. Intégration Hue et mesure du débit.
3. Intégration Nanoleaf ou décision de repli.
4. Source simulateur et gestion de la pause.
5. Alertes et éclairage d’ambiance.
6. Détection audio IVAO.
7. Sorties AirPlay.
8. Interface et icône système.
9. Durcissement et livraison.

Chaque phase doit satisfaire ses critères d’acceptation avant la suivante. Les résultats propres à une installation restent dans `local/discovery/`.
