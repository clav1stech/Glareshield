# Glareshield

Projet d’application Windows reliant un simulateur de vol à des éclairages connectés et à des sorties audio locales. Interface prévue en français : page web locale et icône dans la barre système.

## État du projet

Phase 0 : découverte et validation des intégrations. Aucun pilote ni moteur n’est encore implémenté. Les hypothèses techniques et les variables du simulateur seront vérifiées avant leur utilisation.

Intégrations envisagées : MSFS 2024 / Fenix A320, activité audio du client IVAO, Philips Hue, Nanoleaf et AirPlay. Leur compatibilité reste à valider. Ces noms décrivent les intégrations du logiciel et ne constituent pas un inventaire d’installation.

## Organisation

- `docs/` : documentation publique, indépendante de toute installation.
- `src/glareshield/` : futur code de l’application.
- `tests/` : futurs tests avec appareils et données fictifs.
- `examples/` : futurs exemples de configuration fictifs.
- `scripts/` : futurs outils de lancement et de développement génériques.
- `local/` : données privées de l’installation, entièrement exclues de Git.

Les dossiers de code seront ajoutés au suivi Git lors du démarrage de leur phase de réalisation.

Voir [l’architecture](docs/architecture.md), [la découverte](docs/discovery.md) et [les règles de confidentialité](docs/privacy.md).
