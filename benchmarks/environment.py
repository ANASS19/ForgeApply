"""Local machine metadata and sampled resource use, saved only in private outputs."""
import csv
import io
import json
import platform
import shutil
import subprocess
import threading
import time


def command(args:list[str],timeout=15) -> str|None:
    try:
        result=subprocess.run(args,capture_output=True,text=True,encoding='utf-8',errors='replace',
                              timeout=timeout,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        return result.stdout.strip() if result.returncode==0 else None
    except (OSError,subprocess.TimeoutExpired): return None


def gpu_sample() -> dict:
    raw=command(['nvidia-smi','--query-gpu=memory.used,utilization.gpu,temperature.gpu,power.draw',
                 '--format=csv,noheader,nounits'],timeout=5)
    if not raw: return {}
    try:
        values=next(csv.reader(io.StringIO(raw)))
        return dict(zip(('gpu_used_mib','gpu_utilization_percent','gpu_temperature_c','gpu_power_w'),map(float,values)))
    except (ValueError,StopIteration): return {}


def hardware() -> dict:
    data={'python':platform.python_version(),'os':platform.system(),'os_release':platform.release(),
          'cpu':platform.processor(),'nvidia_smi':command(['nvidia-smi','--query-gpu=name,memory.total,driver_version','--format=csv,noheader'])}
    try:
        import psutil
        memory=psutil.virtual_memory()
        data.update(ram_total_bytes=memory.total,ram_available_bytes=memory.available,
                    cpu_logical_count=psutil.cpu_count(),cpu_physical_count=psutil.cpu_count(logical=False))
    except ImportError: data['resource_monitor_note']='Install benchmarks/requirements.txt for CPU/RAM sampling'
    if platform.system()=='Windows':
        raw=command(['powershell','-NoProfile','-Command','Get-CimInstance Win32_Processor | Select-Object Name,NumberOfCores,NumberOfLogicalProcessors | ConvertTo-Json'])
        if raw:
            try: data['cpu_details']=json.loads(raw)
            except ValueError: pass
    return data


class ResourceMonitor:
    def __init__(self):
        self.samples=[]
        self.stop=threading.Event()
        self.thread=threading.Thread(target=self._run,daemon=True)

    def _run(self):
        try: import psutil
        except ImportError: psutil=None
        if psutil: psutil.cpu_percent()
        while not self.stop.is_set():
            sample={'at':time.perf_counter(),**gpu_sample()}
            if psutil:
                sample.update(system_cpu_percent=psutil.cpu_percent(),system_ram_used_gib=psutil.virtual_memory().used/2**30)
                rss=0
                for process in psutil.process_iter(['name','memory_info']):
                    try:
                        if 'ollama' in (process.info['name'] or '').lower(): rss+=process.info['memory_info'].rss
                    except (psutil.Error,AttributeError): pass
                sample['ollama_rss_gib']=rss/2**30
            self.samples.append(sample)
            self.stop.wait(.5)

    def __enter__(self): self.thread.start(); return self
    def __exit__(self,*args): self.stop.set(); self.thread.join(timeout=10)

    def during(self,start:float,end:float) -> dict:
        samples=[s for s in self.samples if start<=s['at']<=end]
        keys=('gpu_used_mib','gpu_utilization_percent','gpu_temperature_c','gpu_power_w',
              'system_cpu_percent','system_ram_used_gib','ollama_rss_gib')
        return {key+'_peak':max(s[key] for s in samples if key in s) for key in keys if any(key in s for s in samples)}|{'sample_count':len(samples),'sampling_interval_s':.5}
