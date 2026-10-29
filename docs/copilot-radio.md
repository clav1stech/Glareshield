# Messages radio du copilote

Depuis 1.2.8, Vol prépare les messages des six phases depuis les gabarits de
`a320.json` : clairance, mise en route/repoussage, roulage, départ, montée,
en route, descente, approche, atterrissage, remise des gaz, piste dégagée et parking.
Les règles de langue et de format suivent [le guide de phraséologie](SKILL.md#5-messages-radio).

La séquence suit l’ordre du profil ; les déclencheurs confirmés passent d’abord.
Chaque message indique son déclencheur, son état et ses sources. Un événement
manuel est limité à la phase déclarée et peut être révoqué. Une condition
inconnue reste à confirmer : afficher un texte n’autorise jamais son émission.
Le formulaire « Confirmer un événement de procédure » permet ces confirmations.

La station réellement déclarée par le pilote est conservée. Sinon le service
propose une position candidate selon les rôles du gabarit et le rapprochement
IVAO existant. Ni la distance ni le préfixe ne prouvent la couverture. Une
fréquence n’est montrée comme publiée que si le flux est actuel ; elle ne
remplit pas une fréquence de transfert autorisée. Flux inconnu, périmé,
désactivé ou sans position candidate ne signifient pas absence de contrôle :
les variantes voix/UNICOM restent conditionnelles. Aucun changement de radio
n’est envoyé au cockpit.

La voix est française pour les préfixes français explicitement reconnus
(`LF`, `TFF`, `FMEE`, `FMCZ`, `NWW`, `NT`, `SOCA`), anglaise ailleurs. L’indicatif
du vol reste dans la voix. Le flux ne fournit pas de nom de ville vérifié :
`<station>` est conservé dans le texte à lire, avec l’indicatif connu à côté.
Sans station connue, une variante voix et collationnement en français est
proposée à côté de la version anglaise ; le pilote choisit la langue appropriée.

Les valeurs prévues, publiées et déclarées restent identifiées. Les champs de
clairance et de collationnement ne sont remplis qu’à partir de déclarations
structurées et valides du pilote ; une piste OFP n’est pas une piste autorisée.
Un ATIS téléchargé ou annoncé n’est pas un ATIS consulté : le texte utilise
seulement `atis.heard_letter`. Lors d’un changement publié, la lettre consultée
reste celle déclarée jusqu’à correction explicite ; le rappel signale l’écart.
Le collationnement est un gabarit après réception, jamais une réponse ATC
illustrative présentée comme reçue. Les valeurs absentes restent `<…>`.

Les textes UNICOM sont en anglais, sur une ligne, sans indicatif du vol ajouté,
et avec l’aérodrome au début et à la fin lorsqu’il est connu. Les annonces
en route restent masquées sans confirmation de leur déclencheur « trafic ou
aérodrome » ; aucune annonce continue en croisière. La référence 122.800 ne
remplace pas une fréquence ATC inconnue. Lire la fréquence et confirmer
l’absence de contrôle avant de choisir la variante UNICOM.

Chaque variante dispose de son bouton de copie. Seul le texte choisi rejoint
le presse-papiers : pas de titre, de consigne ou d’autre intervenant. Le succès
est affiché, sans marque « émis », sans case cochée et sans écriture d’émission
dans la session. Aucune synthèse vocale, écoute ou interaction Altitude.
