"""Build the SQLite database the app queries, from the raw Fitbit CSVs.

Run from the project folder:   python src/build_db.py
Safe to re-run: it deletes and rebuilds the database file every time.
The raw CSVs in data/raw/ are only read, never changed.
"""
import sqlite3
from pathlib import Path

import pandas as pd

PROJECT = Path(__file__).resolve().parent.parent
RAW = PROJECT / "data" / "raw"
DB_PATH = PROJECT / "app" / "app_data" / "fitbit.db"   # not called data/, so .gitignore doesn't hide it
FMT = "%m/%d/%Y %I:%M:%S %p"

# The schema the model will see. Units are in the column names so answers can't mix them up.
SCHEMA_SQL = """
CREATE TABLE daily_activity (
    user_id                       INTEGER NOT NULL,
    activity_date                 TEXT    NOT NULL,  -- YYYY-MM-DD
    total_steps                   INTEGER,
    total_distance_km             REAL,
    tracker_distance_km           REAL,
    logged_activities_distance_km REAL,
    very_active_distance_km       REAL,
    moderately_active_distance_km REAL,
    light_active_distance_km      REAL,
    sedentary_active_distance_km  REAL,
    very_active_minutes           INTEGER,
    fairly_active_minutes         INTEGER,
    lightly_active_minutes        INTEGER,
    sedentary_minutes             INTEGER,
    calories                      INTEGER,
    PRIMARY KEY (user_id, activity_date)
);
CREATE TABLE sleep_day (
    user_id              INTEGER NOT NULL,
    sleep_date           TEXT    NOT NULL,  -- YYYY-MM-DD, the day the person woke up
    total_sleep_records  INTEGER,
    total_minutes_asleep INTEGER,
    total_time_in_bed    INTEGER,
    PRIMARY KEY (user_id, sleep_date)
);
CREATE TABLE weight_log (
    log_id           INTEGER,
    user_id          INTEGER NOT NULL,
    log_time         TEXT    NOT NULL,  -- YYYY-MM-DD HH:MM:SS
    weight_kg        REAL,
    weight_pounds    REAL,
    fat_percent      REAL,
    bmi              REAL,
    is_manual_report INTEGER            -- 1 = typed in by hand, 0 = smart scale
);
CREATE TABLE heart_rate_hourly (
    user_id    INTEGER NOT NULL,
    hour_start TEXT    NOT NULL,        -- YYYY-MM-DD HH:00:00
    avg_bpm    REAL,
    min_bpm    INTEGER,
    max_bpm    INTEGER,
    n_readings INTEGER,
    PRIMARY KEY (user_id, hour_start)
);
CREATE TABLE hourly_steps (
    user_id       INTEGER NOT NULL,
    activity_hour TEXT    NOT NULL,     -- YYYY-MM-DD HH:00:00
    step_total    INTEGER,
    PRIMARY KEY (user_id, activity_hour)
);
"""

# Facts already known from notebooks 00 and 01. If any differs, something went wrong.
EXPECTED_ROWS = {"daily_activity": 940, "sleep_day": 410, "weight_log": 67,
                 "heart_rate_hourly": 6013, "hourly_steps": 22099}
EXPECTED_HEART_READINGS = 2_483_658


def load(name):
    matches = [f for f in RAW.rglob("*.csv") if f.name == name]
    assert len(matches) == 1, f"Expected 1 file called {name}, found {len(matches)}"
    return pd.read_csv(matches[0])


def as_date(series, fmt):
    return pd.to_datetime(series, format=fmt).dt.strftime("%Y-%m-%d")


def as_datetime(series):
    return pd.to_datetime(series, format=FMT).dt.strftime("%Y-%m-%d %H:%M:%S")


