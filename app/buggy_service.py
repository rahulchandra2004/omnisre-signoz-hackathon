import time
import random
import logging
from fastapi import FastAPI, HTTPException
from opentelemetry import trace
from opentelemetry.trace import StatusCode
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Buggy Service (OmniSRE Target)")

FastAPIInstrumentor.instrument_app(app)

chaos_mode_enabled = False

@app.get("/")
def read_root():
    return {"message": "Buggy Service is running. Try /checkout."}

@app.get("/checkout")
def checkout():
    global chaos_mode_enabled
    
    logger.info("Processing checkout request...")
    
    if chaos_mode_enabled:
        time.sleep(random.uniform(1.0, 3.0))
        
        if random.random() < 0.7: 
            logger.error("Checkout failed due to internal error! (Chaos Mode)")
            
            current_span = trace.get_current_span()
            if current_span.is_recording():
                current_span.set_status(StatusCode.ERROR, "Chaos mode active: Simulated 500 Outage")
                current_span.set_attribute("http.status_code", 500)
                current_span.set_attribute("http.response.status_code", 500)
                
            raise HTTPException(status_code=500, detail="Internal Server Error during checkout.")
    
    time.sleep(random.uniform(0.01, 0.05))
    if random.random() < 0.01:
        logger.error("Checkout failed intermittently.")
        
        current_span = trace.get_current_span()
        if current_span.is_recording():
            current_span.set_status(StatusCode.ERROR, "Baseline intermittent 500 error")
            current_span.set_attribute("http.status_code", 500)
            current_span.set_attribute("http.response.status_code", 500)
            
        raise HTTPException(status_code=500, detail="Intermittent failure.")
        
    logger.info("Checkout successful.")
    return {"status": "success", "message": "Checkout completed successfully."}

@app.post("/chaos/inject")
def inject_chaos():
    """
    Hidden endpoint to enable chaos mode.
    This simulates an incident that the OmniSRE agent should investigate.
    """
    global chaos_mode_enabled
    chaos_mode_enabled = True
    logger.warning("CHAOS MODE ENABLED! /checkout will now fail frequently and be slow.")
    return {"status": "chaos_injected", "message": "Chaos mode is now active."}

@app.post("/chaos/revert")
def revert_chaos():
    """
    Hidden endpoint to revert chaos mode manually if needed.
    """
    global chaos_mode_enabled
    chaos_mode_enabled = False
    logger.info("Chaos mode disabled. Service back to normal.")
    return {"status": "chaos_reverted", "message": "Chaos mode is now inactive."}
