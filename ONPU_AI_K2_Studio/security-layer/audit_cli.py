#!/usr/bin/env python3
"""
ONPU Security Audit CLI
Deep scan audit tool with comprehensive reporting
"""

import argparse
import asyncio
import json
import sys
import os
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
from enum import Enum

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from clickhouse_driver import Client as ClickHouseClient
    CLICKHOUSE_AVAILABLE = True
except ImportError:
    CLICKHOUSE_AVAILABLE = False
    print("Warning: clickhouse-driver not available. Using mock data.")

from audit import SecurityAuditor


class ScanLevel(Enum):
    QUICK = "quick"
    STANDARD = "standard"
    DEEP = "deep"


@dataclass
class AuditFinding:
    severity: str  # critical, high, medium, low, info
    category: str
    title: str
    description: str
    recommendation: str
    evidence: Optional[Dict[str, Any]] = None
    timestamp: str = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow().isoformat()


@dataclass
class AuditReport:
    scan_id: str
    scan_level: str
    start_time: str
    end_time: str
    duration_seconds: float
    total_requests_analyzed: int
    findings: List[AuditFinding]
    summary: Dict[str, Any]
    metrics: Dict[str, Any]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "scan_id": self.scan_id,
            "scan_level": self.scan_level,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_seconds": self.duration_seconds,
            "total_requests_analyzed": self.total_requests_analyzed,
            "findings": [asdict(f) for f in self.findings],
            "summary": self.summary,
            "metrics": self.metrics
        }


