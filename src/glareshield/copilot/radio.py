"""Simulation phrasebook. Bracketed details must be supplied from the actual exchange.

Defaults are conservative preferences, not a claim about a controller's languages.
In particular, Swiss IFR is English except for the Geneva aerodrome default;
no blanket French assumption is made for Switzerland or the Maghreb.
"""

FRENCH_PREFIXES = ('LF', 'TFF', 'FMEE', 'FMCZ', 'NWW', 'NT', 'SOCA')


def radio_language(station, airport, preference='auto'):
    if preference in ('fr', 'en'):
        return preference
    # A foreign centre controlling a French airport must keep its own language.
    prefix = (station or airport or '').upper().split('_', 1)[0]
    return 'fr' if prefix.startswith(FRENCH_PREFIXES) or prefix == 'LSGG' else 'en'


EN_PLACEHOLDERS = {
    'callsign': '<callsign>', 'origin': '<departure airport>', 'destination': '<destination>',
    'stand': '<stand>', 'arrival_stand': '<arrival stand>', 'departure_runway': '<departure runway>',
    'arrival_runway': '<arrival runway>', 'cleared_runway': '<cleared runway>',
    'cleared_sid': '<cleared SID>', 'cleared_altitude': '<cleared level>',
    'cleared_qnh': '<received QNH>', 'squawk': '<assigned squawk>', 'taxi_route': '<cleared taxi route>',
    'frequency': '<assigned frequency>', 'heading': '<assigned heading>', 'speed': '<assigned speed>',
    'approach_position': '<confirmed position>', 'exit': '<runway exit>', 'atis_heard': '<ATIS>',
    'approach': '<approach>', 'alternate': '<alternate>', 'cruise_altitude': '<planned cruise level>',
}

ALL = ()  # No stage restriction; useful even before phase detection.
GROUND = ('parked', 'pushback', 'taxi_out', 'rollout', 'taxi_in', 'parked_in')
DEPARTURE = ('parked', 'pushback', 'taxi_out', 'takeoff', 'climb')
AIRBORNE = ('takeoff', 'climb', 'cruise', 'descent', 'approach', 'final', 'go_around')
ARRIVAL = ('descent', 'approach', 'final', 'go_around', 'rollout', 'taxi_in', 'parked_in')

