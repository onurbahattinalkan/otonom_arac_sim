"""
AWS Lambda function — triggered by Kinesis Data Streams.

Each Kinesis record carries a base64-encoded JSON telemetry payload produced
by producer.py.  The function:
  1. Decodes and parses every record in the batch.
  2. Prints a "High Speed Alert" when speed > 80 km/h.
  3. Writes every record to InfluxDB.
"""

import base64
import json
import logging
import os

from influxdb_client import InfluxDBClient, Point, WriteOptions
from influxdb_client.client.write_api import SYNCHRONOUS

log = logging.getLogger(__name__)
log.setLevel(logging.INFO)

# ---------------------------------------------------------------------------
# InfluxDB configuration — values come from Lambda environment variables,
# which are populated from config/credentials.py during deployment.
# ---------------------------------------------------------------------------
INFLUXDB_URL    = os.environ.get("INFLUXDB_URL", "")
INFLUXDB_TOKEN  = os.environ.get("INFLUXDB_TOKEN", "")
INFLUXDB_ORG    = os.environ.get("INFLUXDB_ORG", "")
INFLUXDB_BUCKET = os.environ.get("INFLUXDB_BUCKET", "")

HIGH_SPEED_THRESHOLD = 80  # km/h


# ---------------------------------------------------------------------------
# InfluxDB helpers
# ---------------------------------------------------------------------------

def _get_write_api():
    """Return a synchronous InfluxDB write API instance."""
    client = InfluxDBClient(
        url=INFLUXDB_URL,
        token=INFLUXDB_TOKEN,
        org=INFLUXDB_ORG,
    )
    return client.write_api(write_options=SYNCHRONOUS)


def write_to_influxdb(write_api, record: dict) -> None:
    """Convert a telemetry dict to an InfluxDB Point and write it."""
    point = (
        Point("vehicle_telemetry")
        .tag("vehicle_id", record.get("vehicle_id", "unknown"))
        .field("speed", float(record.get("speed", 0)))
        .field("battery_level", float(record.get("battery_level", 0)))
        .field("distance_to_obstacle", float(record.get("distance_to_obstacle", 0)))
        .field("lat", float(record.get("lat", 0)))
        .field("long", float(record.get("long", 0)))
    )
    write_api.write(bucket=INFLUXDB_BUCKET, org=INFLUXDB_ORG, record=point)
    log.info("Written to InfluxDB: vehicle_id=%s", record.get("vehicle_id"))


# ---------------------------------------------------------------------------
# Kinesis record processing
# ---------------------------------------------------------------------------

def decode_record(kinesis_record: dict) -> dict:
    """Base64-decode and JSON-parse a single Kinesis record."""
    raw = base64.b64decode(kinesis_record["kinesis"]["data"]).decode("utf-8")
    return json.loads(raw)


def process_record(write_api, record: dict) -> None:
    """Apply business logic and persist a single telemetry record."""
    speed = record.get("speed", 0)
    vehicle_id = record.get("vehicle_id", "unknown")

    if speed > HIGH_SPEED_THRESHOLD:
        log.warning(
            "High Speed Alert — vehicle_id=%s speed=%.2f km/h", vehicle_id, speed
        )

    write_to_influxdb(write_api, record)


# ---------------------------------------------------------------------------
# Lambda entry point
# ---------------------------------------------------------------------------

def lambda_handler(event: dict, context) -> dict:
    """Main handler called by AWS Lambda for each Kinesis batch."""
    kinesis_records = event.get("Records", [])
    log.info("Received %d Kinesis record(s).", len(kinesis_records))

    if not kinesis_records:
        return {"statusCode": 200, "body": "No records to process."}

    write_api = _get_write_api()
    errors = []

    for kinesis_record in kinesis_records:
        try:
            record = decode_record(kinesis_record)
            process_record(write_api, record)
        except (KeyError, ValueError, json.JSONDecodeError) as exc:
            log.error("Failed to process record: %s — %s", kinesis_record, exc)
            errors.append(str(exc))

    if errors:
        return {"statusCode": 207, "body": f"Processed with {len(errors)} error(s)."}

    return {"statusCode": 200, "body": "All records processed successfully."}