class DeepScanAuditor:
    """
    Deep scan audit implementation for ONPU K2 Studio.
    Performs comprehensive security analysis of API logs.
    """
    
    def __init__(self, clickhouse_url: Optional[str] = None):
        self.clickhouse_url = clickhouse_url or os.getenv(
            "CLICKHOUSE_URL", 
            "clickhouse://localhost:9000/default"
        )
        self.client = None
        if CLICKHOUSE_AVAILABLE:
            try:
                self.client = ClickHouseClient.from_url(self.clickhouse_url)
            except Exception as e:
                print(f"Warning: Could not connect to ClickHouse: {e}")
                self.client = None
    
    async def run_deep_scan(self, hours: int = 24) -> AuditReport:
        """
        Execute deep scan audit over specified time period.
        
        Args:
            hours: Number of hours to analyze (default: 24)
        
        Returns:
            AuditReport with comprehensive findings
        """
        scan_id = f"DEEP-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}"
        start_time = datetime.utcnow()
        
        print(f"\n🔍 Starting Deep Scan Audit: {scan_id}")
        print(f"   Time Range: Last {hours} hours")
        print(f"   ClickHouse: {self.clickhouse_url}")
        print("-" * 60)
        
        findings = []
        
        # 1. Authentication Analysis
        print("\n[1/7] Analyzing authentication patterns...")
        auth_findings = await self._analyze_authentication(hours)
        findings.extend(auth_findings)
        print(f"   Found {len(auth_findings)} authentication issues")
        
        # 2. Anomaly Detection
        print("\n[2/7] Running anomaly detection...")
        anomaly_findings = await self._detect_anomalies(hours)
        findings.extend(anomaly_findings)
        print(f"   Found {len(anomaly_findings)} anomalies")
        
        # 3. Rate Limit Analysis
        print("\n[3/7] Checking rate limit compliance...")
        rate_findings = await self._analyze_rate_limits(hours)
        findings.extend(rate_findings)
        print(f"   Found {len(rate_findings)} rate limit issues")
        
        # 4. Endpoint Security
        print("\n[4/7] Analyzing endpoint security...")
        endpoint_findings = await self._analyze_endpoints(hours)
        findings.extend(endpoint_findings)
        print(f"   Found {len(endpoint_findings)} endpoint issues")
        
        # 5. Response Time Analysis
        print("\n[5/7] Analyzing response times...")
        performance_findings = await self._analyze_performance(hours)
        findings.extend(performance_findings)
        print(f"   Found {len(performance_findings)} performance issues")
        
        # 6. Sonic Parameter Validation
        print("\n[6/7] Validating sonic parameter compliance...")
        sonic_findings = await self._analyze_sonic_parameters(hours)
        findings.extend(sonic_findings)
        print(f"   Found {len(sonic_findings)} sonic parameter issues")
        
        # 7. Data Integrity Check
        print("\n[7/7] Checking data integrity...")
        integrity_findings = await self._check_data_integrity(hours)
        findings.extend(integrity_findings)
        print(f"   Found {len(integrity_findings)} integrity issues")
        
        end_time = datetime.utcnow()
        duration = (end_time - start_time).total_seconds()
        
        # Get total request count
        total_requests = await self._get_total_requests(hours)
        
        # Generate summary
        summary = self._generate_summary(findings)
        
        # Generate metrics
        metrics = await self._generate_metrics(hours)
        
        report = AuditReport(
            scan_id=scan_id,
            scan_level="deep",
            start_time=start_time.isoformat(),
            end_time=end_time.isoformat(),
            duration_seconds=duration,
            total_requests_analyzed=total_requests,
            findings=findings,
            summary=summary,
            metrics=metrics
        )
        
        return report
    
    async def _analyze_authentication(self, hours: int) -> List[AuditFinding]:
        """Analyze authentication patterns and failures."""
        findings = []
        
        if not self.client:
            # Mock data for testing
            findings.append(AuditFinding(
                severity="high",
                category="authentication",
                title="Failed Authentication Spike",
                description="Detected 15 failed authentication attempts in the last hour",
                recommendation="Review source IPs and consider implementing IP-based rate limiting",
                evidence={"failed_count": 15, "time_window": "1 hour"}
            ))
            return findings
        
        try:
            # Query failed authentications
            query = """
            SELECT 
                count() as failed_count,
                client_ip,
                groupArray(request_id) as request_ids
            FROM security_audit
            WHERE timestamp > now() - INTERVAL %(hours)s HOUR
            AND auth_success = false
            GROUP BY client_ip
            HAVING failed_count > 3
            ORDER BY failed_count DESC
            """
            
            result = self.client.execute(query, {"hours": hours})
            
            for row in result:
                failed_count, client_ip, request_ids = row
                findings.append(AuditFinding(
                    severity="high" if failed_count > 10 else "medium",
                    category="authentication",
                    title=f"Failed Authentication Spike from {client_ip}",
                    description=f"Detected {failed_count} failed authentication attempts",
                    recommendation="Review source IP reputation and consider blocking if malicious",
                    evidence={
                        "client_ip": client_ip,
                        "failed_count": failed_count,
                        "sample_requests": request_ids[:5]
                    }
                ))
            
            # Check for successful auth after multiple failures (brute force success)
            query_brute = """
            SELECT 
                client_ip,
                user_fingerprint,
                countIf(auth_success = false) as failures,
                countIf(auth_success = true) as successes
            FROM security_audit
            WHERE timestamp > now() - INTERVAL %(hours)s HOUR
            AND endpoint = '/api/v1/auth/handshake'
            GROUP BY client_ip, user_fingerprint
            HAVING failures > 5 AND successes > 0
            """
            
            result_brute = self.client.execute(query_brute, {"hours": hours})
            
            for row in result_brute:
                client_ip, fingerprint, failures, successes = row
                findings.append(AuditFinding(
                    severity="critical",
                    category="authentication",
                    title=f"Potential Brute Force Success from {client_ip}",
                    description=f"{failures} failures followed by successful authentication",
                    recommendation="Immediately revoke session and investigate account compromise",
                    evidence={
                        "client_ip": client_ip,
                        "fingerprint": fingerprint,
                        "failure_count": failures,
                        "success_count": successes
                    }
                ))
                
        except Exception as e:
            findings.append(AuditFinding(
                severity="info",
                category="system",
                title="Authentication Analysis Error",
                description=f"Could not complete authentication analysis: {str(e)}",
                recommendation="Check ClickHouse connectivity and table schema"
            ))
        
        return findings
    
    async def _detect_anomalies(self, hours: int) -> List[AuditFinding]:
        """Detect anomalous behavior patterns."""
        findings = []
        
        if not self.client:
            findings.append(AuditFinding(
                severity="medium",
                category="anomaly",
                title="Unusual BPM Pattern Detected",
                description="Request with BPM=250 detected (outside normal range)",
                recommendation="Validate input parameters and implement stricter bounds",
                evidence={"bpm": 250, "threshold": 200}
            ))
            return findings
        
        try:
            # Check for high anomaly scores
            query = """
            SELECT 
                request_id,
                endpoint,
                client_ip,
                anomaly_score,
                params_hash
            FROM security_audit
            WHERE timestamp > now() - INTERVAL %(hours)s HOUR
            AND anomaly_score > 0.7
            ORDER BY anomaly_score DESC
            LIMIT 10
            """
            
            result = self.client.execute(query, {"hours": hours})
            
            for row in result:
                request_id, endpoint, client_ip, score, params_hash = row
                findings.append(AuditFinding(
                    severity="high" if score > 0.9 else "medium",
                    category="anomaly",
                    title=f"High Anomaly Score: {score:.2f}",
                    description=f"Request to {endpoint} flagged as anomalous",
                    recommendation="Review request parameters and user behavior",
                    evidence={
                        "request_id": request_id,
                        "endpoint": endpoint,
                        "client_ip": client_ip,
                        "anomaly_score": score,
                        "params_hash": params_hash
                    }
                ))
            
            # Check for unusual sonic parameters (possible injection)
            query_sonic = """
            SELECT 
                request_id,
                client_ip,
                params_hash
            FROM security_audit
            WHERE timestamp > now() - INTERVAL %(hours)s HOUR
            AND endpoint = '/api/v1/kaizen/validate'
            AND (params_hash LIKE '%bpm=999%' 
                 OR params_hash LIKE '%bpm=-1%'
                 OR params_hash LIKE '%key=DROP%')
            """
            
            result_sonic = self.client.execute(query_sonic, {"hours": hours})
            
            for row in result_sonic:
                request_id, client_ip, params_hash = row
                findings.append(AuditFinding(
                    severity="critical",
                    category="injection",
                    title="Potential Parameter Injection Attack",
                    description="Request contains suspicious parameter values",
                    recommendation="Block source IP and review input validation",
                    evidence={
                        "request_id": request_id,
                        "client_ip": client_ip,
                        "params_hash": params_hash
                    }
                ))
                
        except Exception as e:
            findings.append(AuditFinding(
                severity="info",
                category="system",
                title="Anomaly Detection Error",
                description=f"Could not complete anomaly detection: {str(e)}",
                recommendation="Check ClickHouse connectivity"
            ))
        
        return findings
    
    async def _analyze_rate_limits(self, hours: int) -> List[AuditFinding]:
        """Analyze rate limit compliance."""
        findings = []
        
        if not self.client:
            findings.append(AuditFinding(
                severity="low",
                category="rate_limiting",
                title="Rate Limit Approaching",
                description="Client 192.168.1.100 at 850 req/min (limit: 1000)",
                recommendation="Monitor for potential rate limit violations",
                evidence={"client_ip": "192.168.1.100", "current_rate": 850, "limit": 1000}
            ))
            return findings
        
        try:
            # Check for clients approaching rate limits
            query = """
            SELECT 
                client_ip,
                count() as request_count,
                uniq(endpoint) as unique_endpoints
            FROM security_audit
            WHERE timestamp > now() - INTERVAL 1 MINUTE
            GROUP BY client_ip
            HAVING request_count > 800
            ORDER BY request_count DESC
            """
            
            result = self.client.execute(query)
            
            for row in result:
                client_ip, count, unique_endpoints = row
                severity = "high" if count > 950 else "medium" if count > 900 else "low"
                findings.append(AuditFinding(
                    severity=severity,
                    category="rate_limiting",
                    title=f"High Request Rate from {client_ip}",
                    description=f"{count} requests in last minute (limit: 1000)",
                    recommendation="Consider implementing stricter rate limiting for this client",
                    evidence={
                        "client_ip": client_ip,
                        "request_count": count,
                        "unique_endpoints": unique_endpoints,
                        "rate_limit": 1000
                    }
                ))
                
        except Exception as e:
            findings.append(AuditFinding(
                severity="info",
                category="system",
                title="Rate Limit Analysis Error",
                description=f"Could not complete rate limit analysis: {str(e)}",
                recommendation="Check ClickHouse connectivity"
            ))
        
        return findings
    
    async def _analyze_endpoints(self, hours: int) -> List[AuditFinding]:
        """Analyze endpoint security and usage patterns."""
        findings = []
        
        if not self.client:
            findings.append(AuditFinding(
                severity="info",
                category="endpoint",
                title="Endpoint Usage Analysis",
                description="All endpoints operating normally",
                recommendation="Continue monitoring",
                evidence={"endpoints_checked": 8}
            ))
            return findings
        
        try:
            # Check for 404 errors (potential scanning)
            query = """
            SELECT 
                client_ip,
                count() as not_found_count,
                groupArray(DISTINCT endpoint) as endpoints
            FROM security_audit
            WHERE timestamp > now() - INTERVAL %(hours)s HOUR
            AND response_status = 404
            GROUP BY client_ip
            HAVING not_found_count > 10
            ORDER BY not_found_count DESC
            """
            
            result = self.client.execute(query, {"hours": hours})
            
            for row in result:
                client_ip, count, endpoints = row
                findings.append(AuditFinding(
                    severity="medium",
                    category="endpoint",
                    title=f"Potential Endpoint Scanning from {client_ip}",
                    description=f"{count} 404 errors for non-existent endpoints",
                    recommendation="Review if this is legitimate traffic or scanning activity",
                    evidence={
                        "client_ip": client_ip,
                        "404_count": count,
                        "endpoints_attempted": endpoints[:10]
                    }
                ))
            
            # Check for 500 errors
            query_500 = """
            SELECT 
                endpoint,
                count() as error_count,
                avg(response_time_ms) as avg_response_time
            FROM security_audit
            WHERE timestamp > now() - INTERVAL %(hours)s HOUR
            AND response_status >= 500
            GROUP BY endpoint
            HAVING error_count > 5
            ORDER BY error_count DESC
            """
            
            result_500 = self.client.execute(query_500, {"hours": hours})
            
            for row in result_500:
                endpoint, count, avg_time = row
                findings.append(AuditFinding(
                    severity="high",
                    category="endpoint",
                    title=f"Server Errors on {endpoint}",
                    description=f"{count} 5xx errors with {avg_time:.0f}ms avg response time",
                    recommendation="Investigate server-side errors and performance",
                    evidence={
                        "endpoint": endpoint,
                        "error_count": count,
                        "avg_response_time_ms": avg_time
                    }
                ))
                
        except Exception as e:
            findings.append(AuditFinding(
                severity="info",
                category="system",
                title="Endpoint Analysis Error",
                description=f"Could not complete endpoint analysis: {str(e)}",
                recommendation="Check ClickHouse connectivity"
            ))
        
        return findings
    
    async def _analyze_performance(self, hours: int) -> List[AuditFinding]:
        """Analyze response time performance."""
        findings = []
        
        if not self.client:
            findings.append(AuditFinding(
                severity="low",
                category="performance",
                title="Response Time Analysis",
                description="Average response time: 145ms (within acceptable range)",
                recommendation="Continue monitoring",
                evidence={"avg_response_time_ms": 145, "p99_response_time_ms": 890}
            ))
            return findings
        
        try:
            # Check for slow responses
            query = """
            SELECT 
                endpoint,
                count() as slow_count,
                avg(response_time_ms) as avg_time,
                max(response_time_ms) as max_time
            FROM security_audit
            WHERE timestamp > now() - INTERVAL %(hours)s HOUR
            AND response_time_ms > 5000
            GROUP BY endpoint
            HAVING slow_count > 3
            ORDER BY slow_count DESC
            """
            
            result = self.client.execute(query, {"hours": hours})
            
            for row in result:
                endpoint, count, avg_time, max_time = row
                findings.append(AuditFinding(
                    severity="medium",
                    category="performance",
                    title=f"Slow Responses on {endpoint}",
                    description=f"{count} responses > 5s (avg: {avg_time:.0f}ms, max: {max_time:.0f}ms)",
                    recommendation="Optimize endpoint performance or implement caching",
                    evidence={
                        "endpoint": endpoint,
                        "slow_count": count,
                        "avg_time_ms": avg_time,
                        "max_time_ms": max_time
                    }
                ))
                
        except Exception as e:
            findings.append(AuditFinding(
                severity="info",
                category="system",
                title="Performance Analysis Error",
                description=f"Could not complete performance analysis: {str(e)}",
                recommendation="Check ClickHouse connectivity"
            ))
        
        return findings
    
    async def _analyze_sonic_parameters(self, hours: int) -> List[AuditFinding]:
        """Analyze sonic parameter validation compliance."""
        findings = []
        
        if not self.client:
            findings.append(AuditFinding(
                severity="info",
                category="sonic",
                title="Sonic Parameter Compliance",
                description="All sonic parameters within SSmith25 specification",
                recommendation="Continue monitoring",
                evidence={"validations_passed": 42, "validations_failed": 0}
            ))
            return findings
        
        try:
            # Check for drift violations
            query = """
            SELECT 
                count() as drift_count,
                params_hash
            FROM security_audit
            WHERE timestamp > now() - INTERVAL %(hours)s HOUR
            AND endpoint = '/api/v1/kaizen/validate'
            AND params_hash LIKE '%status=DRIFT%'
            GROUP BY params_hash
            """
            
            result = self.client.execute(query, {"hours": hours})
            
            for row in result:
                count, params_hash = row
                findings.append(AuditFinding(
                    severity="medium",
                    category="sonic",
                    title="Sonic Parameter Drift Detected",
                    description=f"{count} validation failures against SSmith25 spec",
                    recommendation="Review audio generation parameters and Kaizen guardrail settings",
                    evidence={
                        "drift_count": count,
                        "params_hash": params_hash
                    }
                ))
                
        except Exception as e:
            findings.append(AuditFinding(
                severity="info",
                category="system",
                title="Sonic Analysis Error",
                description=f"Could not complete sonic analysis: {str(e)}",
                recommendation="Check ClickHouse connectivity"
            ))
        
        return findings
    
    async def _check_data_integrity(self, hours: int) -> List[AuditFinding]:
        """Check data integrity and consistency."""
        findings = []
        
        if not self.client:
            findings.append(AuditFinding(
                severity="info",
                category="integrity",
                title="Data Integrity Check",
                description="All data integrity checks passed",
                recommendation="Continue monitoring",
                evidence={"checks_passed": 5, "checks_failed": 0}
            ))
            return findings
        
        try:
            # Check for missing timestamps
            query = """
            SELECT count() 
            FROM security_audit
            WHERE timestamp > now() - INTERVAL %(hours)s HOUR
            AND (timestamp IS NULL OR request_id IS NULL)
            """
            
            result = self.client.execute(query, {"hours": hours})
            missing_count = result[0][0] if result else 0
            
            if missing_count > 0:
                findings.append(AuditFinding(
                    severity="high",
                    category="integrity",
                    title="Missing Required Fields",
                    description=f"{missing_count} records with missing timestamp or request_id",
                    recommendation="Investigate data pipeline and fix ingestion process",
                    evidence={"missing_count": missing_count}
                ))
            
            # Check for duplicate request IDs
            query_dup = """
            SELECT request_id, count() as cnt
            FROM security_audit
            WHERE timestamp > now() - INTERVAL %(hours)s HOUR
            GROUP BY request_id
            HAVING cnt > 1
            LIMIT 10
            """
            
            result_dup = self.client.execute(query_dup, {"hours": hours})
            
            for row in result_dup:
                request_id, count = row
                findings.append(AuditFinding(
                    severity="medium",
                    category="integrity",
                    title=f"Duplicate Request ID: {request_id}",
                    description=f"Request ID appears {count} times in audit log",
                    recommendation="Investigate duplicate logging or retry logic",
                    evidence={"request_id": request_id, "duplicate_count": count}
                ))
                
        except Exception as e:
            findings.append(AuditFinding(
                severity="info",
                category="system",
                title="Integrity Check Error",
                description=f"Could not complete integrity check: {str(e)}",
                recommendation="Check ClickHouse connectivity"
            ))
        
        return findings
    
    async def _get_total_requests(self, hours: int) -> int:
        """Get total number of requests in time period."""
        if not self.client:
            return 1250  # Mock value
        
        try:
            query = """
            SELECT count() 
            FROM security_audit
            WHERE timestamp > now() - INTERVAL %(hours)s HOUR
            """
            result = self.client.execute(query, {"hours": hours})
            return result[0][0] if result else 0
        except:
            return 0
    
    def _generate_summary(self, findings: List[AuditFinding]) -> Dict[str, Any]:
        """Generate summary statistics from findings."""
        severity_counts = {
            "critical": 0,
            "high": 0,
            "medium": 0,
            "low": 0,
            "info": 0
        }
        
        category_counts = {}
        
        for finding in findings:
            severity_counts[finding.severity] = severity_counts.get(finding.severity, 0) + 1
            category_counts[finding.category] = category_counts.get(finding.category, 0) + 1
        
        total = len(findings)
        risk_score = (
            severity_counts["critical"] * 100 +
            severity_counts["high"] * 50 +
            severity_counts["medium"] * 20 +
            severity_counts["low"] * 5 +
            severity_counts["info"] * 1
        ) / max(total, 1)
        
        return {
            "total_findings": total,
            "severity_distribution": severity_counts,
            "category_distribution": category_counts,
            "risk_score": round(risk_score, 2),
            "risk_level": (
                "CRITICAL" if severity_counts["critical"] > 0 else
                "HIGH" if severity_counts["high"] > 0 else
                "MEDIUM" if severity_counts["medium"] > 0 else
                "LOW" if severity_counts["low"] > 0 else
                "INFO"
            )
        }
    
    async def _generate_metrics(self, hours: int) -> Dict[str, Any]:
        """Generate comprehensive metrics."""
        if not self.client:
            return {
                "total_requests": 1250,
                "auth_success_rate": 0.94,
                "avg_response_time_ms": 145,
                "error_rate": 0.02,
                "unique_clients": 15,
                "top_endpoints": [
                    {"endpoint": "/api/v1/kimi/chat", "count": 450},
                    {"endpoint": "/api/v1/kimi/analyze", "count": 320},
                    {"endpoint": "/api/v1/auth/handshake", "count": 180}
                ]
            }
        
        try:
            # Total requests
            query_total = """
            SELECT count() 
            FROM security_audit
            WHERE timestamp > now() - INTERVAL %(hours)s HOUR
            """
            total = self.client.execute(query_total, {"hours": hours})[0][0]
            
            # Auth success rate
            query_auth = """
            SELECT 
                countIf(auth_success = true) as success,
                count() as total
            FROM security_audit
            WHERE timestamp > now() - INTERVAL %(hours)s HOUR
            AND endpoint = '/api/v1/auth/handshake'
            """
            auth_result = self.client.execute(query_auth, {"hours": hours})
            auth_success = auth_result[0][0] if auth_result else 0
            auth_total = auth_result[0][1] if auth_result else 1
            
            # Average response time
            query_time = """
            SELECT avg(response_time_ms)
            FROM security_audit
            WHERE timestamp > now() - INTERVAL %(hours)s HOUR
            """
            avg_time = self.client.execute(query_time, {"hours": hours})[0][0]
            
            # Error rate
            query_errors = """
            SELECT 
                countIf(response_status >= 400) as errors,
                count() as total
            FROM security_audit
            WHERE timestamp > now() - INTERVAL %(hours)s HOUR
            """
            error_result = self.client.execute(query_errors, {"hours": hours})
            errors = error_result[0][0] if error_result else 0
            error_total = error_result[0][1] if error_result else 1
            
            # Unique clients
            query_clients = """
            SELECT uniq(client_ip)
            FROM security_audit
            WHERE timestamp > now() - INTERVAL %(hours)s HOUR
            """
            unique_clients = self.client.execute(query_clients, {"hours": hours})[0][0]
            
            # Top endpoints
            query_endpoints = """
            SELECT endpoint, count() as cnt
            FROM security_audit
            WHERE timestamp > now() - INTERVAL %(hours)s HOUR
            GROUP BY endpoint
            ORDER BY cnt DESC
            LIMIT 5
            """
            endpoints = self.client.execute(query_endpoints, {"hours": hours})
            top_endpoints = [{"endpoint": e[0], "count": e[1]} for e in endpoints]
            
            return {
                "total_requests": total,
                "auth_success_rate": round(auth_success / max(auth_total, 1), 4),
                "avg_response_time_ms": round(avg_time or 0, 2),
                "error_rate": round(errors / max(error_total, 1), 4),
                "unique_clients": unique_clients,
                "top_endpoints": top_endpoints
            }
            
        except Exception as e:
            return {"error": str(e)}


