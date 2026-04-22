"""
GRD Loader — parses Governance Rule Document JSON into GRDConfig objects.

Maps the GRD JSON structure (knowledge_triggers, proxy_exclusion_list,
reviewer_knowledge_roster, etc.) to the internal GRDConfig dataclass.
Validates required keys and threshold completeness before loading.
"""

import json
import math
from pathlib import Path
from typing import Any, Dict, List

from .config import GRDConfig, ThresholdSpec


class GRDValidationError(Exception):
    """Raised when GRD JSON fails validation."""

    def __init__(self, errors: List[str]):
        self.errors = errors
        super().__init__(f"GRD validation failed: {errors}")


class GRDLoader:
    """Loads and validates GRD JSON files into GRDConfig objects."""

    # Logical required keys mapped to actual GRD JSON keys.
    # 'goal' is derived from deployment_decision + reason_weights,
    # 'rules' from epistemic_territory_rules,
    # 'thresholds' from knowledge_triggers.
    REQUIRED_TOP_LEVEL_KEYS = {
        'goal', 'rules', 'thresholds',
        'proxy_exclusion_list', 'knowledge_triggers',
    }

    REQUIRED_THRESHOLD_FIELDS = {
        'threshold_id', 'name', 'trigger_condition',
        'target_fire_rate_min', 'target_fire_rate_max',
    }

    # Maps logical validation key → actual GRD JSON keys that satisfy it
    _LOGICAL_KEY_MAP: Dict[str, List[str]] = {
        'goal': ['deployment_decision', 'reason_weights'],
        'rules': ['epistemic_territory_rules'],
        'thresholds': ['knowledge_triggers'],
        'proxy_exclusion_list': ['proxy_exclusion_list'],
        'knowledge_triggers': ['knowledge_triggers'],
    }

    @staticmethod
    def load(path: str) -> GRDConfig:
        """Load GRD JSON, validate, return GRDConfig.

        Raises GRDValidationError on missing keys or incomplete thresholds.
        Raises FileNotFoundError if path does not exist.
        """
        raw = json.loads(Path(path).read_text(encoding='utf-8'))
        errors = GRDLoader.validate(raw)
        if errors:
            raise GRDValidationError(errors)
        return GRDLoader._build_config(raw)

    @staticmethod
    def validate(raw: dict) -> List[str]:
        """Return list of validation error strings. Empty list means valid."""
        errors: List[str] = []

        # Check logical required keys
        for logical_key in sorted(GRDLoader.REQUIRED_TOP_LEVEL_KEYS):
            actual_keys = GRDLoader._LOGICAL_KEY_MAP[logical_key]
            if not any(k in raw for k in actual_keys):
                errors.append(f"Missing required key: '{logical_key}'")

        # Validate threshold entries if knowledge_triggers present
        triggers = raw.get('knowledge_triggers', [])
        for i, trigger in enumerate(triggers):
            missing = GRDLoader.REQUIRED_THRESHOLD_FIELDS - set(trigger.keys())
            if missing:
                errors.append(
                    f"Threshold entry {i} missing fields: "
                    f"{sorted(missing)}"
                )

        return errors

    @staticmethod
    def to_json(config: GRDConfig) -> dict:
        """Serialize GRDConfig back to GRD JSON-compatible dict for round-trip."""
        result: Dict[str, Any] = {}

        result['system'] = config.name
        result['authored_by'] = config.frame_author
        result['authored_date'] = config.frame_date

        # knowledge_triggers from thresholds
        threshold_ids = getattr(config, '_threshold_ids', [])
        triggers = []
        for i, spec in enumerate(config.thresholds):
            tid = threshold_ids[i] if i < len(threshold_ids) else f'T{i + 1}'
            trigger: Dict[str, Any] = {
                'threshold_id': tid,
                'name': spec.name,
                'trigger_condition': spec.description,
                'target_fire_rate_min': spec.target_fire_rate[0],
                'target_fire_rate_max': spec.target_fire_rate[1],
                'required_reviewer_knowledge': spec.knowledge_owner,
            }
            triggers.append(trigger)
        result['knowledge_triggers'] = triggers

        # proxy_exclusion_list from blocked_features
        proxy_list = []
        for feature in config.blocked_features:
            proxy_list.append({
                'feature': feature,
                'excluded_from_model': True,
            })
        result['proxy_exclusion_list'] = proxy_list

        # reviewer_knowledge_roster from authority_routing
        result['reviewer_knowledge_roster'] = config.authority_routing

        # reason_weights
        result['reason_weights'] = config.reason_weights

        # deployment_decision
        result['deployment_decision'] = {'level': config.deployment_level}

        # data_vintage_config
        result['data_vintage_config'] = {
            'training_period_start': config.data_vintage_start,
            'vintage_window_days': config.staleness_months * 30,
        }

        # residue_domains
        result['residue_domains'] = {d: {'declared': True} for d in config.residue_domains}

        # stakeholder_cost_bearers
        cost_bearers_list = []
        for stakeholder, cost in config.cost_bearers.items():
            cost_bearers_list.append({
                'stakeholder': stakeholder,
                'cost': cost,
            })
        result['stakeholder_cost_bearers'] = cost_bearers_list

        # era_bias_detection_config
        result['era_bias_detection_config'] = config.era_bias_config

        # dataset_metadata
        result['dataset_metadata'] = config.dataset_metadata

        # epistemic_territory_rules — needed for 'rules' validation key
        # Store as empty list if not present (round-trip preserves structure)
        result['epistemic_territory_rules'] = []

        return result

    @staticmethod
    def _build_config(raw: dict) -> GRDConfig:
        """Build a GRDConfig from validated raw GRD JSON dict."""
        config = GRDConfig()

        # Frame origin
        config.name = raw.get('system', 'Unnamed GRD')
        config.frame_author = raw.get('authored_by', '')
        config.frame_date = raw.get('authored_date', '')

        # Thresholds from knowledge_triggers
        config.thresholds = []
        # Store threshold_id → index mapping for round-trip serialization
        config._threshold_ids: List[str] = []  # type: ignore[attr-defined]
        for trigger in raw.get('knowledge_triggers', []):
            spec = ThresholdSpec(
                name=trigger.get('name', ''),
                description=trigger.get('trigger_condition', ''),
                target_fire_rate=(
                    trigger.get('target_fire_rate_min', 0.0),
                    trigger.get('target_fire_rate_max', 1.0),
                ),
                knowledge_owner=trigger.get('required_reviewer_knowledge', ''),
            )
            config.thresholds.append(spec)
            config._threshold_ids.append(trigger.get('threshold_id', ''))  # type: ignore[attr-defined]

        # Blocked features and proxy candidates from proxy_exclusion_list
        proxy_list = raw.get('proxy_exclusion_list', [])
        features = [entry['feature'] for entry in proxy_list if 'feature' in entry]
        config.blocked_features = features
        config.proxy_candidates = list(features)

        # Authority routing from reviewer_knowledge_roster
        config.authority_routing = raw.get('reviewer_knowledge_roster', {})

        # Reason weights
        config.reason_weights = raw.get('reason_weights', {})

        # Deployment level
        deployment = raw.get('deployment_decision', {})
        config.deployment_level = deployment.get('level', 1)

        # Data vintage
        vintage = raw.get('data_vintage_config', {})
        config.data_vintage_start = vintage.get('training_period_start', '')
        window_days = vintage.get('vintage_window_days', 0)
        config.staleness_months = math.floor(window_days / 30) if window_days else 24

        # Residue domains — list of domain keys
        residue = raw.get('residue_domains', {})
        config.residue_domains = list(residue.keys()) if isinstance(residue, dict) else []

        # Cost bearers from stakeholder_cost_bearers
        cost_bearers_raw = raw.get('stakeholder_cost_bearers', [])
        config.cost_bearers = {
            entry['stakeholder']: entry.get('cost', '')
            for entry in cost_bearers_raw
            if 'stakeholder' in entry
        }

        # Era bias config
        config.era_bias_config = raw.get('era_bias_detection_config', {})

        # Dataset metadata
        config.dataset_metadata = raw.get('dataset_metadata', {})

        return config
