"""
ONPU K2 Studio - Main Application
FastAPI application with security middleware
"""

import time
from datetime import datetime, timedelta
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from config.settings import get_settings
from api.v1.endpoints import router as api_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.
    Handles startup and shutdown events.
    """
    # Startup
    settings = get_settings()
    print(f"🚀 {settings.APP_NAME} v{settings.APP_VERSION} starting...")
    
    # Validate ADMIN_SECRET
    if not settings.ADMIN_SECRET or len(settings.ADMIN_SECRET) < 16:
        print("⚠️  CRITICAL: ADMIN_SECRET invalid or too short (< 16 chars)")
        print("⚠️  Admin endpoints will reject all requests")
    else:
        print("🔐 Admin secret validated")
    
    # Initialize security layer
    try:
        from security.persistence import get_persistence
        persistence = get_persistence()
        print("🔒 Security persistence initialized")
    except Exception as e:
        print(f"⚠️  Security persistence not available: {e}")
    
    yield
    
    # Shutdown
    print("👋 Shutting down...")


# Create FastAPI application
settings = get_settings()
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="ONPU AI K2 Studio - Audio Generation API",
    lifespan=lifespan
)


# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Security middleware
@app.middleware("http")
async def security_middleware(request: Request, call_next):
    """
    Security middleware for all requests.
    - IP block check
    - Rate limiting
    - Threat score calculation
    - X-Security-Score header
    """
    client_ip = request.client.host
    start_time = time.time()
    
    # Import security components
    try:
        from security.persistence import get_persistence
        persistence = get_persistence()
    except Exception:
        # Security layer not available, continue
        response = await call_next(request)
        return response
    
    # 1. IP Block Check
    if persistence.is_ip_blocked(client_ip):
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"detail": "IP blocked due to security violations"}
        )
    
    # 2. Rate Limit Check (global)
    # Track request count
    current_time = datetime.utcnow()
    if not hasattr(persistence, '_ip_request_count'):
        persistence._ip_request_count = {}
    
    if client_ip not in persistence._ip_request_count:
        persistence._ip_request_count[client_ip] = []
    
    # Clean old entries (> 1 minute)
    persistence._ip_request_count[client_ip] = [
        t for t in persistence._ip_request_count[client_ip]
        if (current_time - t) < timedelta(minutes=1)
    ]
    
    # Add current request
    persistence._ip_request_count[client_ip].append(current_time)
    
    # Check limit (1000 per minute)
    if len(persistence._ip_request_count[client_ip]) > 1000:
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={"detail": "Rate limit exceeded: 1000 requests per minute"}
        )
    
    # 3. Process request
    response = await call_next(request)
    
    # 4. Calculate threat score for POST requests
    threat_score = 0.0
    if request.method == "POST":
        try:
            from kimia_engine.guardrail import get_kaizen_guardrail
            body = await request.json()
            guardrail = get_kaizen_guardrail(strict_mode=True)
            threat_score = guardrail.calculate_anomaly_score(body)
        except Exception:
            pass  # Ignore errors in threat calculation
    
    # 5. Add security headers
    response.headers["X-Security-Score"] = str(threat_score)
    response.headers["X-Request-ID"] = f"req-{int(time.time() * 1000)}"
    
    # 6. Log security event for high threat scores
    if threat_score > 0.5:
        try:
            persistence.log_security_event(
                ip=client_ip,
                event_type="HIGH_THREAT_REQUEST",
                details=f"Threat score {threat_score} for {request.url.path}",
                threat_score=threat_score
            )
        except Exception:
            pass
    
    return response


# Include API routes
app.include_router(api_router, prefix="/api/v1")


@app.get("/health")
async def health_check():
    """
    Health check endpoint.
    """
    return {
        "status": "healthy",
        "version": settings.APP_VERSION,
        "timestamp": datetime.utcnow().isoformat()
    }


@app.get("/")
async def root():
    """
    Root endpoint - API information.
    """
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs": "/docs",
        "health": "/health"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG
    )
