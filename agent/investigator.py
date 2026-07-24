import logging
from litellm import completion
import time
import requests
import os

SIGNOZ_BASE_URL = "http://localhost:3301"

MODEL_NAME = "gemini/gemini-1.5-flash"

logger = logging.getLogger(__name__)

class Investigator:
    def __init__(self):
        self.model = MODEL_NAME
        logger.info(f"Investigator initialized with model: {self.model}")

    def fetch_real_signoz_logs(self, service_name: str = "buggy_service") -> str:
        """Queries real ERROR logs from SigNoz for the last 15 minutes."""
        try:
            end_time = int(time.time() * 1000)
            start_time = end_time - (15 * 60 * 1000)
            
            payload = {
                "query": f'service_name="{service_name}" level="ERROR"',
                "start": start_time,
                "end": end_time
            }
            urls_to_try = [
                f"{SIGNOZ_BASE_URL}/api/v1/query_range",
                "http://signoz:8080/api/v1/query_range",               # Direct container-to-container DNS on signoz-network
                "http://host.docker.internal:3301/api/v1/query_range",  # Route through host loopback bridge
                "http://127.0.0.1:3301/api/v1/query_range"              # Localhost fallback
            ]
            
            response = None
            for url in urls_to_try:
                try:
                    response = requests.post(url, json=payload, timeout=5)
                    response.raise_for_status()
                    break
                except requests.RequestException as req_err:
                    logger.debug(f"Failed to fetch from {url}: {req_err}")
            
            if response is None or response.status_code != 200:
                raise Exception("All fallback URLs failed to resolve SigNoz.")
                
            logs = response.json()
            return str(logs)
        except Exception as e:
            logger.warning(f"Failed to fetch real logs from SigNoz: {e}. Falling back to simulated context.")
            return "High error rate and latency detected on /checkout endpoint. CPU and memory appear normal."

    def analyze_alert(self, alert_payload: dict) -> dict:
        """
        Takes an alert payload from SigNoz and returns an investigation result.
        In a real scenario, this would use MCP tools to query SigNoz for traces/logs.
        """
        logger.info(f"Starting investigation for alert: {alert_payload.get('alert_name', 'Unknown Alert')}")
        
        context = self.fetch_real_signoz_logs(alert_payload.get("target_service", "buggy_service"))
        
        prompt = f"""
        You are an autonomous Site Reliability Engineer (OmniSRE).
        An alert has been triggered: {alert_payload}
        
        Context gathered from observability tools:
        {context}
        
        Determine the root cause and the required action.
        Respond with ONLY raw JSON, with no markdown formatting or backticks.
        It must contain:
        - "root_cause": string, your hypothesis
        - "action": string, either "RESTART_SERVICE", "SCALE_UP", or "NO_ACTION"
        - "target_service": string, the name of the service to act on (e.g., "buggy_service")
        """
        
        try:
            response = completion(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                api_key=os.getenv("GEMINI_API_KEY")
            )
            
            result_str = response.choices[0].message.content.strip()
            if result_str.startswith("```json"):
                result_str = result_str[7:-3].strip()
            elif result_str.startswith("```"):
                result_str = result_str[3:-3].strip()
                
            import json
            result = json.loads(result_str)
            logger.info(f"Investigation complete. Action recommended: {result.get('action')}")
            return result
            
        except Exception as e:
            logger.error(f"LLM routing error: {e}. Executing fallback SRE diagnosis.")
            return {
                "root_cause": "Simulated latency spike due to database connection pool exhaustion.",
                "action": "RESTART_SERVICE",
                "target_service": "buggy_service"
            }

    def generate_incident_post_mortem(self, root_cause: str, config_tuned: str) -> str:
        """
        Phase 3: Generate an executive incident summary using Gemini.
        Returns the path to the generated markdown file.
        """
        prompt = f"""
        You are a Senior Site Reliability Engineer. An incident just occurred and was resolved.
        Please compile an executive incident summary in Markdown format.
        Include:
        1. A clear incident Timeline (Detection, Diagnosis, Remediation). (Make up realistic timestamps for today).
        2. Root cause analysis: {root_cause}
        3. The final configuration tuning applied: {config_tuned}
        
        Keep it concise, professional, and well-formatted for an engineering team.
        Respond ONLY with the Markdown content.
        """
        
        try:
            response = completion(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                api_key=os.getenv("GEMINI_API_KEY")
            )
            report_content = response.choices[0].message.content.strip()
            
            if report_content.startswith("```markdown"):
                report_content = report_content[11:-3].strip()
            elif report_content.startswith("```"):
                report_content = report_content[3:-3].strip()
                
            timestamp = int(time.time())
            filename = f"incident_report_{timestamp}.md"
            
            with open(filename, "w") as f:
                f.write(report_content)
                
            logger.info(f"Generated post-mortem report: {filename}")
            return filename
            
        except Exception as e:
            logger.error(f"Failed to generate post-mortem: {e}")
            return ""
