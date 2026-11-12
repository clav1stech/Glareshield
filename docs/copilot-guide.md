# Utiliser le suivi Copilote

## Préparer et suivre un vol

1. Dans **Initialisation**, vérifier simulateur et AI Bridge, importer l’OFP et
   consulter son résumé. IVAO et l’éclairage restent facultatifs.
2. **Démarrer le suivi du vol** ouvre **Vol**. La phase est détectée seule, y
   compris si le vol est déjà en cours ([règles de détection](copilot-phases.md)).
3. Lire **Maintenant** : une seule action, celle de l’étape en cours (au poste,
   roulage, montée, approche…), avec les faits utiles (piste, ATIS, distance,
   carburant) et ce qui déclenchera l’étape suivante.
4. Cocher les lignes MCDU, FCU et checklists de la phase. Seule la phase en
   cours est affichée ; ses valeurs viennent de l’OFP, du METAR ou de la
   saisie pilote, indiquée en petit à côté de la valeur.
5. Une valeur inconnue apparaît en pointillés, par exemple `<V1>`. Un clic
   permet de la saisir (Entrée pour valider, Échap pour annuler). Une saisie
   prime sur l’OFP : piste changée, altitude autorisée, squawk, poste… Vider
   le champ revient à la valeur prévue.
6. **Radio** propose les appels de l’étape, avec la station en ligne et sa
   fréquence, puis un modèle de réponse à employer seulement si l’instruction
   correspondante a été reçue. **Copier** ne transmet rien. Sans contrôle coché,
   les annonces UNICOM texte en anglais remplacent les appels concernés.

La colonne de droite résume la situation (altitude, vitesse sol, vario,
carburant et écart au plan, distance parcourue avec le TOD de l’OFP), l’ATC
utile à la phase (aérodrome de départ, puis centres proches, puis arrivée),
l’ATIS de l’aérodrome concerné avec son changement de lettre, et les prochains
repères.

Cliquer une autre phase du parcours l’affiche en **aperçu** pour préparer la
suite. **Je suis en …** corrige la phase : le suivi automatique reprend alors
à partir d’elle. Une correction ne coche aucune case.

Pour reprendre, ouvrir Vol ou choisir **Reprendre le suivi** après une fin.
Les cases, valeurs saisies et l’étape restent sous `local/copilot/`. Un OFP
corrigé conserve les cases ; un nouveau vol archive le suivi précédent. Les
sessions de démonstration et SimConnect sont distinctes.

## Démonstration complète hors réseau

Pour une recette sans configuration installée, utiliser une racine séparée et
les pilotes fictifs publics. Depuis la racine du dépôt :

```powershell
New-Item -ItemType Directory -Force local/copilot-demo
$env:PYTHONPATH='src'
local/.venv/Scripts/python.exe -m glareshield.app --root local/copilot-demo --config examples/demo.yaml --port 18768 --no-tray
```

Ouvrir l’adresse locale affichée. Dans Réglages / Copilote ou les pages AI Bridge,
lancer la **démonstration**, puis charger l’OFP fictif depuis Plan de vol.
Revenir à Initialisation et démarrer le suivi. Le scénario de 26 minutes couvre
les six phases jusqu’au parking, avec télémétrie fictive et cache IVAO fictif.
Les valeurs et le réseau portent leur origine de démonstration. Aucun compte
SimBrief, simulateur, matériel ou accès réseau n’est nécessaire à ce parcours.
La connexion réelle et ses réglages ne sont pas reconfigurés par le mode démo.

Le réseau embarqué produit : départ d’une position sol à 300 s, arrivée d’une
approche à 600 s, changement de lettre ATIS à 900 s, changement de texte à
1 080 s, panne du flux entre 1 160 et 1 220 s, puis disparition/réapparition
de la tour à 1 300/1 400 s. La panne conserve les anciennes positions sans
fabriquer de déconnexion. Le parking final dure de 1 500 à 1 560 s.

La recette automatisée rejoue ce parcours avec une horloge contrôlée :

```powershell
local/.venv/Scripts/python.exe -m pytest tests/test_copilot_acceptance.py -q --basetemp local/copilot-acceptance-run
```

Pour la recette navigateur simulée, utiliser `tests/test_preparation.py`, puis
`node tests/test_preparation_ui.cjs --browser` avec Playwright/Edge disponible.
`GLARESHIELD_TEST_URL` permet de choisir l’URL d’un serveur de recette isolé.
Les captures restent sous `local/ui-test/`, jamais dans Git.

