"""Type definitions for the Orion Finance Python SDK."""

from enum import Enum


class VaultType(str, Enum):
    """Type of the vault."""

    ENCRYPTED = "encrypted"
    TRANSPARENT = "transparent"


class FeeType(str, Enum):
    """Type of the fee."""

    ABSOLUTE = "absolute"  #  Fee based on the latest return, no hurdles or high water mark (HWM)
    SOFT_HURDLE = "soft_hurdle"  # Fee unlocked after hurdle rate is reached
    HARD_HURDLE = "hard_hurdle"  # Fee only above a fixed hurdle rate
    HIGH_WATER_MARK = "high_water_mark"  # Fee only on gains above the previous peak
    HURDLE_HWM = "hurdle_hwm"  # Combination of (hard) hurdle rate and HWM


fee_type_to_int = {
    "absolute": 0,
    "soft_hurdle": 1,
    "hard_hurdle": 2,
    "high_water_mark": 3,
    "hurdle_hwm": 4,
}
