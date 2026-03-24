"""
Seed script for Phase 4 testing — creates 2 RESULTS_RELEASED demo cycles
with varied aggregated_results scores across multiple departments.
"""
import os
import sys
import uuid
from datetime import datetime, timezone

import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.production')
django.setup()

from django.db import connection

NOW = datetime.now(timezone.utc)

# ── Constants ───────────────────────────────────────────────────────────────
ADMIN_ID    = 'a319ea7a-442d-4983-b398-1c0b6ad1e8b2'
TEMPLATE_ID = '154ebb0c-9391-448b-a7d8-208f3cd0ac4a'

# user email -> id
USERS = {
    'emp1@gamyam.com':     'a3afa9a3-4f8a-4638-b3d1-1da7a8286287',
    'emp2@gamyam.com':     '4f4c75e8-3d16-49b7-bba8-7304510ccbd3',
    'emp3@gamyam.com':     '2d6f133b-6ad3-4b63-8817-a51d7e9a7c21',
    'emp4@gamyam.com':     'a3159515-9196-4189-aaea-4d5697e11f24',
    'emp5@gamyam.com':     'fe3a060c-e1c8-494a-9f08-f5b4dd1ed88f',
    'emp6@gamyam.com':     'd4d011d5-4b10-4623-aa22-838148b4e1d1',
    'manager1@gamyam.com': 'd4d0cfb8-6bc3-4680-bf2b-7e8273d16b1b',
}

CYCLE1_ID = str(uuid.uuid4())
CYCLE2_ID = str(uuid.uuid4())

with connection.cursor() as c:
    # ── Clean old demo data ─────────────────────────────────────────────────
    c.execute("SELECT id FROM review_cycles WHERE name LIKE '[DEMO]%'")
    old_ids = [str(r[0]) for r in c.fetchall()]
    for oid in old_ids:
        c.execute("DELETE FROM aggregated_results WHERE cycle_id = %s", [oid])
    if old_ids:
        c.execute("DELETE FROM review_cycles WHERE name LIKE '[DEMO]%'")
        print(f"Deleted {len(old_ids)} old DEMO cycles")

    # ── Create 2 RESULTS_RELEASED demo cycles ──────────────────────────────
    c.execute("""
        INSERT INTO review_cycles
            (id, name, description, state, peer_enabled, peer_min_count, peer_max_count,
             peer_threshold, peer_anonymity, manager_anonymity, self_anonymity,
             review_deadline, nomination_approval_mode, results_released_at,
             created_at, updated_at, created_by_id, template_id)
        VALUES
            (%s, '[DEMO] Q4 2025 Annual Review', 'Demo seeded cycle for Phase 4 analytics testing',
             'RESULTS_RELEASED', true, 2, 5, 3, true, true, false, '2025-12-31',
             'MANUAL', %s, %s, %s, %s, %s),
            (%s, '[DEMO] Q1 2026 Mid-Year', 'Demo seeded cycle for Phase 4 analytics testing',
             'RESULTS_RELEASED', true, 2, 5, 3, true, true, false, '2026-03-15',
             'MANUAL', %s, %s, %s, %s, %s)
    """, [
        CYCLE1_ID, NOW, NOW, NOW, ADMIN_ID, TEMPLATE_ID,
        CYCLE2_ID, NOW, NOW, NOW, ADMIN_ID, TEMPLATE_ID,
    ])
    print(f"Created cycles: {CYCLE1_ID[:8]}... and {CYCLE2_ID[:8]}...")

    # ── Seed CYCLE1 results ([DEMO] Q4 2025 Annual Review) ─────────────────
    # Top performers: emp4 (4.8), emp1 (4.5)
    # Mid-range:      emp2 (4.1), emp3 (3.8), emp6 (3.6)
    # Bottom:         manager1 (3.2), emp5 (2.9)
    cycle1_data = [
        (USERS['emp4@gamyam.com'],     4.8, 4.7, 4.9, 4.8),
        (USERS['emp1@gamyam.com'],     4.5, 4.4, 4.6, 4.5),
        (USERS['emp2@gamyam.com'],     4.1, 4.0, 4.2, 4.1),
        (USERS['emp3@gamyam.com'],     3.8, 3.7, 3.9, 3.8),
        (USERS['emp6@gamyam.com'],     3.6, 3.5, 3.7, None),
        (USERS['manager1@gamyam.com'], 3.2, 3.1, 3.3, None),
        (USERS['emp5@gamyam.com'],     2.9, 2.8, 3.0, None),
    ]
    for uid, overall, peer, mgr, self_s in cycle1_data:
        c.execute(
            "INSERT INTO aggregated_results "
            "(id, reviewee_id, overall_score, peer_score, manager_score, self_score, cycle_id, computed_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            [str(uuid.uuid4()), uid, overall, peer, mgr, self_s, CYCLE1_ID, NOW],
        )

    # ── Seed CYCLE2 results ([DEMO] Q1 2026 Mid-Year) ──────────────────────
    # Different ordering to test comparison / most-improved
    cycle2_data = [
        (USERS['emp1@gamyam.com'],     4.9, 4.8, 5.0, 4.9),
        (USERS['emp4@gamyam.com'],     4.6, 4.5, 4.7, 4.6),
        (USERS['emp2@gamyam.com'],     4.2, 4.1, 4.3, 4.1),
        (USERS['emp3@gamyam.com'],     3.9, 3.8, 4.0, 3.7),
        (USERS['emp5@gamyam.com'],     3.1, 3.0, 3.2, None),
        (USERS['emp6@gamyam.com'],     2.7, 2.6, 2.8, None),
    ]
    for uid, overall, peer, mgr, self_s in cycle2_data:
        c.execute(
            "INSERT INTO aggregated_results "
            "(id, reviewee_id, overall_score, peer_score, manager_score, self_score, cycle_id, computed_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            [str(uuid.uuid4()), uid, overall, peer, mgr, self_s, CYCLE2_ID, NOW],
        )

    # ── Verify ───────────────────────────────────────────────────────────────
    c.execute("""
        SELECT rc.name, rc.state, COUNT(ar.id), ROUND(AVG(ar.overall_score)::numeric, 2)
        FROM review_cycles rc
        JOIN aggregated_results ar ON ar.cycle_id = rc.id
        WHERE rc.name LIKE '[DEMO]%'
        GROUP BY rc.name, rc.state
        ORDER BY rc.name
    """)
    print("\nVerification:")
    for row in c.fetchall():
        print(f"  [{row[1]}] {row[0]}: {row[2]} results, avg={row[3]}")

    # Confirm top_performers query will find data
    c.execute("""
        SELECT rc.id, rc.name, rc.state FROM review_cycles
        WHERE state IN ('RESULTS_RELEASED', 'ARCHIVED')
        ORDER BY created_at DESC LIMIT 1
    """)
    latest = c.fetchone()
    print(f"\nLatest RESULTS_RELEASED cycle: {latest[1]} ({latest[2]})")

print("\nSEED COMPLETE")
