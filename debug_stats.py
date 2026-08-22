import os
import subprocess
import sys
import tempfile

def run_wakayo(args, input_text=None, env=None):
    if env is None:
        env = os.environ.copy()
    wakayo_cmd = Path(sys.executable).parent / "wakayo"
    if not wakayo_cmd.exists():
        wakayo_cmd = "wakayo"
    proc = subprocess.run(
        [str(wakayo_cmd), *args],
        input=input_text,
        text=True,
        capture_output=True,
        env=env,
    )
    return proc.stdout, proc.stderr, proc.returncode

with tempfile.TemporaryDirectory() as tmpdir:
    print(f"Using tmpdir: {tmpdir}")
    env = os.environ.copy()
    env["WAKAYO_DIR"] = tmpdir
    print(f"WAKAYO_DIR set to: {env['WAKAYO_DIR']}")
    
    # Test stats initially
    out, err, code = run_wakayo(["stats"], env=env)
    print(f"Initial stats: code={code}, out={out!r}, err={err!r}")
    
    # Add first entry
    out1, err1, code1 = run_wakayo(["add", "--content", "one", "--source", "hermes"], env=env)
    print(f"Add one: code={code1}, out={out1!r}, err={err1!r}")
    
    # Add second entry
    out2, err2, code2 = run_wakayo(["add", "--content", "two", "--source", "other"], env=env)
    print(f"Add two: code={code2}, out={out2!r}, err={err2!r}")
    
    # Test stats after adds
    out, err, code = run_wakayo(["stats"], env=env)
    print(f"Stats after adds: code={code}, out={out!r}, err={err!r}")