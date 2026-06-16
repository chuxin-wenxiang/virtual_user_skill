"""
Virtual User Skill - Working Modes

Five modes covering the full product lifecycle:
  - explore: 1v1 interview (Idea stage)
  - debate: Pro vs Con structured debate
  - pmf: PMF validation with Sean Ellis scale
  - prd: PRD calibration with 4-dimension scoring
  - metrics: Pre-launch metrics voting (Juster scale)
"""

from .explore import ExploreMode, DebateMode
from .pmf import PMFValidationMode
from .prd import PRDCalibrationMode
from .metrics import MetricsVotingMode

__all__ = [
    'ExploreMode',
    'DebateMode', 
    'PMFValidationMode',
    'PRDCalibrationMode',
    'MetricsVotingMode',
]
