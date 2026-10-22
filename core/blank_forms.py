"""Empty forms to print on A4 – leave, applications, contracts, customer orders …

To add a new form later:
  1. make its page in templates/forms/ (copy one that looks like it; it extends forms/_base.html), and
  2. add one line to FORMS below.
It then shows on the Forms page and prints with the Pondo letterhead and the shop details from Settings.
"""
from django.http import Http404
from django.shortcuts import render
from django.contrib.auth.decorators import login_required

from core.access import rights

# key: (name, what it is for, group, template, who may print it)
#   who: None = everybody who can log in, otherwise a right such as "staff_view"
FORMS = {
    "leave": ("Leave application", "Staff fill it in before they go on leave; the manager approves it and works out the balance.",
              "Staff", "forms/leave.html", None),
    "staff_info": ("Staff information", "Personal details, next of kin, dependents and medical information for the staff file.",
                   "Staff", "forms/staff_info.html", "staff_view"),
    "assessment": ("Staff assessment", "Score a staff member 1–5 on performance, conduct and attitude – e.g. at the end of probation.",
                   "Staff", "forms/assessment.html", "staff_view"),
    "contract": ("Fixed term employment contract", "The contract for a new staff member – 3 pages, signed by both sides.",
                 "Staff", "forms/contract.html", "staff_view"),
    "uniform": ("Uniform issue & return", "Two sets per person: every item issued and returned, signed for by the staff member – with the uniform rules. Kept in the staff file.",
                "Staff", "forms/uniform.html", "staff_view"),
    "application": ("Staff application", "For people who apply for a job, with the list of papers they must bring.",
                    "Hiring", "forms/application.html", "staff_view"),
    "offline_cashup": ("Cash-up sheet – Pondo down", "When Pondo can't be used (no internet, power cut): one sheet per till, typed into Pondo later.",
                       "When Pondo is down", "forms/offline_cashup.html", None),
    "offline_log": ("Day log – Pondo down", "Waste, goods received, orders & deposits and deliveries on paper while Pondo can't be used.",
                    "When Pondo is down", "forms/offline_log.html", None),
    "letterhead": ("Letterhead", "Pondo letterhead on A4 with the logo, address, phone numbers, emails and tax number – print blank, or save as PDF.",
                   "Office", "forms/letterhead.html", None),
    "cleaning": ("Shift cleaning checklist", "One sheet per shift per week – every cleaning task ticked and initialled; the incoming supervisor signs that the place was left clean.",
                 "Food safety & cleaning", "forms/cleaning.html", None),
    "deep_clean": ("Saturday deep-cleaning checklist", "Every Saturday 13:00 – 16:00: who did each deep-cleaning task, checked by the supervisor, and the chemicals running low.",
                   "Food safety & cleaning", "forms/deep_clean.html", None),
    "temp_log": ("Fridge & freezer temperature log", "One sheet per month for up to 4 units – temperatures at opening and closing, with action when out of range.",
                 "Food safety & cleaning", "forms/temp_log.html", None),
    "pest": ("Pest control record", "The monthly visits of the contracted pest control company and every pest seen by staff.",
             "Food safety & cleaning", "forms/pest.html", None),
    "complaints": ("Complaints register", "Kept in a file at the counter: every customer complaint and the action taken – checked daily by the Supervisor (A4 landscape).",
                   "Customers", "forms/complaints.html", None),
    "safety": ("Fire extinguisher & first aid kit record", "The yearly service of every fire extinguisher and the monthly first aid kit check – signed off and kept in the health & safety file.",
               "Health & safety", "forms/safety.html", None),
    "order": ("Customer order form", "Cake and special orders – two copies on one A4 page: one for the customer, one for the bakery.",
              "Customers", "forms/order.html", None),
}
GROUPS = ["When Pondo is down", "Office", "Food safety & cleaning", "Health & safety", "Customers", "Staff", "Hiring"]


def allowed(can, who):
    return who is None or bool(getattr(can, who, False))


@login_required
def forms_list(request):
    can = rights(request)
    groups = []
    for g in GROUPS:
        items = [{"key": k, "label": f[0], "about": f[1]} for k, f in FORMS.items() if f[2] == g and allowed(can, f[4])]
        if items:
            groups.append((g, items))
    return render(request, "forms/list.html", {"groups": groups})


@login_required
def form_print(request, key):
    f = FORMS.get(key)
    if not f or not allowed(rights(request), f[4]):
        raise Http404("No such form")
    return render(request, f[3], {"form_key": key, "form_name": f[0], "days": range(1, 32),
                                  "months": ["January", "February", "March", "April", "May", "June", "July", "August",
                                             "September", "October", "November", "December"]})
