#!/usr/bin/env python3
"""
Generate one full container of raw EIS data into the lower-machine SQLite DB.

Default target matches the current web topology:
  Container 40
  Cluster 79 -> Pack 157, Pack 158
  Cluster 80 -> Pack 159, Pack 160
  104 cells per pack, 10 frequency points per cell

The existing transmitter uploads one complete scan where sent_time IS NULL and
groups by container_number/cluster_number/pack_number/cell_id/real_time_id.
"""

import math
import os
import random
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path


# Edit this block when the lower-machine test target changes.
# Run with: python generate_lower_machine_container_raw_eis.py
DB_PATH = Path(os.environ.get("LOWER_MACHINE_DB_PATH", str(Path("EIS_ENV_INSTALL") / "EIS_Online" / "database" / "eis_xjj.db")))
CONTAINER_NUMBER = 40
CLUSTER_NUMBERS = [79, 80]
PACK_NUMBERS = [157, 158, 159, 160]
CELLS_PER_PACK = 104
FREQUENCIES = [10000, 5000, 1000, 500, 100, 50, 10, 5, 1, 0.1]
RANDOM_SEED = 20260710

# Set to True only when you want to remove existing lower-machine rows for this container first.
CLEAR_EXISTING_CONTAINER_DATA = False


def resolve_default_db_path():
    try:
        repo_root = Path(__file__).resolve().parents[2]
        eis_online_root = repo_root / "EIS_ENV_INSTALL" / "EIS_Online"
        sys.path.insert(0, str(eis_online_root))
        from database.config import DB_PATH  # pylint: disable=import-outside-toplevel

        return Path(DB_PATH)
    except Exception:
        return Path("EIS_ENV_INSTALL") / "EIS_Online" / "database" / "eis_xjj.db"


if "LOWER_MACHINE_DB_PATH" not in os.environ:
    DB_PATH = resolve_default_db_path()


