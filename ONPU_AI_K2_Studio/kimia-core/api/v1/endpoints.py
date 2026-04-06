"""
ONPU K2 Studio - API v1 Endpoints
Main API routes for dashboard functionality with security integration
"""

import time
from typing import Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status, Request, BackgroundTasks
from fastapi.responses import StreamingResponse
import prometheus_client

from auth.curve25519 import require_auth, TokenPayload, get_security_layer, ONPUSecurityLayer
from models.schemas import (
    HandshakeRequest, HandshakeResponse,
    AudioAnalysisRequest, AudioAnalysisResponse,
    ChatRequest, ChatResponse,
    GenerationRequest, JobStatus
)
from config.settings import get_settings
from kimia_engine.guardrail import get_kaizen_guardrail

router = APIRouter()

# Circuit breaker for auth endpoint (fail-fast under load)
class CircuitBreaker:
    def __init__(self, threshold=5, timeout=300):
        self.failures = 0
        self.threshold = threshold
        self.timeout = timeout
        self.last_failure = None
        self.state = 'CLOSED'  # CLOSED, OPEN, HALF_OPEN
    
    def call(self, func, *args, **kwargs):
        from datetime import datetime, timedelta
        if self.state == 'OPEN':
            if datetime.now() - self.last_failure > timedelta(seconds=self.timeout):
                self.state = 'HALF_OPEN'
            else:
                raise Exception("Circuit breaker OPEN")
        
        try:
            result = func(*args, **kwargs)
            if self.state == 'HALF_OPEN':
                self.state = 'CLOSED'
                self.failures = 0
            return result
        except Exception as e:
            self.failures += 1
            self.last_failure = datetime.now()
            if self.failures >= self.threshold:
                self.state = 'OPEN'
            raise e

# Global circuit breaker for auth endpoint
_auth_circuit_breaker = CircuitBreaker(threshold=5, timeout=300)


# Prometheus metrics
REQUEST_COUNT = prometheus_client.Counter(
    'onpu_requests_total',
    'Total requests',
    ['method', 'endpoint', 'status']
)
REQUEST_LATENCY = prometheus_client.Histogram(
    'onpu_request_latency_seconds',
    'Request latency',
    ['method', 'endpoint']
)


async def security_dependency(request: Request):
    """
    Security dependency for all endpoints.
    Validates rate limits and BPM parameters.
    """
    from security.audit import get_persistence
    
    client_ip = request.client.host
    settings = get_settings()
    
    # Check IP block
    persistence = get_persistence()
    if persistence.is_ip_blocked(client_ip):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="IP blocked due to security violations"
        )
    
    # Rate limiting (1000 requests per minute)
    request_count = persistence._ip_request_count.get(client_ip, [])
    current_time = datetime.utcnow()
    recent_requests = [
        t for t in request_count
        if (current_time - t) < timedelta(minutes=1)
    ]
    if len(recent_requests) > 1000:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded: 1000 requests per minute"
        )
    
    # BPM validation for POST requests
    if request.method == "POST":
        try:
            body = await request.json()
            bpm = body.get("bpm")
            if bpm is not None:
                guardrail = get_kaizen_guardrail(strict_mode=True)
                result = guardrail.validate_bpm_strict(bpm, client_ip=client_ip)
                if result['action'] == 'block':
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"REJECTED: {result['reason']}"
                    )
        except Exception as e:
            if isinstance(e, HTTPException):
                raise
            # Ignore JSON parse errors for non-JSON endpoints
    
    return True


@router.post("/auth/handshake", response_model=HandshakeResponse, dependencies=[Depends(security_dependency)])
async def auth_handshake(request: HandshakeRequest):
    """
    Initiate Curve25519 handshake for session authentication.
    
    Returns session token upon successful key exchange.
    Uses circuit breaker for fail-fast under load.
    """
    security = get_security_layer()
    settings = get_settings()
    
    def perform_handshake():
        # Decode client public key
        client_public_bytes = bytes.fromhex(request.client_public_key)
        
        # Perform handshake
        derived_key = security.handshake(client_public_bytes)
        
        # Create session token
        token = security.create_session_token(
            kaizen_sha=request.fingerprint,
            rank=request.rank,
            fingerprint=request.fingerprint,
            ttl=3600
        )
        
        return HandshakeResponse(
            server_public_key=security.get_public_key_hex(),
            session_token=token,
            expires_at=int(time.time()) + 3600,
            status="LOCKED"
        )
    
    try:
        # Use circuit breaker for fail-fast under load
        return _auth_circuit_breaker.call(perform_handshake)
    except Exception as e:
        if "Circuit breaker OPEN" in str(e):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Service temporarily unavailable due to high failure rate"
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Handshake failed: {str(e)}"
        )


@router.post("/kimi/analyze", response_model=AudioAnalysisResponse, dependencies=[Depends(security_dependency)])
async def kimi_analyze(
    request: AudioAnalysisRequest,
    background_tasks: BackgroundTasks,
    current_user: TokenPayload = Depends(require_auth)
):
    """
    Analyze audio file using Kimi-Audio-7B.
    
    Security: Requires valid session token.
    """
    # TODO: Implement actual analysis
    return AudioAnalysisResponse(
        status="LOCKED",
        analysis_id=f"ANALYSIS-{int(time.time())}",
        estimated_time=30
    )


