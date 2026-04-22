"""
GRT Engine — Goals, Rules, Thresholds Governance Framework
Computational implementation for reproducible governance analysis.

Usage:
    from grt_engine import GRTEngine
    engine = GRTEngine(config)
    engine.load_dataset('path/to/data.csv')
    engine.run_proxy_detection()
    engine.run_threshold_calibration()
    engine.compute_hci()
    engine.generate_report()
"""

from grt_engine.engine import GRTEngine, PipelineError
from grt_engine.hci import HCICalculator
from grt_engine.proxy_detector import ProxyDetector
from grt_engine.threshold_calibrator import ThresholdCalibrator
from grt_engine.grd_loader import GRDLoader, GRDValidationError
from grt_engine.schema_normalizer import SchemaNormalizer, SchemaError
from grt_engine.metric_scorer import MetricScorer, MetricScore, MetricScorecard, ClaimVerdict
from grt_engine.report_generator import ReportGenerator
from grt_engine.dataset_generator import DatasetGenerator

__version__ = '0.1.0'
__all__ = [
    'GRTEngine', 'PipelineError',
    'HCICalculator', 'ProxyDetector', 'ThresholdCalibrator',
    'GRDLoader', 'GRDValidationError',
    'SchemaNormalizer', 'SchemaError',
    'MetricScorer', 'MetricScore', 'MetricScorecard', 'ClaimVerdict',
    'ReportGenerator',
    'DatasetGenerator',
]
