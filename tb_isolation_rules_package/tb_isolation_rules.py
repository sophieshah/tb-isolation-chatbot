"""Deterministic COMMUNITY TB restriction proposal, version 0.1.0.

Research/pilot implementation requiring clinical policy validation before deployment.
No external dependencies. Python >=3.10. See RULES_AND_EVIDENCE.txt.
Run: python tb_isolation_rules.py example_input.json
Inputs describe the assessment NOW; never use later DST to rewrite an earlier decision.
"""
from __future__ import annotations
from dataclasses import dataclass, fields, asdict
import argparse
import json
from pathlib import Path

VERSION = "0.1.0-draft"
GRADES = ("low", "moderate", "high", "unknown")
TRI = ("yes", "no", "unknown")
RANK = {"low": 0, "moderate": 1, "high": 2}


@dataclass(frozen=True)
class Inputs:
    # Scope. This engine does not clear healthcare or congregate facility precautions.
    setting: str = "unknown"  # community, healthcare, congregate_facility, unknown
    respiratory_tb: str = "unknown"  # yes, no (evaluated and excluded), unknown
    age_years: int | None = None
    pediatric_noninfectious_confirmed: str = "unknown"
    adult_type_disease: str = "unknown"
    # PRETREATMENT observations only. MTB detection and RIF resistance are separate.
    pretreatment_burden: str = "unknown"
    smear: str = "unknown"  # negative, scanty, 1+, 2+, 3+, 4+, unknown
    cough: str = "unknown"  # none, mild, frequent, unknown
    cavitation: str = "unknown"
    extensive_radiographic_disease: str = "unknown"
    gxp_mtb: str = "unknown"  # detected, not_detected, unknown
    gxp_load: str = "unknown"  # trace, very_low, low, medium, high, unknown
    rifampin: str = "unknown"  # susceptible, resistant, indeterminate, unknown
    other_resistance: str = "unknown"  # none_detected, inh, pza, other, unknown
    resistance_suspected: str = "unknown"  # clinical/epidemiologic concern
    resistance_addressed_by_regimen: str = "unknown"
    # All five are explicit judgments, not inferred from "RIPE" or an LLM narrative.
    on_treatment: str = "unknown"
    regimen_appropriate: str = "unknown"  # adequate multidrug regimen/doses
    effectiveness_assessed: str = "unknown"  # clinician judgment, yes/no/unknown
    adherence_verified: str = "unknown"
    tolerance_adequate: str = "unknown"  # includes absorption/interactions if relevant
    lab_supports_regimen: str = "unknown"  # DST supports actual regimen, not GXP alone
    uninterrupted_effective_days: int | None = None
    days_since_isolation_started: int | None = None
    clinical_response: str = "unknown"  # improving, stable, worsening, asymptomatic, unknown
    micro_response: str = "unknown"  # improving, stable, worsening, unknown
    adverse_response_explained: str = "unknown"  # reviewed alternative cause/sampling issue
    # Community risk is FUTURE exposure if restrictions are lifted, not past exposure.
    community_risk: str = "unknown"
    exposure_duration: str = "unknown"  # brief, recurrent, prolonged, unknown
    exposure_proximity: str = "unknown"  # distant, shared_air, close, unknown
    exposure_environment: str = "unknown"  # outdoor, well_ventilated, poor_ventilation, unknown
    new_contacts: str = "unknown"  # none, few, many, unknown
    vulnerable_contacts: str = "unknown"  # under 5 or immunosuppressed, exposed prospectively
    congregate_return: str = "unknown"
    targeted_restrictions_feasible: str = "unknown"
    # Subjective harm grades after available supports; never infer low from silence.
    patient_harm: str = "unknown"
    financial_harm: str = "unknown"
    housing_harm: str = "unknown"
    food_harm: str = "unknown"
    stigma_harm: str = "unknown"
    mental_health_harm: str = "unknown"
    access_to_care_harm: str = "unknown"
    # Accountable, named individual extensions, not fixed durations for diagnoses.
    individualized_minimum_days: int | None = None
    individualized_reason: str = ""
    expert_review_completed: str = "unknown"


