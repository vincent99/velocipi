"""
Boot-time initialisation — runs before main.py.
Starts WebREPL so it is available over WiFi once the network is up.
"""

try:
    with open('/webrepl_cfg.py', 'w') as f:
        f.write("PASS = 'monkey'\n")
    import webrepl
    webrepl.start()
except Exception as e:
    print('webrepl start failed:', repr(e))
