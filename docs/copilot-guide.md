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
6. **Radio** propose au plus trois messages, ceux de l’étape, avec la station
   en ligne et sa fréquence. **Copier** ne transmet rien. Sans contrôle en
   ligne, un message UNICOM texte est ajouté.

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
