import json
import queue
import sqlite3
import sys
import tempfile
import threading
import unittest
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


PROJECT_DIR = Path(__file__).resolve().parents[1] / "EIS_Online"
sys.path.insert(0, str(PROJECT_DIR))

# 测试环境不需要真实 SocketCAN，仅在导入时提供 python-can 占位模块。
sys.modules.setdefault(
    "can",
    SimpleNamespace(interface=SimpleNamespace(Bus=None), Message=None),
)

from can_tester import CAN_Tester
from acquisition.can_reader import CANReader, CANStreamReassembler
from transport import data_transmitter as transmitter_module


class BoardMappingTests(unittest.TestCase):
    def test_mapping_contains_only_board_topology(self):
        mapping_file = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8")
        try:
            json.dump(
                {
                    "address_mapping": [
                        {
                            "addr_id": "0x11",
                            "container_number": 2,
                            "cluster_number": 3,
                            "pack_number": 4,
                        }
                    ]
                },
                mapping_file,
            )
            mapping_file.close()

            reader = CANReader.__new__(CANReader)
            reader.address_mapping_path = Path(mapping_file.name)
            mapping = reader.load_address_mapping()

            self.assertEqual(
                mapping[0x11],
                {"container_number": 2, "cluster_number": 3, "pack_number": 4},
            )
            self.assertNotIn("cell_id", mapping[0x11])
        finally:
            Path(mapping_file.name).unlink(missing_ok=True)

    def test_response_cell_id_is_used_inside_mapped_pack(self):
        reader = CANReader.__new__(CANReader)
        reader.address_mapping = {
            0x11: {"container_number": 2, "cluster_number": 3, "pack_number": 4}
        }
        captured = {}

        def capture_insert(addr_id, cell_id, data_points, container, cluster, pack):
            captured.update(
                addr_id=addr_id,
                cell_id=cell_id,
                data_points=data_points,
                container=container,
                cluster=cluster,
                pack=pack,
            )

        reader.insert_measurements = capture_insert
        response = (
            ">0x11, GETE, 37, 0.000000,CMD_OK,\r\n"
            "R1,0.1000,I1,-0.2000,F1,1000.0000;"
            "R2,0.3000,I2,-0.4000,F2,10.0000;CHECKSUM,709<"
        )

        self.assertTrue(reader.parse_and_insert_data(response))
        self.assertEqual(captured["addr_id"], 0x11)
        self.assertEqual(captured["cell_id"], 37)
        self.assertEqual((captured["container"], captured["cluster"], captured["pack"]), (2, 3, 4))
        self.assertEqual(captured["data_points"], [(0.1, -0.2, 1000.0), (0.3, -0.4, 10.0)])


class CANReassemblyTests(unittest.TestCase):
    def test_interleaved_board_frames_are_isolated(self):
        reassembler = CANStreamReassembler(timeout_seconds=2)

        self.assertEqual(reassembler.feed(0x11, b">0x11,GET", now=0), [])
        board_12 = reassembler.feed(0x12, b">0x12,STAT,CMD_OK<", now=0.1)
        board_11 = reassembler.feed(0x11, b"E,1,0,CMD_OK<", now=0.2)

        self.assertEqual(board_12, [b">0x12,STAT,CMD_OK<"])
        self.assertEqual(board_11, [b">0x11,GETE,1,0,CMD_OK<"])

    def test_stale_partial_response_is_not_joined_to_later_data(self):
        reassembler = CANStreamReassembler(timeout_seconds=1)
        reassembler.feed(0x11, b">0x11,GETE,old", now=0)

        self.assertEqual(reassembler.feed(0x11, b",tail<", now=1.1), [])
        self.assertEqual(reassembler.dropped_timeouts, 1)

    def test_new_start_resynchronizes_incomplete_response(self):
        reassembler = CANStreamReassembler(timeout_seconds=2)
        reassembler.feed(0x11, b">0x11,broken", now=0)

        completed = reassembler.feed(0x11, b">0x11,STAT,CMD_OK<", now=0.1)

        self.assertEqual(completed, [b">0x11,STAT,CMD_OK<"])
        self.assertEqual(reassembler.dropped_resync, 1)

    def test_multiple_messages_in_one_frame_are_preserved(self):
        reassembler = CANStreamReassembler(timeout_seconds=2)

        completed = reassembler.feed(
            0x11,
            b"noise>0x11,STAT,CMD_OK<\n>0x11,GETT,CMD_OK<",
            now=0,
        )

        self.assertEqual(
            completed,
            [b">0x11,STAT,CMD_OK<", b">0x11,GETT,CMD_OK<"],
        )

    def test_oversize_partial_response_is_discarded(self):
        reassembler = CANStreamReassembler(timeout_seconds=2, max_message_bytes=16)

        self.assertEqual(reassembler.feed(0x11, b">" + b"x" * 16, now=0), [])
        self.assertEqual(reassembler.dropped_oversize, 1)

    def test_response_header_must_match_arbitration_id(self):
        self.assertTrue(CANReader._response_matches_source(b">0x11,GETE,CMD_OK<", 0x11))
        self.assertFalse(CANReader._response_matches_source(b">0x12,GETE,CMD_OK<", 0x11))


