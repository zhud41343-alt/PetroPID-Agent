"""PetroPID-Agent Core Industrial Control Algorithms.

Modules:
    simulator: High-fidelity FOPDT/SOPDT + Choudhury valve stiction chemical process simulator.
    diagnosis: Control loop performance assessment (Harris index, OI, stiction detection).
    identification: Closed-loop / step-response FOPDT system identification & independent validation.
    tuning: SIMC / IMC + constrained multi-objective adaptive PID auto-tuning.
    safety_verifier: Deterministic frequency-domain & multi-operating-point safety verifier.
"""

from .simulator import (
    PlantParams,
    PIDParams,
    ValveParams,
    LoopConfig,
    simulate_loop,
    get_standard_chemical_loops,
)
from .diagnosis import diagnose_loop, DiagnosisResult
from .identification import identify_fopdt, IdentificationResult
from .tuning import tune_pid, TuningResult
from .safety_verifier import verify_pid_safety, SafetyVerificationResult

__all__ = [
    "PlantParams",
    "PIDParams",
    "ValveParams",
    "LoopConfig",
    "simulate_loop",
    "get_standard_chemical_loops",
    "diagnose_loop",
    "DiagnosisResult",
    "identify_fopdt",
    "IdentificationResult",
    "tune_pid",
    "TuningResult",
    "verify_pid_safety",
    "SafetyVerificationResult",
]