def iso_now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def ensure_schema(connection):
    cursor = connection.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS container (
            container_id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
            location TEXT,
            description TEXT
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS battery_cluster (
            cluster_id INTEGER PRIMARY KEY AUTOINCREMENT,
            cluster_number INTEGER UNIQUE,
            container_id INTEGER,
            description TEXT,
            CONSTRAINT fk_cabinet_container
                FOREIGN KEY (container_id)
                REFERENCES container (container_id)
                ON DELETE NO ACTION ON UPDATE NO ACTION
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS battery_pack (
            battery_pack_id INTEGER PRIMARY KEY AUTOINCREMENT,
            container_number INTEGER,
            cluster_id INTEGER,
            cluster_number INTEGER,
            pack_number INTEGER,
            description TEXT,
            dispersion_rate REAL,
            pack_saftety_rate REAL,
            real_time_id TEXT,
            CONSTRAINT fk_pack_cluster
                FOREIGN KEY (cluster_number)
                REFERENCES battery_cluster (cluster_number)
                ON DELETE SET NULL ON UPDATE CASCADE
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS eis_measurement (
            measurement_id INTEGER PRIMARY KEY AUTOINCREMENT,
            cell_id INTEGER,
            real_time_id TEXT,
            frequency REAL,
            real_impedance REAL,
            imag_impedance REAL,
            voltage REAL,
            temperature REAL,
            pack_current REAL,
            container_number INTEGER,
            cluster_id INTEGER,
            cluster_number INTEGER,
            pack_number INTEGER,
            sent_time TEXT,
            CONSTRAINT fk_eis_cluster
                FOREIGN KEY (cluster_number)
                REFERENCES battery_cluster (cluster_number)
                ON DELETE SET NULL ON UPDATE CASCADE
        )
        """
    )
    columns = {row[1] for row in cursor.execute("PRAGMA table_info(eis_measurement)")}
    if "pack_current" not in columns:
        cursor.execute("ALTER TABLE eis_measurement ADD COLUMN pack_current REAL")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_pack_cluster_number ON battery_pack(cluster_number)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_eis_cluster_number ON eis_measurement(cluster_number)")


def clear_container(connection, container_number):
    cursor = connection.cursor()
    cursor.execute("DELETE FROM eis_measurement WHERE container_number = ?", (container_number,))
    cursor.execute("DELETE FROM battery_pack WHERE container_number = ?", (container_number,))
    cursor.execute(
        """
        DELETE FROM battery_cluster
        WHERE container_id = ?
          AND NOT EXISTS (
              SELECT 1
              FROM battery_pack bp
              WHERE bp.cluster_number = battery_cluster.cluster_number
          )
        """,
        (container_number,),
    )


def upsert_topology(connection, container_number, clusters, pack_to_cluster, measured_at):
    cursor = connection.cursor()
    cursor.execute(
        """
        INSERT OR IGNORE INTO container (container_id, location, description)
        VALUES (?, ?, ?)
        """,
        (container_number, f"Container {container_number}", "Generated full-container EIS test target"),
    )

    cluster_ids = {}
    for cluster_number in clusters:
        cursor.execute(
            """
            INSERT OR IGNORE INTO battery_cluster (cluster_number, container_id, description)
            VALUES (?, ?, ?)
            """,
            (cluster_number, container_number, f"Cluster {cluster_number}"),
        )
        cursor.execute("SELECT cluster_id FROM battery_cluster WHERE cluster_number = ?", (cluster_number,))
        cluster_ids[cluster_number] = cursor.fetchone()[0]

    for pack_number, cluster_number in pack_to_cluster.items():
        cursor.execute(
            """
            SELECT battery_pack_id
            FROM battery_pack
            WHERE container_number = ? AND cluster_number = ? AND pack_number = ?
            LIMIT 1
            """,
            (container_number, cluster_number, pack_number),
        )
        existing = cursor.fetchone()
        if existing:
            cursor.execute(
                """
                UPDATE battery_pack
                SET cluster_id = ?, description = ?, real_time_id = ?
                WHERE battery_pack_id = ?
                """,
                (cluster_ids[cluster_number], f"Pack {pack_number}", measured_at, existing[0]),
            )
        else:
            cursor.execute(
                """
                INSERT INTO battery_pack (
                    container_number,
                    cluster_id,
                    cluster_number,
                    pack_number,
                    description,
                    dispersion_rate,
                    pack_saftety_rate,
                    real_time_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    container_number,
                    cluster_ids[cluster_number],
                    cluster_number,
                    pack_number,
                    f"Pack {pack_number}",
                    0.0,
                    1.0,
                    measured_at,
                ),
            )

    return cluster_ids


def assign_packs_to_clusters(clusters, packs):
    if len(packs) % len(clusters) != 0:
        raise ValueError("The number of packs must be divisible by the number of clusters.")

    packs_per_cluster = len(packs) // len(clusters)
    mapping = {}
    for cluster_index, cluster_number in enumerate(clusters):
        start = cluster_index * packs_per_cluster
        for pack_number in packs[start : start + packs_per_cluster]:
            mapping[pack_number] = cluster_number
    return mapping


def impedance_point(container_number, pack_number, cell_id, frequency, rng):
    pack_offset = (pack_number % 10) * 0.000002
    cell_offset = (cell_id % 13) * 0.0000015
    aging_factor = 1.0 + (container_number % 7) * 0.01
    base_resistance = (0.00055 + pack_offset + cell_offset) * aging_factor
    frequency_factor = 1.0 + 0.18 / (1.0 + math.sqrt(max(frequency, 0.0001)))
    real_impedance = base_resistance * frequency_factor + rng.uniform(-0.000003, 0.000003)
    imag_impedance = -(base_resistance * 0.35) / (1.0 + frequency / 120.0)
    imag_impedance += rng.uniform(-0.000002, 0.000002)
    return max(real_impedance, 0.00001), imag_impedance


def insert_measurements(
    connection,
    container_number,
    pack_to_cluster,
    cluster_ids,
    cells_per_pack,
    frequencies,
    measured_at,
    seed,
):
    rng = random.Random(seed)
    cursor = connection.cursor()
    inserted = 0

    for pack_number, cluster_number in pack_to_cluster.items():
        cluster_id = cluster_ids[cluster_number]
        for cell_id in range(1, cells_per_pack + 1):
            real_time_id = f"{measured_at}|C{container_number}|P{pack_number}|CELL{cell_id:03d}"
            voltage = 3.62 + rng.uniform(-0.035, 0.035)
            temperature = 25.0 + rng.uniform(-1.5, 1.5)
            pack_current = rng.uniform(-2.0, 2.0)
            for frequency in frequencies:
                real_impedance, imag_impedance = impedance_point(
                    container_number,
                    pack_number,
                    cell_id,
                    frequency,
                    rng,
                )
                cursor.execute(
                    """
                    INSERT INTO eis_measurement (
                        cell_id,
                        real_time_id,
                        frequency,
                        real_impedance,
                        imag_impedance,
                        voltage,
                        temperature,
                        pack_current,
                        container_number,
                        cluster_id,
                        cluster_number,
                        pack_number,
                        sent_time
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
                    """,
                    (
                        cell_id,
                        real_time_id,
                        frequency,
                        real_impedance,
                        imag_impedance,
                        voltage,
                        temperature,
                        pack_current,
                        container_number,
                        cluster_id,
                        cluster_number,
                        pack_number,
                    ),
                )
                inserted += 1

    return inserted


def main():
    db_path = Path(DB_PATH)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    clusters = CLUSTER_NUMBERS
    packs = PACK_NUMBERS
    frequencies = FREQUENCIES
    measured_at = iso_now()
    pack_to_cluster = assign_packs_to_clusters(clusters, packs)

    with sqlite3.connect(db_path) as connection:
        ensure_schema(connection)
        if CLEAR_EXISTING_CONTAINER_DATA:
            clear_container(connection, CONTAINER_NUMBER)
        cluster_ids = upsert_topology(connection, CONTAINER_NUMBER, clusters, pack_to_cluster, measured_at)
        inserted = insert_measurements(
            connection,
            CONTAINER_NUMBER,
            pack_to_cluster,
            cluster_ids,
            CELLS_PER_PACK,
            frequencies,
            measured_at,
            RANDOM_SEED,
        )
        connection.commit()

    scans = len(packs) * CELLS_PER_PACK
    print(f"DB: {db_path}")
    print(f"Measured at: {measured_at}")
    print(f"Clear existing container data: {CLEAR_EXISTING_CONTAINER_DATA}")
    print(f"Container: {CONTAINER_NUMBER}")
    print(f"Clusters: {clusters}")
    print(f"Packs: {packs}")
    print(f"Cells per pack: {CELLS_PER_PACK}")
    print(f"Frequency points per cell: {len(frequencies)}")
    print(f"Inserted raw EIS points: {inserted}")
    print(f"Unsent upload scans created: {scans}")


if __name__ == "__main__":
    main()
