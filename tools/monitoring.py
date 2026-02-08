import psutil
import platform
import socket
import sys
from datetime import datetime
from fastmcp import Context

async def get_system_resource_usage(ctx: Context) -> dict:
    """Get current CPU and Memory usage statistics."""
    vm = psutil.virtual_memory()
    return {
        "cpu_percent": psutil.cpu_percent(interval=0.1),
        "memory_total_gb": round(vm.total / (1024**3), 2),
        "memory_used_percent": vm.percent,
        "platform": platform.system(),
        "release": platform.release()
    }

async def get_disk_status(ctx: Context) -> list[dict]:
    """Get usage statistics for all mounted disk partitions."""
    disks = []
    for partition in psutil.disk_partitions():
        try:
            usage = psutil.disk_usage(partition.mountpoint)
            disks.append({
                "device": partition.device,
                "mountpoint": partition.mountpoint,
                "total_gb": round(usage.total / (1024**3), 2),
                "free_gb": round(usage.free / (1024**3), 2),
                "percent_used": usage.percent
            })
        except PermissionError:
            continue
    return disks

async def get_system_info(ctx: Context) -> dict:
    """
    Get static system information: OS details, Hardware specs, Network ID, Uptime.
    Use this to understand the environment the server is running on.
    """
    #  Uptime
    boot_time_timestamp = psutil.boot_time()
    boot_time = datetime.fromtimestamp(boot_time_timestamp)
    uptime = datetime.now() - boot_time
    
    # bits of network info
    hostname = socket.gethostname()
    try:
        # not to informative but can be useful for debugging in some cases, e.g. if server is running in a container or VM
        ip_address = socket.gethostbyname(hostname) 
    except Exception:
        ip_address = "Unknown"

    # collecting all info in a structured way for better readability and potential future extensions (e.g. adding GPU info, disk details, etc.)
    info = {
        "os": {
            "system": platform.system(),          # Linux / Windows / Darwin
            "release": platform.release(),        # Kernel version (e.g. 5.10.0)
            "version": platform.version(),        # Full version string
            "architecture": platform.machine(),   # x86_64 / arm64
            "node_name": platform.node()
        },
        "hardware": {
            "cpu_physical_cores": psutil.cpu_count(logical=False), # Physical cores
            "cpu_logical_cores": psutil.cpu_count(logical=True),   # Threads (Hyper-threading)
            "ram_total_gb": round(psutil.virtual_memory().total / (1024**3), 2),
            "hostname": hostname,
            "ip_address": ip_address
        },
        "environment": {
            "python_version": sys.version.split()[0],
            "user": psutil.Process().username() # Who started the server
        },
        "status": {
            "boot_time": boot_time.strftime("%Y-%m-%d %H:%M:%S"),
            "uptime": str(uptime).split('.')[0] # Format: "3 days, 4:20:00"
        }
    }
    
    return info

def register(mcp):
    # function for registering monitoring functions as tools in the MCP server, e.g. router
    mcp.tool(tags=["monitoring"])(get_system_resource_usage)
    mcp.tool(tags=["monitoring"])(get_disk_status)
    mcp.tool(tags=["monitoring"])(get_system_info)