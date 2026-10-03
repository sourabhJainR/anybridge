import unittest
from anybridge.webmcp_replay import SecurityReplayCase, SecurityReplayOutcome, replay_security_corpus

class ReplayTests(unittest.TestCase):
    def test_round_trip(self):
        case=SecurityReplayCase('c1','a1','output_injection','playwright','https://example.com','schema','base64',{'output':'x'})
        report=replay_security_corpus([case],[SecurityReplayOutcome('c1',False)],generate_counter_cases=False)
        self.assertEqual(report.outcomes,1)
        self.assertEqual(report.ignored_outcomes,0)
        self.assertEqual(report.observations,1)
    def test_unknown_case_is_ignored(self):
        report=replay_security_corpus([], [SecurityReplayOutcome('missing',False)], generate_counter_cases=False)
        self.assertEqual(report.ignored_outcomes,1)

if __name__ == '__main__': unittest.main()