ENUMS = {name: TRI for name in (
    "respiratory_tb", "pediatric_noninfectious_confirmed", "adult_type_disease",
    "cavitation", "extensive_radiographic_disease", "resistance_suspected",
    "resistance_addressed_by_regimen", "on_treatment", "regimen_appropriate",
    "effectiveness_assessed", "adherence_verified", "tolerance_adequate",
    "lab_supports_regimen", "adverse_response_explained", "vulnerable_contacts",
    "congregate_return", "targeted_restrictions_feasible", "expert_review_completed")}
ENUMS.update({name: GRADES for name in (
    "pretreatment_burden", "community_risk", "patient_harm", "financial_harm",
    "housing_harm", "food_harm", "stigma_harm", "mental_health_harm", "access_to_care_harm")})
ENUMS.update({
    "setting": ("community", "healthcare", "congregate_facility", "unknown"),
    "smear": ("negative", "scanty", "1+", "2+", "3+", "4+", "unknown"),
    "cough": ("none", "mild", "frequent", "unknown"),
    "gxp_mtb": ("detected", "not_detected", "unknown"),
    "gxp_load": ("trace", "very_low", "low", "medium", "high", "unknown"),
    "rifampin": ("susceptible", "resistant", "indeterminate", "unknown"),
    "other_resistance": ("none_detected", "inh", "pza", "other", "unknown"),
    "clinical_response": ("improving", "stable", "worsening", "asymptomatic", "unknown"),
    "micro_response": ("improving", "stable", "worsening", "unknown"),
    "exposure_duration": ("brief", "recurrent", "prolonged", "unknown"),
    "exposure_proximity": ("distant", "shared_air", "close", "unknown"),
    "exposure_environment": ("outdoor", "well_ventilated", "poor_ventilation", "unknown"),
    "new_contacts": ("none", "few", "many", "unknown"),
})
INTEGER_FIELDS = ("age_years", "uninterrupted_effective_days", "days_since_isolation_started",
                  "individualized_minimum_days")


def parse_inputs(data: dict) -> Inputs:
    if not isinstance(data, dict):
        raise ValueError("Input must be a JSON object")
    extra = set(data) - {f.name for f in fields(Inputs)}
    if extra:
        raise ValueError(f"Unrecognized input field(s): {sorted(extra)}")
    normalized = dict(data)
    for name in ENUMS:
        if name in normalized:
            v = normalized[name]
            if v is None:
                v = "unknown"
            if not isinstance(v, str):
                raise ValueError(f"{name} must be a named string value")
            v = v.strip().lower()
            if name in (n for n, e in ENUMS.items() if e == GRADES) and v == "medium":
                v = "moderate"
            normalized[name] = v
    x = Inputs(**normalized)
    validate(x)
    return x


def validate(x: Inputs) -> None:
    for name, options in ENUMS.items():
        if getattr(x, name) not in options:
            raise ValueError(f"{name} must be one of {options}")
    for name in INTEGER_FIELDS:
        v = getattr(x, name)
        if v is not None and (type(v) is not int or v < 0):
            raise ValueError(f"{name} must be a nonnegative integer or null")
    if not isinstance(x.individualized_reason, str):
        raise ValueError("individualized_reason must be text")
    if x.individualized_minimum_days is not None and not x.individualized_reason.strip():
        raise ValueError("An individualized minimum requires a documented reason")
    if x.gxp_mtb == "not_detected" and x.gxp_load != "unknown":
        raise ValueError("MTB not detected cannot have an MTB semiquantitative load")


