"""Behavior and safety-boundary tests; not evidence of clinical validation.
Run: python -m unittest -v test_tb_isolation_rules.py
"""
import itertools
import unittest
from dataclasses import replace
from tb_isolation_rules import Inputs, Policy, evaluate, parse_inputs


def patient(**kw):
    d = dict(setting="community", respiratory_tb="yes", pretreatment_burden="low",
             rifampin="susceptible", resistance_suspected="no", on_treatment="yes",
             regimen_appropriate="yes", effectiveness_assessed="yes", adherence_verified="yes",
             tolerance_adequate="yes", uninterrupted_effective_days=5,
             clinical_response="improving", community_risk="low", patient_harm="low",
             vulnerable_contacts="no", congregate_return="no", targeted_restrictions_feasible="yes")
    d.update(kw)
    return Inputs(**d)


class RulesTest(unittest.TestCase):
    def test_five_day_boundary(self):
        for day, level in [(0,"moderate"),(1,"moderate"),(4,"moderate"),(5,"none"),(6,"none")]:
            with self.subTest(day=day):
                self.assertEqual(evaluate(patient(uninterrupted_effective_days=day))["isolation_level"], level)

    def test_unknown_treatment_never_receives_credit(self):
        for field in ("on_treatment", "effectiveness_assessed", "regimen_appropriate", "adherence_verified", "tolerance_adequate"):
            for value in ("no", "unknown"):
                with self.subTest(field=field,value=value):
                    r=evaluate(patient(**{field:value,"uninterrupted_effective_days":100}))
                    self.assertNotEqual(r["isolation_level"],"none")
                    self.assertEqual(r["duration"]["credited_effective_days"],0)
                    self.assertIsNone(r["duration"]["remaining_days_if_conditions_remain_met"])

    def test_unknown_dst_can_be_judged_effective(self):
        for burden, risk, target in [("low","low",10),("high","low",14),("low","high",14)]:
            with self.subTest(burden=burden,risk=risk):
                x=patient(rifampin="unknown",pretreatment_burden=burden,community_risk=risk,
                          uninterrupted_effective_days=target)
                r=evaluate(x)
                self.assertEqual(r["duration"]["conditional_target_total_days"],target)
                self.assertEqual(r["isolation_level"],"none")

    def test_unknown_dst_without_response_is_hold(self):
        r=evaluate(patient(rifampin="unknown",clinical_response="unknown",uninterrupted_effective_days=30))
        self.assertNotEqual(r["isolation_level"],"none")

    def test_indeterminate_rif_behaves_as_unknown(self):
        a=evaluate(patient(rifampin="unknown"))
        b=evaluate(patient(rifampin="indeterminate"))
        self.assertEqual(a,b)

    def test_lab_support_can_resolve_missing_rif(self):
        r=evaluate(patient(rifampin="unknown",lab_supports_regimen="yes"))
        self.assertEqual(r["isolation_level"],"none")

    def test_rif_susceptibility_not_full_dst(self):
        r=evaluate(patient(rifampin="susceptible",other_resistance="unknown"))
        self.assertEqual(r["isolation_level"],"none")
        self.assertNotEqual(evaluate(patient(resistance_suspected="yes"))["isolation_level"],"none")

    def test_unknown_resistance_suspicion_not_no(self):
        r=evaluate(patient(resistance_suspected="unknown",uninterrupted_effective_days=30))
        self.assertIn("RESISTANCE_NOT_ADDRESSED",r["release_blockers"])

    def test_rif_resistant_day14_and_evidence(self):
        x=patient(rifampin="resistant",resistance_addressed_by_regimen="yes",lab_supports_regimen="yes",
                  micro_response="improving",expert_review_completed="yes",uninterrupted_effective_days=14)
        self.assertEqual(evaluate(x)["isolation_level"],"none")
        self.assertEqual(evaluate(replace(x,uninterrupted_effective_days=13))["isolation_level"],"moderate")
        for kw in ({"lab_supports_regimen":"unknown"},{"micro_response":"unknown"},
                   {"clinical_response":"stable"},{"expert_review_completed":"unknown"}):
            with self.subTest(kw=kw):
                self.assertNotEqual(evaluate(replace(x,**kw))["isolation_level"],"none")

    def test_inh_pza_do_not_automatically_mean_ineffective(self):
        for drug in ("inh","pza"):
            r=evaluate(patient(other_resistance=drug,resistance_addressed_by_regimen="yes",lab_supports_regimen="yes"))
            self.assertEqual(r["isolation_level"],"none")

    def test_response_worsening_needs_review(self):
        for field in ("clinical_response","micro_response"):
            x=patient(**{field:"worsening"})
            self.assertNotEqual(evaluate(x)["isolation_level"],"none")
            self.assertEqual(evaluate(replace(x,adverse_response_explained="yes"))["isolation_level"],"none")

    def test_stable_positive_followup_smear_not_release_barrier(self):
        self.assertEqual(evaluate(patient(micro_response="stable"))["isolation_level"],"none")

    def test_unknown_days_is_not_five(self):
        r=evaluate(patient(uninterrupted_effective_days=None))
        self.assertIn("EFFECTIVE_DURATION_UNKNOWN",r["release_blockers"])
        self.assertIsNone(r["duration"]["remaining_days_if_conditions_remain_met"])

    def test_all_missing_is_conservative(self):
        r=evaluate(parse_inputs({}))
        self.assertEqual(r["isolation_level"],"extensive")
        self.assertIsNone(r["duration"]["remaining_days_if_conditions_remain_met"])

    def test_harm_can_shorten_discretionary_extension(self):
        x=patient(pretreatment_burden="high",patient_harm="high",uninterrupted_effective_days=5)
        self.assertEqual(evaluate(x)["isolation_level"],"none")
        self.assertNotEqual(evaluate(replace(x,on_treatment="unknown"))["isolation_level"],"none")

    def test_harm_never_shortens_special_floor(self):
        for h in ("low","moderate","high","unknown"):
            r=evaluate(patient(patient_harm=h,vulnerable_contacts="yes"))
            self.assertEqual(r["duration"]["conditional_target_total_days"],14)

    def test_partial_harm_is_unknown(self):
        r=evaluate(patient(patient_harm="unknown",financial_harm="low"))
        self.assertEqual(r["normalized_assessment"]["patient_harm"],"unknown")
        r=evaluate(patient(patient_harm="low",housing_harm="high"))
        self.assertEqual(r["normalized_assessment"]["patient_harm"],"high")

    def test_burden_conflict_cannot_lower_observation(self):
        r=evaluate(patient(smear="3+"))
        self.assertEqual(r["normalized_assessment"]["pretreatment_burden"],"high")

    def test_derived_burden(self):
        for kw,grade in [({"smear":"negative","cavitation":"no","extensive_radiographic_disease":"no","cough":"mild"},"low"),
                         ({"smear":"1+"},"moderate"),({"cavitation":"yes"},"high"),({"gxp_load":"high"},"high")]:
            r=evaluate(patient(pretreatment_burden="unknown",**kw))
            self.assertEqual(r["normalized_assessment"]["pretreatment_burden"],grade)

    def test_exposure_can_raise_direct_community_grade(self):
        r=evaluate(patient(exposure_duration="prolonged",exposure_proximity="close",exposure_environment="poor_ventilation"))
        self.assertEqual(r["normalized_assessment"]["community_risk"],"high")

    def test_unknown_community_blocks_release(self):
        self.assertNotEqual(evaluate(patient(community_risk="unknown",uninterrupted_effective_days=30))["isolation_level"],"none")

    def test_unknown_burden_blocks_release(self):
        self.assertNotEqual(evaluate(patient(pretreatment_burden="unknown",uninterrupted_effective_days=30))["isolation_level"],"none")

    def test_pediatric_exception_not_negative_gxp_alone(self):
        x=patient(age_years=8,pediatric_noninfectious_confirmed="yes",adult_type_disease="no",smear="negative",
                  cavitation="no",cough="none",extensive_radiographic_disease="no",gxp_mtb="not_detected",
                  on_treatment="no",uninterrupted_effective_days=0)
        self.assertEqual(evaluate(x)["isolation_level"],"none")
        for kw in ({"age_years":10},{"adult_type_disease":"unknown"},{"smear":"1+"},{"gxp_mtb":"detected"}):
            self.assertNotEqual(evaluate(replace(x,**kw))["isolation_level"],"none")

    def test_extrapulmonary_exemption_and_conflict(self):
        self.assertEqual(evaluate(patient(respiratory_tb="no",on_treatment="unknown"))["isolation_level"],"none")
        self.assertNotEqual(evaluate(patient(respiratory_tb="no",smear="3+"))["isolation_level"],"none")

    def test_no_facility_clearance(self):
        for setting in ("healthcare","congregate_facility","unknown"):
            r=evaluate(patient(setting=setting,uninterrupted_effective_days=100))
            self.assertEqual(r["decision_status"],"out_of_scope_provisional_hold")
            self.assertFalse(r["facility_clearance_granted"])

    def test_actual_isolation_time_triggers_review(self):
        r=evaluate(patient(days_since_isolation_started=21))
        self.assertIn("PROLONGED_RESTRICTIONS_EXPERT_REVIEW_REQUIRED",r["release_blockers"])
        self.assertEqual(evaluate(patient(days_since_isolation_started=21,expert_review_completed="yes"))["isolation_level"],"none")

    def test_individual_extension(self):
        x=patient(individualized_minimum_days=10,individualized_reason="Documented response uncertainty")
        self.assertEqual(evaluate(x)["duration"]["conditional_target_total_days"],10)
        with self.assertRaises(ValueError): evaluate(replace(x,individualized_reason=""))

    def test_restrictive_environment_feasibility(self):
        x=patient(community_risk="high",targeted_restrictions_feasible="no")
        self.assertEqual(evaluate(x)["isolation_level"],"extensive")
        self.assertEqual(evaluate(replace(x,targeted_restrictions_feasible="yes"))["isolation_level"],"moderate")

    def test_schema_input_validation(self):
        for data in ({"smear":"positive"},{"on_treatment":True},{"uninterrupted_effective_days":-1},
                     {"uninterrupted_effective_days":5.5},{"uninterrupted_effective_days":True},
                     {"typo":0},{"gxp_mtb":"not_detected","gxp_load":"low"}):
            with self.subTest(data=data), self.assertRaises(ValueError): parse_inputs(data)
        self.assertEqual(parse_inputs({"community_risk":"medium","on_treatment":None}).community_risk,"moderate")

    def test_policy_floor(self):
        self.assertGreaterEqual(evaluate(patient(patient_harm="high"),Policy(base_days=7))["duration"]["conditional_target_total_days"],7)
        with self.assertRaises(ValueError): evaluate(patient(),Policy(base_days=4))

    def test_permutation_safety_invariants(self):
        count=0
        for burden,risk,harm,rif,tx,day in itertools.product(
                ("low","moderate","high","unknown"),("low","moderate","high","unknown"),
                ("low","moderate","high","unknown"),("susceptible","resistant","unknown"),
                ("yes","no","unknown"),(0,4,5,7,10,13,14,15)):
            r=evaluate(patient(pretreatment_burden=burden,community_risk=risk,patient_harm=harm,
                               rifampin=rif,on_treatment=tx,uninterrupted_effective_days=day))
            count+=1
            self.assertIn(r["isolation_level"],("none","moderate","extensive"))
            if r["isolation_level"]=="none":
                self.assertFalse(r["release_blockers"])
                self.assertEqual(tx,"yes")
                self.assertGreaterEqual(day,r["duration"]["conditional_target_total_days"])
            if tx!="yes":
                self.assertEqual(r["duration"]["credited_effective_days"],0)
                self.assertIsNone(r["duration"]["remaining_days_if_conditions_remain_met"])
        self.assertEqual(count,4608)


if __name__ == "__main__":
    unittest.main()
