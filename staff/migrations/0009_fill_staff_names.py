"""Names, birthdays and jobs from the staff list of 10 Oct 2026. The places nobody is employed for yet
(counter hands, cashiers, security) lose their made-up names but keep their staff number, job and pay."""
import datetime

from django.db import migrations

D = datetime.date
PEOPLE = {
    # staff no.: (known as, first name, second name, surname, born, job)
    "26003": ("Sidney", "Sydney", "Talent", "Ndlovu", D(1987, 2, 24), "Confectioner"),
    "26004": ("", "Chris", "", "Nyarirangwe", D(1982, 7, 1), "Confectioner"),
    "26005": ("Mike", "Michael", "Larry", "Nywasha", D(1993, 12, 7), "Confectioner"),
    "26006": ("", "Herbert", "Kudakwashe", "Mvundura", D(1989, 2, 22), "Pie Chef"),
    "26007": ("", "Natalie", "", "Chagonda", D(2005, 2, 24), "Pie Chef"),
    "26008": ("Jay", "Jambo", "", "Kamvura", D(2000, 5, 23), "Griller"),
    "26009": ("Kofi", "Stalline", "Edward", "Kofi", D(2001, 5, 21), "Chef"),
    "26010": ("Welly", "Wellington", "", "Manase", D(1991, 10, 8), "Confectioner"),
    "26011": ("Talent", "Tatenda", "Talent", "Murwira", D(2001, 6, 5), "Confectioner"),
    "26012": ("", "Oscar", "", "Denhere", D(1989, 10, 17), "Confectioner"),
    "26013": ("Henry", "Makhosi", "Henry", "Ndlovu", D(1987, 12, 11), "Confectioner"),
    "26014": ("Clive", "Clever", "Clive", "Nyatando", D(1998, 1, 15), "Confectioner"),
    "26015": ("", "Nyasha", "", "Mukanya", D(2002, 12, 13), "Packer"),
    "26023": ("", "Allan", "", "Mugari", D(2000, 6, 24), "Assistant Chef"),
}
OPEN = ["26016", "26017", "26018", "26019", "26020", "26021", "26022"]
PLACEHOLDER = ("Counter hand ", "Cashier ", "Security guard ")


def fill(apps, schema_editor):
    Employee = apps.get_model("staff", "Employee")
    for code, (known, first, second, surname, born, job) in PEOPLE.items():
        e = Employee.objects.filter(code=code).first()
        if not e:
            continue
        e.known_as, e.first_name, e.middle_name, e.last_name = known, first, second, surname
        e.date_of_birth, e.job_title = born, job
        e.save()
    for e in Employee.objects.filter(code__in=OPEN):
        if e.first_name.startswith(PLACEHOLDER):  # only the made-up names, never a real one typed since
            e.first_name = e.last_name = e.known_as = e.middle_name = ""
            e.notes = "Open place – type the name when somebody is employed."
            e.save()


class Migration(migrations.Migration):
    dependencies = [("staff", "0008_known_as_second_name")]
    operations = [migrations.RunPython(fill, migrations.RunPython.noop)]