# Each entry: stable identifier, French intent, English transmission, French transmission.
# Readback variants are separate: line-up, crossing, take-off and landing are never merged.
PHRASE_GROUPS = (
    ('Comprendre et répondre', ALL, (), (
        ('say_again', 'Faire répéter', '{callsign}, say again.', '{callsign}, répétez.'),
        ('speak_slower', 'Demander de parler moins vite', '{callsign}, speak slower.', '{callsign}, parlez plus lentement.'),
        ('say_again_part', 'Faire répéter un élément', '{callsign}, say again <item: level / heading / frequency / taxi route>.', '{callsign}, répétez <élément : niveau / cap / fréquence / roulage>.'),
        ('confirm', 'Confirmer une instruction incertaine', '{callsign}, confirm <instruction or value>.', '{callsign}, confirmez <instruction ou valeur>.'),
        ('correction', 'Corriger son propre message', 'Correction, <correct message>, {callsign}.', 'Correction, <message corrigé>, {callsign}.'),
        ('unable', 'Impossible de suivre une instruction', '{callsign}, unable <instruction>, due <reason>, request <alternative>.', '{callsign}, impossible <instruction>, cause <raison>, demandons <alternative>.'),
        ('standby', 'Demander un instant', '{callsign}, standby.', '{callsign}, attendez.'),
        ('affirm', 'Réponse affirmative', 'Affirm, {callsign}.', 'Affirme, {callsign}.'),
        ('negative', 'Réponse négative', 'Negative, {callsign}.', 'Négatif, {callsign}.'),
        ('roger', 'Accuser réception d’une information', 'Roger, {callsign}.', 'Reçu, {callsign}.'),
        ('wilco', 'Instruction comprise et sera exécutée', 'Wilco, {callsign}.', 'Compris, sera exécuté, {callsign}.'),
        ('radio_check', 'Vérifier la radio', '{station}, {callsign}, radio check <frequency>.', '{station}, {callsign}, essai radio <fréquence>.'),
        ('readability', 'Répondre à un essai radio', 'Reading you <one to five>, {callsign}.', 'Vous reçois <un à cinq>, {callsign}.'),
        ('request_english', 'Demander l’anglais', '{callsign}, request English.', '{callsign}, demandons à poursuivre en anglais.'),
        ('request_text', 'IVAO : demander l’instruction par écrit', '{callsign}, unable to understand, please send instructions by text.', '{callsign}, instruction non comprise, pouvez-vous l’envoyer par texte ?'),
        ('verify_level', 'Lever un doute sur le niveau autorisé', '{callsign}, confirm cleared level <level heard>.', '{callsign}, confirmez niveau autorisé <niveau entendu>.'),
    )),
    ('Clairance et sol', GROUND, ('GND', 'TWR', 'DEL', 'APP', 'CTR'), (
        ('clearance_repeat', 'Clairance à répéter entièrement', '{callsign}, say again clearance.', '{callsign}, répétez la clairance.'),
        ('clearance_readback', 'Collationner la clairance IFR', 'Cleared to {destination} via <cleared route / SID>, runway <cleared runway>, climb to {cleared_altitude}, squawk {squawk}, {callsign}.', 'Autorisé vers {destination} via <route / SID autorisée>, piste <piste autorisée>, montée vers {cleared_altitude}, code {squawk}, {callsign}.'),
        ('startup_request', 'Demander la mise en route seule', '{station}, {callsign}, stand {stand}, request start-up.', '{station}, {callsign}, poste {stand}, demandons mise en route.'),
        ('startup_readback', 'Mise en route autorisée', 'Start-up approved, {callsign}.', 'Mise en route approuvée, {callsign}.'),
        ('pushback_request', 'Demander le repoussage seul', '{station}, {callsign}, stand {stand}, request pushback.', '{station}, {callsign}, poste {stand}, demandons repoussage.'),
        ('pushback_readback', 'Repoussage autorisé avec orientation', 'Pushback approved, facing <direction received>, {callsign}.', 'Repoussage approuvé, face <direction reçue>, {callsign}.'),
        ('pushback_complete', 'Repoussage terminé, prêt au roulage', '{callsign}, pushback complete, ready to taxi.', '{callsign}, repoussage terminé, prêts au roulage.'),
        ('taxi_readback', 'Collationner le roulage et sa limite', 'Taxi to holding point <holding point>, runway <cleared runway>, via {taxi_route}, {callsign}.', 'Roulons point d’attente <point>, piste <piste autorisée>, via {taxi_route}, {callsign}.'),
        ('hold_position', 'Maintenir sa position', 'Holding position, {callsign}.', 'Maintenons position, {callsign}.'),
        ('hold_short', 'Attendre avant une piste', 'Holding short of runway <runway received>, {callsign}.', 'Maintenons avant piste <piste reçue>, {callsign}.'),
        ('cross_request', 'Demander à traverser une piste', '{callsign}, request crossing runway <runway>.', '{callsign}, demandons traversée piste <piste>.'),
        ('cross_readback', 'Traversée expressément autorisée', 'Cross runway <runway received>, {callsign}.', 'Traversons piste <piste reçue>, {callsign}.'),
        ('backtrack', 'Remontée de piste autorisée', 'Backtrack runway <runway received>, <clearance limit received>, {callsign}.', 'Remontons piste <piste reçue>, <limite reçue>, {callsign}.'),
        ('give_way', 'Céder le passage à un trafic identifié', 'Give way to <identified traffic> at <location>, {callsign}.', 'Cédons le passage à <trafic identifié> à <position>, {callsign}.'),
        ('progressive_taxi', 'Demander un guidage au roulage', '{callsign}, unfamiliar with airport, request progressive taxi.', '{callsign}, aérodrome peu familier, demandons guidage au roulage.'),
        ('position_uncertain', 'Position incertaine au sol', '{callsign}, position uncertain, stopping, request assistance.', '{callsign}, position incertaine, nous arrêtons, demandons assistance.'),
        ('taxi_stand', 'Roulage vers le poste reçu', 'Taxi to stand <assigned stand> via {taxi_route}, {callsign}.', 'Roulons poste <poste attribué> via {taxi_route}, {callsign}.'),
    )),
    ('Départ', DEPARTURE, ('TWR', 'DEP', 'APP', 'CTR'), (
        ('ready_departure', 'Prêt au départ au point d’attente', '{station}, {callsign}, holding point <holding point>, runway <runway>, ready for departure.', '{station}, {callsign}, point d’attente <point>, piste <piste>, prêts au départ.'),
        ('intersection', 'Demander un départ depuis une intersection', '{callsign}, request departure runway <runway> from intersection <intersection>.', '{callsign}, demandons départ piste <piste> depuis intersection <intersection>.'),
        ('not_ready_departure', 'Pas prêt pour un départ immédiat', '{callsign}, not ready for immediate departure, request <time required>.', '{callsign}, pas prêts pour départ immédiat, demandons <délai>.'),
        ('lineup', 'Alignement autorisé, attendre', 'Line up and wait runway <runway received>, {callsign}.', 'Nous alignons et attendons piste <piste reçue>, {callsign}.'),
        ('conditional_lineup', 'Alignement conditionnel reçu', 'Behind <identified traffic>, line up and wait runway <runway received>, behind, {callsign}.', 'Derrière <trafic identifié>, nous alignons et attendons piste <piste reçue>, derrière, {callsign}.'),
        ('takeoff_readback', 'Décollage expressément autorisé', 'Runway <runway received>, cleared for take-off, {callsign}.', 'Piste <piste reçue>, autorisé décollage, {callsign}.'),
        ('takeoff_cancelled', 'Autorisation de décollage annulée', 'Holding, {callsign}.', 'Maintenons position, {callsign}.'),
        ('departure_contact', 'Premier contact départ', '{station}, {callsign}, passing <current altitude>, climbing to {cleared_altitude}, <cleared SID>.', '{station}, {callsign}, passons <altitude actuelle>, en montée vers {cleared_altitude}, <SID autorisée>.'),
        ('sid_change', 'Changement de SID reçu', '<Cleared SID and transition>, runway <runway received>, climb to {cleared_altitude}, {callsign}.', '<SID et transition autorisées>, piste <piste reçue>, montée vers {cleared_altitude}, {callsign}.'),
        ('stop_departure', 'Interruption du décollage', '{callsign}, stopping.', '{callsign}, interrompons le décollage.'),
    )),
    ('Transferts et collationnements', ALL, (), (
        ('contact_frequency', 'Transfert vers une autre station', '<Next station> {frequency}, {callsign}.', '<Station suivante> {frequency}, {callsign}.'),
        ('monitor_frequency', 'Veille d’une fréquence demandée', 'Monitor <station> {frequency}, {callsign}.', 'Veillons <station> {frequency}, {callsign}.'),
        ('frequency_request', 'Demander un changement de fréquence', '{callsign}, request frequency change to <station and frequency>.', '{callsign}, demandons changement de fréquence vers <station et fréquence>.'),
        ('no_contact', 'Impossible de joindre la station suivante', '{station}, {callsign}, unable contact <station> on <frequency>.', '{station}, {callsign}, impossible de joindre <station> sur <fréquence>.'),
        ('climb_readback', 'Montée autorisée', 'Climb to {cleared_altitude}, {callsign}.', 'Montons vers {cleared_altitude}, {callsign}.'),
        ('descent_readback', 'Descente autorisée', 'Descend to {cleared_altitude}, {callsign}.', 'Descendons vers {cleared_altitude}, {callsign}.'),
        ('maintain_level', 'Maintenir le niveau autorisé', 'Maintain {cleared_altitude}, {callsign}.', 'Maintenons {cleared_altitude}, {callsign}.'),
        ('heading_readback', 'Virage vers un cap reçu', 'Turn <left / right> heading {heading}, {callsign}.', 'Virons <gauche / droite> cap {heading}, {callsign}.'),
        ('present_heading', 'Conserver le cap actuel', 'Continue present heading, {callsign}.', 'Conservons cap actuel, {callsign}.'),
        ('speed_readback', 'Vitesse imposée', 'Maintain {speed}, {callsign}.', 'Maintenons {speed}, {callsign}.'),
        ('speed_change', 'Accélération ou réduction demandée', '<Increase / reduce> speed to <assigned speed and units>, {callsign}.', '<Accélérons / réduisons> vers <vitesse et unité reçues>, {callsign}.'),
        ('qnh_readback', 'Calage altimétrique reçu', 'QNH {cleared_qnh}, {callsign}.', 'QNH {cleared_qnh}, {callsign}.'),
        ('squawk_readback', 'Code transpondeur reçu', 'Squawk {squawk}, {callsign}.', 'Code {squawk}, {callsign}.'),
        ('ident', 'IDENT demandé', 'Squawk ident, {callsign}.', 'Ident, {callsign}.'),
        ('direct_readback', 'Direct vers un point autorisé', 'Direct <cleared waypoint>, {callsign}.', 'Direct <point autorisé>, {callsign}.'),
        ('restriction', 'Contrainte de passage reçue', 'Cross <waypoint> <at / at or above / at or below> <level>, <speed restriction if received>, {callsign}.', 'Passons <point> <à / à ou au-dessus / à ou en dessous> <niveau>, <vitesse si reçue>, {callsign}.'),
        ('vertical_rate', 'Taux de montée ou descente imposé', '<Climb / descend> at <rate and minimum/maximum received> feet per minute, {callsign}.', '<Montons / descendons> à <taux et minimum/maximum reçus> pieds par minute, {callsign}.'),
        ('mach', 'Nombre de Mach imposé', 'Maintain Mach <assigned Mach>, {callsign}.', 'Maintenons Mach <Mach reçu>, {callsign}.'),
        ('resume_navigation', 'Reprendre sa navigation après guidage', 'Resume own navigation to <cleared point>, {callsign}.', 'Reprenons navigation vers <point autorisé>, {callsign}.'),
    )),
    ('En route', AIRBORNE, ('CTR', 'APP', 'DEP'), (
        ('enroute_contact', 'Premier contact en route', '{station}, {callsign}, <current altitude>, <climbing / descending to cleared level, or maintaining>.', '{station}, {callsign}, <altitude actuelle>, <en montée / descente vers niveau autorisé, ou en palier>.'),
        ('position_report', 'Compte rendu de position', '{callsign}, <position> at <time UTC>, <level>, estimating <next point> at <time UTC>, <following point>.', '{callsign}, <position> à <heure UTC>, <niveau>, estimons <point suivant> à <heure UTC>, puis <point>.'),
        ('level_report', 'Signaler le niveau atteint', '{callsign}, maintaining {cleared_altitude}.', '{callsign}, en palier {cleared_altitude}.'),
        ('climb_request', 'Demander un niveau supérieur', '{callsign}, request climb to <requested level>.', '{callsign}, demandons montée vers <niveau souhaité>.'),
        ('descent_request', 'Demander la descente', '{callsign}, request descent to <requested level>.', '{callsign}, demandons descente vers <niveau souhaité>.'),
        ('direct_request', 'Demander un direct', '{callsign}, request direct <waypoint>.', '{callsign}, demandons direct <point>.'),
        ('weather_deviation', 'Éviter une zone météo', '{callsign}, request deviation <left / right, distance> due weather.', '{callsign}, demandons déviation <gauche / droite, distance> cause météo.'),
        ('turbulence', 'Signaler des turbulences', '{callsign}, <light / moderate / severe> turbulence at <level>, request <level or route>.', '{callsign}, turbulences <faibles / modérées / fortes> au <niveau>, demandons <niveau ou route>.'),
        ('icing', 'Signaler du givrage', '{callsign}, <light / moderate / severe> icing at <level>, request <level or route>.', '{callsign}, givrage <faible / modéré / fort> au <niveau>, demandons <niveau ou route>.'),
        ('traffic_in_sight', 'Trafic en vue', 'Traffic in sight, {callsign}.', 'Trafic en vue, {callsign}.'),
        ('traffic_negative', 'Trafic non acquis visuellement', 'Negative contact, {callsign}.', 'Trafic non en vue, {callsign}.'),
    )),
    ('Arrivée et approche', ARRIVAL, ('APP', 'TWR', 'CTR', 'GND'), (
        ('arrival_contact', 'Premier contact arrivée', '{station}, {callsign}, <current altitude>, descending to {cleared_altitude}, information {atis_heard}.', '{station}, {callsign}, <altitude actuelle>, en descente vers {cleared_altitude}, information {atis_heard}.'),
        ('star_readback', 'STAR et transition autorisées', 'Cleared <STAR and transition received>, <level restriction if received>, {callsign}.', 'Autorisé <STAR et transition reçues>, <contrainte de niveau si reçue>, {callsign}.'),
        ('approach_request', 'Demander une approche', '{callsign}, request <approach type> approach runway <runway>.', '{callsign}, demandons approche <type> piste <piste>.'),
        ('approach_clearance', 'Autorisation d’approche reçue', 'Cleared <approach type received> approach runway <runway received>, {callsign}.', 'Autorisé approche <type reçu> piste <piste reçue>, {callsign}.'),
        ('visual_clearance', 'Approche à vue autorisée', 'Cleared visual approach runway <runway received>, {callsign}.', 'Autorisé approche à vue piste <piste reçue>, {callsign}.'),
        ('unable_approach', 'Impossible d’effectuer l’approche proposée', '{callsign}, unable <approach>, due <reason>, request <alternative approach>.', '{callsign}, impossible <approche>, cause <raison>, demandons <autre approche>.'),
        ('atis_update', 'Signaler la nouvelle information ATIS', '{callsign}, information {atis_heard} received.', '{callsign}, information {atis_heard} reçue.'),
        ('localizer', 'Localizer établi', '{callsign}, established localizer runway <runway>.', '{callsign}, établi localizer piste <piste>.'),
        ('ils_established', 'Établi sur l’ILS', '{callsign}, established ILS runway <runway>.', '{callsign}, établi ILS piste <piste>.'),
        ('visual', 'Terrain en vue', '{callsign}, airfield in sight.', '{callsign}, terrain en vue.'),
        ('continue_approach', 'Poursuivre l’approche sans autorisation d’atterrir', 'Continue approach, {callsign}.', 'Poursuivons approche, {callsign}.'),
        ('final_report', 'Signaler la finale', '{station}, {callsign}, final runway {arrival_runway}.', '{station}, {callsign}, finale piste {arrival_runway}.'),
        ('landing_readback', 'Atterrissage expressément autorisé', 'Runway <runway received>, cleared to land, {callsign}.', 'Piste <piste reçue>, autorisé atterrissage, {callsign}.'),
        ('holding_readback', 'Attente publiée ou détaillée reçue', 'Hold at <fix>, <level>, <published hold or inbound track, turn direction, leg time/distance>, <EFC if received>, {callsign}.', 'Attendons à <point>, <niveau>, <attente publiée ou axe, sens, durée/distance des branches>, <heure prévue si reçue>, {callsign}.'),
        ('holding_request', 'Demander une attente pour se préparer', '{callsign}, request holding at <fix> for <time>, due <reason>.', '{callsign}, demandons attente à <point> pendant <durée>, cause <raison>.'),
        ('not_ready', 'Besoin de temps ou de distance', '{callsign}, not ready for approach, request <delay vectors / extended final>.', '{callsign}, pas prêts pour l’approche, demandons <guidage de retardement / finale prolongée>.'),
        ('go_around_report', 'Annoncer une remise des gaz', '{callsign}, going around, <reason if time permits>.', '{callsign}, remettons les gaz, <raison si disponible>.'),
        ('missed_approach', 'Procédure de remise des gaz reçue', '<Published missed approach or heading received>, climb to {cleared_altitude}, {callsign}.', '<Approche interrompue publiée ou cap reçu>, montons vers {cleared_altitude}, {callsign}.'),
        ('another_approach', 'Demander une nouvelle approche', '{callsign}, request another <approach type> approach runway <runway>.', '{callsign}, demandons une nouvelle approche <type> piste <piste>.'),
        ('vacated', 'Signaler la piste dégagée', '{callsign}, runway <runway vacated> vacated via {exit}.', '{callsign}, piste <piste dégagée> dégagée par {exit}.'),
        ('stand_request', 'Demander le poste ou un autre poste', '{callsign}, request taxi to stand {stand}.', '{callsign}, demandons roulage poste {stand}.'),
        ('parking', 'Au poste, quitter la fréquence', '{callsign}, parked stand {stand}, request frequency change.', '{callsign}, au poste {stand}, demandons à quitter la fréquence.'),
    )),
    ('Situations inhabituelles et urgences', ALL, (), (
        ('technical_problem', 'Problème technique, besoin de temps', '{callsign}, technical problem <nature>, request <holding / vectors / return>, standby for further information.', '{callsign}, problème technique <nature>, demandons <attente / guidage / retour>, précisions à suivre.'),
        ('return', 'Demander un retour au départ', '{callsign}, request return to <airport> due <reason>, request <vectors / approach>.', '{callsign}, demandons retour vers <aérodrome> cause <raison>, demandons <guidage / approche>.'),
        ('diversion', 'Demander un déroutement', '{callsign}, request diversion to <airport> due <reason>, request clearance.', '{callsign}, demandons déroutement vers <aérodrome> cause <raison>, demandons clairance.'),
        ('pan', 'Urgence — PAN PAN', 'PAN PAN, PAN PAN, PAN PAN, {station}, {callsign}, <nature of urgency>, <intentions / assistance required>, <position>, <level>, <heading>.', 'PAN PAN, PAN PAN, PAN PAN, {station}, {callsign}, <nature de l’urgence>, <intentions / assistance>, <position>, <niveau>, <cap>.'),
        ('mayday', 'Détresse — MAYDAY', 'MAYDAY, MAYDAY, MAYDAY, {station}, {callsign}, <nature of distress>, <intentions / assistance required>, <position>, <level>, <heading>.', 'MAYDAY, MAYDAY, MAYDAY, {station}, {callsign}, <nature de la détresse>, <intentions / assistance>, <position>, <niveau>, <cap>.'),
        ('emergency_details', 'Précisions demandées par le contrôle', '{callsign}, <persons on board> persons on board, endurance <hours and minutes>, <dangerous goods information>.', '{callsign}, <personnes à bord> personnes à bord, autonomie <heures et minutes>, <information marchandises dangereuses>.'),
        ('radio_failure', 'Rétablissement après panne radio', '{station}, {callsign}, radio failure, now receiving you, <position>, <level>, request instructions.', '{station}, {callsign}, panne radio, vous recevons à nouveau, <position>, <niveau>, demandons instructions.'),
        ('navigation_failure', 'Perte de capacité de navigation', '{callsign}, unable RNAV due equipment, request radar vectors.', '{callsign}, impossible RNAV cause équipement, demandons guidage radar.'),
        ('minimum_fuel', 'Carburant minimum, aucune marge de délai', '{callsign}, minimum fuel.', '{callsign}, minimum fuel.'),
        ('fuel_emergency', 'Détresse carburant', 'MAYDAY, MAYDAY, MAYDAY, FUEL, {callsign}, <position>, <level>, request <intentions>.', 'MAYDAY, MAYDAY, MAYDAY, FUEL, {callsign}, <position>, <niveau>, demandons <intentions>.'),
        ('medical', 'Urgence médicale', 'PAN PAN, PAN PAN, PAN PAN, {station}, {callsign}, medical emergency, request <diversion / priority / medical assistance>.', 'PAN PAN, PAN PAN, PAN PAN, {station}, {callsign}, urgence médicale, demandons <déroutement / priorité / assistance médicale>.'),
        ('tcas', 'Résolution TCAS en cours', '{callsign}, TCAS RA.', '{callsign}, TCAS RA.'),
        ('unable_tcas', 'Instruction incompatible avec le TCAS', '{callsign}, unable, TCAS RA.', '{callsign}, impossible, TCAS RA.'),
        ('clear_conflict', 'Conflit terminé, retour à la clairance', '{callsign}, clear of conflict, returning to <assigned clearance>.', '{callsign}, conflit terminé, retour vers <clairance assignée>.'),
        ('clearance_resumed', 'Conflit terminé, clairance reprise', '{callsign}, clear of conflict, <assigned clearance> resumed.', '{callsign}, conflit terminé, <clairance assignée> reprise.'),
        ('windshear', 'Remise des gaz pour cisaillement', '{callsign}, going around, windshear.', '{callsign}, remise des gaz, cisaillement de vent.'),
        ('emergency_descent', 'Descente d’urgence', 'MAYDAY, MAYDAY, MAYDAY, {callsign}, emergency descent, <reason>, <position>, <level passing>, descending to <level>, <heading>.', 'MAYDAY, MAYDAY, MAYDAY, {callsign}, descente d’urgence, <raison>, <position>, <niveau passé>, descendons vers <niveau>, <cap>.'),
        ('cancel_emergency', 'Fin de la situation d’urgence', '{callsign}, cancel <distress / urgency>, <situation and intentions>.', '{callsign}, annulons <détresse / urgence>, <situation et intentions>.'),
    )),
)

PHRASE_NOTES = {
    'roger': '« Roger » ne remplace pas le collationnement d’une clairance.',
    'wilco': 'Collationner aussi les éléments obligatoires : piste, niveau, cap, vitesse, code, QNH, fréquence et route.',
    'conditional_lineup': 'Seulement si la condition a été reçue et le trafic identifié. Répéter la condition ; elle n’autorise pas le décollage.',
    'continue_approach': 'Poursuivre l’approche n’est pas une autorisation d’atterrir.',
    'minimum_fuel': 'Ne demande pas de priorité. Si la réserve finale prévue sera entamée à l’atterrissage au terrain sûr le plus proche, déclarer la détresse carburant.',
    'fuel_emergency': 'À utiliser pour une détresse carburant ; renseigner la position et les intentions réelles.',
    'medical': 'Adapter le niveau d’urgence à la situation ; une détresse immédiate appelle MAYDAY.',
}
