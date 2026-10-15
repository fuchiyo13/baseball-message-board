"""日本の土日・祝日判定。"""

from datetime import date, timedelta

import jpholiday


def is_weekend_or_holiday(day):
    return day.weekday() >= 5 or jpholiday.is_holiday(day)


def holiday_dates_between(start, end):
    """start〜end（両端含む）の祝日だけを返す。"""
    days = []
    cursor = start
    while cursor <= end:
        if jpholiday.is_holiday(cursor):
            days.append(cursor)
        cursor += timedelta(days=1)
    return days
