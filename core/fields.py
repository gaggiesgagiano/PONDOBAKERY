"""Small form helpers shared by the apps."""
from decimal import Decimal

from django import forms


def tidy(v):
    """15.0000 -> 15, 8.3300 -> 8.33 (for showing a number in a box without a tail of zeros)."""
    if v is None:
        return None
    v = Decimal(v)
    if not v.is_finite():
        return v
    return v.quantize(Decimal(1)) if v == v.to_integral_value() else v.normalize()


class TidyDecimalField(forms.DecimalField):
    """A number box where zeros at the end do not count as decimal places.

    A percentage like 15% is kept as 0.1500, so the box used to show "15.0000" – and saving the form
    then failed with "no more than 3 decimal places". Here "15.0000" is simply 15.
    """

    default_error_messages = {
        "max_decimal_places": "Too many numbers after the dot – use at most %(max)s.",
    }

    def to_python(self, value):
        return tidy(super().to_python(value))

    def prepare_value(self, value):
        if isinstance(value, Decimal):
            return format(tidy(value), "f")
        return super().prepare_value(value)