@router.post("/kimi/chat", response_model=ChatResponse, dependencies=[Depends(security_dependency)])
async def kimi_chat(
    request: ChatRequest,
    current_user: TokenPayload = Depends(require_auth)
):
    """
    Chat with Kimi-Audio model.
    
    Security: Requires valid session token.
    """
    return ChatResponse(
        response="Chat functionality coming soon",
        context_id=request.context_id or f"CTX-{int(time.time())}"
    )


@router.get("/jobs/{job_id}", dependencies=[Depends(security_dependency)])
async def get_job_status(job_id: str):
    """
    Get generation job status.
    """
    return {
        "job_id": job_id,
        "status": JobStatus.COMPLETED,
        "progress": 100,
        "result_url": f"/api/v1/results/{job_id}"
    }


@router.get("/metrics", dependencies=[Depends(security_dependency)])
async def metrics():
    """
    Prometheus metrics endpoint.
    """
    return StreamingResponse(
        prometheus_client.generate_latest(),
        media_type="text/plain"
    )


@router.get("/swarm/status", dependencies=[Depends(security_dependency)])
async def swarm_status():
    """
    Get distributed processing swarm status.
    """
    return {
        "active_nodes": 3,
        "queue_depth": 12,
        "processing_rate": 2.5,
        "status": "healthy"
    }


@router.post("/kaizen/validate", dependencies=[Depends(security_dependency)])
async def kaizen_validate(request: Request):
    """
    Validate sonic parameters against SSmith25 spec.
    
    Security: Strict mode validation with blocking.
    """
    settings = get_settings()
    body = await request.json()
    
    bpm = body.get("bpm")
    key = body.get("key")
    sub_freq = body.get("sub_freq")
    lufs = body.get("lufs")
    
    validations = []
    all_passed = True
    
    # BPM validation
    if bpm is not None:
        bpm_diff = abs(bpm - settings.SONIC_TARGET_BPM)
        bpm_pass = bpm_diff <= settings.SONIC_BPM_TOLERANCE
        validations.append({
            "parameter": "BPM",
            "value": bpm,
            "target": settings.SONIC_TARGET_BPM,
            "passed": bpm_pass,
            "message": "✓" if bpm_pass else f"BPM drift: {bpm_diff:.1f}"
        })
        all_passed = all_passed and bpm_pass
    
    # Key validation
    if key:
        key_pass = key in settings.SONIC_ALLOWED_KEYS
        validations.append({
            "parameter": "Key",
            "value": key,
            "allowed": settings.SONIC_ALLOWED_KEYS,
            "passed": key_pass,
            "message": "✓" if key_pass else "Key not in allowed list"
        })
        all_passed = all_passed and key_pass
    
    # Sub frequency validation
    if sub_freq is not None:
        freq_diff = abs(sub_freq - settings.SONIC_TARGET_SUB_FREQ)
        freq_pass = freq_diff <= settings.SONIC_SUB_FREQ_TOLERANCE
        validations.append({
            "parameter": "Sub Frequency",
            "value": sub_freq,
            "target": settings.SONIC_TARGET_SUB_FREQ,
            "passed": freq_pass,
            "message": "✓" if freq_pass else f"Frequency drift: {freq_diff:.1f}Hz"
        })
        all_passed = all_passed and freq_pass
    
    # LUFS validation
    if lufs is not None:
        lufs_diff = abs(lufs - settings.SONIC_TARGET_LUFS)
        lufs_pass = lufs_diff <= settings.SONIC_LUFS_TOLERANCE
        validations.append({
            "parameter": "LUFS",
            "value": lufs,
            "target": settings.SONIC_TARGET_LUFS,
            "passed": lufs_pass,
            "message": "✓" if lufs_pass else f"LUFS drift: {lufs_diff:.1f}"
        })
        all_passed = all_passed and lufs_pass
    
    return {
        "status": "LOCKED" if all_passed else "DRIFT",
        "validations": validations,
        "security_check": "PASSED",
        "timestamp": datetime.utcnow().isoformat()
    }


@router.post("/generate", dependencies=[Depends(security_dependency)])
async def generate_audio(
    request: GenerationRequest,
    current_user: TokenPayload = Depends(require_auth)
):
    """
    Queue audio generation job.
    """
    job_id = f"K2-{int(time.time() * 1000):x}"
    
    return {
        "job_id": job_id,
        "status": JobStatus.QUEUED,
        "estimated_time": 45,
        "message": "Generation queued. Poll /jobs/{job_id} for progress."
    }


@router.post("/admin/block-ip")
async def block_ip(ip: str, admin_key: str, duration: int = 3600):
    """
    Admin endpoint to manually block an IP address.
    
    Requires admin_key matching settings.ADMIN_SECRET.
    """
    from security.persistence import get_persistence
    
    settings = get_settings()
    
    # Verify admin key
    if admin_key != settings.ADMIN_SECRET:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid admin key"
        )
    
    # Block the IP
    persistence = get_persistence()
    persistence.persist_block(ip, duration_seconds=duration, reason="admin_manual")
    
    # Log admin action
    persistence.log_security_event(
        ip=ip,
        event_type="ADMIN_IP_BLOCK",
        details=f"IP manually blocked by admin for {duration} seconds",
        threat_score=1.0
    )
    
    return {
        "status": "blocked",
        "ip": ip,
        "duration": duration,
        "expires_at": (datetime.utcnow() + timedelta(seconds=duration)).isoformat()
    }
