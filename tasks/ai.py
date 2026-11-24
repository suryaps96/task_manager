
from datetime import date, timedelta


def next_first_month(today):
    if today.month == 12:
        return date(today.year + 1, 1, 1)

    return date(today.year, today.month + 1, 1)


def parse_task_text(text, today):

    normalized = text.lower()

    due_date = None
    recurrence = None

    if "tomorrow" in normalized:
        due_date = today + timedelta(days=1)

    elif "next week" in normalized:
        due_date = today + timedelta(weeks=1)

    if "every month" in normalized:
        due_date = next_first_month(today)
        recurrence = "monthly"

    elif "1st" in normalized:
        due_date = next_first_month(today)

    # Basic title cleanup
    title = normalized.replace("remind me to", "")
    title = title.replace("on the 1st of every month", "")
    title = title.replace("on the 1st", "")
    title = title.replace("every month", "")
    title = title.replace("tomorrow", "")
    title = title.replace("next week", "")

    title = " ".join(title.split()).capitalize()

    if not title:
        title = text.strip().capitalize()

    return {
            "title": title,
            "description": text,
            "due_date": due_date,
            "recurrence": recurrence
        }



def break_down_task(task):
    description = task.description.strip()

    # Split the description using "and" or commas
    parts = description.replace(" and ", ",").split(",")

    subtasks = []

    for part in parts:
        item = part.strip().strip(".")

        if item:
            subtasks.append({
                "title": item.capitalize(),
                "description": f"Complete this step: {item}",
                "priority": task.priority,
                "due_date": task.due_date
            })

    return subtasks

