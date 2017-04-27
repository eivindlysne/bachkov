"""Markov Chain generator for Bach chorales"""
import sys
import json
from decimal import Decimal
from ast import literal_eval as make_tuple
from markovify import Chain
from music21 import (
    corpus,
    duration,
    environment,
    instrument,
    note,
    stream
)


class Voice(object):
    Soprano = 'Soprano'
    Alto = 'Alto'
    Tenor = 'Tenor'
    Bass = 'Bass'
    All = frozenset({'Soprano', 'Alto', 'Tenor', 'Bass'})

    @classmethod
    def order(cls, voice):
        keys = {
            cls.Soprano: 1,
            cls.Alto: 2,
            cls.Tenor: 3,
            cls.Bass: 4,
        }
        return keys[voice]


def init_settings():
    settings = environment.UserSettings()
    environment.UserSettings()
    try:
        settings.create()
    except environment.UserSettingsException:
        pass
    settings['musicxmlPath'] = '/usr/bin/musescore'
    settings['directoryScratch'] = '/home/eivind/Repositories/bachkov/tmp'
    return settings


def bach_chorales():
    def _filter(chorale):
        part_names = {part.partName for part in chorale.parts}
        return part_names == Voice.All

    chorales = corpus.chorales.Iterator(numberingSystem='bwv')
    return filter(_filter, chorales)


def filter_by_key(chorales, key):
    def _filter(chorale):
        return chorale.analyze('key').mode == key

    return filter(_filter, chorales)


def filter_by_time_signature(chorales, signature='4/4'):
    def _filter(chorale):
        time_signature = chorale.parts[0].measure(1).getTimeSignatures()[0]
        return time_signature.ratioString == signature

    return filter(_filter, chorales)


def notes_and_durations(chorale, voice):
    part = chorale.getElementById(voice)
    for elem in part.recurse(skipSelf=True).notesAndRests:
        try:
            name = elem.nameWithOctave if elem.isNote else elem.name
        except AttributeError:
            # Element is a Chord. Return the first note
            elem = elem._notes[0]
            name = elem.nameWithOctave
        else:
            yield name, elem.duration


def gen_states(S, A, T, B):
    counter = {
        Voice.Soprano: Decimal(0.),
        Voice.Alto: Decimal(0.),
        Voice.Tenor: Decimal(0.),
        Voice.Bass: Decimal(0.),
    }
    streams = {
        Voice.Soprano: S,
        Voice.Alto: A,
        Voice.Tenor: T,
        Voice.Bass: B,
    }
    state = {
        Voice.Soprano: None,
        Voice.Alto: None,
        Voice.Tenor: None,
        Voice.Bass: None,
    }
    while True:
        min_value = min(counter.values())
        min_voices = [k for k in counter if counter[k] == min_value]
        for voice in min_voices:
            elem, dur = next(streams[voice])
            state[voice] = (elem, dur.quarterLength)
            counter[voice] += Decimal(dur.quarterLength)
        yield (
            state[Voice.Soprano],
            state[Voice.Alto],
            state[Voice.Tenor],
            state[Voice.Bass],
        )


def make_model(model_file, state_size, key):
    init_settings()
    chorales = bach_chorales()
    chorales = filter_by_time_signature(chorales)
    if key:
        chorales = filter_by_key(chorales, key)
    training = []

    for chorale in chorales:
        sop = notes_and_durations(chorale, Voice.Soprano)
        alt = notes_and_durations(chorale, Voice.Alto)
        ten = notes_and_durations(chorale, Voice.Tenor)
        bas = notes_and_durations(chorale, Voice.Bass)
        states = [str(state) for state in gen_states(sop, alt, ten, bas)]
        training.append(states)

    chain = Chain(training, state_size=state_size)
    with open(model_file, 'w') as f:
        f.write(chain.to_json())


def make_music(model_file):
    with open(model_file) as f:
        model = json.load(f)

    chain = Chain.from_json(model)

    score = stream.Score()
    soprano_part = stream.Part()
    soprano_part.insert(0, instrument.Soprano())
    alto_part = stream.Part()
    alto_part.insert(0, instrument.Alto())
    tenor_part = stream.Part()
    tenor_part.insert(0, instrument.Tenor())
    bass_part = stream.Part()
    bass_part.insert(0, instrument.Bass())

    counter = {
        Voice.Soprano: Decimal(0.),
        Voice.Alto: Decimal(0.),
        Voice.Tenor: Decimal(0.),
        Voice.Bass: Decimal(0.),
    }
    current_state = {
        Voice.Soprano: None,
        Voice.Alto: None,
        Voice.Tenor: None,
        Voice.Bass: None,
    }
    parts = {
        Voice.Soprano: soprano_part,
        Voice.Alto: alto_part,
        Voice.Tenor: tenor_part,
        Voice.Bass: bass_part,
    }

    for state in chain.walk():
        S, A, T, B = make_tuple(state)
        current_state[Voice.Soprano] = S
        current_state[Voice.Alto] = A
        current_state[Voice.Tenor] = T
        current_state[Voice.Bass] = B
        min_value = min(counter.values())
        min_voices = [k for k in counter if counter[k] == min_value]
        for voice in min_voices:
            pitch, d = current_state[voice]
            if pitch == 'rest':
                n = note.Rest(duration=duration.Duration(d))
            else:
                n = note.Note(pitch, duration=duration.Duration(d))
            parts[voice].append(n)
            counter[voice] += Decimal(d)
    for k, v in parts.items():
        score.insert(Voice.order(k), v)
    score.show()


if __name__ == '__main__':
    cmd, file_name, *args = sys.argv[1:]
    if cmd == 'make_model':
        state_size = args[0]
        key = args[1] if len(args) >= 2 else None
        make_model(file_name, int(state_size), key)
    elif cmd == 'make_music':
        make_music(file_name)
    else:
        sys.exit(1)
