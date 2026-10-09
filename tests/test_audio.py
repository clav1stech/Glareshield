from glareshield.audio import AudioDetector
from glareshield.model import Source


def test_debounce_hold_and_cooldown():
    detector=AudioDetector(Source(type='audio_process',threshold=.1,min_ms=300,cooldown_s=10,hold_s=5))
    assert not detector.sample(.2,0)
    assert not detector.sample(.2,.2)
    assert detector.sample(.2,.31)
    assert detector.sample(0,4)
    assert not detector.sample(0,6)
    assert not detector.sample(.2,7)
    assert not detector.sample(.2,8)
    assert detector.sample(.2,11)


def test_short_spike_is_rejected():
    detector=AudioDetector(Source(type='audio_process',threshold=.1,min_ms=300))
    assert not detector.sample(.8,0)
    assert not detector.sample(0,.1)
    assert not detector.sample(.8,.2)
    assert not detector.sample(0,.4)
