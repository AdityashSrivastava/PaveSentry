"""
test_additional_capabilities.py
Comprehensive End-to-End Verification Test Suite for Delhi NCR Municipal Capabilities:
1. Citizen Crowdsourcing Portal (Delhi 311 / WhatsApp PWA Sync)
2. Monsoon Waterlogging & Hydroplaning Vulnerability Index (IRC:37:2018)
3. Anti-Corruption Cryptographic Audit Trail (CAG / Lokayukta Audit Ready)
"""

import io
import json
import sqlite3
import pytest
from pathlib import Path
from PIL import Image
from fastapi.testclient import TestClient

from backend.main import app
from database.audit_chain import (
    CryptographicAuditLedger,
    compute_sha256,
    compute_block_hash,
    GENESIS_BLOCK_HASH
)
from backend.citizen_portal import submit_citizen_pothole, track_citizen_ticket
from ml.waterlogging_engine import (
    calculate_waterlogging_risk,
    get_network_waterlogging_summary,
    DELHI_WATERLOGGING_HOTSPOTS
)

client = TestClient(app)


def create_dummy_pothole_image() -> bytes:
    """Generates a small synthetic in-memory JPEG for testing."""
    img = Image.new("RGB", (256, 256), color=(60, 60, 65))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


# ==============================================================================
# 1. CITIZEN CROWDSOURCING PORTAL TESTS
# ==============================================================================

