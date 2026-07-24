import docker
import logging
import os
import time
import re

logger = logging.getLogger(__name__)

class Healer:
    def __init__(self):
        try:
            self.client = docker.from_env()
            logger.info("Successfully connected to Docker daemon.")
        except Exception as e:
            logger.error(f"Failed to connect to Docker daemon: {e}")
            self.client = None

    def restart_target_service(self, container_name: str = "buggy_service") -> bool:
        """
        Attempts to restart a container by name or partial name matching.
        """
        if not self.client:
            logger.error("Docker client not initialized. Cannot perform self-healing.")
            return False
            
        try:
            logger.info(f"Attempting to find and restart container matching: {container_name}")
            containers = self.client.containers.list()
            
            target_container = None
            for container in containers:
                if container_name in container.name:
                    target_container = container
                    break
                    
            if target_container:
                logger.info(f"Found target container: {target_container.name} (ID: {target_container.id[:12]})")
                target_container.restart()
                logger.info(f"Container {target_container.name} restarted successfully.")
                return True
            else:
                logger.warning(f"Could not find any running container matching name: {container_name}")
                return False
                
        except Exception as e:
            logger.error(f"Error during self-healing (restart): {e}")
            return False

    def tune_configuration(self, target_variable: str = "DB_POOL_SIZE", target_value: str = "50") -> bool:
        """
        Phase 1: Programmatically look for local .env or docker-compose.yml
        and dynamically update its value.
        """
        possible_files = [
            ".env", "../.env", "/app_root/.env",
            "docker-compose.yml", "../docker-compose.yml", "/app_root/docker-compose.yml"
        ]
        target_file = None
        for file in possible_files:
            if os.path.exists(file):
                target_file = file
                break
                
        if not target_file:
            logger.warning("No .env or docker-compose.yml found for configuration tuning.")
            return False
            
        try:
            with open(target_file, "r") as f:
                content = f.read()
                
            pattern = re.compile(rf"^({target_variable}\s*[:=]\s*)(.*)$", re.MULTILINE)
            if pattern.search(content):
                new_content = pattern.sub(rf"\g<1>{target_value}", content)
                logger.info(f"Updated {target_variable} to {target_value} in {target_file}")
            else:
                delimiter = "=" if target_file.endswith(".env") else ": "
                new_content = content + f"\n{target_variable}{delimiter}{target_value}\n"
                logger.info(f"Added {target_variable}={target_value} to {target_file}")
                
            with open(target_file, "w") as f:
                f.write(new_content)
                
            return True
        except Exception as e:
            logger.error(f"Failed to tune configuration: {e}")
            return False

    def verify_health(self, container_name: str = "buggy_service", wait_seconds: int = 5) -> bool:
        """
        Phase 3: Wait a few seconds and verify the target service is healthy/running.
        """
        if not self.client:
            return False
            
        logger.info(f"Waiting {wait_seconds} seconds before verifying health of {container_name}...")
        time.sleep(wait_seconds)
        
        try:
            containers = self.client.containers.list()
            for container in containers:
                if container_name in container.name:
                    if container.status == "running":
                        logger.info(f"Container {container.name} is running and verified healthy.")
                        return True
                    else:
                        logger.warning(f"Container {container.name} is not running (Status: {container.status})")
                        return False
                        
            logger.warning(f"Could not find running container {container_name} during health check.")
            return False
        except Exception as e:
            logger.error(f"Error during health verification: {e}")
            return False
