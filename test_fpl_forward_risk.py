import unittest
from fpl_forward_risk import team_form, forecast

class RiskForecastTests(unittest.TestCase):
    def setUp(self):
        self.fixtures=[
          {"event":1,"finished":True,"team_h":1,"team_a":2,"team_h_score":2,"team_a_score":0},
          {"event":2,"finished":True,"team_h":1,"team_a":2,"team_h_score":0,"team_a_score":2},
          {"event":3,"finished":True,"team_h":1,"team_a":2,"team_h_score":0,"team_a_score":1},
          {"event":4,"finished":False,"team_h":1,"team_a":2,"team_h_score":None,"team_a_score":None}]
        self.boot={"events":[{"id":4,"is_next":True,"finished":False}],
          "teams":[{"id":1,"short_name":"AAA"},{"id":2,"short_name":"BBB"}],
          "elements":[{"id":10,"team":1,"element_type":4,"minutes":270,
                       "expected_goals":"2.0","expected_assists":"0.2",
                       "bonus":2,"status":"a","web_name":"Forward"}]}
    def test_no_target_or_future_leakage(self):
        baseline=forecast(self.boot,self.fixtures)
        changed=list(self.fixtures)
        changed[-1]={**changed[-1],"finished":True,"team_h_score":10,"team_a_score":0}
        future={**changed[-1],"event":5}
        altered=forecast(self.boot,changed+[future])
        self.assertEqual(baseline["ranking"][0]["expected_points_proxy"],
                         altered["ranking"][0]["expected_points_proxy"])
        self.assertEqual(baseline["ranking"][0]["attack_trend"],
                         altered["ranking"][0]["attack_trend"])
    def test_recent_downturn_is_bounded(self):
        _,f=team_form(self.fixtures,4)
        self.assertLess(f[1]["attack_trend"],1)
        self.assertGreaterEqual(f[1]["attack_trend"],.83)
    def test_no_news_penalty(self):
        a=forecast(self.boot,self.fixtures)["ranking"][0]["expected_points_proxy"]
        self.boot["elements"][0]["news"]="Club financial investigation reported"
        b=forecast(self.boot,self.fixtures)["ranking"][0]["expected_points_proxy"]
        self.assertEqual(a,b)
if __name__=="__main__": unittest.main()
