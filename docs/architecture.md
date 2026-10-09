# Architecture prévue

Processus Python asynchrone, interface HTTP limitée à la boucle locale, page web sans compilation front-end et icône système. La version de Python et les dépendances seront validées sous Windows avant développement.

## Composants

- Configuration : validation stricte, sauvegarde atomique et séparation des secrets.
- Modèle : appareils, groupes imbriqués, portées, sources, effets et règles.
- Sources : simulateur, activité audio par processus et commandes simulées.
- Moteur : priorités, rendu différentiel, limitation de cadence et restauration des états.
- Pilotes : découverte, capture d’état, application et restauration.
- Interface : configuration, sondes, tests manuels et état des connexions.

Les appareils, groupes, variables, couleurs, seuils et affectations sont configurables. Les noms et valeurs des variables du simulateur ne seront pas inventés.

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
