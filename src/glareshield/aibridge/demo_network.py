"""Fictional IVAO fixtures for the existing flight scenario; never opens a socket."""
from __future__ import annotations

from datetime import UTC, datetime

from .config import IVAOSettings
from .ivao import IVAOError, IVAOService


class DemoNetwork(IVAOService):
    simulation = True

    def __init__(self, clock, scenario):
        super().__init__(clock, settings=IVAOSettings(enabled=True))
        self.scenario = scenario
        self.updated = None
        # Feed metadata must not imply that an actual IVAO endpoint was contacted.
        for feed in self.feeds:
            feed.url = 'scenario:'+feed.name

    def tick(self, force=False):
        now, elapsed = self.clock(), self.scenario.elapsed()
        if not force and self.updated is not None and 0 <= now-self.updated < 15:
            return self
        self.updated = now
        if 1160 <= elapsed < 1220:
            self.whazzup.error = 'Panne fictive du flux ; positions précédentes conservées.'
            return self
        revision = 'K' if elapsed < 900 else 'L'
        extra = 'Texte fictif actualisé, lettre inchangée.' if elapsed >= 1080 else 'Publication fictive initiale.'
        stamp = datetime.fromtimestamp(now, UTC).strftime('%d%H%MZ')
        stations = []

        def add(callsign, position, lat, lon, frequency, atis=None):
            stations.append({'callsign': callsign, 'kind': 'atc', 'position': position,
                'latitude': lat, 'longitude': lon, 'frequency_mhz': frequency,
                'range_nm': None, 'connected_since': None, 'atis': atis})

        if elapsed < 300:
            add('XXPO_GND', 'GND', 48.72, 2.38, 121.8, {'revision': 'B',
                'lines': ['Démonstration sol XXPO information BRAVO'], 'timestamp': now-60, 'truncated': False})
        if not 1300 <= elapsed < 1400:
            add('XXNC_TWR', 'TWR', 43.66, 7.22, 118.7, {'revision': revision,
                'lines': ['Démonstration tour XXNC information '+revision, extra,
                          'Vent fictif 090/06, QNH 1015'],
                'timestamp': now-60, 'truncated': False})
        if elapsed >= 600:
            add('XXNC_APP', 'APP', 43.60, 7.10, 134.475)
        add('XXZZ_CTR', 'CTR', 46., 5., 127.85)
        self.whazzup.data = {'stations': stations, 'updated_at': now}
        self.whazzup.source_updated_at = now
        self.track_atis(stations, now)
        self.track_presence(stations)
        self.metar.data = {code: {'raw': f'{code} {stamp} 09006KT CAVOK 20/12 Q1015',
                                  'updated_at': now, 'truncated': False} for code in ('XXPO', 'XXNC')}
        self.taf.data = {}
        for feed in self.feeds:
            feed.fetched_at, feed.last_attempt, feed.error, feed.failures = now, now, None, 0
        return self

    async def download(self, url):
        raise IVAOError('Flux fictif : aucun accès réseau.')

    async def refresh(self):
        self.tick(force=True)
        return {feed.name: {'result': 'fetched', 'source': 'scenario'} for feed in self.feeds}

    def summary(self, now=None):
        return {**super().summary(now), 'simulation': True,
                'notice': 'IVAO fictif ; fixtures embarquées, aucun téléchargement.'}
