from dataclasses import dataclass
from datetime import datetime

@dataclass
class EisMeasurement:
    cell_id: int
    real_time_id: datetime
    frequency: float
    real_impedance: float
    imag_impedance: float
    voltage: float
    temperature: float
    container_number: int
    cluster_number: int
    pack_number: int