def build_tables():
    d = load("dailyActivity_merged.csv")
    daily = pd.DataFrame({
        "user_id": d["Id"],
        "activity_date": as_date(d["ActivityDate"], "%m/%d/%Y"),
        "total_steps": d["TotalSteps"],
        "total_distance_km": d["TotalDistance"],
        "tracker_distance_km": d["TrackerDistance"],
        "logged_activities_distance_km": d["LoggedActivitiesDistance"],
        "very_active_distance_km": d["VeryActiveDistance"],
        "moderately_active_distance_km": d["ModeratelyActiveDistance"],
        "light_active_distance_km": d["LightActiveDistance"],
        "sedentary_active_distance_km": d["SedentaryActiveDistance"],
        "very_active_minutes": d["VeryActiveMinutes"],
        "fairly_active_minutes": d["FairlyActiveMinutes"],
        "lightly_active_minutes": d["LightlyActiveMinutes"],
        "sedentary_minutes": d["SedentaryMinutes"],
        "calories": d["Calories"],
    })

    s = load("sleepDay_merged.csv").drop_duplicates()   # Stage 1 decision: 413 -> 410
    sleep = pd.DataFrame({
        "user_id": s["Id"],
        "sleep_date": as_date(s["SleepDay"], FMT),
        "total_sleep_records": s["TotalSleepRecords"],
        "total_minutes_asleep": s["TotalMinutesAsleep"],
        "total_time_in_bed": s["TotalTimeInBed"],
    })

    w = load("weightLogInfo_merged.csv")
    weight = pd.DataFrame({
        "log_id": w["LogId"],
        "user_id": w["Id"],
        "log_time": as_datetime(w["Date"]),
        "weight_kg": w["WeightKg"].round(2),
        "weight_pounds": w["WeightPounds"].round(2),
        "fat_percent": w["Fat"],
        "bmi": w["BMI"].round(2),
        "is_manual_report": w["IsManualReport"].astype(int),
    })

    h = load("heartrate_seconds_merged.csv")
    h["hour_start"] = pd.to_datetime(h["Time"], format=FMT).dt.floor("h").dt.strftime("%Y-%m-%d %H:%M:%S")
    heart = (h.groupby(["Id", "hour_start"])["Value"]
               .agg(avg_bpm="mean", min_bpm="min", max_bpm="max", n_readings="count")
               .reset_index().rename(columns={"Id": "user_id"}))
    heart["avg_bpm"] = heart["avg_bpm"].round(1)

    hs = load("hourlySteps_merged.csv")
    hourly = pd.DataFrame({
        "user_id": hs["Id"],
        "activity_hour": as_datetime(hs["ActivityHour"]),
        "step_total": hs["StepTotal"],
    })

    return {"daily_activity": daily, "sleep_day": sleep, "weight_log": weight,
            "heart_rate_hourly": heart, "hourly_steps": hourly}


def write_db(tables):
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if DB_PATH.exists():
        DB_PATH.unlink()                      # rebuild from scratch every time
    con = sqlite3.connect(DB_PATH)
    con.executescript(SCHEMA_SQL)
    for name, df in tables.items():
        df.to_sql(name, con, if_exists="append", index=False)   # fails loudly on duplicate keys
    con.commit()
    con.execute("VACUUM")
    con.close()


def check_db():
    con = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)     # read-only, like the app will be
    ok = True
    for name, expected in EXPECTED_ROWS.items():
        n = con.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
        users = con.execute(f"SELECT COUNT(DISTINCT user_id) FROM {name}").fetchone()[0]
        flag = "PASS" if n == expected else "FAIL"
        ok &= n == expected
        print(f"{flag}  {name:18s} rows={n:>6,} (expected {expected:>6,})  users={users}")
    readings = con.execute("SELECT SUM(n_readings) FROM heart_rate_hourly").fetchone()[0]
    flag = "PASS" if readings == EXPECTED_HEART_READINGS else "FAIL"
    ok &= readings == EXPECTED_HEART_READINGS
    print(f"{flag}  heart readings summarised: {readings:,} (expected {EXPECTED_HEART_READINGS:,})")
    first, last = con.execute("SELECT MIN(activity_date), MAX(activity_date) FROM daily_activity").fetchone()
    print(f"      daily_activity dates: {first} to {last}")
    con.close()
    print(f"\nDatabase: {DB_PATH.relative_to(PROJECT)}  ({DB_PATH.stat().st_size / 1_000_000:.2f} MB)")
    print("ALL CHECKS PASSED" if ok else "SOME CHECKS FAILED - stop and investigate before going on")


if __name__ == "__main__":
    write_db(build_tables())
    check_db()
