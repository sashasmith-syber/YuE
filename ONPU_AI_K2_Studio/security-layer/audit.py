"""
ONPU Security Audit Layer
Comprehensive logging, anomaly detection, and IP-based security controls
"""

import hashlib
import time
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Set
import asyncio
from collections import defaultdict
import threading

try:
    from clickhouse_driver import Client as ClickHouseClient
    CLICKHOUSE_AVAILABLE = True
except ImportError:
    CLICKHOUSE_AVAILABLE = False
    ClickHouseClient = None

# Import persistence layer
try:
    from .persistence import SecurityPersistence, get_persistence
    PERSISTENCE_AVAILABLE = True
except ImportError:
    PERSISTENCE_AVAILABLE = False
    SecurityPersistence = None
    get_persistence = None


class SecurityAuditor:
    """
    Security audit system for ONPU K2 Studio.
    
    Logs every API call to ClickHouse with:
    - Timestamp and request ID
    - User fingerprint and endpoint
    - Parameters hash (for privacy)
    - Response status and timing
    - Anomaly scoring
    - IP-based rate limiting and blocking
    """
    
    def __init__(self, clickhouse_url: str):
        if not CLICKHOUSE_AVAILABLE:
            raise RuntimeError("ClickHouse driver not available")
        self.clickhouse = ClickHouseClient.from_url(clickhouse_url)
        self.alert_thresholds = {
            'failed_auth_per_minute': 3,
            'unusual_bpm_pattern': True,
            'unusual_key_pattern': True,
            'bpm_max': 200,  # Align with SSmith25 spec
            'bpm_min': 60,
            'anomaly_block_threshold': 0.9,  # Block requests with score > 0.9
        }
        
        # IP-based security tracking (SQLite is single source of truth for blocks)
        self._ip_request_count: Dict[str, list] = defaultdict(list)
        self._blocked_ips: Set[str] = set()  # In-memory cache only
        self._ip_lock = threading.Lock()
        
        # Circuit breaker tracking
        self._circuit_breakers: Dict[str, Dict[str, Any]] = {}
        self._circuit_lock = threading.Lock()
    
    def hash_params(self, params: Dict[str, Any]) -> str:
        """Create SHA-256 hash of parameters for audit trail."""
        param_str = str(sorted(params.items()))
        return hashlib.sha256(param_str.encode()).hexdigest()
    
    def is_ip_blocked(self, client_ip: str) -> bool:
        """
        Check if IP address is currently blocked.
        Uses SQLite persistence if available, falls back to in-memory.
        """
        # First check SQLite persistence
        if PERSISTENCE_AVAILABLE and get_persistence:
            try:
                persistence = get_persistence()
                if persistence.is_ip_blocked(client_ip):
                    return True
            except Exception as e:
                # Log error but continue with in-memory check
                print(f"[AUDIT WARNING] SQLite check failed: {e}")
        
        # Fallback to in-memory check
        with self._ip_lock:
            # Clean up expired blocks
            current_time = datetime.utcnow()
            expired_ips = [
                ip for ip, block_time in self._blocked_ips.copy().items()
                if isinstance(block_time, datetime) and 
                (current_time - block_time) > timedelta(minutes=30)
            ]
            for ip in expired_ips:
                self._blocked_ips.discard(ip)
            
            return client_ip in self._blocked_ips
    
    def block_ip(self, client_ip: str, duration_minutes: int = 30) -> None:
        """Block an IP address for specified duration."""
        with self._ip_lock:
            self._blocked_ips.add(client_ip)
            # Store block time for automatic expiration
            self._circuit_breakers[client_ip] = {
                'blocked_at': datetime.utcnow(),
                'duration_minutes': duration_minutes,
                'reason': 'security_violation'
            }
    
    def record_auth_failure(self, client_ip: str, username: str = None) -> int:
        """
        Record a failed authentication attempt with SQLite persistence.
        Single source of truth - no dual tracking.
        
        Tracks 10 failures per hour before blocking.
        
        Args:
            client_ip: IP address
            username: Optional username hint (for credential stuffing detection)
            
        Returns:
            Count of failures in last hour for this IP
        """
        if not PERSISTENCE_AVAILABLE or not get_persistence:
            raise RuntimeError("SQLite persistence required for auth tracking")
        
        persistence = get_persistence()
        count = persistence.record_auth_failure(client_ip, username)
        
        # Block if threshold exceeded (10 per hour)
        if count >= 10:
            persistence.persist_block(
                client_ip, 
                duration_seconds=3600,  # 1 hour
                reason="brute_force"
            )
            # Log security event
            persistence.log_security_event(
                ip=client_ip,
                event_type="BRUTE_FORCE",
                details=f"Blocked after {count} failed auth attempts",
                threat_score=min(count / 10.0, 1.0)
            )
        
        return count
    
    def record_failed_auth(self, client_ip: str) -> bool:
        """
        DEPRECATED: Use record_auth_failure() instead.
        Kept for backward compatibility - delegates to SQLite method.
        
        Returns True if IP should be blocked.
        """
        count = self.record_auth_failure(client_ip)
        return count >= 10
    
    def calculate_threat_score(self, client_ip: str, bpm: float = None) -> float:
        """
        Calculate threat score for IP based on behavior patterns.
        
        Score components:
        - +0.5 for BPM outside 60-200 (injection attempt signature)
        - +0.3 for >5 auth failures in last hour
        - +0.2 for >100 requests per minute
        
        Args:
            client_ip: IP address
            bpm: Optional BPM value to check
            
        Returns:
            Threat score from 0.0 (safe) to 1.0 (critical)
        """
        score = 0.0
        
        # Check BPM for injection signature
        if bpm is not None:
            bpm_min = self.alert_thresholds.get('bpm_min', 60)
            bpm_max = self.alert_thresholds.get('bpm_max', 200)
            
            if bpm < bpm_min or bpm > bpm_max:
                # BPM outside bounds - possible injection attempt
                score += 0.5
                # Log security event
                if PERSISTENCE_AVAILABLE and get_persistence:
                    try:
                        persistence = get_persistence()
                        persistence.log_security_event(
                            ip=client_ip,
                            event_type="BPM_INJECTION",
                            details=f"BPM={bpm} outside bounds [{bpm_min}-{bpm_max}]",
                            bpm=bpm,
                            threat_score=0.5
                        )
                    except Exception as e:
                        print(f"[AUDIT WARNING] Failed to log BPM event: {e}")
        
        # Check auth failures
        auth_failures = 0
        if PERSISTENCE_AVAILABLE and get_persistence:
            try:
                persistence = get_persistence()
                auth_failures = persistence.get_auth_failure_count(client_ip, hours=1)
            except Exception as e:
                print(f"[AUDIT WARNING] Failed to get auth count: {e}")
        
        if auth_failures > 5:
            score += 0.3
        
        # Check request rate
        with self._ip_lock:
            current_time = datetime.utcnow()
            recent_requests = [
                t for t in self._ip_request_count.get(client_ip, [])
                if (current_time - t) < timedelta(minutes=1)
            ]
            if len(recent_requests) > 100:
                score += 0.2
        
        return min(score, 1.0)
    
    def check_rate_limit(self, client_ip: str) -> tuple[bool, int]:
        """
        Check if IP is approaching rate limit.
        Returns (is_limited, current_count).
        """
        with self._ip_lock:
            current_time = datetime.utcnow()
            # Clean old entries (> 1 minute)
            self._ip_request_count[client_ip] = [
                t for t in self._ip_request_count[client_ip]
                if (current_time - t) < timedelta(minutes=1)
            ]
            # Add current request
            self._ip_request_count[client_ip].append(current_time)
            
            count = len(self._ip_request_count[client_ip])
            # Rate limit: 1000 requests per minute
            is_limited = count > 1000
            return is_limited, count
    
    def check_circuit_breaker(self, endpoint: str, client_ip: str) -> bool:
        """
        Check if circuit breaker is open for this endpoint/IP.
        Returns True if request should be blocked.
        """
        with self._circuit_lock:
            key = f"{endpoint}:{client_ip}"
            if key not in self._circuit_breakers:
                return False
            
            breaker = self._circuit_breakers[key]
            if breaker.get('open', False):
                # Check if it's time to half-open
                opened_at = breaker.get('opened_at')
                if opened_at:
                    elapsed = (datetime.utcnow() - opened_at).total_seconds()
                    if elapsed > breaker.get('timeout_seconds', 60):
                        # Transition to half-open
                        breaker['open'] = False
                        breaker['half_open'] = True
                        return False
                return True
            return False
    
    def record_circuit_breaker_failure(self, endpoint: str, client_ip: str) -> None:
        """Record a failure for circuit breaker tracking."""
        with self._circuit_lock:
            key = f"{endpoint}:{client_ip}"
            if key not in self._circuit_breakers:
                self._circuit_breakers[key] = {
                    'failures': 0,
                    'open': False,
                    'half_open': False
                }
            
            breaker = self._circuit_breakers[key]
            breaker['failures'] += 1
            
            # Open circuit after 5 failures in 1 minute
            if breaker['failures'] >= 5:
                breaker['open'] = True
                breaker['opened_at'] = datetime.utcnow()
                breaker['timeout_seconds'] = 60
    
    async def log_api_call(
        self,
        request_id: str,
        endpoint: str,
        method: str,
        user_fingerprint: Optional[str],
        user_rank: Optional[str],
        params: Dict[str, Any],
        client_ip: str,
        user_agent: str,
        response_status: int,
        response_time_ms: float,
        auth_success: bool
    ) -> None:
        """Log API call to ClickHouse."""
        
        # Calculate anomaly score
        anomaly_score = self._calculate_anomaly_score(
            endpoint, params, auth_success, response_status
        )
        
        # Determine if flagged
        flagged = anomaly_score > 0.7 or (
            not auth_success and endpoint == '/auth/handshake'
        )
        
        # Insert to ClickHouse
        query = """
        INSERT INTO security_audit (
            timestamp, request_id, endpoint, method,
            user_fingerprint, user_rank, auth_success, auth_method,
            params_hash, client_ip, user_agent,
            response_status, response_time_ms,
            anomaly_score, flagged
        ) VALUES
        """
        
        data = [(
            datetime.utcnow(),
            request_id,
            endpoint,
            method,
            user_fingerprint,
            user_rank,
            auth_success,
            'curve25519',
            self.hash_params(params),
            client_ip,
            user_agent,
            response_status,
            response_time_ms,
            anomaly_score,
            flagged
        )]
        
        try:
            self.clickhouse.execute(query, data)
        except Exception as e:
            # Log to fallback (stdout)
            print(f"[AUDIT ERROR] Failed to log to ClickHouse: {e}")
    
    def _calculate_anomaly_score(
        self,
        endpoint: str,
        params: Dict[str, Any],
        auth_success: bool,
        response_status: int
    ) -> float:
        """Calculate anomaly score for request."""
        score = 0.0
        
        # Failed authentication
        if not auth_success:
            score += 0.3
        
        # Error responses
        if response_status >= 500:
            score += 0.2
        elif response_status == 429:
            score += 0.15
        
        # Unusual BPM patterns (possible prompt injection)
        # Use configured thresholds aligned with SSmith25 spec
        bpm = params.get('bpm')
        if bpm is not None:
            bpm_min = self.alert_thresholds.get('bpm_min', 60)
            bpm_max = self.alert_thresholds.get('bpm_max', 200)
            
            if bpm < bpm_min or bpm > bpm_max:
                # Extreme deviation - high anomaly score
                score += 0.4
            elif bpm < 100 or bpm > 150:
                # Moderate deviation from typical music BPM
                score += 0.15
        
        # Unusual key patterns
        key = params.get('key')
        allowed_keys = ['C# minor', 'D minor', 'F# minor', 'C major', 'G major']
        if key and key not in allowed_keys:
            score += 0.1
        
        # Suspicious parameter patterns (injection attempts)
        for param_name, param_value in params.items():
            param_str = str(param_value).lower()
            suspicious_patterns = ['drop', 'delete', 'insert', 'update', 'select', '--', ';--', '/*']
            if any(pattern in param_str for pattern in suspicious_patterns):
                score += 0.35
                break
        
        return min(score, 1.0)
    
    def should_block_request(
        self,
        client_ip: str,
        endpoint: str,
        params: Dict[str, Any],
        auth_success: bool
    ) -> tuple[bool, str]:
        """
        Determine if request should be blocked based on security rules.
        Returns (should_block, reason).
        """
        # Check if IP is already blocked
        if self.is_ip_blocked(client_ip):
            return True, "IP_BLOCKED"
        
        # Check circuit breaker
        if self.check_circuit_breaker(endpoint, client_ip):
            return True, "CIRCUIT_BREAKER_OPEN"
        
        # Calculate anomaly score
        anomaly_score = self._calculate_anomaly_score(
            endpoint, params, auth_success, 200
        )
        
        # Block if anomaly score exceeds threshold
        if anomaly_score > self.alert_thresholds.get('anomaly_block_threshold', 0.9):
            self.block_ip(client_ip, duration_minutes=30)
            return True, f"HIGH_ANOMALY_SCORE:{anomaly_score:.2f}"
        
        # Check BPM bounds strictly
        bpm = params.get('bpm')
        if bpm is not None:
            bpm_min = self.alert_thresholds.get('bpm_min', 60)
            bpm_max = self.alert_thresholds.get('bpm_max', 200)
            if bpm < bpm_min or bpm > bpm_max:
                return True, f"BPM_OUT_OF_BOUNDS:{bpm}"
        
        return False, ""
    
    async def check_alerts(self) -> list:
        """Check for security alerts."""
        alerts = []
        
        # Check failed auth rate
        query = """
        SELECT count() as count
        FROM security_audit
        WHERE timestamp > now() - INTERVAL 1 MINUTE
        AND auth_success = false
        """
        
        result = self.clickhouse.execute(query)
        failed_auth_count = result[0][0] if result else 0
        
        if failed_auth_count > self.alert_thresholds['failed_auth_per_minute']:
            alerts.append({
                'type': 'failed_auth_spike',
                'severity': 'high',
                'message': f'{failed_auth_count} failed auth attempts in last minute',
                'timestamp': datetime.utcnow().isoformat()
            })
        
        return alerts


