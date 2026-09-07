from __future__ import annotations

from typing import Tuple

# Retail SGTIN-96 profile: 7-digit GS1 company prefix, partition 5,
# filter 1, and a 38-bit serial. The prefix itself is configuration,
# not a constant.
RETAIL_COMPANY_PREFIX_DIGITS = 7
RETAIL_FILTER = 1
SGTIN96_HEADER = 48
SERIAL_BITS = 38
SERIAL_MAX = (1 << SERIAL_BITS) - 1

# SGTIN-96 partition table: partition_value -> (company_prefix_bits, item_ref_bits,
#                                               company_prefix_digits, item_ref_digits)
SGTIN96_PARTITION_TABLE = {
    0: (40, 4, 12, 1),
    1: (37, 7, 11, 2),
    2: (34, 10, 10, 3),
    3: (30, 14, 9, 4),
    4: (27, 17, 8, 5),
    5: (24, 20, 7, 6),
    6: (20, 24, 6, 7),
}

# Reverse lookup: company_prefix_digits -> partition_value
_PREFIX_DIGITS_TO_PARTITION = {
    entry[2]: pval for pval, entry in SGTIN96_PARTITION_TABLE.items()
}


def ean13_to_sgtin96(
    ean13: str,
    serial: int,
    company_prefix_digits: int = 7,
    filter_value: int = 1,
) -> str:
    """Encode any EAN-13 into a SGTIN-96 EPC hex string (24 hex chars).

    ``company_prefix_digits`` selects the GS1 partition (6-12 digits).
    The indicator digit is taken from the GTIN-14 conversion of EAN-13
    (always 0 for retail consumer trade items).
    """
    normalized = normalize_ean13(ean13)
    if serial < 0 or serial > SERIAL_MAX:
        raise ValueError("Serial must be in range 0..%s" % SERIAL_MAX)
    if company_prefix_digits not in _PREFIX_DIGITS_TO_PARTITION:
        raise ValueError(
            "company_prefix_digits must be one of %s"
            % sorted(_PREFIX_DIGITS_TO_PARTITION.keys())
        )

    partition = _PREFIX_DIGITS_TO_PARTITION[company_prefix_digits]
    cp_bits, ir_bits, cp_digits, ir_digits = SGTIN96_PARTITION_TABLE[partition]

    # GTIN-14 from EAN-13: indicator(0) + EAN-13 without check digit
    gtin14_no_check = "0" + normalized[:-1]
    company_prefix = int(gtin14_no_check[1 : 1 + cp_digits])
    item_ref = int(gtin14_no_check[1 + cp_digits :])

    value = 0
    value |= SGTIN96_HEADER << 88
    value |= (filter_value & 0x7) << 85
    value |= (partition & 0x7) << 82
    value |= company_prefix << (ir_bits + SERIAL_BITS)
    value |= item_ref << SERIAL_BITS
    value |= serial
    return value.to_bytes(12, "big").hex().upper()


def ean13_to_retail_epc(
    ean13: str,
    serial: int,
    company_prefix: str | None = None,
) -> str:
    """Encode an EAN-13 into the retail SGTIN-96 profile.

    ``company_prefix`` optionally restricts input to one GS1 company prefix;
    its length selects the partition. Without it, the default 7-digit
    partition is used for any valid EAN-13.
    """
    normalized = normalize_ean13(ean13)
    prefix_digits = RETAIL_COMPANY_PREFIX_DIGITS
    if company_prefix is not None:
        if not company_prefix.isdigit():
            raise ValueError("company_prefix must contain digits only")
        if not normalized.startswith(company_prefix):
            raise ValueError("EAN-13 must start with %s" % company_prefix)
        prefix_digits = len(company_prefix)
    return ean13_to_sgtin96(
        normalized,
        serial,
        company_prefix_digits=prefix_digits,
        filter_value=RETAIL_FILTER,
    )


def normalize_ean13(ean13: str) -> str:
    digits = "".join(char for char in ean13 if char.isdigit())
    if len(digits) != 13:
        raise ValueError("EAN-13 must contain exactly 13 digits")
    expected = digits[:-1] + str(calculate_check_digit(digits[:-1]))
    if digits != expected:
        raise ValueError("EAN-13 checksum mismatch")
    return digits


def calculate_check_digit(data: str) -> int:
    if not data or not data.isdigit():
        raise ValueError("Check digit input must contain digits")
    weighted_sum = 0
    for index, char in enumerate(reversed(data)):
        weighted_sum += (3 if index % 2 == 0 else 1) * int(char)
    return (10 - (weighted_sum % 10)) % 10