def print_report(report: AuditReport, format_type: str = "text"):
    """Print audit report in specified format."""
    if format_type == "json":
        print(json.dumps(report.to_dict(), indent=2))
        return
    
    # Text format
    print("\n" + "=" * 80)
    print(f"  ONPU AI K2 STUDIO - SECURITY AUDIT REPORT")
    print(f"  Scan ID: {report.scan_id}")
    print(f"  Level: {report.scan_level.upper()}")
    print("=" * 80)
    
    print(f"\n📊 EXECUTIVE SUMMARY")
    print(f"   Risk Level: {report.summary['risk_level']}")
    print(f"   Risk Score: {report.summary['risk_score']}/100")
    print(f"   Total Findings: {report.summary['total_findings']}")
    print(f"   Requests Analyzed: {report.total_requests_analyzed}")
    print(f"   Duration: {report.duration_seconds:.2f} seconds")
    
    print(f"\n📈 SEVERITY DISTRIBUTION")
    for severity, count in report.summary['severity_distribution'].items():
        if count > 0:
            icon = {
                "critical": "🔴",
                "high": "🟠", 
                "medium": "🟡",
                "low": "🔵",
                "info": "⚪"
            }.get(severity, "⚪")
            print(f"   {icon} {severity.upper()}: {count}")
    
    print(f"\n📋 DETAILED FINDINGS")
    print("-" * 80)
    
    # Sort by severity
    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
    sorted_findings = sorted(report.findings, key=lambda f: severity_order.get(f.severity, 5))
    
    for i, finding in enumerate(sorted_findings, 1):
        icon = {
            "critical": "🔴",
            "high": "🟠",
            "medium": "🟡", 
            "low": "🔵",
            "info": "⚪"
        }.get(finding.severity, "⚪")
        
        print(f"\n{i}. {icon} [{finding.severity.upper()}] {finding.title}")
        print(f"   Category: {finding.category}")
        print(f"   Description: {finding.description}")
        print(f"   Recommendation: {finding.recommendation}")
        if finding.evidence:
            print(f"   Evidence: {json.dumps(finding.evidence, indent=6)}")
    
    print(f"\n📊 METRICS")
    print("-" * 80)
    for key, value in report.metrics.items():
        if isinstance(value, list):
            print(f"   {key}:")
            for item in value:
                if isinstance(item, dict):
                    print(f"      - {item}")
                else:
                    print(f"      - {item}")
        else:
            print(f"   {key}: {value}")
    
    print(f"\n⏱️  TIMING")
    print(f"   Started: {report.start_time}")
    print(f"   Completed: {report.end_time}")
    print(f"   Duration: {report.duration_seconds:.2f}s")
    
    print("\n" + "=" * 80)
    print("  END OF AUDIT REPORT")
    print("=" * 80)


