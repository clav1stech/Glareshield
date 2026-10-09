"""Exercise the publication guard against staged installation data."""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def repository(tmp_path):
    (tmp_path/'scripts').mkdir()
    shutil.copyfile(ROOT/'scripts/check_public.py',tmp_path/'scripts/check_public.py')
    (tmp_path/'local/discovery').mkdir(parents=True)
    (tmp_path/'local/secrets').mkdir()
    subprocess.run(['git','init','--quiet'],cwd=tmp_path,check=True)
    return tmp_path


def audit(repository):
    subprocess.run(['git','add','.'],cwd=repository,check=True)
    return subprocess.run([sys.executable,'scripts/check_public.py'],cwd=repository,
                          text=True,capture_output=True)


def test_public_files_are_accepted(repository):
    (repository/'README.md').write_text('Generic project documentation.\n',encoding='utf-8')
    assert audit(repository).returncode == 0


def test_private_directory_cannot_be_published(repository):
    (repository/'local/secrets/private.txt').write_text('Private installation notes.',encoding='utf-8')
    result = audit(repository)
    assert result.returncode == 1
    assert 'local/secrets/private.txt' in result.stdout


def test_known_device_identifier_in_public_readme_is_rejected(repository):
    identifier = 'fixture-device-123456'
    private = repository/'local/discovery/inventory.json'
    private.write_text(json.dumps({'identifier':identifier}),encoding='utf-8')
    subprocess.run(['git','add','scripts/check_public.py'],cwd=repository,check=True)
    (repository/'README.md').write_text('Connect to '+identifier,encoding='utf-8')
    subprocess.run(['git','add','README.md'],cwd=repository,check=True)
    result = subprocess.run([sys.executable,'scripts/check_public.py'],cwd=repository,
                            text=True,capture_output=True)
    assert result.returncode == 1
    assert identifier not in result.stdout


def test_secret_in_public_file_is_rejected_without_echoing_it(repository):
    token = 'fixture-sensitive-token-123456'
    (repository/'local/secrets/demo.json').write_text(json.dumps({'key':token}),encoding='utf-8')
    (repository/'README.md').write_text('Token: '+token,encoding='utf-8')
    subprocess.run(['git','add','README.md','scripts/check_public.py'],cwd=repository,check=True)
    result = subprocess.run([sys.executable,'scripts/check_public.py'],cwd=repository,
                            text=True,capture_output=True)
    assert result.returncode == 1
    assert token not in result.stdout


def test_private_network_address_is_rejected(repository):
    address='192.'+'168.'+'99.17'
    (repository/'README.md').write_text('Host: '+address,encoding='utf-8')
    result=audit(repository)
    assert result.returncode==1
    assert address not in result.stdout
