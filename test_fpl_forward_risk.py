import unittest
from fpl_forward_risk import team_form, forecast, participation
from fpl_recent_minutes import collect
from fpl_defensive_risk import defensive_form, defensive_availability, squad_defensive_concentration

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
    def test_short_cameos_reduce_expected_minutes(self):
        regular=[{"gw":i,"minutes":90} for i in (1,2,3)]
        cameos=[{"gw":i,"minutes":20} for i in (1,2,3)]
        player=self.boot["elements"][0]
        self.assertLess(participation(player,cameos)["expected_minutes"],
                        participation(player,regular)["expected_minutes"])
        self.assertGreater(participation(player,cameos)["cameo_rate"],.9)

    def test_absent_key_teammate_changes_attacking_forecast(self):
        key={"id":11,"team":1,"element_type":3,"minutes":800,
             "expected_goals":"1.2","expected_assists":"1.4",
             "bonus":2,"status":"a","web_name":"Partner"}
        self.boot["elements"].append(key)
        base=next(p for p in forecast(self.boot,self.fixtures)["ranking"] if p["id"]==10)
        key["status"]="i"
        missing=next(p for p in forecast(self.boot,self.fixtures)["ranking"] if p["id"]==10)
        self.assertLess(missing["expected_points_proxy"],base["expected_points_proxy"])
        self.assertEqual(missing["key_teammates_unavailable"],1)

    def test_recent_archive_must_precede_target(self):
        recent={"completed_gws":[3,4],"players":{"10":[{"gw":3,"minutes":20},{"gw":4,"minutes":20}]}}
        row=forecast(self.boot,self.fixtures,recent_minutes=recent)["ranking"][0]
        self.assertEqual(row["recent_minutes_sample"],0)

    def test_live_collect_only_finished_gws(self):
        boot={"events":[{"id":1,"finished":True},{"id":2,"finished":False},
                        {"id":3,"finished":False,"is_next":True}]}
        paths=[]
        def getter(path):
            paths.append(path)
            return {"elements":[{"id":10,"stats":{"minutes":90}}]}
        out=collect(boot,getter)
        self.assertEqual(paths,["/event/1/live/"])
        self.assertEqual(out["completed_gws"],[1])

    def test_defensive_downturn_increases_conceding_risk(self):
        self.assertGreater(defensive_form({"defense":1.0,"recent_defense":1.8},1.4),1.0)
        self.assertLessEqual(defensive_form({"defense":1.0,"recent_defense":4},1.4),1.16)

    def test_keeper_injury_is_flagged_not_assumed_penalty(self):
        keeper={"id":12,"team":1,"element_type":1,"minutes":900,
                "web_name":"FirstGK","status":"a"}
        defender={"id":13,"team":1,"element_type":2,"minutes":800,
                  "web_name":"Fullback","status":"a"}
        self.boot["elements"].extend([keeper,defender])
        base=next(x for x in forecast(self.boot,self.fixtures)["ranking"] if x["id"]==13)
        keeper["status"]="i"
        changed=next(x for x in forecast(self.boot,self.fixtures)["ranking"] if x["id"]==13)
        self.assertTrue(changed["defensive_absence_flags"]["primary_gk_flag"])
        self.assertTrue(defensive_availability(self.boot["elements"],1)["review_required"])
        # Injury flag is not converted into an arbitrary clean-sheet penalty.
        self.assertEqual(base["expected_points_proxy"],changed["expected_points_proxy"])

    def test_double_defender_concentration_detected(self):
        a={"id":11,"team":1,"element_type":2,"web_name":"DefA"}
        b={"id":12,"team":1,"element_type":2,"web_name":"DefB"}
        picks={"picks":[{"element":11,"position":2},{"element":12,"position":3}]}
        audit=squad_defensive_concentration(picks,{11:a,12:b})
        self.assertEqual(audit["same_club_clusters"][0]["count"],2)

    def test_cameo_less_clean_sheet_eligibility(self):
        defender={"id":20,"team":1,"element_type":2,"minutes":540,"web_name":"Def",
                  "expected_goals":0,"expected_assists":0,"status":"a"}
        self.boot["elements"].append(defender)
        regular={"completed_gws":[1,2,3],
                 "players":{"20":[{"gw":i,"minutes":90} for i in (1,2,3)]}}
        cameo={"completed_gws":[1,2,3],
               "players":{"20":[{"gw":i,"minutes":15} for i in (1,2,3)]}}
        a=next(x for x in forecast(self.boot,self.fixtures,recent_minutes=regular)["ranking"] if x["id"]==20)
        b=next(x for x in forecast(self.boot,self.fixtures,recent_minutes=cameo)["ranking"] if x["id"]==20)
        self.assertGreater(a["expected_points_proxy"],b["expected_points_proxy"])

    def test_no_news_penalty(self):
        a=forecast(self.boot,self.fixtures)["ranking"][0]["expected_points_proxy"]
        self.boot["elements"][0]["news"]="Club financial investigation reported"
        b=forecast(self.boot,self.fixtures)["ranking"][0]["expected_points_proxy"]
        self.assertEqual(a,b)
if __name__=="__main__": unittest.main()
