import logging
import time
from fastapi import FastAPI, BackgroundTasks, Request
from pydantic import BaseModel
from investigator import Investigator
from healer import Healer
from notifier import Notifier

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="OmniSRE Agent")

investigator = Investigator()
healer = Healer()
notifier = Notifier()

class AlertPayload(BaseModel):
    status: str = "firing"
    alert_name: str = "Unknown Alert"
    description: str = ""

@app.post("/webhook/signoz")
async def signoz_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Receives webhook alerts from SigNoz and triggers the autonomous investigation.
    """
    try:
        payload = await request.json()
        logger.info(f"Received webhook alert payload: {payload}")
    except Exception as e:
        logger.error(f"Failed to parse webhook payload: {e}")
        payload = {"error": "Invalid JSON"}

    background_tasks.add_task(process_alert, payload)
    
    return {"message": "Alert received and investigation started"}

def process_alert(payload: dict):
    outage_start = time.time()
    notifier.notify(f"Alert Received: {payload.get('alert_name', 'Unnamed Alert')}. Starting investigation...")
    
    investigation_result = investigator.analyze_alert(payload)
    
    root_cause = investigation_result.get("root_cause", "Unknown")
    action = investigation_result.get("action", "NO_ACTION")
    target = investigation_result.get("target_service", "buggy_service")
    
    notifier.notify(f"Investigation complete. Root Cause Hypothesis: {root_cause}")
    
    if action == "RESTART_SERVICE":
        config_msg = "Restart container."
        config_tuned = "None"
        if "pool" in root_cause.lower() or "db" in root_cause.lower() or "database" in root_cause.lower():
            tuned = healer.tune_configuration(target_variable="DB_POOL_SIZE", target_value="50")
            if tuned:
                config_msg = "Scale `DB_POOL_SIZE` to 50 and restart container."
                config_tuned = "DB_POOL_SIZE=50"
                
        alert_sent = notifier.send_telegram_alert_with_analytics(root_cause=root_cause, proposed_fix=config_msg)
        if alert_sent:
            approved = notifier.wait_for_approval()
            if approved:
                notifier.notify(f"Approval received. Executing fix on {target}...")
                success = healer.restart_target_service(target)
                if success:
                    outage_end = time.time()
                    actual_mttr = int(outage_end - outage_start)
                    notifier.send_telegram_recovery_alert(actual_mttr)
                    notifier.notify("Service healed. Generating incident post-mortem...")
                    report_path = investigator.generate_incident_post_mortem(root_cause, config_tuned)
                    
                    if report_path:
                        notifier.send_telegram_document(report_path)
            else:
                notifier.notify("Recovery action rejected or timed out by human operator.")
        else:
            notifier.notify("Telegram alert failed. Proceeding with manual remediation mode.")
    else:
        notifier.notify(f"No self-healing action taken. Recommended action was: {action}")
