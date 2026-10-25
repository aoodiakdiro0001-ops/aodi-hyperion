"""Aodı-Hyperion — telemetry funnel. NEVER blocks: daemon threads only."""
import json, threading, urllib.request

import storage


def _targets():
    import config
    if config.TELEGRAM_RELAY:
        yield ("relay", config.TELEGRAM_RELAY, None)
    if config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID:
        yield ("direct", "https://api.telegram.org/bot%s/sendMessage"
               "?chat_id=%s" % (config.TELEGRAM_BOT_TOKEN,
                                config.TELEGRAM_CHAT_ID), None)


def emit(task_id, level, message):
    record = {"task_id": task_id, "level": level, "message": message[:280]}
    storage.log_event(task_id, level, record["message"])
    threading.Thread(target=_fire, args=(record,), daemon=True).start()


def _fire(record):
    for kind, url, _payload in _targets():
        try:
            if kind == "relay":
                data = json.dumps(record).encode("utf-8")
                req = urllib.request.Request(
                    url, data=data, method="POST",
                    headers={"Content-Type": "application/json"})
                urllib.request.urlopen(req, timeout=4).read()
            else:
                text = ("[%s] Hyperion#%s\n%s" %
                        (record["level"].upper(), record["task_id"],
                         record["message"]))
                urllib.request.urlopen(url + "&text=" +
                                       urllib.request.quote(text),
                                       timeout=4).read()
        except Exception:
            pass
