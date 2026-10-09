# Phase 0 — Découverte

Objectif : vérifier les possibilités réelles des intégrations avant d’écrire les pilotes. Les observations, inventaires et adresses sont consignés exclusivement dans `local/discovery/`.

Les outils sont regroupés sous `scripts/` : découverte mDNS/AirPlay, appairage des éclairages, mesure des sessions audio sur toutes les sorties Windows et lecture de LVars explicitement renseignées. Les commandes figurent dans le README. Les outils d’appairage créent des accès persistants et nécessitent le geste d’autorisation sur le matériel ou dans l’application constructeur ; leurs clés restent sous `local/secrets/`.

Sources techniques : [découverte et démarrage Hue](https://developers.meethue.com/develop/get-started-2/), [API Essentials Wi-Fi Nanoleaf](https://nanoleaf.atlassian.net/wiki/spaces/nlapid/pages/2296381472/Nanoleaf+Matter+WiFi+Essentials+Open+API+Documentation), [scan et connexion pyatv](https://pyatv.dev/development/scan_pair_and_connect/), [pycaw](https://github.com/AndreMiras/pycaw), [variables Fenix](https://support.fenixsim.com/hc/en-us/articles/12466468901135-Example-of-How-to-Bind-Switches-Knobs-and-Buttons-on-FenixSim-Aircraft-to-External-Hardware).

## Vérifications

- Compatibilité de Python et des dépendances sous Windows.
- Découverte réseau et identification stable des équipements.
- Accès aux API locales d’éclairage et décision de repli si nécessaire.
- Variables du simulateur : noms, valeurs, positions et acquittement observés.
- Client IVAO : processus, sortie audio et comportement des notifications texte.
- AirPlay : découverte, éventuel appairage et comportement des cibles audio.
- Hue : zones de divertissement et coexistence avec une synchronisation existante.

## Acceptation

Chaque point est renseigné et les intégrations non disponibles font l’objet d’une décision explicite. Aucune adresse, variable constructeur ou valeur d’API non vérifiée n’est présentée comme acquise.
