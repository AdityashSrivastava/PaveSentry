"""
test_phase_g_complete.py
Comprehensive End-to-End Verification Test Suite for Phase G:
Production DevOps, Multi-Container Orchestration, Observability Probes,
CI/CD Automation, and Full Platform Regression across Phases A through G.
"""

import os
import sys
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

ROOT_DIR = Path(__file__).resolve().parent
sys.path.append(str(ROOT_DIR))

from backend.main import app

client = TestClient(app)

# ==============================================================================
# SECTION 1: Observability & Health Probes (Liveness & Readiness)
# ==============================================================================

@pytest.mark.devops
def test_phase_g_liveness_probe():
    """Verify Kubernetes/Docker liveness endpoint /healthz."""
    res = client.get("/healthz")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"
    assert data["service"] == "pavesentry-api"
    assert "timestamp" in data
    assert data["version"] == "3.0.0"


@pytest.mark.devops
def test_phase_g_readiness_probe():
    """Verify deep dependency readiness endpoint /readyz."""
    res = client.get("/readyz")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ready"
    assert "checks" in data
    checks = data["checks"]
    assert "ok" in checks["database"]
    assert "ok" in checks["postgis_engine"]
    assert "ok" in checks["ml_models"]


@pytest.mark.devops
def test_phase_g_api_health_diagnostics():
    """Verify operational health diagnostics endpoint /api/health."""
    res = client.get("/api/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"
    assert data["version"] == "3.0.0"
    assert "database" in data
    assert data["database"]["corridors"] > 0
    assert "connected_fleet" in data
    assert data["connected_fleet"]["active_vehicles"] >= 3


# ==============================================================================
# SECTION 2: Dockerfile Multi-Stage & Security Hardening Verification
# ==============================================================================

@pytest.mark.devops
def test_phase_g_dockerfile_hardening():
    """Verify Dockerfile multi-stage structure, non-root user, and health check."""
    dockerfile_path = ROOT_DIR / "Dockerfile"
    assert dockerfile_path.exists(), "Dockerfile must exist at repository root"
    
    content = dockerfile_path.read_text(encoding="utf-8")
    
    # 1. Multi-stage build check
    assert "AS builder" in content, "Dockerfile must define a builder stage"
    assert "AS runner" in content, "Dockerfile must define a hardened runner stage"
    
    # 2. Base image security check (slim-bookworm)
    assert "python:3.11-slim" in content, "Must use minimal slim base image"
    
    # 3. Non-root user privileges (CIS Benchmark)
    assert "useradd" in content or "adduser" in content, "Must create dedicated system user"
    assert "pavesentry" in content, "Must use 'pavesentry' non-root user"
    assert "USER pavesentry" in content, "Must switch to non-root user before execution"
    
    # 4. Exposed port & healthcheck
    assert "EXPOSE 9005" in content, "Must expose internal port 9005"
    assert "HEALTHCHECK" in content, "Must declare container HEALTHCHECK"
    assert "/healthz" in content, "HEALTHCHECK must probe /healthz"


# ==============================================================================
# SECTION 3: Docker Compose Multi-Container Orchestration Verification
# ==============================================================================

@pytest.mark.devops
def test_phase_g_docker_compose_architecture():
    """Verify Docker Compose multi-service architecture (FastAPI, PostGIS, Redis, Nginx)."""
    compose_path = ROOT_DIR / "docker-compose.yml"
    assert compose_path.exists(), "docker-compose.yml must exist at repository root"
    
    content = compose_path.read_text(encoding="utf-8")
    
    # 1. All 4 microservices present
    assert "pavesentry-api:" in content, "Must define API backend service"
    assert "pavesentry-postgis:" in content, "Must define PostgreSQL 16 PostGIS service"
    assert "pavesentry-redis:" in content, "Must define Redis 7 cache service"
    assert "pavesentry-nginx:" in content, "Must define Nginx reverse proxy service"
    
    # 2. Correct images and versions
    assert "postgis/postgis:16" in content, "Must use official PostgreSQL 16 + PostGIS image"
    assert "redis:7" in content, "Must use Redis 7 image"
    assert "nginx:alpine" in content, "Must use Nginx Alpine image"
    
    # 3. Automated PostGIS 16 initialization script mounting
    assert "schema_postgis.sql" in content, "Must mount schema_postgis.sql for auto-init"
    
    # 4. Healthcheck conditions & dependencies
    assert "service_healthy" in content, "Must use service_healthy dependency conditions"
    
    # 5. Persistent named volumes & isolated bridge network
    assert "postgis_data:" in content, "Must declare postgis_data volume"
    assert "redis_data:" in content, "Must declare redis_data volume"
    assert "uploads_data:" in content, "Must declare uploads_data volume"
    assert "pavesentry-net:" in content, "Must declare isolated internal network"


# ==============================================================================
# SECTION 4: Nginx Reverse Proxy Configuration Verification
# ==============================================================================

@pytest.mark.devops
def test_phase_g_nginx_reverse_proxy_config():
    """Verify Nginx reverse proxy configuration for rate-limiting, gzip, and security headers."""
    nginx_path = ROOT_DIR / "deploy" / "nginx" / "nginx.conf"
    assert nginx_path.exists(), "deploy/nginx/nginx.conf must exist"
    
    content = nginx_path.read_text(encoding="utf-8")
    
    # 1. Upstream backend routing
    assert "upstream pavesentry_backend" in content
    assert "pavesentry-api:9005" in content
    
    # 2. Security headers (OWASP)
    assert "X-Frame-Options" in content
    assert "X-Content-Type-Options" in content
    assert "Referrer-Policy" in content
    
    # 3. Gzip compression & max body size
    assert "gzip on;" in content
    assert "client_max_body_size 50M;" in content
    
    # 4. Rate limiting zones
    assert "limit_req_zone" in content
    assert "pavesentry_api_limit" in content
    assert "pavesentry_vision_limit" in content


# ==============================================================================
# SECTION 5: Secrets Hygiene & CI/CD Pipeline Verification
# ==============================================================================

@pytest.mark.devops
def test_phase_g_secrets_and_dockerignore():
    """Verify .env.example template and .dockerignore security exclusion."""
    env_example = ROOT_DIR / ".env.example"
    assert env_example.exists(), ".env.example must exist"
    env_content = env_example.read_text(encoding="utf-8")
    
    # Must have variable names but NO real secrets
    assert "DATABASE_URL=" in env_content
    assert "POSTGRES_PASSWORD=" in env_content
    assert "SECRET_KEY=" in env_content
    assert "REDIS_URL=" in env_content
    
    dockerignore = ROOT_DIR / ".dockerignore"
    assert dockerignore.exists(), ".dockerignore must exist"
    di_content = dockerignore.read_text(encoding="utf-8")
    assert ".git" in di_content
    assert ".env" in di_content
    assert "__pycache__" in di_content
    assert "*.key" in di_content or "*.pem" in di_content


@pytest.mark.devops
def test_phase_g_github_actions_workflow():
    """Verify GitHub Actions CI/CD pipeline workflow configuration."""
    ci_path = ROOT_DIR / ".github" / "workflows" / "ci.yml"
    assert ci_path.exists(), ".github/workflows/ci.yml must exist"
    
    content = ci_path.read_text(encoding="utf-8")
    
    # Triggers
    assert "push:" in content
    assert "pull_request:" in content
    
    # Critical Pipeline Jobs
    assert "lint-and-syntax:" in content
    assert "test-suite:" in content
    assert "security-audit:" in content
    assert "docker-validation:" in content
    
    # Tests across all phases executed
    assert "test_phase_a_complete.py" in content
    assert "test_phase_b_complete.py" in content
    assert "test_phase_c_complete.py" in content
    assert "test_phase_d_complete.py" in content
    assert "test_phase_e_complete.py" in content
    assert "test_phase_f_complete.py" in content
    assert "test_phase_g_complete.py" in content


# ==============================================================================
# SECTION 6: Full Multi-Phase Regression (Phases A through F Verification)
# ==============================================================================

@pytest.mark.regression
def test_full_platform_regression_phases_a_to_f():
    """End-to-end regression verifying that all previous phase engines remain operational."""
    # Phase A: Vision calibration presets
    res_a = client.get("/api/vision/calibration-presets")
    assert res_a.status_code == 200
    assert len(res_a.json()["presets"]) >= 4
    
    # Phase B: Multi-year master plan
    from optimization.multi_year_optimizer import optimize_multi_year_capital_plan
    plan = optimize_multi_year_capital_plan(annual_budget_inr=500000000.0, horizon_years=3)
    assert len(plan) > 0
    
    # Phase C: Kanban work orders & DSR BOQ
    res_c_kb = client.get("/api/kanban/work-orders")
    assert res_c_kb.status_code == 200
    res_c_boq = client.post("/api/dsr/generate-boq", json={"segment_id": "DL-NCT-0001"})
    assert res_c_boq.status_code == 200
    
    # Phase D: Explainable AI TreeSHAP
    from ml.xai_engine import explain_corridor_risk
    xai = explain_corridor_risk("DL-NCT-0001")
    assert "top_risk_drivers" in xai
    
    # Phase E: PostGIS spatial radius query & DTC fleet telemetry
    from database.postgis_manager import get_postgis_engine
    pg = get_postgis_engine()
    nearby = pg.query_corridors_within_radius(77.2090, 28.6139, 5000)
    assert len(nearby) > 0
    
    from ml.telemetry_engine import get_telemetry_engine
    fleet = get_telemetry_engine().get_live_fleet_telemetry()
    assert len(fleet) >= 3
    
    # Phase F: IRC:SP:98 Green Roads LCA & Certificate
    res_f = client.get("/api/green-roads/corridor/DL-NCT-0001")
    assert res_f.status_code == 200
    assert "carbon_lca" in res_f.json()
    res_f_cert = client.get("/api/green-roads/certificate/DL-NCT-0001")
    assert res_f_cert.status_code == 200
    assert res_f_cert.json()["certificate"]["certificate_id"].startswith("IRC-SP98-DEL-")


if __name__ == "__main__":
    pytest.main(["-v", __file__])
