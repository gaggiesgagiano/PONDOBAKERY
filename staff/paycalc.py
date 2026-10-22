"""Payroll maths (monthly, US$).

basic     monthly: salary − salary ÷ working days × unpaid days
          day rate: rate × days worked        hourly: rate × hours worked
overtime  hourly rate × (overtime hours × 1.5 + Sunday/holiday hours × 2)
          hourly rate = salary ÷ working hours a month, or day rate ÷ hours a day, or the hourly rate
gross     basic + overtime + allowances + bonus + other earnings
NSSA      gross (up to the insurable earnings ceiling) × 4.5%  – the business pays the same again
taxable   gross − NSSA (NSSA is allowed as a deduction for PAYE)
PAYE      taxable × band rate − band deduct  (ZIMRA monthly USD table)
AIDS levy PAYE × 3%
net       gross − NSSA − PAYE − AIDS levy − advances − other deductions
ZIMDEF    gross × 1%, paid by the business
"""
from decimal import ROUND_HALF_UP, Decimal

Z = Decimal("0")
C = Decimal("0.01")


def r2(v):
    return Decimal(v).quantize(C, rounding=ROUND_HALF_UP)


def paye(taxable, bands):
    """bands: list of (up_to or None, rate, deduct), lowest first."""
    if taxable <= 0:
        return Z
    for up_to, rate, deduct in bands:
        if up_to is None or taxable <= up_to:
            return max(Z, r2(taxable * rate - deduct))
    up_to, rate, deduct = bands[-1]
    return max(Z, r2(taxable * rate - deduct))


def band_list(qs):
    rows = [(b.up_to, b.rate, b.deduct) for b in qs]
    rows.sort(key=lambda x: (x[0] is None, x[0] or 0))
    return rows


def hourly_rate(pay_type, rate, s):
    if pay_type == "monthly":
        return rate / s.normal_hours if s.normal_hours else Z
    if pay_type == "daily":
        return rate / s.day_hours if s.day_hours else Z
    return rate


def work_out(line, s, bands, pays_nssa=True, pays_paye=True):
    """Fill in the worked-out fields of a PayLine (not saved)."""
    rate = line.rate or Z
    if line.pay_type == "monthly":
        per_day = rate / s.normal_days if s.normal_days else Z
        basic = rate - per_day * (line.unpaid_days or Z)
    elif line.pay_type == "daily":
        basic = rate * (line.days or Z)
    else:
        basic = rate * (line.hours or Z)
    line.basic = max(Z, r2(basic))
    hr = hourly_rate(line.pay_type, rate, s)
    line.overtime_pay = r2(hr * ((line.overtime_hours or Z) * s.overtime_rate + (line.holiday_hours or Z) * s.holiday_rate))
    line.gross = r2(line.basic + line.overtime_pay + (line.allowances or Z) + (line.bonus or Z) + (line.other_earnings or Z))
    insurable = min(line.gross, s.nssa_ceiling) if s.nssa_ceiling else line.gross
    line.nssa = r2(insurable * s.nssa_rate) if pays_nssa else Z
    line.nssa_employer = r2(insurable * s.nssa_employer_rate) if pays_nssa else Z
    line.taxable = max(Z, line.gross - line.nssa)
    line.paye = paye(line.taxable, bands) if pays_paye else Z
    line.aids_levy = r2(line.paye * s.aids_levy)
    line.zimdef = r2(line.gross * s.zimdef_rate)
    line.net = line.gross - line.nssa - line.paye - line.aids_levy - (line.advances or Z) - (line.other_deductions or Z)
    return line
