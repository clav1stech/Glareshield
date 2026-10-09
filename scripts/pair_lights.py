"""Pair a discovered light controller; keep all installation data private."""
from __future__ import annotations

import argparse
import ipaddress
import json
import ssl
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]


def save(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(path)


def pair(driver: str, model: str | None, seconds: int) -> None:
    inventory = json.loads((ROOT/'local/discovery/inventory.json').read_text(encoding='utf-8'))
    service = '_hue._tcp.local.' if driver == 'hue' else '_nanoleafapi._tcp.local.'
    candidates = [d for d in inventory['network'] if d['service'] == service
                  and (model is None or d['properties'].get('md') == model)]
    if len(candidates) != 1:
        raise RuntimeError('La sélection doit désigner exactement un contrôleur découvert.')
    device = candidates[0]
    hosts = [a for a in device['addresses'] if ipaddress.ip_address(a).version == 4]
    if not hosts:
        raise RuntimeError('Adresse IPv4 non découverte.')
    host = hosts[0]
    props = device['properties']
    identifier = props.get('bridgeid') or props.get('eui64') or props['id']
    path = ROOT/'local/secrets'/f'{driver}.json'
    saved = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    credentials = saved.get(identifier)
    verify = True
    if driver == 'hue':
        from cryptography import x509
        from cryptography.x509.oid import NameOID
        certificate = ROOT/'local/secrets'/f'hue-{identifier}.pem'
        if not certificate.exists():
            pem = ssl.get_server_certificate((host, device['port']), timeout=5)
            cert = x509.load_pem_x509_certificate(pem.encode('ascii'))
            names = cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
            if not names or names[0].value.lower() != identifier.lower():
                raise RuntimeError('Certificat incohérent avec l’identifiant du pont.')
            certificate.parent.mkdir(parents=True, exist_ok=True)
            certificate.write_text(pem, encoding='ascii')
        verify = ssl.create_default_context(cafile=str(certificate))
        verify.check_hostname = False
        verify.verify_flags |= ssl.VERIFY_X509_PARTIAL_CHAIN
        verify.verify_flags &= ~ssl.VERIFY_X509_STRICT
    scheme = 'https' if driver == 'hue' else 'http'
    with httpx.Client(base_url=f'{scheme}://{host}:{device["port"]}',
                      verify=verify, trust_env=False, timeout=5) as client:
        if driver == 'nanoleaf':
            client.headers['Connection'] = 'close'
        if not credentials:
            print('En attente de la fenêtre d’appairage…', flush=True)
            deadline = time.monotonic()+seconds
            while time.monotonic() < deadline:
                if driver == 'hue':
                    response = client.post('/api', json={'devicetype': 'glareshield#local'})
                    response.raise_for_status()
                    body = response.json()
                    if body and 'success' in body[0]:
                        credentials = body[0]['success']
                        break
                    if not body or body[0].get('error', {}).get('type') != 101:
                        raise RuntimeError('Le pont a refusé l’appairage.')
                else:
                    response = client.post('/api/v1/new')
                    if response.is_success and response.content:
                        credentials = response.json()
                        if not credentials.get('auth_token'):
                            raise RuntimeError('Réponse sans jeton d’appairage.')
                        break
                    if response.status_code not in (401,403):
                        raise RuntimeError(f'Appairage refusé (HTTP {response.status_code}).')
                time.sleep(1)
            else:
                raise RuntimeError('Délai écoulé sans ouverture de la fenêtre d’appairage.')
            saved[identifier] = credentials
            save(path,saved)
        if driver == 'hue':
            client.headers['hue-application-key'] = credentials['username']
            resources = {}
            for kind in ('light','device','room','zone','entertainment_configuration'):
                response = client.get(f'/clip/v2/resource/{kind}')
                response.raise_for_status()
                body = response.json()
                if body.get('errors'):
                    raise RuntimeError('Lecture des ressources refusée par le pont.')
                resources[kind] = body['data']
        else:
            response = client.get(f'/api/v1/{credentials["auth_token"]}')
            response.raise_for_status()
            information = response.json()
            response = client.get(f'/api/v1/{credentials["auth_token"]}/state')
            response.raise_for_status()
            state = response.json()
            response = client.get(f'/api/v1/{credentials["auth_token"]}/effects/select')
            response.raise_for_status()
            effect = response.text.strip().strip('"')
            resources = {'information': information, 'state': state, 'effect': effect}
    save(ROOT/'local/discovery'/f'{driver}-resources.json',resources)
    print('Appairage et inventaire réussis ; données conservées dans local/.')
    if driver == 'hue':
        print(f'Lampes : {len(resources["light"])} ; zones de divertissement : {len(resources["entertainment_configuration"])}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Appairage des éclairages Glareshield')
    parser.add_argument('driver', choices=['hue','nanoleaf'])
    parser.add_argument('--model')
    parser.add_argument('--seconds',type=int,default=120)
    args = parser.parse_args()
    if not 1 <= args.seconds <= 300:
        parser.error('Délai requis entre 1 et 300 secondes.')
    try:
        pair(args.driver,args.model,args.seconds)
    except (RuntimeError,OSError,httpx.HTTPError,ValueError,KeyError) as error:
        # Request URLs can contain private tokens.
        detail = str(error) if isinstance(error,RuntimeError) else type(error).__name__
        parser.exit(1,f'Échec : {detail}\n')