@dataclass(frozen=True)
class Policy:
    """Proposed case-informed policy. Numerical choices beyond day 5 need approval."""
    name: str = "case_informed_draft"
    base_days: int = 5
    moderate_burden_low_risk_days: int = 7
    high_burden_low_risk_days: int = 10
    low_burden_high_risk_days: int = 10
    higher_burden_high_risk_days: int = 14
    unknown_dst_low_burden_low_risk_days: int = 10
    unknown_dst_other_days: int = 14
    vulnerable_or_congregate_days: int = 14
    rif_resistant_days: int = 14
    review_interval_days: int = 7


def _max_grade(values: list[str]) -> str:
    known = [v for v in values if v != "unknown"]
    return max(known, key=RANK.get) if known else "unknown"


def derive_burden(x: Inputs) -> tuple[str, list[str]]:
    """Proposed phenotype mapping, not a validated score; never uses follow-up smear."""
    why = []
    if (x.smear in ("2+", "3+", "4+") or x.cavitation == "yes"
            or x.extensive_radiographic_disease == "yes" or x.gxp_load == "high"):
        derived = "high"
    elif x.smear in ("scanty", "1+") or x.gxp_load == "medium":
        derived = "moderate"
    elif (x.smear == "negative" and x.cavitation == "no"
          and x.extensive_radiographic_disease == "no"
          and x.cough in ("none", "mild")):
        derived = "low"
    elif x.smear == "negative" and x.cough == "frequent":
        derived = "moderate"
    else:
        derived = "unknown"
    grade = _max_grade([x.pretreatment_burden, derived])
    if (x.pretreatment_burden != "unknown" and derived != "unknown"
            and RANK[derived] > RANK[x.pretreatment_burden]):
        why.append("BURDEN_CONFLICT: observed pretreatment markers raised supplied grade")
    if grade == "unknown":
        why.append("BURDEN_UNKNOWN: use high for precautionary decisions, not a diagnosis")
    return grade, why


def derive_community(x: Inputs) -> tuple[str, list[str]]:
    why = []
    high = (x.vulnerable_contacts == "yes" or x.congregate_return == "yes" or
            (x.exposure_duration in ("recurrent", "prolonged") and
             x.exposure_proximity in ("close", "shared_air") and
             x.exposure_environment == "poor_ventilation"))
    if high:
        inferred = "high"
    elif (x.exposure_duration == "brief" and x.exposure_proximity == "distant"
          and x.exposure_environment in ("outdoor", "well_ventilated")
          and x.new_contacts in ("none", "few")
          and x.vulnerable_contacts == x.congregate_return == "no"):
        inferred = "low"
    elif all(v != "unknown" for v in (x.exposure_duration, x.exposure_proximity,
             x.exposure_environment, x.new_contacts, x.vulnerable_contacts, x.congregate_return)):
        inferred = "moderate"
    else:
        inferred = "unknown"
    grade = _max_grade([x.community_risk, inferred])
    if x.community_risk != "unknown" and inferred != "unknown" and RANK[inferred] > RANK[x.community_risk]:
        why.append("COMMUNITY_CONFLICT: exposure details raised supplied grade")
    if grade == "unknown":
        why.append("COMMUNITY_UNKNOWN: use high pending exposure assessment")
    return grade, why


def derive_harm(x: Inputs) -> str:
    # Max of clinician grades preserves a severe problem in one domain.
    vals = [getattr(x, n) for n in ("financial_harm", "housing_harm", "food_harm",
                                   "stigma_harm", "mental_health_harm", "access_to_care_harm")]
    grade = _max_grade([x.patient_harm] + vals)
    if x.patient_harm == "unknown" and "unknown" in vals and grade != "high":
        return "unknown"  # partial questionnaire cannot establish low overall harm
    return grade