class AuditMiddleware:
    """FastAPI middleware for request auditing and security enforcement."""
    
    def __init__(self, auditor: SecurityAuditor, enforce_security: bool = True):
        self.auditor = auditor
        self.enforce_security = enforce_security
    
    async def __call__(self, request, call_next):
        start_time = time.time()
        client_ip = request.client.host if request.client else 'unknown'
        endpoint = request.url.path
        
        # Security checks before processing
        if self.enforce_security:
            # Check if IP is blocked
            if self.auditor.is_ip_blocked(client_ip):
                from fastapi import HTTPException, status
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied: IP address blocked due to security violations"
                )
            
            # Check rate limiting
            is_limited, current_count = self.auditor.check_rate_limit(client_ip)
            if is_limited:
                from fastapi import HTTPException, status
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Rate limit exceeded: {current_count} requests per minute"
                )
            
            # Check circuit breaker
            if self.auditor.check_circuit_breaker(endpoint, client_ip):
                from fastapi import HTTPException, status
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Service temporarily unavailable due to repeated failures"
                )
        
        # Process request
        response = await call_next(request)
        
        # Calculate timing
        response_time_ms = (time.time() - start_time) * 1000
        
        # Extract request info
        request_id = getattr(request.state, 'request_id', 'unknown')
        user_fingerprint = getattr(request.state, 'user_fingerprint', None)
        user_rank = getattr(request.state, 'user_rank', None)
        
        # Determine auth success
        auth_success = response.status_code != 401
        
        # Record failed auth for security tracking
        if not auth_success and response.status_code == 401:
            should_block = self.auditor.record_failed_auth(client_ip)
            if should_block:
                # Log the block event
                print(f"[SECURITY] IP {client_ip} blocked due to excessive failed auth attempts")
        
        # Check for circuit breaker failures (5xx errors)
        if response.status_code >= 500:
            self.auditor.record_circuit_breaker_failure(endpoint, client_ip)
        
        # Log asynchronously (don't block response)
        asyncio.create_task(self.auditor.log_api_call(
            request_id=request_id,
            endpoint=endpoint,
            method=request.method,
            user_fingerprint=user_fingerprint,
            user_rank=user_rank,
            params=dict(request.query_params),
            client_ip=client_ip,
            user_agent=request.headers.get('user-agent', 'unknown'),
            response_status=response.status_code,
            response_time_ms=response_time_ms,
            auth_success=auth_success
        ))
        
        return response
