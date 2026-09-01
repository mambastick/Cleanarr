"""Pure evaluation for the optional, reversible seeding-stop policy."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from cleanarr.domain.config import SeedingStopPolicyConfig, SeedingStopPolicyMode
from cleanarr.domain.downloads import ListingFreshness, TorrentOwnership, TorrentSnapshot, TorrentState


class PolicyDecision(StrEnum):
    ELIGIBLE = "eligible"
    BLOCKED = "blocked"
    EXCLUDED = "excluded"


@dataclass(frozen=True)
class PolicyEvaluation:
    decision: PolicyDecision
    reason_code: str
    facts: dict[str, object]


def evaluate_seeding_stop_policy(policy: SeedingStopPolicyConfig, snapshot: TorrentSnapshot) -> PolicyEvaluation:
    """Evaluate one observation without performing any external mutation."""

    facts: dict[str, object] = {
        "ratio": snapshot.ratio,
        "seeding_minutes": (snapshot.seeding_time_seconds / 60 if snapshot.seeding_time_seconds is not None else None),
        "state": snapshot.state.value,
        "freshness": snapshot.freshness.value,
        "ownership": snapshot.ownership.value,
    }
    if not policy.enabled:
        return PolicyEvaluation(PolicyDecision.BLOCKED, "policy_disabled", facts)
    if snapshot.freshness is not ListingFreshness.FRESH:
        return PolicyEvaluation(PolicyDecision.BLOCKED, "stale_or_unknown_observation", facts)
    if snapshot.ownership is not TorrentOwnership.MANAGED:
        return PolicyEvaluation(PolicyDecision.BLOCKED, "ownership_not_managed", facts)
    if snapshot.state is not TorrentState.SEEDING:
        return PolicyEvaluation(PolicyDecision.BLOCKED, "not_seeding", facts)

    scope = _scope_decision(policy, snapshot)
    if scope is not None:
        return PolicyEvaluation(*scope, facts=facts)

    checks: list[bool | None] = []
    if policy.min_ratio is not None:
        checks.append(snapshot.ratio >= policy.min_ratio if snapshot.ratio is not None else None)
        facts["ratio_passed"] = checks[-1]
    if policy.min_seeding_minutes is not None:
        minutes = snapshot.seeding_time_seconds / 60 if snapshot.seeding_time_seconds is not None else None
        checks.append(minutes >= policy.min_seeding_minutes if minutes is not None else None)
        facts["seeding_minutes_passed"] = checks[-1]
    if not checks:
        return PolicyEvaluation(PolicyDecision.BLOCKED, "no_configured_threshold", facts)
    if any(value is None for value in checks):
        return PolicyEvaluation(PolicyDecision.BLOCKED, "required_metric_unknown", facts)
    passed = all(checks) if policy.mode is SeedingStopPolicyMode.ALL else any(checks)
    return PolicyEvaluation(
        PolicyDecision.ELIGIBLE if passed else PolicyDecision.BLOCKED,
        "thresholds_met" if passed else "thresholds_not_met",
        facts,
    )


def _scope_decision(policy: SeedingStopPolicyConfig, snapshot: TorrentSnapshot) -> tuple[PolicyDecision, str] | None:
    category = snapshot.category.casefold() if snapshot.category is not None else None
    tags = {tag.casefold() for tag in snapshot.tags} if snapshot.tags is not None else None
    excluded_categories = {value.casefold() for value in policy.exclude_categories}
    excluded_tags = {value.casefold() for value in policy.exclude_tags}
    if excluded_categories and category is None or excluded_tags and tags is None:
        return PolicyDecision.BLOCKED, "scope_metadata_unknown"
    if category is not None and category in excluded_categories:
        return PolicyDecision.EXCLUDED, "excluded_category"
    if tags is not None and tags & excluded_tags:
        return PolicyDecision.EXCLUDED, "excluded_tag"
    included_categories = {value.casefold() for value in policy.include_categories}
    included_tags = {value.casefold() for value in policy.include_tags}
    if included_categories or included_tags:
        if included_categories and category is None or included_tags and tags is None:
            return PolicyDecision.BLOCKED, "scope_metadata_unknown"
        category_match = category in included_categories if included_categories else False
        tag_match = bool(tags & included_tags) if included_tags and tags is not None else False
        if not category_match and not tag_match:
            return PolicyDecision.BLOCKED, "outside_include_scope"
    return None