def assess_treatment(x: Inputs) -> tuple[bool, list[str]]:
    blocks = []
    for n in ("on_treatment", "regimen_appropriate", "effectiveness_assessed",
              "adherence_verified", "tolerance_adequate"):
        if getattr(x, n) != "yes":
            blocks.append(f"TREATMENT_UNVERIFIED:{n}")
    resistance = x.rifampin == "resistant" or x.other_resistance in ("inh", "pza", "other")
    if resistance or x.resistance_suspected != "no":
        if x.resistance_addressed_by_regimen != "yes":
            blocks.append("RESISTANCE_NOT_ADDRESSED")
        if x.lab_supports_regimen != "yes":
            blocks.append("RESISTANCE_REQUIRES_REGIMEN_EVIDENCE")
    if x.lab_supports_regimen == "no":
        blocks.append("LAB_DOES_NOT_SUPPORT_REGIMEN")
    if (x.clinical_response == "worsening" or x.micro_response == "worsening") and x.adverse_response_explained != "yes":
        blocks.append("UNEXPLAINED_ADVERSE_RESPONSE")
    # Unknown RIF is NOT synonymous with resistant. Empiric treatment may be judged
    # effective if no resistance suspicion and clinical improvement supports that judgment.
    if x.rifampin in ("unknown", "indeterminate") and x.lab_supports_regimen != "yes":
        if x.resistance_suspected != "no" or x.clinical_response not in ("improving", "asymptomatic"):
            blocks.append("UNKNOWN_DST_NEEDS_CLINICAL_SUPPORT")
    return not blocks, blocks


def _target(x: Inputs, p: Policy, burden: str, community: str, harm: str) -> tuple[int, list[str]]:
    rules = []
    elevated_harm = harm in ("moderate", "high")
    if community == "low":
        target = {"low": p.base_days, "moderate": p.moderate_burden_low_risk_days,
                  "high": p.high_burden_low_risk_days}[burden]
        if elevated_harm:
            target = p.base_days
        rules.append("D01_CASE_INFORMED_LOW_COMMUNITY")
    elif community == "moderate":
        # Medium-risk interpolation is a proposed policy, not directly in the matrix.
        target = p.base_days if burden == "low" else (7 if elevated_harm else 10)
        rules.append("D02_PROPOSED_MEDIUM_COMMUNITY")
    else:
        target = p.low_burden_high_risk_days if burden == "low" else (10 if elevated_harm else p.higher_burden_high_risk_days)
        rules.append("D03_CASE_INFORMED_HIGH_COMMUNITY")
    if x.rifampin in ("unknown", "indeterminate") and x.lab_supports_regimen != "yes":
        target = max(target, p.unknown_dst_low_burden_low_risk_days if burden == community == "low" else p.unknown_dst_other_days)
        rules.append("D04_UNKNOWN_DST_EXTENSION")
    if x.vulnerable_contacts == "yes" or x.congregate_return == "yes":
        target = max(target, p.vulnerable_or_congregate_days)
        rules.append("D05_SPECIAL_EXPOSURE_EXTENSION")
    if x.rifampin == "resistant":
        target = max(target, p.rif_resistant_days)
        rules.append("D06_RIF_RESISTANT_POLICY_MINIMUM")
    if x.individualized_minimum_days is not None:
        target = max(target, x.individualized_minimum_days)
        rules.append("D07_DOCUMENTED_INDIVIDUAL_EXTENSION")
    return max(target, p.base_days), rules