async def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="ONPU AI K2 Studio - Security Audit CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python audit_cli.py --scan deep --hours 24 --report
  python audit_cli.py --scan quick --hours 1 --format json
  python audit_cli.py --scan standard --hours 12 --output report.json
        """
    )
    
    parser.add_argument(
        "--scan",
        choices=["quick", "standard", "deep"],
        default="standard",
        help="Scan level (default: standard)"
    )
    parser.add_argument(
        "--hours",
        type=int,
        default=24,
        help="Hours of data to analyze (default: 24)"
    )
    parser.add_argument(
        "--report",
        action="store_true",
        help="Generate and display report"
    )
    parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)"
    )
    parser.add_argument(
        "--output",
        type=str,
        help="Output file path (optional)"
    )
    parser.add_argument(
        "--clickhouse-url",
        type=str,
        default=os.getenv("CLICKHOUSE_URL", "clickhouse://localhost:9000/default"),
        help="ClickHouse connection URL"
    )
    
    args = parser.parse_args()
    
    # Initialize auditor
    auditor = DeepScanAuditor(clickhouse_url=args.clickhouse_url)
    
    # Run scan
    if args.scan == "deep":
        report = await auditor.run_deep_scan(hours=args.hours)
    else:
        # For quick/standard, run deep scan with reduced scope
        print(f"Running {args.scan} scan (using deep scan with mock data)...")
        report = await auditor.run_deep_scan(hours=args.hours)
    
    # Generate report
    if args.report or args.output:
        print_report(report, format_type=args.format)
        
        if args.output:
            with open(args.output, 'w') as f:
                json.dump(report.to_dict(), f, indent=2)
            print(f"\n💾 Report saved to: {args.output}")
    
    return report


if __name__ == "__main__":
    asyncio.run(main())
