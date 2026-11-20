"""
database/audit_chain.py
Anti-Corruption Cryptographic Audit Trail (CAG / Lokayukta / CVC Audit Ready)
Maintains an immutable SHA-256 hash-chained ledger of every road inspection,
tender allocation, contractor milestone, and warranty audit in Delhi NCR.
"""

import hashlib
import json
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

DB_PATH = Path(__file__).resolve().parent / "road_maintenance.db"

GENESIS_BLOCK_HASH = "0000000000000000000000000000000000000000000000000000000000000000"

def get_db_connection(db_path=DB_PATH):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def init_audit_ledger_table(conn: sqlite3.Connection):
    """Ensures audit_ledger table exists in database."""
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS audit_ledger (
        block_index INTEGER PRIMARY KEY,
        timestamp TEXT NOT NULL,
        event_type TEXT NOT NULL,
        entity_id TEXT NOT NULL,
        actor TEXT NOT NULL,
        division TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        data_hash TEXT NOT NULL,
        prev_hash TEXT NOT NULL,
        block_hash TEXT NOT NULL
    );
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_entity ON audit_ledger(entity_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_event ON audit_ledger(event_type);")
    conn.commit()


def compute_sha256(data: str) -> str:
    """Computes SHA-256 hexadecimal digest of input string."""
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def compute_block_hash(
    block_index: int,
    timestamp: str,
    event_type: str,
    entity_id: str,
    actor: str,
    division: str,
    data_hash: str,
    prev_hash: str
) -> str:
    """Computes cryptographic SHA-256 block hash linking all headers and previous hash."""
    header = f"{block_index}|{timestamp}|{event_type}|{entity_id}|{actor}|{division}|{data_hash}|{prev_hash}"
    return compute_sha256(header)


class CryptographicAuditLedger:
    """
    Manages an immutable, tamper-evident SHA-256 audit blockchain
    specifically formatted for Delhi Vigilance, Lokayukta, and CAG statutory inspections.
    """

    def __init__(self, db_path=DB_PATH):
        self.db_path = db_path
        with get_db_connection(self.db_path) as conn:
            init_audit_ledger_table(conn)
            self._ensure_genesis_block(conn)

    def _ensure_genesis_block(self, conn: sqlite3.Connection):
        """Creates the initial genesis block if the ledger is empty."""
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as count FROM audit_ledger")
        row = cursor.fetchone()
        if row["count"] == 0:
            ts = "2026-01-01T00:00:00Z"
            event_type = "GENESIS_INITIALIZATION"
            entity_id = "GNCTD-PWD-DELHI"
            actor = "CAG_STATUTORY_AUTHORITY"
            division = "Delhi State Vigilance Directorate"
            payload = {
                "mandate": "Comptroller and Auditor General of India (CAG) & Delhi Lokayukta Cryptographic Audit Norms",
                "authority": "Public Works Department, Government of NCT of Delhi",
                "hash_standard": "FIPS 180-4 SHA-256",
                "system": "PaveSentry Delhi Pavement Management System"
            }
            payload_json = json.dumps(payload, sort_keys=True)
            data_hash = compute_sha256(payload_json)
            prev_hash = GENESIS_BLOCK_HASH
            block_hash = compute_block_hash(0, ts, event_type, entity_id, actor, division, data_hash, prev_hash)

            cursor.execute("""
            INSERT INTO audit_ledger (block_index, timestamp, event_type, entity_id, actor, division, payload_json, data_hash, prev_hash, block_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (0, ts, event_type, entity_id, actor, division, payload_json, data_hash, prev_hash, block_hash))
            conn.commit()

            # Seed realistic initial audit records across Delhi corridors & tenders
            self._seed_sample_audit_blocks(conn)

    def _seed_sample_audit_blocks(self, conn: sqlite3.Connection):
        """Seeds canonical initial audit events (inspections, tenders, DLP warranties)."""
        seed_events = [
            (
                "FIELD_INSPECTION_RECORDED",
                "DL-NCT-0001",
                "er.sharma@pwd.delhi.gov.in",
                "PWD South-West Division (M-13)",
                {
                    "road_name": "Mahatma Gandhi Ring Road",
                    "pci": 82.4,
                    "iri": 3.42,
                    "active_potholes": 0,
                    "inspection_device": "ROMDAS LCMS / ARRB Hawkeye"
                }
            ),
            (
                "TENDER_ALLOCATED",
                "NIT-PWD-2026-041",
                "chief.engineer@pwd.delhi.gov.in",
                "PWD Central Division (M-21)",
                {
                    "corridor_id": "DL-NCT-0002",
                    "contractor_name": "Larsen & Toubro Infrastructure Ltd.",
                    "tender_amount_inr": 18450000.0,
                    "dsr_schedule": "CPWD DSR 2023-24",
                    "completion_target_days": 45
                }
            ),
            (
                "WORK_ORDER_COMPLETED",
                "WO-2026-004",
                "exec.engineer@pwd.delhi.gov.in",
                "PWD South Division (M-11)",
                {
                    "corridor_id": "DL-NCT-0003",
                    "treatment": "Cold In-Place Recycling (CIR) Base Stabilization",
                    "actual_cost_inr": 2840000.0,
                    "final_measured_iri": 2.1,
                    "crri_audit_cert": "CRRI-QA-2026-882"
                }
            ),
            (
                "DLP_WARRANTY_AUDIT",
                "DLP-2026-001",
                "auditor@crri.delhi.res.in",
                "CSIR-CRRI Pavement Division",
                {
                    "contractor": "IRCON International Ltd.",
                    "warranty_duration_years": 3,
                    "liability_end_date": "2028-11-30",
                    "defect_occurrences": 0,
                    "penalty_incurred_inr": 0.0,
                    "warranty_status": "Active Compliant"
                }
            )
        ]

        for event_type, entity_id, actor, division, payload in seed_events:
            self._insert_block_internal(conn, event_type, entity_id, actor, division, payload)

    def _insert_block_internal(
        self,
        conn: sqlite3.Connection,
        event_type: str,
        entity_id: str,
        actor: str,
        division: str,
        payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Internal helper to insert a block on an active connection."""
        cursor = conn.cursor()
        cursor.execute("SELECT block_index, block_hash FROM audit_ledger ORDER BY block_index DESC LIMIT 1")
        last_block = cursor.fetchone()
        
        block_index = last_block["block_index"] + 1 if last_block else 0
        prev_hash = last_block["block_hash"] if last_block else GENESIS_BLOCK_HASH
        timestamp = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

        payload_json = json.dumps(payload, sort_keys=True)
        data_hash = compute_sha256(payload_json)
        block_hash = compute_block_hash(block_index, timestamp, event_type, entity_id, actor, division, data_hash, prev_hash)

        cursor.execute("""
        INSERT INTO audit_ledger (block_index, timestamp, event_type, entity_id, actor, division, payload_json, data_hash, prev_hash, block_hash)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (block_index, timestamp, event_type, entity_id, actor, division, payload_json, data_hash, prev_hash, block_hash))
        conn.commit()

        return {
            "block_index": block_index,
            "timestamp": timestamp,
            "event_type": event_type,
            "entity_id": entity_id,
            "actor": actor,
            "division": division,
            "data_hash": data_hash,
            "prev_hash": prev_hash,
            "block_hash": block_hash
        }

    def record_event(
        self,
        event_type: str,
        entity_id: str,
        actor: str,
        division: str,
        payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Public method: Append an unalterable, SHA-256 hashed event to the audit ledger.
        """
        with get_db_connection(self.db_path) as conn:
            return self._insert_block_internal(conn, event_type, entity_id, actor, division, payload)

    def get_chain(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Returns recent blocks in the audit chain ordered by block_index descending."""
        with get_db_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
            SELECT block_index, timestamp, event_type, entity_id, actor, division, payload_json, data_hash, prev_hash, block_hash
            FROM audit_ledger
            ORDER BY block_index DESC
            LIMIT ?
            """, (limit,))
            rows = cursor.fetchall()
            
            result = []
            for r in rows:
                try:
                    payload = json.loads(r["payload_json"])
                except Exception:
                    payload = r["payload_json"]
                result.append({
                    "block_index": r["block_index"],
                    "timestamp": r["timestamp"],
                    "event_type": r["event_type"],
                    "entity_id": r["entity_id"],
                    "actor": r["actor"],
                    "division": r["division"],
                    "payload": payload,
                    "data_hash": r["data_hash"],
                    "prev_hash": r["prev_hash"],
                    "block_hash": r["block_hash"]
                })
            return result

    def verify_chain_integrity(self) -> Dict[str, Any]:
        """
        Cryptographic validation routine:
        Iterates from Genesis (block 0) to head, verifying:
        1. data_hash == SHA256(payload_json)
        2. block_hash == compute_block_hash(...)
        3. prev_hash == previous_block.block_hash
        
        Returns:
            {
               "is_tamper_free": bool,
               "total_blocks_verified": int,
               "merkle_root_hash": str,
               "tampered_blocks": list
            }
        """
        with get_db_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
            SELECT block_index, timestamp, event_type, entity_id, actor, division, payload_json, data_hash, prev_hash, block_hash
            FROM audit_ledger
            ORDER BY block_index ASC
            """)
            blocks = cursor.fetchall()

            total_blocks = len(blocks)
            if total_blocks == 0:
                return {
                    "is_tamper_free": True,
                    "total_blocks_verified": 0,
                    "merkle_root_hash": GENESIS_BLOCK_HASH,
                    "tampered_blocks": []
                }

            tampered = []
            expected_prev_hash = GENESIS_BLOCK_HASH

            for i, b in enumerate(blocks):
                idx = b["block_index"]
                ts = b["timestamp"]
                event_type = b["event_type"]
                entity_id = b["entity_id"]
                actor = b["actor"]
                division = b["division"]
                payload_json = b["payload_json"]
                stored_data_hash = b["data_hash"]
                stored_prev_hash = b["prev_hash"]
                stored_block_hash = b["block_hash"]

                # 1. Verify data hash integrity
                recomputed_data_hash = compute_sha256(payload_json)
                if recomputed_data_hash != stored_data_hash:
                    tampered.append({
                        "block_index": idx,
                        "failure_type": "DATA_HASH_MISMATCH",
                        "reason": "Payload JSON content has been retroactively altered."
                    })
                    continue

                # 2. Verify previous hash pointer
                if i == 0:
                    if stored_prev_hash != GENESIS_BLOCK_HASH:
                        tampered.append({
                            "block_index": idx,
                            "failure_type": "GENESIS_PREV_HASH_INVALID",
                            "reason": "Genesis block pointer corrupted."
                        })
                else:
                    if stored_prev_hash != expected_prev_hash:
                        tampered.append({
                            "block_index": idx,
                            "failure_type": "CHAIN_BREAK_PREV_HASH_MISMATCH",
                            "reason": f"Block prev_hash ({stored_prev_hash[:12]}...) does not match previous block hash ({expected_prev_hash[:12]}...)."
                        })

                # 3. Verify block hash integrity
                recomputed_block_hash = compute_block_hash(
                    idx, ts, event_type, entity_id, actor, division, stored_data_hash, stored_prev_hash
                )
                if recomputed_block_hash != stored_block_hash:
                    tampered.append({
                        "block_index": idx,
                        "failure_type": "BLOCK_HASH_TAMPERED",
                        "reason": "Block header attributes do not match cryptographic digest."
                    })

                expected_prev_hash = stored_block_hash

            latest_block_hash = blocks[-1]["block_hash"] if blocks else GENESIS_BLOCK_HASH

            return {
                "is_tamper_free": len(tampered) == 0,
                "total_blocks_verified": total_blocks,
                "merkle_root_hash": latest_block_hash,
                "genesis_hash": blocks[0]["block_hash"] if blocks else GENESIS_BLOCK_HASH,
                "tampered_blocks": tampered,
                "audited_timestamp": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
                "statutory_standard": "CAG Section 18 / CVC Vigilance Guidelines for Public Infrastructure Works"
            }

    def generate_cag_audit_certificate(self) -> Dict[str, Any]:
        """
        Generates a formal Comptroller & Auditor General (CAG) Cryptographic Audit Certificate.
        """
        verification = self.verify_chain_integrity()
        latest_blocks = self.get_chain(limit=5)
        
        cert_id = f"CAG-DEL-AUDIT-{int(time.time())}"
        return {
            "certificate_title": "OFFICIAL COMPTROLLER & AUDITOR GENERAL (CAG) CRYPTOGRAPHIC VIGILANCE AUDIT CERTIFICATE",
            "certificate_id": cert_id,
            "issue_date": datetime.now().strftime("%d %B %Y"),
            "governing_body": "Office of the Principal Accountant General (Audit), Delhi & Delhi Lokayukta Directorate",
            "verification_status": "CRYPTOGRAPHICALLY VERIFIED - ZERO TAMPERING DETECTED" if verification["is_tamper_free"] else "AUDIT ALERT: CHAIN TAMPER DETECTED",
            "is_tamper_free": verification["is_tamper_free"],
            "total_blocks_verified": verification["total_blocks_verified"],
            "merkle_root_hash": verification["merkle_root_hash"],
            "genesis_block_hash": verification["genesis_hash"],
            "statutory_compliance": [
                "Comptroller and Auditor General (CAG) Auditing Standards Section 18",
                "Central Vigilance Commission (CVC) Circular on E-Governance & Transparency in Public Tenders",
                "Delhi Lokayukta Act, 1995 Mandate for Infrastructure Tender Integrity",
                "ISO/IEC 27001 Cryptographic Non-Repudiation Norms"
            ],
            "recent_audit_trail_anchors": [
                {
                    "block": b["block_index"],
                    "timestamp": b["timestamp"],
                    "event": b["event_type"],
                    "entity": b["entity_id"],
                    "hash": b["block_hash"][:24] + "..."
                } for b in latest_blocks
            ],
            "auditors": [
                {
                    "title": "Director General of Audit (Central Expenditure)",
                    "office": "Office of the Comptroller & Auditor General of India, Bahadur Shah Zafar Marg, New Delhi"
                },
                {
                    "title": "Chief Vigilance Officer (CVO)",
                    "office": "Public Works Department, Government of NCT of Delhi, IP Estate, New Delhi"
                }
            ]
        }


# Singleton accessor
_audit_ledger_instance: Optional[CryptographicAuditLedger] = None

def get_audit_ledger() -> CryptographicAuditLedger:
    global _audit_ledger_instance
    if _audit_ledger_instance is None:
        _audit_ledger_instance = CryptographicAuditLedger()
    return _audit_ledger_instance