## Limites

- La validation automatique d’une case exige une [correspondance de source
  validée pour l’appareil](copilot-contract.md#validation-des-étapes). Sinon,
  la case reste manuelle.
- Le TOD n’est connu que s’il figure dans le journal de navigation de l’OFP ;
  il n’est pas lu dans le MCDU.
- Les stations ATC sont rapprochées par indicatif et distance : une station
  proposée n’est pas une couverture confirmée. Le nom prononcé est déduit de
  l’OFP (aérodromes) ou de l’indicatif (centres) ; le relire avant d’émettre.
- La lettre d’ATIS publiée sert à préremplir les messages ; elle ne prouve pas
  que l’ATIS a été écouté.
- Les fixtures ne valident aucun matériel ni aucune source réelle. La recette
  visuelle est documentée dans la [matrice de couverture](copilot-acceptance.md).

Voir aussi les [règles de session](copilot-session.md).

## Radio en anglais et répertoire complet

Le choix **Voix / Automatique** suit l’indicatif du contrôleur contacté : français
pour `LF`, les préfixes ultramarins français déjà pris en charge et Genève `LSGG` ;
anglais ailleurs. Un centre étranger contrôlant un terrain français reste en
anglais. Les autres stations suisses, dont Sion en IFR, et celles du Maghreb
restent en anglais par défaut. Il s’agit d’une préférence prudente, pas d’une
détection des langues effectivement parlées par une personne.

Choisir **Anglais** ou **Français** pour adapter les modèles vocaux au contrôleur
ou s’entraîner. Ce choix s’applique à tout le répertoire vocal du suivi ; repasser
en **Automatique** lors d’un changement de pays si nécessaire. Il est conservé
sous `local/copilot/`, séparément par suivi et par univers de démonstration ou
SimConnect. Un nouveau suivi repart en automatique. UNICOM reste en anglais.

Ouvrir **Répertoire radio** sous les appels de l’étape. Les intentions sont
expliquées en français, les phrases sont dans la langue choisie. Rechercher en
français ou en anglais, avec ou sans accents. **Cette étape + messages généraux**
limite les suggestions ; **Tout le vol** donne accès à tous les modèles :

- Compréhension : répétition entière ou partielle, débit plus lent, confirmation,
  correction, impossibilité, demande d’instructions écrites sur IVAO, essai radio.
- Sol : clairance IFR et collationnement, mise en route et repoussage séparés ou
  combinés, roulage, maintien avant piste, traversée, remontée, guidage et poste.
- Départ : point d’attente, alignement simple ou conditionnel, départ immédiat,
  décollage, annulation, interruption, premier contact et changement de SID.
- Transferts : contact ou veille, fréquence impossible à joindre, cap, vitesse,
  Mach, taux vertical, niveau, QNH, code, direct et contraintes de passage.
- En route : premier contact et position, niveau atteint, demandes de montée,
  descente ou direct, météo, turbulence, givrage et acquisition du trafic.
- Arrivée : STAR, approche ILS/RNP/autre, approche à vue, attente, besoin de temps,
  localizer/ILS établi, finale, atterrissage, remise des gaz et retour au poste.
- Situations inhabituelles : problème technique, retour ou déroutement, panne
  radio/navigation, PAN PAN, MAYDAY, urgence médicale, carburant, TCAS et descente
  d’urgence. Ces modèles restent accessibles à toutes les étapes.

Compléter les `<chevrons>` avec les informations vérifiées et collationner
l’instruction exacte, y compris ses restrictions. Les clairances ne sont pas
déduites de l’OFP : la piste prévue ne remplit pas une piste autorisée dans une
réponse. La piste de décollage ne remplit pas la piste reçue pour l’atterrissage.
Les valeurs saisies restent à corriger lorsqu’une nouvelle clairance les remplace ;
les champs libres du pilote ne sont pas traduits automatiquement. L’application
n’écoute pas la radio et une phrase affichée ne prouve aucune autorisation.

Références de phraséologie et de langue :
[CAA CAP 413](https://www.caa.co.uk/data-and-publications/publications/documents/content/cap-413/),
[IVAO Genève](https://generic.ch.ivao.aero/page/atcopslsgg),
[AIP Sion, AD 2.18](https://www.sionaeroport.ch/wp-content/uploads/2016/12/AIP_Full.pdf).
Le répertoire vise les échanges IFR A320 usuels et les principales situations
inhabituelles en simulation ; les procédures locales et les instructions reçues
peuvent nécessiter d’autres formulations.
