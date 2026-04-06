"""
Kaizen Guardrail - Quality Control System
ONPU K2 Studio - Sonic Parameter Validation
"""

from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from enum import Enum
import logging

from config.settings import get_settings

logger = logging.getLogger(__name__)


class ValidationStatus(str, Enum):
    """Validation status enum."""
    LOCKED = "LOCKED"
    REVERT = "REVERT"
    DRIFT = "DRIFT"


@dataclass
class ValidationResult:
    """Validation result container."""
    status: ValidationStatus
    message: str
    violations: List[str]
    corrected_params: Optional[Dict[str, Any]] = None


class KaizenGuardrail:
    """
    Kaizen v1.9 Guardrail - Quality validation system with security enforcement.
    
    Validates sonic parameters against SSmith25 spec:
    - BPM: 122 ± 3 (security bounds: 60-200)
    - Key: C# minor, D minor, F# minor
    - Sub frequency: 38.9 Hz ± 3.1
    - LUFS: -8.2 ± 2
    - DR: 7
    
    Security Features:
    - Strict mode: Blocks invalid requests
    - BPM bounds enforcement: 60-200 range
    - Preflight rejection for critical violations
    """
    
    # Security bounds for BPM (outside SSmith25 spec but within reasonable limits)
    SECURITY_BPM_MIN = 60
    SECURITY_BPM_MAX = 200
    
    def __init__(self, strict_mode: bool = False):
        self.settings = get_settings()
        self.violations: List[str] = []
        self.strict_mode = strict_mode
    
    def validate_sonic_parameters(self, params: Dict[str, Any]) -> ValidationResult:
        """
        Validate sonic parameters against spec.
        
        Args:
            params: Dictionary containing bpm, key, sub_freq, lufs, dr
            
        Returns:
            ValidationResult with status and corrections
        """
        self.violations = []
        corrected = dict(params)
        
        # BPM validation
        bpm = params.get("bpm")
        if bpm is not None:
            bpm_result = self._validate_bpm(bpm)
            if bpm_result:
                self.violations.append(bpm_result)
                corrected["bpm"] = self._correct_bpm(bpm)
        
        # Key validation
        key = params.get("key")
        if key is not None:
            key_result = self._validate_key(key)
            if key_result:
                self.violations.append(key_result)
                corrected["key"] = self._correct_key(key)
        
        # Sub frequency validation
        sub_freq = params.get("sub_freq") or params.get("sub_frequency")
        if sub_freq is not None:
            freq_result = self._validate_sub_freq(sub_freq)
            if freq_result:
                self.violations.append(freq_result)
                corrected["sub_freq"] = self._correct_sub_freq(sub_freq)
        
        # LUFS validation
        lufs = params.get("lufs")
        if lufs is not None:
            lufs_result = self._validate_lufs(lufs)
            if lufs_result:
                self.violations.append(lufs_result)
                corrected["lufs"] = self._correct_lufs(lufs)
        
        # Dynamic range validation
        dr = params.get("dr") or params.get("dynamic_range")
        if dr is not None:
            dr_result = self._validate_dr(dr)
            if dr_result:
                self.violations.append(dr_result)
                corrected["dr"] = self._correct_dr(dr)
        
        # Determine status
        if not self.violations:
            status = ValidationStatus.LOCKED
            message = "All parameters within spec"
        elif self.strict_mode:
            status = ValidationStatus.REVERT
            message = f"Strict mode: {len(self.violations)} violations - blocking"
        else:
            status = ValidationStatus.DRIFT
            message = f"{len(self.violations)} parameters adjusted to spec"
        
        return ValidationResult(
            status=status,
            message=message,
            violations=self.violations,
            corrected_params=corrected if status == ValidationStatus.DRIFT else None
        )
    
    def _validate_bpm(self, bpm: float) -> Optional[str]:
        """Validate BPM against 122 ± 3."""
        target = self.settings.SONIC_TARGET_BPM
        tolerance = self.settings.SONIC_BPM_TOLERANCE
        diff = abs(bpm - target)
        if diff > tolerance:
            return f"BPM {bpm} outside tolerance {target}±{tolerance} (diff: {diff:.1f})"
        return None
    
    def _correct_bpm(self, bpm: float) -> float:
        """Clamp BPM to valid range."""
        target = self.settings.SONIC_TARGET_BPM
        tolerance = self.settings.SONIC_BPM_TOLERANCE
        return max(target - tolerance, min(bpm, target + tolerance))
    
    def _validate_key(self, key: str) -> Optional[str]:
        """Validate key against allowed list."""
        allowed = self.settings.SONIC_ALLOWED_KEYS
        if key not in allowed:
            return f"Key '{key}' not in allowed list: {allowed}"
        return None
    
    def _correct_key(self, key: str) -> str:
        """Return default key."""
        return self.settings.SONIC_ALLOWED_KEYS[0]
    
    def _validate_sub_freq(self, freq: float) -> Optional[str]:
        """Validate sub frequency against 38.9 ± 3.1."""
        target = self.settings.SONIC_TARGET_SUB_FREQ
        tolerance = self.settings.SONIC_SUB_FREQ_TOLERANCE
        diff = abs(freq - target)
        if diff > tolerance:
            return f"Sub frequency {freq}Hz outside tolerance {target}±{tolerance}Hz"
        return None
    
    def _correct_sub_freq(self, freq: float) -> float:
        """Clamp sub frequency."""
        target = self.settings.SONIC_TARGET_SUB_FREQ
        tolerance = self.settings.SONIC_SUB_FREQ_TOLERANCE
        return max(target - tolerance, min(freq, target + tolerance))
    
    def _validate_lufs(self, lufs: float) -> Optional[str]:
        """Validate LUFS against -8.2 ± 2."""
        target = self.settings.SONIC_TARGET_LUFS
        tolerance = self.settings.SONIC_LUFS_TOLERANCE
        diff = abs(lufs - target)
        if diff > tolerance:
            return f"LUFS {lufs} outside tolerance {target}±{tolerance}"
        return None
    
    def _correct_lufs(self, lufs: float) -> float:
        """Clamp LUFS."""
        target = self.settings.SONIC_TARGET_LUFS
        tolerance = self.settings.SONIC_LUFS_TOLERANCE
        return max(target - tolerance, min(lufs, target + tolerance))
    
    def _validate_dr(self, dr: float) -> Optional[str]:
        """Validate dynamic range."""
        target = self.settings.SONIC_TARGET_DR
        if dr < target:
            return f"Dynamic range {dr} below minimum {target}"
        return None
    
    def _correct_dr(self, dr: float) -> float:
        """Ensure minimum DR."""
        return max(dr, self.settings.SONIC_TARGET_DR)
    
    def validate_bpm_security(self, bpm: float) -> tuple[bool, str]:
        """
        Security-focused BPM validation.
        Returns (is_valid, error_message).
        """
        if bpm < self.SECURITY_BPM_MIN or bpm > self.SECURITY_BPM_MAX:
            return False, f"BPM {bpm} outside security bounds [{self.SECURITY_BPM_MIN}-{self.SECURITY_BPM_MAX}]"
        return True, ""
    
    def should_block_request(self, params: Dict[str, Any]) -> bool:
        """
        Determine if request should be blocked based on validation.
        
        Args:
            params: Request parameters
            
        Returns:
            True if request should be blocked
        """
        validation = self.validate_sonic_parameters(params)
        
        # In strict mode, block on any violation
        if self.strict_mode and validation.violations:
            return False
        
        # Only block on critical violations
        critical_params = ["bpm", "key"]
        critical_violations = [
            v for v in validation.violations
            if any(param in v.lower() for param in critical_params)
        ]
        
        return len(critical_violations) == 0
    
    def security_preflight_check(self, params: Dict[str, Any]) -> tuple[bool, List[str]]:
        """
        Security-focused preflight check.
        Returns (is_allowed, violation_list).
        """
        violations = []
        
        # BPM security check
        bpm = params.get("bpm")
        if bpm is not None:
            is_valid, error = self.validate_bpm_security(bpm)
            if not is_valid:
                violations.append(error)
        
        # Key validation
        key = params.get("key")
        if key is not None:
            allowed = self.settings.SONIC_ALLOWED_KEYS
            if key not in allowed:
                violations.append(f"Key '{key}' not in allowed list")
        
        # Check for suspicious patterns in any parameter
        for param_name, param_value in params.items():
            param_str = str(param_value).lower()
            suspicious = ['drop', 'delete', 'insert', 'update', 'select', '--', ';--', '/*', 'script']
            if any(pattern in param_str for pattern in suspicious):
                violations.append(f"Suspicious pattern in parameter '{param_name}'")
                break
        
        is_allowed = len(violations) == 0
        return is_allowed, violations
    
    def validate_bpm_strict(self, bpm: float, client_ip: str = None) -> dict:
        """
        Strict mode BPM validation that blocks instead of clamps.
        
        Args:
            bpm: BPM value to validate
            client_ip: Optional client IP for security logging
            
        Returns:
            Dict with 'action' ('allow', 'block', or 'clamp') and 'reason'
        """
        # Critical violation: Outside absolute bounds (60-200)
        if bpm < self.SECURITY_BPM_MIN or bpm > self.SECURITY_BPM_MAX:
            # Log security event if IP provided
            if client_ip:
                try:
                    from security.persistence import get_persistence
                    persistence = get_persistence()
                    persistence.log_security_event(
                        ip=client_ip,
                        event_type="BPM_INJECTION",
                        details=f"BPM={bpm} outside bounds [{self.SECURITY_BPM_MIN}-{self.SECURITY_BPM_MAX}]",
                        bpm=bpm,
                        threat_score=0.5
                    )
                except Exception as e:
                    logger.warning(f"Failed to log BPM security event: {e}")
            
            return {
                'valid': False,
                'action': 'block',
                'reason': f'BPM {bpm} outside absolute bounds [{self.SECURITY_BPM_MIN}-{self.SECURITY_BPM_MAX}]',
                'value': None
            }
        
        # Nominal violation: Outside 122±3 (strict mode blocks, non-strict clamps)
        target = self.settings.SONIC_TARGET_BPM
        tolerance = self.settings.SONIC_BPM_TOLERANCE
        
        if abs(bpm - target) > tolerance:
            if self.strict_mode:
                return {
                    'valid': False,
                    'action': 'block',
                    'reason': f'BPM {bpm} outside tolerance {target}±{tolerance}',
                    'value': None
                }
            else:
                # Clamp to bounds
                clamped = max(target - tolerance, min(bpm, target + tolerance))
                return {
                    'valid': True,
                    'action': 'clamp',
                    'reason': f'BPM clamped from {bpm} to {clamped}',
                    'value': clamped
                }
        
        return {'valid': True, 'action': 'allow', 'reason': None, 'value': bpm}
    
    def calculate_anomaly_score(self, params: Dict[str, Any]) -> float:
        """
        Calculate anomaly score for parameter set.
        
        Score: 0.0 = normal, 1.0 = critical anomaly
        
        Args:
            params: Parameter dictionary
            
        Returns:
            Anomaly score from 0.0 to 1.0
        """
        score = 0.0
        bpm = params.get('bpm', 122)
        
        # BPM anomaly
        if bpm > 200 or bpm < 60:
            score += 0.5
        if abs(bpm - 122) > 50:
            score += 0.3
        
        # Pattern anomaly (multiple rapid changes)
        if self._detect_rapid_changes(params):
            score += 0.2
        
        return min(score, 1.0)
    
    def _detect_rapid_changes(self, params: Dict[str, Any]) -> bool:
        """
        Detect rapid parameter changes (parameter jitter).
        
        Args:
            params: Current parameters
            
        Returns:
            True if rapid changes detected
        """
        # This would typically compare against previous requests
        # For now, check for extreme values that suggest manipulation
        bpm = params.get('bpm')
        if bpm and (bpm > 250 or bpm < 20):
            return True
        return False


# Global guardrail instances
_kaizen_guardrail: Optional[KaizenGuardrail] = None
_strict_kaizen_guardrail: Optional[KaizenGuardrail] = None


def get_kaizen_guardrail(strict_mode: bool = False) -> KaizenGuardrail:
    """
    Get or create global KaizenGuardrail instance.
    
    Args:
        strict_mode: If True, returns guardrail that blocks on any violation
        
    Returns:
        KaizenGuardrail instance
    """
    global _kaizen_guardrail, _strict_kaizen_guardrail
    
    if strict_mode:
        if _strict_kaizen_guardrail is None:
            _strict_kaizen_guardrail = KaizenGuardrail(strict_mode=True)
        return _strict_kaizen_guardrail
    
    if _kaizen_guardrail is None:
        _kaizen_guardrail = KaizenGuardrail(strict_mode=False)
    return _kaizen_guardrail
