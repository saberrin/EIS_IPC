import sqlite3
import sys
import tempfile
import types
import unittest
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

# The parser tests do not open a CAN device. Keep them runnable on development
# machines where the Linux python-can dependency is intentionally absent.
if "can" not in sys.modules:
    sys.modules["can"] = types.SimpleNamespace(interface=types.SimpleNamespace())

from acquisition.can_reader import CANReader
from database import db_init
from database import repository as repository_module
from database.entity import EisMeasurement
from transport.data_transmitter import DataTransmitter


class EisTelemetryProtocolTest(unittest.TestCase):
    def test_parses_confirmed_v_first_telemetry_format(self):
        telemetry = CANReader.parse_telemetry_section(
            "V,3.2145,CUR,-0.8421,T,28.60,VALID,7"
        )

        self.assertEqual(7, telemetry["valid_flags"])
        self.assertAlmostEqual(3.2145, telemetry["voltage"])
        self.assertAlmostEqual(-0.8421, telemetry["pack_current"])
        self.assertAlmostEqual(28.60, telemetry["temperature"])

    def test_valid_mask_converts_unavailable_values_to_none(self):
        telemetry = CANReader.parse_telemetry_section(
            "V,3.2145,CUR,0.0000,T,28.60,VALID,5"
        )

        self.assertAlmostEqual(3.2145, telemetry["voltage"])
        self.assertIsNone(telemetry["pack_current"])
        self.assertAlmostEqual(28.60, telemetry["temperature"])

    def test_gete_parser_passes_one_snapshot_to_all_points(self):
        reader = object.__new__(CANReader)
        reader.address_mapping = {
            0x11: {
                "container_number": 1,
                "cluster_number": 2,
                "pack_number": 3,
            }
        }
        captured = {}

        def capture_insert(*args):
            captured["args"] = args

        reader.insert_measurements = capture_insert
        line = (
            ">0x11,GETE,6,0.000000,CMD_OK,"
            "V,3.2145,CUR,-0.8421,T,28.60,VALID,7;"
            "R1,0.0012,I1,-0.0004,F1,10000.0;"
            "R2,0.0013,I2,-0.0005,F2,8000.0;"
            "CHECKSUM,123<"
        )

        self.assertTrue(reader.parse_and_insert_data(line))
        args = captured["args"]
        self.assertEqual(0x11, args[0])
        self.assertEqual(6, args[1])
        self.assertEqual(2, len(args[2]))
        self.assertAlmostEqual(-0.8421, args[6]["pack_current"])


class EisTelemetryDatabaseTest(unittest.TestCase):
    def test_existing_database_is_migrated_idempotently(self):
        original_path = db_init.DB_PATH
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = str(Path(temp_dir) / "eis.db")
            try:
                db_init.DB_PATH = database_path
                db_init.init_database()
                db_init.init_database()

                connection = sqlite3.connect(database_path)
                try:
                    columns = {
                        row[1]
                        for row in connection.execute("PRAGMA table_info(eis_measurement)")
                    }
                finally:
                    connection.close()
                self.assertIn("pack_current", columns)
            finally:
                db_init.DB_PATH = original_path

    def test_repository_persists_and_reads_pack_current(self):
        original_init_path = db_init.DB_PATH
        original_repository_path = repository_module.DB_PATH
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = str(Path(temp_dir) / "eis.db")
            try:
                db_init.DB_PATH = database_path
                repository_module.DB_PATH = database_path
                db_init.init_database()
                repository = repository_module.Repository()
                repository.insert_measurements([
                    EisMeasurement(
                        cell_id=6,
                        real_time_id="2026-09-01 10:00:00",
                        frequency=10000.0,
                        real_impedance=0.0012,
                        imag_impedance=-0.0004,
                        voltage=3.2145,
                        temperature=28.60,
                        container_number=1,
                        cluster_number=2,
                        pack_number=3,
                        pack_current=-0.8421,
                    )
                ])

                saved = repository.get_cell_measurements(6, 1)[0]
                self.assertAlmostEqual(3.2145, saved.voltage)
                self.assertAlmostEqual(-0.8421, saved.pack_current)
                self.assertAlmostEqual(28.60, saved.temperature)
            finally:
                db_init.DB_PATH = original_init_path
                repository_module.DB_PATH = original_repository_path

    def test_uploader_uses_measured_values(self):
        transmitter = DataTransmitter()
        rows = [
            (
                1,
                6,
                "2026-09-01 10:00:00",
                10000.0,
                0.0012,
                -0.0004,
                3.2145,
                28.60,
                -0.8421,
                1,
                2,
                3,
            )
        ]

        payload = transmitter.format_data(rows)
        measurement = payload["eisMeasurements"][0]
        self.assertAlmostEqual(3.2145, measurement["voltage"])
        self.assertAlmostEqual(-0.8421, measurement["packCurrent"])
        self.assertAlmostEqual(28.60, measurement["temperature"])


if __name__ == "__main__":
    unittest.main()
