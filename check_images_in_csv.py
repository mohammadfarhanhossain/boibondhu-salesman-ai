import csv

with open(r"c:\Automation_project\rokomar_scrapper\data\processed\master.csv", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    for i, row in enumerate(reader):
        print("Rokomari row:", row)
        if i >= 2:
            break

with open(r"c:\Automation_project\wafilife scrapper\master.csv", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    for i, row in enumerate(reader):
        print("Wafilife row:", row)
        if i >= 2:
            break
