import tkinter as tk
from tkinter import scrolledtext, messagebox
import queue
import subprocess
import threading
import os
import requests

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
CONFIG_DIR = os.path.join(PROJECT_ROOT, "config")
SCRIPTS_DIR = os.path.join(PROJECT_ROOT, "scripts")

class OmniSREDemoGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("OmniSRE Hackathon Control Panel")
        self.root.geometry("700x500")
        
        self.traffic_process = None
        self.log_process = None
        self.log_queue = queue.Queue()
        self._poll_log_queue()
        
        
        control_frame = tk.Frame(root, padx=10, pady=10)
        control_frame.pack(side=tk.LEFT, fill=tk.Y)
        
        tk.Label(control_frame, text="1. Infrastructure", font=("Helvetica", 12, "bold")).pack(anchor="w", pady=(0, 5))
        tk.Button(control_frame, text="Start Docker Compose", command=self.start_docker, width=25, bg="#4CAF50", fg="white").pack(pady=2)
        tk.Button(control_frame, text="Stop Docker Compose", command=self.stop_docker, width=25, bg="#f44336", fg="white").pack(pady=2)
        
        tk.Label(control_frame, text="2. Traffic Generation", font=("Helvetica", 12, "bold")).pack(anchor="w", pady=(15, 5))
        tk.Button(control_frame, text="Start Traffic", command=self.start_traffic, width=25, bg="#2196F3", fg="white").pack(pady=2)
        tk.Button(control_frame, text="Stop Traffic", command=self.stop_traffic, width=25, bg="#607D8B", fg="white").pack(pady=2)
        
        tk.Label(control_frame, text="3. Chaos & Recovery", font=("Helvetica", 12, "bold")).pack(anchor="w", pady=(15, 5))
        tk.Button(control_frame, text="Inject Chaos (Break Service)", command=self.inject_chaos, width=25, bg="#FF9800", fg="white").pack(pady=2)
        tk.Button(control_frame, text="Trigger Agent Webhook", command=self.trigger_webhook, width=25, bg="#9C27B0", fg="white").pack(pady=2)
        
        log_frame = tk.Frame(root, padx=10, pady=10)
        log_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        
        log_header = tk.Frame(log_frame)
        log_header.pack(fill=tk.X)
        tk.Label(log_header, text="Agent Logs", font=("Helvetica", 12, "bold")).pack(side=tk.LEFT)
        tk.Button(log_header, text="Refresh Logs", command=self.fetch_logs, height=1).pack(side=tk.RIGHT)
        
        self.log_text = scrolledtext.ScrolledText(log_frame, state='disabled', bg="#1e1e1e", fg="#00ff00", font=("Consolas", 10))
        self.log_text.pack(fill=tk.BOTH, expand=True, pady=5)
        
        self.log_message("Control Panel initialized. Ready.")

    def log_message(self, message):
        self.log_queue.put(message)

    def _poll_log_queue(self):
        try:
            while True:
                message = self.log_queue.get_nowait()
                self.log_text.config(state='normal')
                self.log_text.insert(tk.END, message + "\n")
                self.log_text.see(tk.END)
                self.log_text.config(state='disabled')
        except queue.Empty:
            pass
        self.root.after(100, self._poll_log_queue)

    def start_docker(self):
        self.log_message("Starting Docker Compose (build & detached)...")
        threading.Thread(target=self._run_cmd, args=(["docker-compose", "up", "--build", "-d"], CONFIG_DIR)).start()

    def stop_docker(self):
        self.log_message("Stopping Docker Compose...")
        threading.Thread(target=self._run_cmd, args=(["docker-compose", "down"], CONFIG_DIR)).start()

    def start_traffic(self):
        if self.traffic_process is not None:
            self.log_message("Traffic is already running!")
            return
            
        self.log_message("Starting traffic generation script...")
        script_path = os.path.join(SCRIPTS_DIR, "generate_traffic.ps1")
        self.traffic_process = subprocess.Popen(["powershell.exe", "-ExecutionPolicy", "Bypass", "-File", script_path], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
        
        def read_output():
            for line in iter(self.traffic_process.stdout.readline, ''):
                if line:
                    self.log_message(f"[Traffic] {line.strip()}")
            self.traffic_process = None
            
        threading.Thread(target=read_output, daemon=True).start()

    def stop_traffic(self):
        if self.traffic_process:
            self.log_message("Stopping traffic generation...")
            self.traffic_process.terminate()
            self.traffic_process = None
        else:
            self.log_message("Traffic is not currently running.")

    def inject_chaos(self):
        self.log_message("Injecting chaos via API...")
        try:
            response = requests.post("http://localhost:8000/chaos/inject")
            self.log_message(f"[Chaos Response]: {response.json()}")
        except Exception as e:
            self.log_message(f"Failed to inject chaos: {e}")

    def trigger_webhook(self):
        self.log_message("Triggering OmniSRE Agent webhook...")
        try:
            payload = {"alert_name": "High Checkout Latency", "status": "firing"}
            response = requests.post("http://localhost:8001/webhook/signoz", json=payload)
            self.log_message(f"[Webhook Response]: {response.json()}")
            
            self.root.after(3000, self.fetch_logs)
        except Exception as e:
            self.log_message(f"Failed to trigger webhook: {e}")

    def fetch_logs(self):
        self.log_message("Fetching recent logs from omnisre_agent...")
        try:
            output = subprocess.check_output(["docker", "logs", "--tail", "200", "omnisre_agent"], text=True, stderr=subprocess.STDOUT, encoding="utf-8", errors="replace")
            self.log_message("\n--- AGENT LOGS ---\n" + output + "------------------")
        except subprocess.CalledProcessError as e:
            self.log_message(f"Failed to fetch logs: {e.output}")

    def _run_cmd(self, cmd, cwd):
        try:
            process = subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
            for line in iter(process.stdout.readline, ''):
                if line:
                    self.log_message(f"[Docker] {line.strip()}")
        except Exception as e:
            self.log_message(f"Command error: {e}")

if __name__ == "__main__":
    root = tk.Tk()
    app = OmniSREDemoGUI(root)
    root.protocol("WM_DELETE_WINDOW", lambda: (app.stop_traffic(), root.destroy()))
    root.mainloop()
