# Détection de la phase du vol

`copilot/phases.py` répond à une seule question : où en est l'appareil ?
Il lit uniquement la télémétrie SimConnect déjà collectée (ou le scénario de
démonstration) et la destination de l'OFP. Il ne lit ni les cases cochées, ni
les moteurs d'éclairage, ni une page MCDU, ni un mode de guidage, et n'envoie
aucune commande au simulateur.

## Treize étapes, six phases

Les six phases du contrat restent la structure de l'écran. Chacune est découpée
en étapes plus fines, qui pilotent « Maintenant » et les messages radio.

| Phase | Étapes |
| --- | --- |
| Prévol | Au poste · Repoussage / mise en route |
| Départ | Roulage · Décollage |
| Montée | Montée |
| Croisière | Croisière |
| Descente | Descente |
| Arrivée | Approche · Finale · Remise des gaz · Atterrissage · Roulage · Au poste |

## Transitions

Chaque étape n'autorise que les transitions qui ont un sens depuis elle. Une
condition doit rester vraie pendant la durée indiquée ; toute interruption la
remet à zéro. Les seuils sont regroupés dans `PhaseThresholds`.

| Depuis | Vers | Condition | Durée |
| --- | --- | --- | --- |
| Au poste | Repoussage | Au sol, vitesse sol ≥ 1 kt ou un moteur en marche | 3 s |
| Au poste, repoussage | Roulage | Au sol, vitesse sol > 6 kt | 5 s |
| Prévol, roulage | Décollage | Vitesse sol ≥ 40 kt, ou en vol | 2 s |
| Décollage | Roulage | Au sol sous 30 kt sans avoir volé (décollage interrompu) | 5 s |
| Décollage | Montée | En vol, au-dessus de 1 500 ft sol | 3 s |
| Montée | Croisière | Vario entre −300 et +300 ft/min, altitude ≥ niveau prévu − 4 000 ft | 60 s |
| Montée, croisière | Descente | Vario < −500 ft/min et 3 000 ft sous le plus haut niveau atteint | 20 s |
| Descente | Croisière | Nouveau palier haut, à plus de 90 NM de la destination | 120 s |
| Montée, croisière, descente | Approche | Vario ≤ +300 ft/min et : destination ≤ 30 NM sous 8 000 ft sol, ou (en descente) sous 3 000 ft sol | 5 s |
| Approche | Finale | Sous 1 500 ft sol en descente | 2 s |
| Approche, finale | Remise des gaz | Vario > +500 ft/min | 5 s |
| Remise des gaz | Approche | Vario < −300 ft/min | 15 s |
| En vol | Atterrissage | Retour au sol | 2 s |
| Atterrissage | Roulage | Vitesse sol < 30 kt | 5 s |
| Roulage, atterrissage | Au poste | Vitesse sol < 1 kt | 20 s |

Sans niveau prévu dans l'OFP, la croisière exige 20 000 ft. Le palier de
croisière est comparé à l'altitude indiquée (altitude vraie si elle manque),
avec une marge large : en altitude, l'écart entre altitude vraie et niveau de
vol dépasse souvent 1 000 ft. C'est ce qui empêchait la version 1.2 de
reconnaître la croisière, et donc la descente.

La descente n'exige plus d'avoir vu la croisière : un vol court ou un palier
imposé par l'ATC est suivi correctement. Un palier de descente de 1 000 à
2 000 ft en croisière ne déclenche pas la descente.

## Démarrage, interruptions et correction

- **Démarrage du suivi** : l'appareil est placé directement d'après ses mesures
  (au sol, en montée, en croisière, en descente ou près de la destination),
  après 3 s stables. Le suivi peut donc commencer en plein vol.
- **Pause, déconnexion, mesure absente ou périmée (> 8 s)** : l'étape est
  conservée, les temporisations repartent à zéro, aucune transition n'a lieu.
  Une entrée manquante n'interdit que les transitions qui l'utilisent.
- **Correction du pilote** : cliquer une phase du parcours l'affiche en aperçu ;
  « Je suis en … » la déclare. Le suivi automatique reprend aussitôt à partir
  de cette phase : il n'y a plus de mode manuel figé à désactiver.

Seuls les changements d'étape et les nouveaux plus hauts niveaux (par pas de
500 ft) sont écrits sous `local/copilot/`, avec un événement d'historique par
étape. Les sessions de la version 1.2 sont relues : leur phase devient l'étape
d'entrée correspondante.

Les tests `test_copilot_phases.py` et `test_copilot_acceptance.py` utilisent
uniquement des données fictives, une horloge contrôlée et des racines
temporaires. Le scénario de démonstration de 1 560 s traverse toutes les étapes
dans l'ordre à partir de la seule télémétrie, sans jamais lire le nom de phase
du scénario.
