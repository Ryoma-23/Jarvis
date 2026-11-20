import unittest
from pydantic import ValidationError
from app.routes.voice_diagnostics import Snapshot, summarize
from scripts.evaluate_speaker_diagnostics import evaluate
from app.services.speaker_service import enrollment_consistency


class SpeakerEvaluationTests(unittest.TestCase):
    def document(self):
        events = []
        for i, (label, score) in enumerate([('owner', .89), ('video', .88), ('mixed', .95), ('owner', None)]):
            base = {'session': 's', 'item': str(i)}
            events.extend([dict(base, kind='speech_start', ms=i*3, scenario='video_only'),
                           dict(base, kind='speaker_result', ms=i*3+1, score=score, value='insufficient' if score is None else 'owner_candidate'),
                           dict(base, kind='speaker_label', ms=i*3+2, speaker_label=label)])
        return {'id': '25736bf6-ab34-495a-a941-9dcffab9a84e', 'started_at': 'test', 'complete': True, 'events': events}

    def test_threshold_denominators_and_unknown_old_logs(self):
        doc = self.document(); report = evaluate(doc, [.85, .9])
        self.assertEqual(report['comparisons'][0]['video_passed'], 1)
        self.assertEqual(report['comparisons'][1]['owner_rejected'], 1)
        self.assertEqual(report['comparisons'][1]['owner_scored'], 1)
        self.assertEqual(report['unscored_by_label'], {'owner': 1})
        doc['events'] = [e for e in doc['events'] if e['kind'] != 'speaker_label']
        self.assertEqual(evaluate(doc)['labels'], {'unknown': 4})
        self.assertIsNone(evaluate(doc)['comparisons'][0]['video_pass_rate'])

    def test_last_label_wins_and_invalid_labels_rejected(self):
        doc = self.document()
        doc['events'].append(dict(ms=20, kind='speaker_label', session='s', item='0', speaker_label='video'))
        snapshot = Snapshot.model_validate(doc)
        self.assertEqual(summarize(snapshot)['turns'][0]['speaker_label'], 'video')
        self.assertEqual(evaluate(doc)['labels']['video'], 2)
        doc['events'][-1]['session'] = 'another_session'
        with self.assertRaises(ValidationError): Snapshot.model_validate(doc)

    def test_read_only_registration_consistency(self):
        self.assertEqual(enrollment_consistency([])['pair_count'], 0)
        samples = [{'embedding': [1, 0]}, {'embedding': [1, 0]}, {'embedding': [0, 1]}]
        result = enrollment_consistency(samples)
        self.assertEqual(result['pair_count'], 3)
        self.assertEqual(result['pair_min'], 0)
        self.assertAlmostEqual(result['pair_mean'], 1/3, places=5)

    def test_invalid_thresholds(self):
        with self.assertRaises(ValueError): evaluate(self.document(), [float('nan')])