class AutomaticUploadTests(unittest.TestCase):
    def test_sweep_complete_enqueues_upload(self):
        tester = CAN_Tester.__new__(CAN_Tester)
        tester.eis_sweep_in_progress = True
        tester.data_transmitter = object()
        tester.upload_queue = queue.Queue(maxsize=1)
        tester.log_info = lambda _message: None

        tester._on_eis_sweep_complete()

        self.assertFalse(tester.eis_sweep_in_progress)
        self.assertEqual(tester.upload_queue.qsize(), 1)

    def test_upload_worker_drains_pending_scans(self):
        completed = threading.Event()

        class FakeTransmitter:
            def __init__(self):
                self.calls = 0

            def upload_once(self):
                self.calls += 1
                if self.calls >= 2:
                    completed.set()
                    return False
                return True

        tester = CAN_Tester.__new__(CAN_Tester)
        tester.running = True
        tester.data_transmitter = FakeTransmitter()
        tester.upload_queue = queue.Queue(maxsize=1)
        tester.log_info = lambda _message: None
        tester.log_error = lambda message: self.fail(message)

        worker = threading.Thread(target=tester.upload_worker_loop)
        worker.start()
        tester.request_upload()

        self.assertTrue(completed.wait(timeout=2))
        tester.running = False
        worker.join(timeout=2)
        self.assertFalse(worker.is_alive())
        self.assertEqual(tester.data_transmitter.calls, 2)

    def test_successful_upload_marks_scan_as_sent(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "eis.db"
            with closing(sqlite3.connect(db_path)) as connection:
                connection.execute(
                    """
                    CREATE TABLE eis_measurement (
                        measurement_id INTEGER PRIMARY KEY,
                        cell_id INTEGER,
                        real_time_id TEXT,
                        frequency REAL,
                        real_impedance REAL,
                        imag_impedance REAL,
                        voltage REAL,
                        temperature REAL,
                        container_number INTEGER,
                        cluster_number INTEGER,
                        pack_number INTEGER,
                        sent_time TEXT
                    )
                    """
                )
                connection.executemany(
                    """
                    INSERT INTO eis_measurement (
                        measurement_id, cell_id, real_time_id, frequency,
                        real_impedance, imag_impedance, voltage, temperature,
                        container_number, cluster_number, pack_number, sent_time
                    ) VALUES (?, 37, '2026-08-21 10:00:00', ?, ?, ?, 3.2, 25.0, 2, 3, 4, NULL)
                    """,
                    [(1, 1000.0, 0.1, -0.2), (2, 10.0, 0.3, -0.4)],
                )
                connection.commit()

            transmitter = transmitter_module.DataTransmitter(max_retries=1)
            response = SimpleNamespace(status_code=201, text='{"status":"ingested"}')
            with mock.patch.object(transmitter_module, "DB_PATH", str(db_path)), mock.patch.object(
                transmitter_module.requests,
                "post",
                return_value=response,
            ) as post:
                self.assertTrue(transmitter.upload_once())

            payload = post.call_args.kwargs["json"]
            self.assertEqual(payload["eisMeasurements"][0]["cellId"], "37")
            with closing(sqlite3.connect(db_path)) as connection:
                unsent = connection.execute(
                    "SELECT COUNT(*) FROM eis_measurement WHERE sent_time IS NULL"
                ).fetchone()[0]
            self.assertEqual(unsent, 0)


if __name__ == "__main__":
    unittest.main()
