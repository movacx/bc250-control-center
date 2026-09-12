"""BC-250 CPU tuning limits preserved from the reviewed upstream contract.

The values themselves live in ``bc250cc.shared.contract``, which the helpers
and the Decky backend read through a generated copy. They are re-exported here
— by identity, not by value — so every existing caller keeps working and
``test_cpu_frequency_bound_is_single_sourced`` can keep asserting ``is``.
"""

from __future__ import annotations

from bc250cc.shared.contract import (
    CPU_FREQUENCY_RANGE as FREQUENCY_RANGE,
)
from bc250cc.shared.contract import (
    CPU_SCALE_RANGE as SCALE_RANGE,
)
from bc250cc.shared.contract import (
    CPU_TEMPERATURE_RANGE as TEMPERATURE_RANGE,
)
from bc250cc.shared.contract import (
    CPU_VID_LIMIT_MV as VID_LIMIT_MV,
)
from bc250cc.shared.contract import (
    estimated_vid,
)

__all__ = [
    "FREQUENCY_RANGE",
    "SCALE_RANGE",
    "TEMPERATURE_RANGE",
    "VID_LIMIT_MV",
    "estimated_vid",
]
