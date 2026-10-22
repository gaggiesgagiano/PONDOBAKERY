"""Accountant month report: the A4 print page and the Excel workbook (one sheet per section)."""
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone

from core.access import need, rights
from core.models import log_change

from .accountant import accountant_pack
from .views import _month


@need(costs=True)
def accountant_print(request):
    month = _month(request, default_last=True)
    can = rights(request)
    p = accountant_pack(month, with_payroll=bool(can.staff_view))
    if can.money_view:
        from money.calc import pack_extra
        p["money"] = pack_extra(p["start"], p["end"])
    return render(request, "reports/accountant.html", {"p": p, "form_name": "Accountant month report"})


@need(costs=True)
def accountant_excel(request):
    from core.export import DATE, MONEY, NUM, PCT, Col, Sheet, workbook

    month = _month(request, default_last=True)
    can = rights(request)
    p = accountant_pack(month, with_payroll=bool(can.staff_view))
    if can.money_view:
        from money.calc import pack_extra
        p["money"] = pack_extra(p["start"], p["end"])
    m = p["m"]
    sheets = []

    # 1 income statement + VAT
    rows = [["Sales (excl. VAT)", m["sales"], 1 if m["sales"] else None]]
    if m["cos_from"] == "stock":
        rows += [[f"  Opening stock {m['opening'].date:%d %b %Y}", m["opening"].total_value, None],
                 ["  + Purchases (excl. VAT)", m["purchases"], None],
                 [f"  − Closing stock {m['closing'].date:%d %b %Y}", m["closing"].total_value, None]]
    rows += [["Cost of sales" + (" (from recipe costs – no stock takes)" if m["cos_from"] == "recipes" else ""),
              m["cos"], m["pcts"]["cos"]],
             ["GROSS PROFIT", m["gross"], m["gross_pct"]],
             ["Salaries & wages" + (" (payroll incl. employer NSSA & ZIMDEF)" if m["wages_from"] == "payroll"
                                    else " (salary list – no final pay run)"), m["wages"], m["pcts"]["wages"]],
             ["Casual wages & overtime", m["casual"], m["pcts"]["casual"]]]
    if m["running_from"] == "actual":
        rows += [[n, v, None] for n, v in m["by_cat"] if n.lower() != "casual wages & overtime"]
    else:
        rows += [["Running expenses (monthly budget – none typed)", m["running"], m["pcts"]["running"]]]
    rows += [["Depreciation – equipment", m["dep"], m["pcts"]["dep"]],
             ["Total expenses", m["expenses"], m["pcts"]["expenses"]],
             ["NET PROFIT / (LOSS) BEFORE TAX", m["net"], m["pcts"]["net"]],
             [], ["VAT SUMMARY", None, None],
             ["Output VAT in till takings (estimate – confirm with Z-reports)", p["vat"]["out_till"], None],
             ["Output VAT on tax invoices not linked to a delivery", p["vat"]["out_inv_other"], None],
             ["Input VAT – supplier invoices", p["vat"]["in_grv"], None],
             ["Input VAT – expenses", p["vat"]["in_exp"], None],
             ["VAT payable / (refundable)", p["vat"]["net"], None]]
    if p["checks"]:
        rows += [[], ["POINTS TO CHECK", None, None]] + [[c, None, None] for c in p["checks"]]
    sheets.append(Sheet("Income statement", [Col("", 62), Col("US$", 16, MONEY), Col("% of sales", 11, PCT)], rows,
                        f"{p['start']:%d %B %Y} – {p['end']:%d %B %Y} · excl. VAT"))

    # 2 days
    sheets.append(Sheet("Sales per day", [Col("Date", 13, DATE), Col("Sales excl. VAT", 14, MONEY, True),
                                          Col("Till takings incl. VAT", 15, MONEY, True), Col("VAT in takings", 13, MONEY, True),
                                          Col("Over / (short)", 13, MONEY, True), Col("Pay-outs", 12, MONEY, True),
                                          Col("Banked", 12, MONEY, True), Col("ZiG counted", 12, NUM, True),
                                          Col("Tills", 7), Col("Not signed off", 9)],
                        [[r["date"], r["sales"], r["till"], r["vat"], r["variance"], r["payouts"], r["banked"],
                          r["zig"] or None, r["n_tills"] or None, r["unsigned"] or None] for r in p["days"]]))
    sheets.append(Sheet("Sales & takings", [Col("Sales per category / takings per payment type", 40), Col("US$", 16, MONEY)],
                        [["SALES PER CATEGORY (excl. VAT)", None]] + [[n, v] for n, v in p["by_category"]]
                        + [["Total", p["cat_total"]], [], ["TAKINGS PER PAYMENT TYPE (incl. VAT)", None]]
                        + [[n, v] for n, v in p["methods"]] + [["Total", p["methods_total"]]]))
    # 3 expenses
    sheets.append(Sheet("Expenses", [Col("Date", 12, DATE), Col("Category", 20), Col("Paid to", 20), Col("What for", 30),
                                     Col("Receipt no.", 12), Col("Paid from", 18), Col("Excl. VAT", 13, MONEY, True),
                                     Col("VAT", 11, MONEY, True), Col("Total", 13, MONEY, True)],
                        [[r["e"].date, r["e"].category.name, r["e"].payee, r["e"].description, r["e"].receipt_no,
                          r["e"].get_paid_from_display(), r["excl"], r["vat"], r["incl"]] for r in p["exp_rows"]]))
    # 4 purchases
    sheets.append(Sheet("Purchases", [Col("Date", 12, DATE), Col("GRV", 10), Col("Supplier", 24), Col("Invoice no.", 14),
                                      Col("Excl. VAT", 13, MONEY, True), Col("VAT", 11, MONEY, True),
                                      Col("Total", 13, MONEY, True), Col("Invoice says", 13, MONEY),
                                      Col("Difference", 11, MONEY)],
                        [[r["g"].date, r["g"].number, r["g"].supplier.name, r["g"].invoice_no, r["excl"], r["vat"],
                          r["incl"], r["invoice_total"], r["diff"]] for r in p["grv_rows"]]))
    # 5 payroll
    if p["pay"] is not None:
        sheets.append(Sheet("Payroll", [Col("Staff no.", 9), Col("Name", 26), Col("Basic", 11, MONEY, True),
                                        Col("Overtime", 10, MONEY, True), Col("Allowances & other", 11, MONEY, True),
                                        Col("Gross", 11, MONEY, True), Col("NSSA", 10, MONEY, True), Col("PAYE", 10, MONEY, True),
                                        Col("AIDS levy", 10, MONEY, True), Col("Advances & other", 11, MONEY, True),
                                        Col("Net pay", 11, MONEY, True), Col("NSSA employer", 11, MONEY, True),
                                        Col("ZIMDEF", 10, MONEY, True)],
                            [[ln.employee.code, ln.employee.full_name, ln.basic, ln.overtime_pay, ln.extra, ln.gross,
                              ln.nssa, ln.paye, ln.aids_levy, ln.deduct, ln.net, ln.nssa_employer, ln.zimdef]
                             for ln in p["pay"]["lines"]],
                            f"ZIMRA (PAYE + AIDS levy) {p['pay']['zimra']:,.2f} · NSSA total {p['pay']['nssa_total']:,.2f} · "
                            f"ZIMDEF {p['pay']['t']['zimdef']:,.2f} · payroll cost {p['pay']['t']['cost']:,.2f}"))
    # 6 invoices & debtors
    sheets.append(Sheet("Tax invoices", [Col("Number", 11), Col("Date", 12, DATE), Col("Customer", 28), Col("Type", 16),
                                         Col("Excl. VAT", 13, MONEY, True), Col("VAT", 11, MONEY, True),
                                         Col("Total", 13, MONEY, True), Col("Status", 10), Col("Paid on", 12, DATE)],
                        [[r["d"].number, r["d"].date, r["d"].company or r["d"].name,
                          "Delivery (on till)" if r["delivery"] else "Invoice", r["d"].subtotal, r["d"].vat, r["d"].total,
                          r["d"].get_status_display(), r["d"].paid_on] for r in p["inv_rows"]]))
    sheets.append(Sheet("Debtors", [Col("Number", 11), Col("Date", 12, DATE), Col("Customer", 28), Col("Days", 7),
                                    Col("Amount incl. VAT", 15, MONEY, True)],
                        [[r["d"].number, r["d"].date, r["d"].company or r["d"].name, r["days"], r["d"].total]
                         for r in p["deb_rows"]], f"unpaid at {p['end']:%d %B %Y}"))
    # 7 equipment
    sheets.append(Sheet("Equipment", [Col("Category", 26), Col("Cost", 14, MONEY, True),
                                      Col("Depreciation this month", 14, MONEY, True), Col("Book value", 14, MONEY, True)],
                        [list(r) for r in p["eq_rows"]]))

    # 8 money: cash book, suppliers owed, balance sheet (only with the Money right, once the accounts are set up)
    mx = p.get("money")
    if mx:
        sheets.append(Sheet("Cash book summary", [Col("Account", 24), Col("Opening", 14, MONEY), Col("In", 14, MONEY, True),
                                                  Col("Out", 14, MONEY, True), Col("Closing", 14, MONEY),
                                                  Col("Statement / count", 16, MONEY), Col("Checked on", 12, DATE), Col("Difference", 12, MONEY)],
                            [[b["a"].name, b["cb"]["opening"], b["cb"]["in"], b["cb"]["out"], b["cb"]["closing"],
                              b["check"].statement_balance if b["check"] else None, b["check"].date if b["check"] else None,
                              b["check"].difference if b["check"] else None] for b in mx["books"]]))
        sheets.append(Sheet("Cash book", [Col("Account", 16), Col("Date", 12, DATE), Col("What", 46), Col("Ref", 14),
                                          Col("In", 13, MONEY, True), Col("Out", 13, MONEY, True), Col("Balance", 14, MONEY)],
                            [[b["a"].name, r["date"], r["what"], r["ref"], r["amount"] if r["amount"] > 0 else None,
                              -r["amount"] if r["amount"] < 0 else None, r["balance"]] for b in mx["books"] for r in b["cb"]["rows"]]))
        sheets.append(Sheet("Suppliers owed", [Col("Supplier", 24), Col("Received", 12, DATE), Col("GRV", 10), Col("Invoice no.", 14),
                                               Col("Amount", 13, MONEY), Col("Paid", 13, MONEY), Col("Owe", 13, MONEY, True),
                                               Col("Due", 12, DATE), Col("Days late", 9)],
                            [[r["supplier"].name, r["grv"].date, r["grv"].number, r["grv"].invoice_no, r["amount"], r["paid"],
                              r["owing"], r["due"], r["late"] or None] for r in mx["cred"]], f"unpaid at {p['end']:%d %B %Y}"))
        bs = mx["bs"]
        if bs:
            rows = [["WHAT THE BUSINESS OWNS", None]] + [[f"  {a.name}", b] for a, b in bs["money"]] + [[n, v] for n, v in bs["assets"]]
            rows += [["Total owned", bs["total_assets"]], [], ["WHAT THE BUSINESS OWES", None]] + [[n, v] for n, v in bs["liabilities"]]
            rows += [["Total owed", bs["total_liab"]], [], ["NET WORTH (owned − owed)", bs["net"]],
                     ["Already there when the books started (owner's / boss's investment)", bs["opening"]],
                     ["Capital put in by the owner / boss since then", bs["capital"]], ["Drawings", bs["drawings"]],
                     ["Profit kept in the business (balancing figure)", bs["kept"]]]
            sheets.append(Sheet("Balance sheet", [Col("", 56), Col("US$", 16, MONEY)], rows,
                                f"management balance sheet at {p['end']:%d %B %Y} · books start {bs['start']:%d %B %Y}"))

    data = workbook(f"Accountant report {p['start']:%B %Y}", sheets, request.user.get_full_name() or request.user.username)
    log_change(request.user, "Reports", "Accountant report", "downloaded", f"{p['start']:%B %Y}")
    resp = HttpResponse(data, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    resp["Content-Disposition"] = (f'attachment; filename="Pondo accountant report {p["start"]:%Y-%m} '
                                   f'{timezone.localdate():%Y-%m-%d}.xlsx"')
    return resp
