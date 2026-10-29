# Utiliser le suivi Copilote

## Préparer et suivre un vol

1. Dans **Initialisation**, vérifier simulateur et AI Bridge, importer l’OFP et
   consulter son résumé. IVAO et l’éclairage restent facultatifs. Les notes
   libres sont conservées, mais ne remplissent jamais une clairance structurée.
2. **Démarrer le suivi du vol** ouvre **Vol**. Choisir les déclarations utiles :
   clairance reçue, piste/approche retenue, ATIS consulté avec sa référence,
   performances manuelles sourcées, station réellement utilisée et poste/position.
   Les inconnues restent `<…>`.
3. Suivre **Maintenant**, puis les groupes MCDU, FCU et checklists. Les cases
   manuelles priment dans les deux sens ; une détection contraire reste visible.
   La détection du levier de train ne prouve pas son verrouillage, et STD ne
   prouve pas le respect du seuil de transition. APPR reste manuel.
4. Les rappels restent présents jusqu’à **Acquitter le rappel**. Leur méthode
   et leurs seuils sont affichés ; les rappels secondaires sont différés en
   phase critique. Acquitter un rappel ne coche aucune procédure.
5. Lire le déclencheur et la station avant de choisir une variante radio.
   **Copier** prend seulement le texte choisi et ne signifie jamais « émis ».
   Remplir un collationnement après réception de l’instruction. La lettre d’ATIS
   publiée n’est pas utilisée comme lettre consultée sans déclaration explicite.

La phase avance à partir des observations et du plan. Les six boutons de phase
et le formulaire permettent une correction manuelle. Le retour en automatique
est explicite. Une correction ne coche aucune étape. Les déclencheurs des
étapes sont du contexte à confirmer ; Maintenant classe les cases non terminées
de la phase, avec les rappels admissibles selon leur priorité.

Pour reprendre, ouvrir Vol ou choisir **Reprendre le suivi** après une fin.
Les cases, déclarations, rappels et acquittements restent sous `local/copilot/`.
Un OFP corrigé conserve les cases et invalide les déclarations à revoir ; un
nouveau vol archive le suivi précédent. **Réinitialiser** est une action explicite.
Les sessions de démonstration et SimConnect sont distinctes.

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

## Limites de cette livraison

- Les validations réelles exigent une [correspondance de source validée pour
  l’appareil](copilot-contract.md#validation-des-étapes). Une simple SimVar SDK
  ou un nom de LVar familier ne suffit pas. Les sources Fenix connues incorrectes
  restent exclues ; les tests d’éclairage ne servent jamais de preuves.
- Le TOD MCDU reste absent. Le pilote peut fournir une date/heure de TOD avec
  fuseau et référence ; à défaut, le TOD est inconnu. La distance de préparation
  arrivée n’est pas une estimation du TOD et ne guide pas la descente.
- Les franchissements livrés utilisent l’altitude vraie MSL, pas FL100. Aucun
  état FMA/ECAM, réglage FCU non exposé ou performance n’est inventé.
- Une station candidate et une fréquence publiée ne prouvent pas la couverture
  ni un transfert reçu. Un flux indisponible ne permet pas de conclure UNICOM.
- Une pause ou une perte de télémétrie suspend les nouvelles détections et
  temporisations ; les gestes et preuves historiques sont conservés.
- Les fixtures ne valident aucun matériel ni aucune source réelle. La recette
  visuelle est documentée dans la [matrice de couverture](copilot-acceptance.md).

Voir aussi les [rappels](copilot-reminders.md), la [radio](copilot-radio.md) et
les [règles de session](copilot-session.md).
