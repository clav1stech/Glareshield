"""Generate replaceable local PCM sounds without shipping installation data."""
import math
import struct
import wave
from pathlib import Path


def generate(directory:Path):
    directory.mkdir(parents=True,exist_ok=True)
    for name,notes in {'warning.wav':[(880,.18),(0,.1),(880,.18)],
                       'contact.wav':[(660,.2),(880,.25),(1100,.3)]}.items():
        path=directory/name
        if path.exists():
            continue
        samples=[]
        rate=44100
        for frequency,duration in notes:
            count=round(rate*duration)
            for index in range(count):
                envelope=min(1,index/(rate*.01),(count-index)/(rate*.025))
                sample=int(7000*envelope*math.sin(2*math.pi*frequency*index/rate)) if frequency else 0
                samples.append(sample)
        with wave.open(str(path),'wb') as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(rate)
            output.writeframes(struct.pack('<'+'h'*len(samples),*samples))
