import json
import time
import random
import ssl
import logging
from datetime import datetime, timezone

import paho.mqtt.client as mqtt

from config.credentials import (
    AWS_IOT_ENDPOINT,
    AWS_IOT_PORT,
    AWS_IOT_CLIENT_ID,
    AWS_IOT_TOPIC,
    CA_CERT_PATH,
    CLIENT_CERT_PATH,
    PRIVATE_KEY_PATH,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

RECONNECT_DELAY_SECS = 5


# ---------------------------------------------------------------------------
# MQTT callbacks
# ---------------------------------------------------------------------------

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        log.info("Connected to AWS IoT Core.")
    else:
        log.error("Connection failed with code %d.", rc)


def on_disconnect(client, userdata, rc):
    if rc != 0:
        log.warning("Unexpected disconnection (rc=%d). Will retry.", rc)


def on_publish(client, userdata, mid):
    log.debug("Message published (mid=%d).", mid)


# ---------------------------------------------------------------------------
# Telemetry helpers
# ---------------------------------------------------------------------------

def generate_telemetry(vehicle_id: str) -> dict:
    """Return a single telemetry snapshot for the given vehicle."""
    return {
        "vehicle_id": vehicle_id,
        "speed": round(random.uniform(0, 120), 2),          # km/h
        "battery_level": round(random.uniform(10, 100), 2), # percent
        "distance_to_obstacle": round(random.uniform(0, 50), 2),  # metres
        "lat": round(random.uniform(36.0, 42.0), 6),
        "long": round(random.uniform(26.0, 45.0), 6),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def build_client() -> mqtt.Client:
    """Create and configure an MQTT client with TLS for AWS IoT Core."""
    client = mqtt.Client(client_id=AWS_IOT_CLIENT_ID)
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_publish = on_publish

    client.tls_set(
        ca_certs=CA_CERT_PATH,
        certfile=CLIENT_CERT_PATH,
        keyfile=PRIVATE_KEY_PATH,
        tls_version=ssl.PROTOCOL_TLS_CLIENT,
    )
    return client


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def run(vehicle_id: str = "VH-001", interval: float = 1.0):
    client = build_client()

    while True:
        try:
            log.info("Connecting to %s:%d …", AWS_IOT_ENDPOINT, AWS_IOT_PORT)
            client.connect(AWS_IOT_ENDPOINT, AWS_IOT_PORT, keepalive=60)
            client.loop_start()

            while True:
                payload = generate_telemetry(vehicle_id)
                result = client.publish(AWS_IOT_TOPIC, json.dumps(payload), qos=1)
                if result.rc == mqtt.MQTT_ERR_SUCCESS:
                    log.info("Published: %s", payload)
                else:
                    log.warning("Publish failed (rc=%d).", result.rc)
                time.sleep(interval)

        except (OSError, ConnectionRefusedError) as exc:
            log.error("Connection error: %s. Retrying in %ds …", exc, RECONNECT_DELAY_SECS)
            time.sleep(RECONNECT_DELAY_SECS)
        except KeyboardInterrupt:
            log.info("Shutting down producer.")
            client.loop_stop()
            client.disconnect()
            break


if __name__ == "__main__":
    run()