def evaluate(x: Inputs, policy: Policy = Policy()) -> dict:
    validate(x)
    for f in fields(policy):
        if f.name != "name" and (type(getattr(policy, f.name)) is not int or getattr(policy, f.name) < 1):
            raise ValueError("Policy day values must be positive integers")
    if policy.base_days < 5:
        raise ValueError("Routine policy cannot shorten the five-day treatment anchor")
    burden, notes = derive_burden(x)
    community, community_notes = derive_community(x)
    notes += community_notes
    harm = derive_harm(x)
    b = "high" if burden == "unknown" else burden
    c = "high" if community == "unknown" else community
    target, rules = _target(x, policy, b, c, harm)
    effective, blocks = assess_treatment(x)
    credited = x.uninterrupted_effective_days if effective and x.uninterrupted_effective_days is not None else 0
    if effective and x.uninterrupted_effective_days is None:
        blocks.append("EFFECTIVE_DURATION_UNKNOWN")
    # Unknown site is not evidence that respiratory involvement was excluded.
    if x.respiratory_tb == "unknown":
        blocks.append("RESPIRATORY_INVOLVEMENT_UNKNOWN")
    if burden == "unknown":
        blocks.append("PRETREATMENT_BURDEN_UNRESOLVED")
    if community == "unknown":
        blocks.append("COMMUNITY_RISK_UNRESOLVED")
    if harm == "unknown":
        notes.append("HARM_UNKNOWN: no automatic shortening; complete harm assessment")
    if x.uninterrupted_effective_days and not effective:
        notes.append("UNVERIFIED_DAYS_NOT_CREDITED: supplied duration is preserved in input only")
    clinical_ok = x.clinical_response in ("improving", "asymptomatic")
    if c == "high" and b != "low" and not (clinical_ok or x.micro_response == "improving"):
        blocks.append("HIGH_RISK_RESPONSE_SUPPORT_REQUIRED")
    # Stable positive smear alone is not a treatment failure and does not block routine release.
    if x.rifampin == "resistant":
        if x.expert_review_completed != "yes":
            blocks.append("RIF_RESISTANT_EXPERT_REVIEW_REQUIRED")
        if not clinical_ok:
            blocks.append("RIF_RESISTANT_CLINICAL_RESPONSE_REQUIRED")
        if x.micro_response != "improving":
            blocks.append("RIF_RESISTANT_MICRO_RESPONSE_REQUIRED")
    if x.rifampin in ("unknown", "indeterminate") and x.lab_supports_regimen != "yes" and not clinical_ok:
        blocks.append("UNKNOWN_DST_CLINICAL_RESPONSE_REQUIRED")
    # A prolonged actual isolation episode needs review even if the treatment clock is short.
    overdue = x.days_since_isolation_started is not None and x.days_since_isolation_started > 14
    if (overdue or target > 14) and x.expert_review_completed != "yes":
        blocks.append("PROLONGED_RESTRICTIONS_EXPERT_REVIEW_REQUIRED")
    exemption = None
    if x.respiratory_tb == "no":
        # Reject contradictory exclusion rather than silently releasing.
        if x.smear in ("scanty", "1+", "2+", "3+", "4+") or x.gxp_mtb == "detected" or x.cavitation == "yes":
            blocks.append("CONFLICT_RESPIRATORY_EXCLUSION")
        else:
            exemption = "S01_RESPIRATORY_TB_EXCLUDED"
    if (x.age_years is not None and x.age_years < 10 and x.pediatric_noninfectious_confirmed == "yes"
            and x.adult_type_disease == "no" and x.smear == "negative"
            and x.cavitation == "no" and x.cough == "none"
            and x.gxp_mtb != "detected" and x.extensive_radiographic_disease == "no"):
        exemption = "S02_CONFIRMED_NONINFECTIOUS_PEDIATRIC_PHENOTYPE"
    in_scope = x.setting == "community"
    if not in_scope:
        blocks.append("SETTING_REQUIRES_SEPARATE_PROTOCOL")
    if exemption and in_scope:
        level, status, target, credited, remaining = "none", "no_community_restrictions", 0, 0, 0
        blocks = []
        rules = [exemption]
    else:
        if not in_scope:
            level, status = "extensive", "out_of_scope_provisional_hold"
            rules.append("L00_OUT_OF_SCOPE")
        elif not blocks and credited >= target:
            level, status = "none", "eligible_to_discontinue_under_draft_policy"
            rules.append("L01_TARGET_AND_RELEASE_CONDITIONS_MET")
        else:
            resistance_unresolved = any(v.startswith("RESISTANCE_") for v in blocks)
            if not effective:
                level = "extensive" if b == "high" or c == "high" or resistance_unresolved else "moderate"
                rules.append("L02_NO_VERIFIED_EFFECTIVE_TREATMENT")
            elif x.targeted_restrictions_feasible == "no" and c == "high":
                level = "extensive"
                rules.append("L03_TARGETED_RESTRICTIONS_NOT_FEASIBLE")
            elif (x.rifampin == "resistant" and credited < 5) or (credited == 0 and b == "high"):
                level = "extensive"
                rules.append("L04_EARLY_HIGHER_RISK_TREATMENT")
            elif x.targeted_restrictions_feasible == "unknown" and c == "high":
                level = "extensive"
                rules.append("L05_RESTRICTION_FEASIBILITY_UNKNOWN")
            else:
                level = "moderate"
                rules.append("L06_TARGETED_RESTRICTIONS_DURING_TREATMENT")
            status = "hold_pending_reassessment" if blocks else "continue_to_conditional_target"
        # NULL means there is no defensible finite release countdown, not zero days.
        remaining = None if blocks else max(0, target - credited)
    support = [n for n in ("financial_harm", "housing_harm", "food_harm", "stigma_harm",
                            "mental_health_harm", "access_to_care_harm") if getattr(x, n) in ("moderate", "high")]
    if level == "none":
        reassess = None
    elif blocks or harm == "high":
        reassess = 1  # operational proposal: prompt review; not a release interval
    else:
        reassess = min(policy.review_interval_days, max(1, target - credited),
                       max(1, 5 - credited) if credited < 5 else policy.review_interval_days)
    return {
        "ruleset_version": VERSION, "policy": policy.name, "clinical_validation_status": "draft_not_validated",
        "isolation_level": level, "decision_status": status,
        "duration": {
            "clock": "verified_uninterrupted_effective_treatment_days",
            "conditional_target_total_days": target,
            "credited_effective_days": credited,
            "remaining_days_if_conditions_remain_met": remaining,
            "fixed_release_date": None,
            "reassess_within_days": reassess,
        },
        "normalized_assessment": {"pretreatment_burden": burden, "burden_used_for_policy": b,
                                  "community_risk": community, "community_used_for_policy": c,
                                  "patient_harm": harm, "effective_treatment_verified": effective},
        "rule_ids": rules, "release_blockers": list(dict.fromkeys(blocks)),
        "notes": notes, "support_domains": support,
        "expert_review_required": bool(overdue or target > 14 or x.rifampin == "resistant"),
        "restriction_definition": {
            "none": "No community RIR under this draft policy; treatment and follow-up continue.",
            "moderate": "Restrict high-risk shared-air activities; allow individually planned low-risk activities with mitigation.",
            "extensive": "Provisional broad separation from new contacts; arrange essential care and supports. This does not mandate hospitalization.",
        }[level],
        "facility_clearance_granted": False,
        "llm_contract": "Explain this structured decision and unresolved inputs. Do not remove blockers, invent treatment credit, or silently change the level/duration. Record any clinician-approved deviation separately.",
    }


def input_schema() -> dict:
    properties = {name: {"type": ["string", "null"], "enum": list(options) + [None]}
                  for name, options in ENUMS.items()}
    for name, options in ENUMS.items():
        if options == GRADES:
            properties[name]["enum"].append("medium")
    properties.update({n: {"type": ["integer", "null"], "minimum": 0} for n in INTEGER_FIELDS})
    properties["individualized_reason"] = {"type": "string"}
    return {"$schema": "https://json-schema.org/draft/2020-12/schema", "title": "TB community isolation inputs",
            "type": "object", "additionalProperties": False, "properties": properties,
            "description": "Omitted fields remain unknown. Integer durations count completed days of verified uninterrupted effective treatment."}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", nargs="?", type=Path)
    parser.add_argument("--schema", action="store_true")
    args = parser.parse_args()
    if args.schema:
        print(json.dumps(input_schema(), indent=2))
    elif args.input:
        try:
            result = evaluate(parse_inputs(json.loads(args.input.read_text(encoding="utf-8-sig"))))
        except (ValueError, TypeError) as e:
            parser.error(str(e))
        print(json.dumps(result, indent=2))
    else:
        parser.error("Supply an input JSON file or --schema")


if __name__ == "__main__":
    main()
