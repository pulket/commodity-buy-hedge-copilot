import commodity_copilot as cc
src = open("app.py").read().replace("value=10000", "value=5000")
exec(compile(src, "app.py", "exec"))