class TestCitizenCrowdsourcing:
    """Tests for Delhi 311 / WhatsApp citizen pothole reporting & tracking."""

    def test_submit_citizen_pothole_direct(self):
        """Verify python-level citizen submission with AI verification & reverse geocoding."""
        img_bytes = create_dummy_pothole_image()
        result = submit_citizen_pothole(
            image_bytes=img_bytes,
            filename="pothole_test.jpg",
            latitude=28.5672,
            longitude=77.2100,
            citizen_name="Rajesh Kumar",
            citizen_mobile="9811223344",
            road_description="Deep crater near AIIMS flyover slip road",
            source_channel="delhi_311"
        )

        assert result["status"] == "success"
        assert result["ticket_id"].startswith("DEL-311-2026-")
        assert result["source_channel"] == "delhi_311"
        assert "is_ai_verified" in result
        assert "verification_details" in result
        assert result["verification_details"]["confidence_score"] > 0
        assert "routing" in result
        assert result["routing"]["assigned_division"] is not None
        assert "@pwd.delhi.gov.in" in result["routing"]["assigned_executive_engineer"]

    def test_api_submit_citizen_report(self):
        """Verify REST API POST /api/citizen/report endpoint."""
        img_bytes = create_dummy_pothole_image()
        response = client.post(
            "/api/citizen/report",
            data={
                "latitude": "28.6294",
                "longitude": "77.2435",
                "citizen_name": "Priya Sharma",
                "citizen_mobile": "9899112233",
                "road_description": "Water pooled pothole near ITO Vikas Marg",
                "source_channel": "whatsapp_pwa"
            },
            files={
                "file": ("ito_pothole.jpg", img_bytes, "image/jpeg")
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        ticket_id = data["ticket_id"]
        assert ticket_id.startswith("DEL-311-2026-")
        assert data["source_channel"] == "whatsapp_pwa"
        assert "verification_details" in data
        assert "routing" in data

        # Check tracking for newly created ticket
        track_res = client.get(f"/api/citizen/track/{ticket_id}")
        assert track_res.status_code == 200
        track_data = track_res.json()
        assert track_data["status"] == "success"
        assert track_data["ticket_id"] == ticket_id
        assert len(track_data["milestones"]) == 5
        assert track_data["milestones"][0]["stage"] == "Complaint Logged"
        assert track_data["milestones"][0]["completed"] is True

    def test_track_nonexistent_citizen_ticket(self):
        """Verify tracking a non-existent ticket returns 404."""
        response = client.get("/api/citizen/track/DEL-311-2026-NONEXISTENT")
        assert response.status_code == 404
        data = response.json()
        assert "not found" in data["detail"].lower()

    def test_api_get_citizen_reports(self):
        """Verify GET /api/citizen/reports lists crowdsourced reports."""
        response = client.get("/api/citizen/reports?limit=10")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "reports" in data
        assert isinstance(data["reports"], list)


# ==============================================================================
# 2. MONSOON WATERLOGGING & HYDROPLANING VULNERABILITY INDEX TESTS
# ==============================================================================

class TestMonsoonWaterlogging:
    """Tests for IRC:37:2018 subgrade saturation, hydroplaning, and underpass risks."""

    def test_delhi_waterlogging_hotspots_catalog(self):
        """Verify known Delhi flood hotspots are registered (Minto Bridge, Pul Prahladpur, etc.)."""
        response = client.get("/api/waterlogging/hotspots")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["total_hotspots"] >= 8
        hotspot_names = [h["name"] for h in data["hotspots"]]
        assert any("Minto Bridge" in name for name in hotspot_names)
        assert any("Pul Prahladpur" in name for name in hotspot_names)
        assert any("ITO" in name for name in hotspot_names)
        assert any("Zakhira" in name for name in hotspot_names)

        # Validate engineering properties of Minto Bridge
        minto = next(h for h in data["hotspots"] if "Minto Bridge" in h["name"])
        assert minto["depression_depth_m"] > 3.0
        assert minto["sump_pump_capacity_cusecs"] > 50.0
        assert minto["vulnerability_tier"] == "Critical"

    def test_calculate_corridor_waterlogging_risk(self):
        """Verify IRC:37:2018 soaked CBR degradation & hydroplaning risk index."""
        response = client.get("/api/waterlogging/corridor/DL-NCT-0001")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        wl = data["waterlogging_analysis"]

        # 1. WPRF Score validation
        assert 0.0 <= wl["waterlogging_risk_score"] <= 100.0
        assert "risk_tier" in wl
        assert wl["risk_color"].startswith("#")

        # 2. Nearest Hotspot Link
        assert "nearest_hotspot" in wl
        assert wl["nearest_hotspot"]["distance_km"] >= 0.0

        # 3. IRC:37:2018 Subgrade Mechanics
        subgrade = wl["soaked_subgrade_mechanics"]
        assert subgrade["dry_cbr_pct"] == 8.5
        assert subgrade["soaked_cbr_pct"] < subgrade["dry_cbr_pct"]
        assert subgrade["cbr_loss_pct"] > 0.0
        assert subgrade["dry_resilient_modulus_mpa"] == 85.0  # 10 * 8.5
        assert subgrade["soaked_resilient_modulus_mpa"] < 85.0
        assert 0.0 <= subgrade["fatigue_life_reduction_pct"] <= 100.0

        # 4. Hydroplaning Assessment
        hydro = wl["hydroplaning_assessment"]
        assert 0.0 <= hydro["hydroplaning_risk_index"] <= 100.0
        assert hydro["estimated_water_film_depth_mm"] > 0.0
        assert hydro["critical_hydroplaning_speed_kmh"] > 40.0
        assert "verdict" in hydro

        # 5. Pre-Monsoon Preparedness Protocol
        prep = wl["pre_monsoon_preparedness"]
        assert "15 June" in prep["statutory_deadline"]
        assert 0.0 <= prep["effective_priority_score"] <= 100.0

    def test_corridor_waterlogging_invalid_segment(self):
        """Verify invalid segment ID returns 404."""
        response = client.get("/api/waterlogging/corridor/INVALID-SEGMENT-ID")
        assert response.status_code == 404

    def test_network_waterlogging_summary(self):
        """Verify network-wide aggregation of waterlogging risks across Delhi NCT."""
        response = client.get("/api/waterlogging/network-summary")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["total_corridors_analyzed"] > 0
        assert 0.0 <= data["network_average_wprf"] <= 100.0
        assert "vulnerability_distribution" in data
        dist = data["vulnerability_distribution"]
        assert (dist["critical"] + dist["high"] + dist["moderate"] + dist["low"]) == data["total_corridors_analyzed"]
        assert len(data["top_waterlogging_vulnerable_corridors"]) > 0
        assert len(data["flood_control_agencies"]) >= 3


# ==============================================================================
# 3. ANTI-CORRUPTION CRYPTOGRAPHIC AUDIT TRAIL TESTS
# ==============================================================================

class TestCryptographicAuditTrail:
    """Tests for CAG / Lokayukta SHA-256 chained audit ledger and non-repudiation."""

    def test_audit_chain_structure_and_genesis(self):
        """Verify audit chain starts with Genesis Block 0 having 64 zero hash pointer."""
        response = client.get("/api/audit-trail/chain?limit=50")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data.get("blocks_returned", len(data.get("chain", []))) > 0
        blocks = data["chain"]

        # The oldest block in full chain must be Genesis (block_index = 0)
        # Note: blocks are returned DESC, so last element in full chain or block_index==0
        genesis = next((b for b in blocks if b["block_index"] == 0), None)
        assert genesis is not None
        assert genesis["prev_hash"] == GENESIS_BLOCK_HASH
        assert genesis["event_type"] == "GENESIS_INITIALIZATION"
        assert genesis["actor"] == "CAG_STATUTORY_AUTHORITY"
        assert len(genesis["block_hash"]) == 64  # Valid SHA-256 hex length

    def test_audit_chain_record_event(self):
        """Verify recording a new event correctly extends chain with valid hashes."""
        response = client.get("/api/audit-trail/chain?limit=1")
        last_block = response.json()["chain"][0]

        from database.audit_chain import get_audit_ledger
        ledger = get_audit_ledger()
        new_block = ledger.record_event(
            event_type="TEST_CORRIDOR_AUDIT",
            entity_id="DL-TEST-9999",
            actor="test.auditor@cag.gov.in",
            division="Delhi State Audit Directorate",
            payload={"test_param": 12345, "status": "APPROVED"}
        )

        assert new_block["block_index"] == last_block["block_index"] + 1
        assert new_block["prev_hash"] == last_block["block_hash"]
        assert len(new_block["block_hash"]) == 64
        assert len(new_block["data_hash"]) == 64

    def test_audit_integrity_verification_endpoint(self):
        """Verify GET /api/audit-trail/verify verifies complete chain tamper-free."""
        response = client.get("/api/audit-trail/verify")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        v = data["verification"]
        assert v["is_tamper_free"] is True
        assert v["total_blocks_verified"] >= 5
        assert len(v["tampered_blocks"]) == 0
        assert len(v["merkle_root_hash"]) == 64
        assert "CAG Section 18" in v["statutory_standard"]

    def test_cag_audit_certificate_generation(self):
        """Verify generation of official CAG compliance certificate."""
        response = client.get("/api/audit-trail/certificate")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "certificate" in data
        cert = data["certificate"]
        assert "OFFICIAL COMPTROLLER & AUDITOR GENERAL" in cert["certificate_title"]
        assert cert["certificate_id"].startswith("CAG-DEL-AUDIT-")
        assert cert["is_tamper_free"] is True
        assert "ZERO TAMPERING DETECTED" in cert["verification_status"]
        assert len(cert["statutory_compliance"]) >= 3
        assert len(cert["auditors"]) >= 2
        assert len(cert["recent_audit_trail_anchors"]) > 0

    def test_tamper_detection_logic(self, tmp_path):
        """Verify that altering a block payload or previous hash is immediately flagged as tampered."""
        db_file = tmp_path / "tamper_test.db"
        test_ledger = CryptographicAuditLedger(db_path=db_file)

        # Add two legitimate blocks
        b1 = test_ledger.record_event("TENDER_AWARD", "T-01", "auditor@gov.in", "North Div", {"amt": 100000})
        b2 = test_ledger.record_event("WORK_START", "T-01", "auditor@gov.in", "North Div", {"stage": "Mobilization"})

        # Chain should be pristine initially
        init_verify = test_ledger.verify_chain_integrity()
        assert init_verify["is_tamper_free"] is True

        # Maliciously tamper with b1's payload directly in SQLite without updating block_hash
        conn = sqlite3.connect(db_file)
        cursor = conn.cursor()
        cursor.execute("UPDATE audit_ledger SET payload_json = '{\"amt\": 99999999}' WHERE block_index = 1")
        conn.commit()
        conn.close()

        # Chain verification must catch the tamper
        tampered_verify = test_ledger.verify_chain_integrity()
        assert tampered_verify["is_tamper_free"] is False
        assert len(tampered_verify["tampered_blocks"]) > 0
        assert tampered_verify["tampered_blocks"][0]["failure_type"] == "DATA_HASH_MISMATCH"
